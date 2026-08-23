"""T0-6 · TVL provider interface (fail-closed liquidity).

Replaces the hardcoded ``5_000_000`` TVL sentinel in ``base_venues`` with
an explicit provider abstraction. The default provider returns ``None``
(TVL unverifiable) which makes Gate 8 fail closed — no route may pass the
liquidity gate on fabricated depth. A real (cached) provider is wired in
T1; this module only establishes the seam.

Design:
  * ``get_pool_tvl_usd(chain, pool) -> Optional[float]`` — None = unknown.
  * ``UnknownTVLProvider`` — always None (safe default; fail closed).
  * ``StaticTVLProvider`` — fixed map, for tests/fixtures only.

INV: never fabricates liquidity. Unknown → downstream Gate 8 denies.
"""
from __future__ import annotations

import time
from typing import (
    Awaitable, Callable, Dict, Optional, Protocol, Tuple, runtime_checkable,
)


@runtime_checkable
class TVLProvider(Protocol):
    async def get_pool_tvl_usd(self, chain: str,
                               pool_address: str) -> Optional[float]: ...


class UnknownTVLProvider:
    """Default T0 provider: TVL is unverifiable → Gate 8 fails closed."""

    provider_id = "tvl_unknown"

    async def get_pool_tvl_usd(self, chain: str,
                               pool_address: str) -> Optional[float]:
        return None


class StaticTVLProvider:
    """Fixture provider — explicit pool→TVL map. TEST/RESEARCH ONLY."""

    provider_id = "tvl_static_fixture"

    def __init__(self, tvl_by_pool: Optional[Dict[str, float]] = None) -> None:
        self._map: Dict[str, float] = dict(tvl_by_pool or {})

    async def get_pool_tvl_usd(self, chain: str,
                               pool_address: str) -> Optional[float]:
        v = self._map.get(pool_address)
        return float(v) if v is not None else None


__all__ = ["TVLProvider", "UnknownTVLProvider", "StaticTVLProvider",
           "CachedTVLProvider", "OnChainReserveTVLProvider"]


# ── T1: real TVL sources (fail-closed; never fabricates liquidity) ─────────

class CachedTVLProvider:
    """T1 · TTL cache in front of a real ``TVLProvider`` source.

    Caches both hits and *misses* (None) briefly to avoid hammering the RPC
    while still failing closed: a cached None keeps Gate 8 denying. Deterministic
    with an injectable clock for tests.
    """

    provider_id = "tvl_cached"

    def __init__(self, source: "TVLProvider", *, ttl_sec: float = 30.0,
                 miss_ttl_sec: float = 5.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._source = source
        self._ttl = float(ttl_sec)
        self._miss_ttl = float(miss_ttl_sec)
        self._clock = clock
        self._cache: Dict[str, Tuple[float, Optional[float]]] = {}

    async def get_pool_tvl_usd(self, chain: str,
                               pool_address: str) -> Optional[float]:
        key = f"{chain}:{pool_address}"
        now = self._clock()
        hit = self._cache.get(key)
        if hit is not None:
            expires, val = hit
            if now < expires:
                return val
        val = await self._source.get_pool_tvl_usd(chain, pool_address)
        ttl = self._ttl if val is not None else self._miss_ttl
        self._cache[key] = (now + ttl, val)
        return val


class OnChainReserveTVLProvider:
    """T1 · TVL = Σ(reserveᵢ × priceᵢ) from real on-chain reads.

    ``reserves_fn(chain, pool) -> (token0, reserve0, token1, reserve1) | None``
    ``price_fn(chain, token) -> usd | None``
    If reserves or ANY token price is unavailable, returns None (fail closed —
    no fabricated liquidity). On the VPS these callables wrap the live
    QuoterRegistry / RPC; in tests they are deterministic fixtures.
    """

    provider_id = "tvl_onchain_reserves"

    def __init__(
        self,
        reserves_fn: Callable[[str, str], Awaitable[Optional[Tuple[str, float, str, float]]]],
        price_fn: Callable[[str, str], Awaitable[Optional[float]]],
    ) -> None:
        self._reserves_fn = reserves_fn
        self._price_fn = price_fn

    async def get_pool_tvl_usd(self, chain: str,
                               pool_address: str) -> Optional[float]:
        data = await self._reserves_fn(chain, pool_address)
        if not data:
            return None
        t0, r0, t1, r1 = data
        p0 = await self._price_fn(chain, t0)
        p1 = await self._price_fn(chain, t1)
        if p0 is None or p1 is None:
            return None
        tvl = float(r0) * float(p0) + float(r1) * float(p1)
        return tvl if tvl > 0 else None
