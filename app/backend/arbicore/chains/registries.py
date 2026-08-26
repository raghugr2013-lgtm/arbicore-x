"""Phase-2 · Per-chain token + DEX registries (verified public constants).

Data ONLY. These are canonical, publicly-verifiable token contract addresses and
DEX factory addresses for each Phase-2 chain. They contain NO fabricated pool
addresses — concrete pools are resolved + validated on-chain at runtime (the
same fail-closed pattern as ``searcher/aero_resolver.py`` on Base). Until a
chain's identity / quote / gas / pools are probed live on the VPS, the chain
stays NOT ``active_ready`` (see ``EvmChainAdapter.capability``).

Address casing is EIP-55 checksummed where practical; consumers should treat
them case-insensitively and re-verify on-chain before any economic use.
"""
from __future__ import annotations

from typing import Any, Dict, List

# token symbol -> {address, decimals}
# dexes: list of {dex, kind, factory}  (kind: "v3" | "v2" | "stable")
CHAIN_REGISTRIES: Dict[str, Dict[str, Any]] = {
    "arbitrum": {
        "chain_id": 42161,
        "native_token": "ETH",
        "tokens": {
            "WETH": {"address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "decimals": 18},
            "USDC": {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "decimals": 6},
            "USDC.e": {"address": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8", "decimals": 6},
            "USDT": {"address": "0xFd086bC7CD5C481DCC9C85ebE478A1C0b69FCbb9", "decimals": 6},
            "DAI": {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
            "WBTC": {"address": "0x2f2a2543B76A4166549F7aaB2e75Bef0aefC5B0f", "decimals": 8},
            "ARB": {"address": "0x912CE59144191C1204E64559FE8253a0e49E6548", "decimals": 18},
            "wstETH": {"address": "0x5979D7b546E38E414F7E9822514be443A4800529", "decimals": 18},
        },
        "dexes": [
            {"dex": "uniswap_v3", "kind": "v3", "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984"},
            {"dex": "sushiswap_v3", "kind": "v3", "factory": "0x1af415a1EbA07a4986a52B6f2e7dE7003D82231e"},
            {"dex": "camelot_v3", "kind": "v3", "factory": "0x1a3c9B1d2F0529D97f2afC5136Cc23e58f1FD35B"},
        ],
    },
    "optimism": {
        "chain_id": 10,
        "native_token": "ETH",
        "tokens": {
            "WETH": {"address": "0x4200000000000000000000000000000000000006", "decimals": 18},
            "USDC": {"address": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85", "decimals": 6},
            "USDC.e": {"address": "0x7F5c764cBc14f9669B88837ca1490cCa17c31607", "decimals": 6},
            "USDT": {"address": "0x94b008aA00579c1307B0EF2c499aD98a8ce58e58", "decimals": 6},
            "DAI": {"address": "0xDA10009cBd5D07dd0CeCc66161FC93D7c9000da1", "decimals": 18},
            "WBTC": {"address": "0x68f180fcCe6836688e9084f035309E29Bf0A2095", "decimals": 8},
            "OP": {"address": "0x4200000000000000000000000000000000000042", "decimals": 18},
            "wstETH": {"address": "0x1F32b1c2345538c0c6f582fCB022739c4A194Ebb", "decimals": 18},
        },
        "dexes": [
            {"dex": "uniswap_v3", "kind": "v3", "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984"},
            {"dex": "velodrome_v2", "kind": "stable", "factory": "0xF1046053aa5682b4F9a81b5481394DA16BE5FF5a"},
        ],
    },
    "ethereum": {
        "chain_id": 1,
        "native_token": "ETH",
        "tokens": {
            "WETH": {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "decimals": 18},
            "USDC": {"address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "decimals": 6},
            "USDT": {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "decimals": 6},
            "DAI": {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "decimals": 18},
            "WBTC": {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "decimals": 8},
            "wstETH": {"address": "0x7f39C581F595B53c5cb19bD0b3f8dA6c935E2Ca0", "decimals": 18},
            "rETH": {"address": "0xae78736Cd615f374D3085123A210448E74Fc6393", "decimals": 18},
            "weETH": {"address": "0xCd5fE23C85820F7B72D0926FC9b05b43E359b7ee", "decimals": 18},
        },
        "dexes": [
            {"dex": "uniswap_v3", "kind": "v3", "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984"},
            {"dex": "sushiswap_v2", "kind": "v2", "factory": "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac"},
            {"dex": "curve_stable", "kind": "stable", "factory": "0xB9fC157394Af804a3578134A6585C0dc9cc990d4"},
        ],
    },
    "polygon": {
        "chain_id": 137,
        "native_token": "POL",
        "tokens": {
            "WMATIC": {"address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "decimals": 18},
            "WETH": {"address": "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619", "decimals": 18},
            "USDC": {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "decimals": 6},
            "USDC.e": {"address": "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174", "decimals": 6},
            "USDT": {"address": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F", "decimals": 6},
            "DAI": {"address": "0x8f3Cf7ad23Cd3CaDbD9735AFf958023239c6A063", "decimals": 18},
            "WBTC": {"address": "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6", "decimals": 8},
        },
        "dexes": [
            {"dex": "uniswap_v3", "kind": "v3", "factory": "0x1F98431c8aD98523631AE4a59f267346ea31F984"},
            {"dex": "quickswap_v3", "kind": "v3", "factory": "0x411b0fAcC3489691f28ad58c47006AF5E3Ab3A28"},
        ],
    },
    "bnb": {
        "chain_id": 56,
        "native_token": "BNB",
        "tokens": {
            "WBNB": {"address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "decimals": 18},
            "WETH": {"address": "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", "decimals": 18},
            "USDC": {"address": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d", "decimals": 18},
            "USDT": {"address": "0x55d398326f99059fF775485246999027B3197955", "decimals": 18},
            "DAI": {"address": "0x1AF3F329e8BE154074D8769D1FFa4eE058B1DBc3", "decimals": 18},
            "BTCB": {"address": "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", "decimals": 18},
        },
        "dexes": [
            {"dex": "pancakeswap_v3", "kind": "v3", "factory": "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865"},
            {"dex": "uniswap_v3", "kind": "v3", "factory": "0xdB1d10011AD0Ff90774D0C6Bb92e5C5c8b4461F7"},
        ],
    },
}


def registry_for(chain: str) -> Dict[str, Any]:
    return CHAIN_REGISTRIES.get((chain or "").lower(), {})


def tokens_for(chain: str) -> Dict[str, Any]:
    return dict(registry_for(chain).get("tokens", {}))


def dexes_for(chain: str) -> List[Dict[str, Any]]:
    return list(registry_for(chain).get("dexes", []))


__all__ = ["CHAIN_REGISTRIES", "registry_for", "tokens_for", "dexes_for"]
