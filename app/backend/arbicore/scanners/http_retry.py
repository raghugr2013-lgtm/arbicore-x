"""Universal HTTP retry + TTL cache substrate for ArbiCore X scanners.

Promoted from the D-4 hotfix wave (formerly inline inside
``arbicore/scanners/launch_arbitrage/helius_venue_provider.py``). Zero
behaviour change — this is a pure refactor / DRY consolidation.

Consumers:
  - D-4 ``HeliusLaunchVenueProvider`` (after hotfix-2 — this wave)
  - D-5 ``LiFiTransferProvider`` (pending D-5.3 implementation)
  - Any future scanner-side HTTP read needing retry / cache discipline

INV-1: This module never constructs ``CanonicalOpportunity``.
INV-2: This module never imports ``EmissionBus``.
INV-3: This module is provenance-agnostic (callers set their own
       ``source_id`` on the legs they assemble).

The module is purely read-only at the HTTP layer. No signing. No state
mutation outside the per-instance ``TTLCache``.
"""
from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, Optional, Tuple

import httpx

# ── Defaults (unchanged values from the D-4 hotfix wave) ──
DEFAULT_TIMEOUT_S = 10.0
DEFAULT_RETRY_MAX_ATTEMPTS = 3
DEFAULT_RETRY_INITIAL_BACKOFF_S = 0.2
DEFAULT_RETRY_MAX_BACKOFF_S = 2.0
DEFAULT_TTL_CACHE_S = 60.0
DEFAULT_JITTER_FRACTION = 0.25       # ±25% symmetric jitter

RETRYABLE_STATUS_CODES: FrozenSet[int] = frozenset(
    {429, 500, 502, 503, 504})


# ============================================================================
# RetryConfig — operator-tunable parameter bundle
# ============================================================================

@dataclass(frozen=True)
class RetryConfig:
    """Bundles all retry/backoff parameters into a single immutable value.

    All fields default to the values shipped in the D-4 hotfix wave.
    Construct via ``RetryConfig(...)`` or use ``RetryConfig.from_kwargs(...)``
    for ergonomic conversion from provider constructor kwargs.
    """
    max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    initial_backoff_s: float = DEFAULT_RETRY_INITIAL_BACKOFF_S
    max_backoff_s: float = DEFAULT_RETRY_MAX_BACKOFF_S
    retryable_status_codes: FrozenSet[int] = RETRYABLE_STATUS_CODES

    @classmethod
    def from_kwargs(
        cls,
        *,
        retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS,
        retry_initial_backoff_s: float = DEFAULT_RETRY_INITIAL_BACKOFF_S,
        retry_max_backoff_s: float = DEFAULT_RETRY_MAX_BACKOFF_S,
    ) -> "RetryConfig":
        return cls(
            max_attempts=max(1, int(retry_max_attempts)),
            initial_backoff_s=float(retry_initial_backoff_s),
            max_backoff_s=float(retry_max_backoff_s),
        )


# ============================================================================
# sleep_with_jitter — bounded ±25% jittered sleep
# ============================================================================

async def sleep_with_jitter(base_s: float,
                              jitter_fraction: float =
                              DEFAULT_JITTER_FRACTION) -> None:
    """Sleeps approximately ``base_s`` seconds with symmetric jitter.

    Jitter avoids thundering-herd against rate-limited upstream APIs when
    multiple provider instances retry simultaneously. Bounded at 0 to
    prevent negative sleeps under pathological random values.
    """
    jitter = random.uniform(-jitter_fraction, jitter_fraction) * base_s
    await asyncio.sleep(max(0.0, base_s + jitter))


# ============================================================================
# post_json_with_retry — POST JSON with jittered exponential backoff
# ============================================================================

async def post_json_with_retry(
    client: httpx.AsyncClient,
    url: str,
    body: Dict[str, Any],
    *,
    config: Optional[RetryConfig] = None,
) -> Optional[Dict[str, Any]]:
    """POST a JSON body with jittered exponential backoff over 429 / 5xx.

    Returns the parsed JSON response on 200, or ``None`` on any of:
      - retry budget exhausted (all ``config.max_attempts`` attempts failed)
      - non-retryable non-200 status code
      - JSON parse error
      - non-dict / non-list response body

    Behaviourally identical to the inline retry loop that shipped in the
    D-4 hotfix wave inside ``HeliusLaunchVenueProvider._rpc_call``.
    """
    cfg = config or RetryConfig()
    backoff = cfg.initial_backoff_s
    for attempt in range(1, cfg.max_attempts + 1):
        try:
            resp = await client.post(url, json=body)
        except httpx.HTTPError:
            if attempt == cfg.max_attempts:
                return None
            await sleep_with_jitter(backoff)
            backoff = min(backoff * 2, cfg.max_backoff_s)
            continue
        if resp.status_code in cfg.retryable_status_codes:
            if attempt == cfg.max_attempts:
                return None
            await sleep_with_jitter(backoff)
            backoff = min(backoff * 2, cfg.max_backoff_s)
            continue
        if resp.status_code != 200:
            return None
        try:
            payload = resp.json()
        except ValueError:
            return None
        if not isinstance(payload, (dict, list)):
            return None
        return payload
    return None


# ============================================================================
# get_json_with_retry — GET JSON with jittered exponential backoff
# ============================================================================

async def get_json_with_retry(
    client: httpx.AsyncClient,
    url: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    config: Optional[RetryConfig] = None,
) -> Optional[Dict[str, Any]]:
    """GET a URL with optional query params, jittered exponential backoff
    over 429 / 5xx, identical retry semantics to ``post_json_with_retry``.

    Subset C — added when LI.FI deprecated ``POST /v1/quote`` (now GET-only).
    The retry / backoff / non-retryable / parse-error / response-shape
    contract is byte-identical to the POST helper above, so any caller can
    swap POST for GET without retry-behaviour drift.
    """
    cfg = config or RetryConfig()
    backoff = cfg.initial_backoff_s
    for attempt in range(1, cfg.max_attempts + 1):
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError:
            if attempt == cfg.max_attempts:
                return None
            await sleep_with_jitter(backoff)
            backoff = min(backoff * 2, cfg.max_backoff_s)
            continue
        if resp.status_code in cfg.retryable_status_codes:
            if attempt == cfg.max_attempts:
                return None
            await sleep_with_jitter(backoff)
            backoff = min(backoff * 2, cfg.max_backoff_s)
            continue
        if resp.status_code != 200:
            return None
        try:
            payload = resp.json()
        except ValueError:
            return None
        if not isinstance(payload, (dict, list)):
            return None
        return payload
    return None


# ============================================================================
# TTLCache — per-key TTL cache
# ============================================================================

class TTLCache:
    """Simple per-key TTL cache.

    Used by venue / transfer / bridge providers to deduplicate same-key
    reads across the scanner's tick interval. Cache entries are stored as
    ``(timestamp, value)``; ``get(key)`` evicts expired entries lazily.

    Stores ``None`` values as legitimate cache entries — useful for caching
    "we tried this upstream and it returned no useful data" results so
    subsequent ticks don't hammer the same dead endpoint.

    Not concurrency-safe by design (each provider owns its own instance,
    and Python's asyncio model serialises access within a task).
    """

    def __init__(self, ttl_s: float = DEFAULT_TTL_CACHE_S) -> None:
        self._ttl_s = float(ttl_s)
        self._store: Dict[str, Tuple[float, Any]] = {}

    @property
    def ttl_s(self) -> float:
        return self._ttl_s

    def get(self, key: str) -> Tuple[bool, Any]:
        """Returns ``(hit, value)``. ``hit=False`` means key is absent or
        expired; ``value`` is meaningless in that case."""
        entry = self._store.get(key)
        if entry is None:
            return False, None
        ts, value = entry
        if (time.time() - ts) > self._ttl_s:
            self._store.pop(key, None)
            return False, None
        return True, value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.time(), value)

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
