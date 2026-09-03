"""Phase-2 · Generic multi-chain pool-discovery / venue universe (fail-closed).

Builds the candidate VENUE universe (the same ``PoolNode`` graph the
``RouteSearchEngine`` consumes) for the Phase-2 chains from the VERIFIED public
registries (``chains/registries.py`` — real token addresses + real DEX factory
addresses). Like ``discovery/base_venues``, venues carry a SYNTHETIC id and
``tvl_usd=0.0``; the CONCRETE pool address, live quote, real reserves and USD
TVL are resolved on-chain DOWNSTREAM (fail-closed per pool). Nothing here is
fabricated: no pool addresses, no prices, no TVL.

A chain contributes venues ONLY when it has a registry entry AND a configured
RPC (``resolve_rpc_url_from_env``). Unknown / un-configured chains ⇒ empty
universe (fail-closed — never a Base-derived or invented universe).

Base is intentionally NOT served here — it keeps its own dedicated,
regression-frozen ``base_venues`` graph.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import base_venues  # for PoolNode via its import surface
from ..scanners.flash_loan_arbitrage.route_search import PoolNode
from ..chains import registries

# Majors + stables we route through per chain (only those actually in the
# chain's verified registry are used). Deterministic, no fabrication.
_PREFERRED = ["WETH", "WBNB", "WMATIC", "WBTC", "BTCB",
              "USDC", "USDT", "DAI", "USDC.e", "ARB", "OP", "wstETH"]
# Uniswap-V3-style fee tiers (ppm) probed for same-/cross-DEX surfaces.
_V3_FEE_TIERS = (500, 3000)


def _venue_id(dex: str, a: str, b: str, param: Any) -> str:
    lo, hi = sorted([a, b])
    return f"{dex}:{lo}:{hi}:{param}"


def build_pool_graph(chain: str) -> List[PoolNode]:
    """Venue universe for ``chain`` (fail-closed empty if unsupported)."""
    chain = (chain or "").lower()
    reg = registries.registry_for(chain)
    if not reg:
        return []
    tokens = reg.get("tokens", {})
    present = [s for s in _PREFERRED if s in tokens]
    if len(present) < 2:
        return []
    v3_dexes = [d["dex"] for d in registries.dexes_for(chain)
                if d.get("kind") == "v3"]
    if not v3_dexes:
        return []

    pools: List[PoolNode] = []
    seen: set = set()
    for dex in v3_dexes:
        for i in range(len(present)):
            for j in range(i + 1, len(present)):
                a, b = present[i], present[j]
                for fee_ppm in _V3_FEE_TIERS:
                    vid = _venue_id(dex, a, b, fee_ppm)
                    if vid in seen:
                        continue
                    seen.add(vid)
                    pools.append(PoolNode(
                        pool_address=vid, dex_protocol=dex, chain=chain,
                        token_a=a, token_b=b, tvl_usd=0.0,
                        fee_bps=int(fee_ppm // 100) or 5))
    return pools


def supported_discovery_chains() -> List[str]:
    return sorted(registries.CHAIN_REGISTRIES.keys())


__all__ = ["build_pool_graph", "supported_discovery_chains"]
