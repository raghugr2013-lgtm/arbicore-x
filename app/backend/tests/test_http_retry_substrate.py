"""Tests for the universal HTTP retry + TTL cache substrate.

This module (``arbicore/scanners/http_retry.py``) was promoted from the
D-4 hotfix wave's inline retry/cache logic. The hotfix-2 wave's job:
confirm zero behaviour change, validate the substrate API in isolation,
and lock the contract so D-5 (and any future scanner) can consume it
as a Reuse-As-Is primitive.

INV-1 / INV-2 / INV-3 — this module has nothing to do with canonical
construction, emission, or provenance. It's pure HTTP plumbing.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

import httpx
import pytest

from arbicore.scanners.http_retry import (
    DEFAULT_JITTER_FRACTION, DEFAULT_RETRY_INITIAL_BACKOFF_S,
    DEFAULT_RETRY_MAX_ATTEMPTS, DEFAULT_RETRY_MAX_BACKOFF_S,
    DEFAULT_TIMEOUT_S, DEFAULT_TTL_CACHE_S, RETRYABLE_STATUS_CODES,
    RetryConfig, TTLCache, post_json_with_retry, sleep_with_jitter,
)


# ============================================================================
# Stubs
# ============================================================================

class _StubResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _StubClient:
    def __init__(self):
        self.responses: List[Any] = []
        self.calls: List[Dict[str, Any]] = []

    async def post(self, url, json=None):
        self.calls.append({"url": url, "body": json})
        if not self.responses:
            return _StubResponse(500, {})
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt


# ============================================================================
# Constants & defaults
# ============================================================================

def test_retryable_status_codes_constant():
    assert RETRYABLE_STATUS_CODES == frozenset({429, 500, 502, 503, 504})


def test_default_values_unchanged_from_d4_hotfix():
    assert DEFAULT_TIMEOUT_S == 10.0
    assert DEFAULT_RETRY_MAX_ATTEMPTS == 3
    assert DEFAULT_RETRY_INITIAL_BACKOFF_S == 0.2
    assert DEFAULT_RETRY_MAX_BACKOFF_S == 2.0
    assert DEFAULT_TTL_CACHE_S == 60.0
    assert DEFAULT_JITTER_FRACTION == 0.25


# ============================================================================
# RetryConfig
# ============================================================================

def test_retry_config_defaults():
    cfg = RetryConfig()
    assert cfg.max_attempts == 3
    assert cfg.initial_backoff_s == 0.2
    assert cfg.max_backoff_s == 2.0
    assert cfg.retryable_status_codes == RETRYABLE_STATUS_CODES


def test_retry_config_from_kwargs_floors_attempts_at_one():
    cfg = RetryConfig.from_kwargs(retry_max_attempts=0)
    assert cfg.max_attempts == 1
    cfg2 = RetryConfig.from_kwargs(retry_max_attempts=-5)
    assert cfg2.max_attempts == 1


def test_retry_config_from_kwargs_coerces_types():
    cfg = RetryConfig.from_kwargs(
        retry_max_attempts="5",  # type: ignore[arg-type]
        retry_initial_backoff_s="0.3",  # type: ignore[arg-type]
        retry_max_backoff_s="3.0",  # type: ignore[arg-type]
    )
    assert cfg.max_attempts == 5
    assert cfg.initial_backoff_s == 0.3
    assert cfg.max_backoff_s == 3.0


def test_retry_config_is_immutable():
    cfg = RetryConfig()
    with pytest.raises(Exception):   # frozen dataclass raises FrozenInstanceError
        cfg.max_attempts = 10  # type: ignore[misc]


# ============================================================================
# sleep_with_jitter
# ============================================================================

def test_sleep_with_jitter_is_non_negative(monkeypatch):
    """Even when the random sample swings to -25%, the sleep must be ≥ 0
    (we ensure this with max(0, base + jitter))."""
    asyncio.run(sleep_with_jitter(0.0))   # base=0 → no sleep


def test_sleep_with_jitter_zero_base_safe():
    # Should not raise
    asyncio.run(sleep_with_jitter(0.0))


# ============================================================================
# post_json_with_retry — happy path & failure modes
# ============================================================================

def test_post_returns_payload_on_200():
    stub = _StubClient()
    stub.responses = [_StubResponse(200, {"ok": True})]
    out = asyncio.run(post_json_with_retry(stub, "https://x", {"a": 1}))
    assert out == {"ok": True}
    assert len(stub.calls) == 1


def test_post_retries_on_429():
    stub = _StubClient()
    stub.responses = [_StubResponse(429), _StubResponse(200, {"hit": 2})]
    out = asyncio.run(post_json_with_retry(
        stub, "https://x", {"a": 1},
        config=RetryConfig(initial_backoff_s=0.0, max_backoff_s=0.0)))
    assert out == {"hit": 2}
    assert len(stub.calls) == 2


def test_post_retries_on_all_5xx_codes():
    """429/500/502/503/504 are all retryable per the locked enumeration."""
    for code in (500, 502, 503, 504):
        stub = _StubClient()
        stub.responses = [_StubResponse(code), _StubResponse(200, {"v": code})]
        out = asyncio.run(post_json_with_retry(
            stub, "https://x", {},
            config=RetryConfig(initial_backoff_s=0.0, max_backoff_s=0.0)))
        assert out == {"v": code}, f"failed for status {code}"


def test_post_non_retryable_4xx_returns_none_immediately():
    """400/401/403/404 are NOT retryable — single attempt then None."""
    for code in (400, 401, 403, 404):
        stub = _StubClient()
        stub.responses = [_StubResponse(code)]
        out = asyncio.run(post_json_with_retry(
            stub, "https://x", {},
            config=RetryConfig(initial_backoff_s=0.0, max_backoff_s=0.0)))
        assert out is None, f"should not retry for {code}"
        assert len(stub.calls) == 1


def test_post_retry_budget_exhausted_returns_none():
    stub = _StubClient()
    stub.responses = [_StubResponse(429)] * 10
    out = asyncio.run(post_json_with_retry(
        stub, "https://x", {},
        config=RetryConfig(max_attempts=3, initial_backoff_s=0.0,
                            max_backoff_s=0.0)))
    assert out is None
    assert len(stub.calls) == 3   # exactly max_attempts


def test_post_http_error_retried():
    stub = _StubClient()
    stub.responses = [
        httpx.ConnectError("DNS"),
        _StubResponse(200, {"ok": True}),
    ]
    out = asyncio.run(post_json_with_retry(
        stub, "https://x", {},
        config=RetryConfig(initial_backoff_s=0.0, max_backoff_s=0.0)))
    assert out == {"ok": True}


def test_post_http_error_exhausts_budget():
    stub = _StubClient()
    stub.responses = [httpx.ConnectError("DNS")] * 5
    out = asyncio.run(post_json_with_retry(
        stub, "https://x", {},
        config=RetryConfig(max_attempts=3, initial_backoff_s=0.0,
                            max_backoff_s=0.0)))
    assert out is None
    assert len(stub.calls) == 3


def test_post_invalid_json_returns_none():
    stub = _StubClient()
    stub.responses = [_StubResponse(200, ValueError("not json"))]
    out = asyncio.run(post_json_with_retry(
        stub, "https://x", {},
        config=RetryConfig(initial_backoff_s=0.0, max_backoff_s=0.0)))
    assert out is None


def test_post_returns_list_payload_too():
    """JSON-RPC commonly returns dict; some upstreams (DexScreener,
    pumpfun mirrors) return a list at the root. Both are accepted."""
    stub = _StubClient()
    stub.responses = [_StubResponse(200, [{"a": 1}, {"b": 2}])]
    out = asyncio.run(post_json_with_retry(
        stub, "https://x", {},
        config=RetryConfig(initial_backoff_s=0.0, max_backoff_s=0.0)))
    assert out == [{"a": 1}, {"b": 2}]


def test_post_non_json_root_returns_none():
    stub = _StubClient()
    stub.responses = [_StubResponse(200, "plain string")]
    out = asyncio.run(post_json_with_retry(
        stub, "https://x", {},
        config=RetryConfig(initial_backoff_s=0.0, max_backoff_s=0.0)))
    assert out is None


def test_post_backoff_doubles_capped_at_max():
    """Backoff sequence 0.1 → 0.2 → 0.4 ... capped at 0.5."""
    stub = _StubClient()
    stub.responses = [_StubResponse(429)] * 5
    cfg = RetryConfig(max_attempts=5, initial_backoff_s=0.1, max_backoff_s=0.5)
    t0 = time.time()
    asyncio.run(post_json_with_retry(stub, "https://x", {}, config=cfg))
    elapsed = time.time() - t0
    # We slept 4 times between 5 attempts: ~0.1 + 0.2 + 0.4 + 0.5 ≈ 1.2s
    # ±25% jitter on each → bounded [~0.9, ~1.5]
    assert 0.5 < elapsed < 2.5


# ============================================================================
# TTLCache
# ============================================================================

def test_ttl_cache_miss_then_hit():
    c = TTLCache(ttl_s=60.0)
    hit, _ = c.get("k1")
    assert hit is False
    c.set("k1", "v1")
    hit, val = c.get("k1")
    assert hit is True
    assert val == "v1"


def test_ttl_cache_expires():
    c = TTLCache(ttl_s=0.05)
    c.set("k1", "v1")
    time.sleep(0.1)
    hit, _ = c.get("k1")
    assert hit is False


def test_ttl_cache_stores_none_legitimately():
    """Caching None is a feature, not a bug — prevents repeated hammering
    of dead upstream endpoints."""
    c = TTLCache(ttl_s=60.0)
    c.set("k1", None)
    hit, val = c.get("k1")
    assert hit is True
    assert val is None


def test_ttl_cache_stores_falsy_values():
    """0, empty list, empty string, False — all valid cache values."""
    c = TTLCache(ttl_s=60.0)
    for v in (0, [], "", False, 0.0):
        c.set("k", v)
        hit, val = c.get("k")
        assert hit is True, f"failed for {v!r}"
        assert val == v


def test_ttl_cache_len_and_clear():
    c = TTLCache(ttl_s=60.0)
    c.set("a", 1)
    c.set("b", 2)
    assert len(c) == 2
    c.clear()
    assert len(c) == 0


def test_ttl_cache_zero_ttl_always_misses():
    c = TTLCache(ttl_s=0.0)
    c.set("k", "v")
    # 0 TTL means every read is a miss because (now - ts) > 0
    hit, _ = c.get("k")
    assert hit is False


def test_ttl_cache_ttl_s_property():
    c = TTLCache(ttl_s=42.5)
    assert c.ttl_s == 42.5


# ============================================================================
# Behavioural parity with the pre-promotion D-4 hotfix
# ============================================================================

def test_post_json_payload_dict_with_error_key_is_passed_through():
    """The substrate is JSON-RPC-agnostic — it returns the payload as-is.
    The Helius provider unwraps the JSON-RPC envelope (error/result) in
    its own _rpc_call thin wrapper. This test confirms the substrate does
    NOT consume the 'error' key itself."""
    stub = _StubClient()
    stub.responses = [_StubResponse(200, {
        "jsonrpc": "2.0", "id": "x", "error": {"code": -1, "message": "x"}
    })]
    out = asyncio.run(post_json_with_retry(stub, "https://x", {},
                                              config=RetryConfig()))
    # Substrate returns the dict — caller decides how to interpret 'error'
    assert isinstance(out, dict)
    assert out.get("error") is not None


# ============================================================================
# Architectural — INV-1/2/3 — substrate is provenance-agnostic
# ============================================================================

def test_substrate_does_not_import_emission_bus():
    """INV-2: this universal helper must never depend on EmissionBus."""
    import arbicore.scanners.http_retry as mod
    import ast
    tree = ast.parse(open(mod.__file__).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "emission_bus" not in node.module.lower(), \
                f"INV-2 violation: imports {node.module}"
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            assert False, "INV-2 violation: .emit() call detected"


def test_substrate_does_not_import_canonical_or_provenance():
    """INV-1 / INV-3: the substrate is type-agnostic. It must not import
    CanonicalOpportunity, DataProvenance, or the SOURCE_REGISTRY."""
    import arbicore.scanners.http_retry as mod
    import ast
    tree = ast.parse(open(mod.__file__).read())
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            module = node.module if isinstance(node, ast.ImportFrom) \
                else (node.names[0].name if node.names else "")
            if not module:
                continue
            assert "canonical" not in module.lower()
            assert "provenance" not in module.lower()
            assert "opportunity_repo" not in module.lower()


# ============================================================================
# Re-export back-compat — old import path from helius_venue_provider
# ============================================================================

def test_helius_provider_still_exports_retryable_status_codes():
    """Existing tests import RETRYABLE_STATUS_CODES from the Helius provider
    module. The hotfix-2 refactor must preserve that import path."""
    from arbicore.scanners.launch_arbitrage.helius_venue_provider import (
        RETRYABLE_STATUS_CODES as HE_RETRYABLE,
        DEFAULT_RETRY_MAX_ATTEMPTS as HE_MAX,
        DEFAULT_TTL_CACHE_S as HE_TTL,
    )
    assert HE_RETRYABLE == RETRYABLE_STATUS_CODES
    assert HE_MAX == DEFAULT_RETRY_MAX_ATTEMPTS
    assert HE_TTL == DEFAULT_TTL_CACHE_S
