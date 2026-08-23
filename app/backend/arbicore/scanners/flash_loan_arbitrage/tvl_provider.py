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

from typing import Dict, Optional, Protocol, runtime_checkable


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


__all__ = ["TVLProvider", "UnknownTVLProvider", "StaticTVLProvider"]
