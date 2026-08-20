"""ArbiCore X — curated Base venue registry + route pool graph (P0 discovery).

All token addresses here are VERIFIED on-chain (ERC-20 ``symbol()`` checked
against Base mainnet). Venues are (dex, token pair, fee/tick/stable) tuples.
We deliberately do NOT hardcode pool contract addresses or TVL — a venue that
does not actually exist on-chain simply fails to quote and is rejected
(UNAVAILABLE) rather than fabricated. Real pool TVL/depth is a separate
engineering task (see readiness matrix LIQUIDITY_DEPTH).

The registry feeds the already-built ``RouteSearchEngine`` (symbol graph +
bounded cycle DFS) and maps each synthesised pool node back to a concrete
quoter hop spec for the read-only ``QuoterRegistry``.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from ..scanners.flash_loan_arbitrage.route_search import PoolNode

CHAIN = "base"

# Verified Base mainnet ERC-20s (address, decimals, is_stable).
TOKENS: Dict[str, Dict[str, Any]] = {
    "WETH":   {"address": "0x4200000000000000000000000000000000000006", "decimals": 18, "stable": False},
    "USDC":   {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "decimals": 6,  "stable": True},
    "cbETH":  {"address": "0x2Ae3F1Ec7F1F5012CFEab0185bfc7aa3cf0DEc22", "decimals": 18, "stable": False},
    "DAI":    {"address": "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb", "decimals": 18, "stable": True},
    "USDbC":  {"address": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA", "decimals": 6,  "stable": True},
    "cbBTC":  {"address": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf", "decimals": 8,  "stable": False},
    "AERO":   {"address": "0x940181a94A35A4569E4529A3CDfB74e38FD98631", "decimals": 18, "stable": False},
    "USDT":   {"address": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2", "decimals": 6,  "stable": True},
    "rETH":   {"address": "0xB6fe221Fe9EeF5aBa221c348bA20A1Bf5e73624c", "decimals": 18, "stable": False},
    "wstETH": {"address": "0xc1CBa3fCea344f92D9239c08C0568f6F2F0ee452", "decimals": 18, "stable": False},
    "weETH":  {"address": "0x04C0599Ae5A44757c0af6F9eC3b93da8976c150A", "decimals": 18, "stable": False},
    "DEGEN":  {"address": "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed", "decimals": 18, "stable": False},
}

# Approved borrow (flash-loan) tokens — must be deep + flash-loanable.
BORROW_TOKENS = ["WETH", "USDC", "cbETH", "USDbC"]

# Probe notional (in token base units) used to measure the MARGINAL spread of
# a route. The size optimizer later searches the profitable notional.
PROBE_AMOUNT: Dict[str, int] = {
    "WETH": 5 * 10**16,     # 0.05 WETH
    "USDC": 200 * 10**6,    # 200 USDC
    "cbETH": 5 * 10**16,
    "DAI": 200 * 10**18,
    "USDbC": 200 * 10**6,
    "cbBTC": 2 * 10**5,     # 0.002 cbBTC
    "AERO": 200 * 10**18,
    "USDT": 200 * 10**6,
    "rETH": 5 * 10**16,
    "wstETH": 4 * 10**16,
    "weETH": 5 * 10**16,
    "DEGEN": 20000 * 10**18,
}

# Router allowlist (canonical Base). SlipStream + classic share the router.
ROUTER_ALLOWLIST = [
    "0x2626664c2603336E57B271c5C0b26F421741e481",   # Uniswap V3 SwapRouter02
    "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43",   # Aerodrome Router
]

# Venue list: (dex, token_a, token_b, param). ``param`` semantics:
#   uniswap_v3            -> fee in ppm (500 = 0.05%)
#   aerodrome_slipstream  -> tick_spacing
#   aerodrome (classic)   -> "stable" | "volatile"
VENUES: List[Tuple[str, str, str, Any]] = [
    # Uniswap V3 — majors across fee tiers (same-DEX fee-tier arb surface)
    ("uniswap_v3", "WETH", "USDC", 500),
    ("uniswap_v3", "WETH", "USDC", 3000),
    ("uniswap_v3", "WETH", "USDC", 10000),
    ("uniswap_v3", "WETH", "cbETH", 500),
    ("uniswap_v3", "WETH", "cbETH", 3000),
    ("uniswap_v3", "cbETH", "USDC", 500),
    ("uniswap_v3", "WETH", "DAI", 3000),
    ("uniswap_v3", "WETH", "USDT", 500),
    ("uniswap_v3", "WETH", "rETH", 500),
    ("uniswap_v3", "WETH", "wstETH", 100),
    ("uniswap_v3", "WETH", "weETH", 500),
    ("uniswap_v3", "WETH", "cbBTC", 3000),
    ("uniswap_v3", "USDC", "cbBTC", 3000),
    ("uniswap_v3", "WETH", "DEGEN", 3000),
    ("uniswap_v3", "USDC", "AERO", 3000),
    ("uniswap_v3", "WETH", "AERO", 3000),
    # Stablecoin surfaces
    ("uniswap_v3", "USDC", "DAI", 100),
    ("uniswap_v3", "USDC", "USDT", 100),
    ("uniswap_v3", "USDC", "USDbC", 100),
    # Aerodrome SlipStream (concentrated)
    ("aerodrome_slipstream", "WETH", "USDC", 100),
    ("aerodrome_slipstream", "WETH", "cbETH", 1),
    ("aerodrome_slipstream", "WETH", "wstETH", 1),
    ("aerodrome_slipstream", "WETH", "AERO", 200),
    # Aerodrome classic AMM
    ("aerodrome", "USDC", "USDbC", "stable"),
    ("aerodrome", "USDC", "USDT", "stable"),
    ("aerodrome", "USDC", "DAI", "stable"),
    ("aerodrome", "WETH", "USDC", "volatile"),
    ("aerodrome", "WETH", "AERO", "volatile"),
    ("aerodrome", "WETH", "DEGEN", "volatile"),
    ("aerodrome", "AERO", "USDC", "volatile"),
]

# Nominal fee (bps) per venue kind — used only for the route-search fee prune
# hint; the REAL cost comes from live quoting.
_NOMINAL_FEE_BPS = {"uniswap_v3": None, "aerodrome_slipstream": 5, "aerodrome": 5}


def token_address(symbol: str) -> str:
    return TOKENS[symbol]["address"]


def is_stable(symbol: str) -> bool:
    return bool(TOKENS.get(symbol, {}).get("stable"))


def _venue_id(dex: str, a: str, b: str, param: Any) -> str:
    lo, hi = sorted([a, b])
    return f"{dex}:{lo}:{hi}:{param}"


def build_pool_graph() -> Tuple[List[PoolNode], Dict[str, Dict[str, Any]]]:
    """Return (pool_nodes, venue_specs).

    ``venue_specs`` maps ``pool_address`` (synthetic venue id) → the concrete
    quoter hop spec extras (dex + fee/tick/stable). TVL is set to a large
    sentinel so the route-search TVL gate is a no-op here (real TVL is future
    engineering); depth risk is instead handled by live slippage + the size
    optimizer's liquidity-impact model.
    """
    pools: List[PoolNode] = []
    specs: Dict[str, Dict[str, Any]] = {}
    for dex, a, b, param in VENUES:
        vid = _venue_id(dex, a, b, param)
        fee_ppm = int(param) if dex == "uniswap_v3" else 0
        fee_bps = (fee_ppm // 100) if dex == "uniswap_v3" else _NOMINAL_FEE_BPS[dex]
        pools.append(PoolNode(
            pool_address=vid, dex_protocol=dex, chain=CHAIN,
            token_a=a, token_b=b, tvl_usd=5_000_000.0, fee_bps=int(fee_bps or 5)))
        spec: Dict[str, Any] = {"dex": dex}
        if dex == "uniswap_v3":
            spec["fee"] = fee_ppm
        elif dex == "aerodrome_slipstream":
            spec["tick_spacing"] = int(param)
        elif dex == "aerodrome":
            spec["stable"] = (param == "stable")
        specs[vid] = spec
    return pools, specs


__all__ = ["CHAIN", "TOKENS", "BORROW_TOKENS", "PROBE_AMOUNT",
           "ROUTER_ALLOWLIST", "VENUES", "token_address", "is_stable",
           "build_pool_graph"]
