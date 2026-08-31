"""Env-driven provider bootstrap (Stage 2 · v2.5.0).

Reads ``PROVIDER_*`` environment variables and registers concrete
providers with the existing :class:`ProviderRegistry`.

Everything registered here is READ-ONLY. Zero signing. Zero
transactions. No wallet interaction.

Env contract:
  PROVIDER_RPC_URL_ETHEREUM   / PROVIDER_RPC_URL_ARBITRUM /
  PROVIDER_RPC_URL_BASE       / PROVIDER_RPC_URL_POLYGON  /
  PROVIDER_RPC_URL_OPTIMISM   / PROVIDER_RPC_URL_BNB       /
  PROVIDER_RPC_URL_SOLANA     — override the free-tier defaults

  PROVIDER_CEX_ENABLED        — csv of venues (default: 'binance,bybit,okx,coinbase,kraken,kucoin')
  PROVIDER_DEX_ENABLED        — csv of families (default:
                                'uniswap_v3,uniswap_v2,sushiswap,pancakeswap,jupiter,raydium,balancer_v2')
  PROVIDER_QUOTE_ENABLED      — csv of aggregators (default: 'oneinch,zeroex')

  PROVIDER_1INCH_API_KEY / PROVIDER_0X_API_KEY  — optional auth
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from .registry import ProviderRegistry
from .rpc import EthJsonRpcProvider, SolanaRpcProvider, DEFAULT_RPC_URLS
from .dex import (
    UniswapV3Quoter, UniswapV2Router, CurvePool,
    BalancerV2Vault, JupiterQuoter, RaydiumHealth,
)
from .cex import ALL_CEX
from .aux_providers import (
    OneInchQuoter, ZeroExQuoter,
    RpcDerivedGasProvider, StaticTokenMetadataProvider,
)

logger = logging.getLogger(__name__)


_EVM_CHAINS = ["ethereum", "arbitrum", "base",
               "polygon", "optimism", "bnb"]


def _csv(name: str, default: str) -> List[str]:
    raw = os.environ.get(name, default) or ""
    return [x.strip() for x in raw.split(",") if x.strip()]


def _rpc_urls(chain: str) -> List[str]:
    """Return configured RPC endpoints for a chain.

    Preferred:
        PROVIDER_RPC_URLS_<CHAIN>  (comma-separated)

    Backward compatible:
        PROVIDER_RPC_URL_<CHAIN>   (single endpoint)

    If neither is configured, use the existing public default.
    """
    urls = _csv(f"PROVIDER_RPC_URLS_{chain.upper()}", "")
    if urls:
        return urls

    single = os.environ.get(f"PROVIDER_RPC_URL_{chain.upper()}")
    if single:
        return [single.strip()]

    default = DEFAULT_RPC_URLS.get(chain)
    return [default] if default else []


from .rpc_failover import set_default_registry


def bootstrap(registry: ProviderRegistry) -> Dict[str, Any]:
    """Register every enabled provider. Returns a summary of what landed.

    Idempotent — safe to call multiple times if registry is fresh; will
    silently overwrite prior instances with the same provider_id.
    """
    set_default_registry(registry)
    summary: Dict[str, Any] = {
        "rpc": [], "dex": [], "cex": [], "quote": [],
        "gas": [], "metadata": [], "errors": [],
    }
    # ---- RPC (EVM) ----------------------------------------------------
    # Register EVERY configured endpoint independently.
    #
    # Preferred:
    #   PROVIDER_RPC_URLS_<CHAIN> = comma-separated endpoints
    #
    # Backward compatible:
    #   PROVIDER_RPC_URL_<CHAIN> = single endpoint
    #
    # If neither is configured, use DEFAULT_RPC_URLS.
    rpc_by_chain: Dict[str, EthJsonRpcProvider] = {}

    for chain in _EVM_CHAINS:
        urls = _rpc_urls(chain)

        for index, url in enumerate(urls):
            if not url:
                continue

            try:
                host = (
                    url.split("//", 1)[-1]
                       .split("/", 1)[0]
                       .replace(".", "_")[:24]
                )

                provider_id = f"rpc_{chain}_{index}_{host}"

                p = EthJsonRpcProvider(
                    chain=chain,
                    url=url,
                    provider_id=provider_id,
                )

                registry.register(
                    p,
                    chain=chain,
                    priority=100 + index,
                )

                summary["rpc"].append({
                    "chain": chain,
                    "index": index,
                    "provider_id": p.provider_id,
                })

                # Existing DEX/gas providers use the primary RPC.
                if chain not in rpc_by_chain:
                    rpc_by_chain[chain] = p

            except Exception as e:                                   # noqa
                summary["errors"].append({
                    "provider": f"rpc:{chain}:{index}",
                    "error": str(e),
                })


    # ---- RPC (Solana) -------------------------------------------------
    sol_url = os.environ.get("PROVIDER_RPC_URL_SOLANA") \
              or DEFAULT_RPC_URLS["solana"]
    try:
        sol = SolanaRpcProvider(url=sol_url)
        registry.register(sol, chain="solana", priority=100)
        summary["rpc"].append({"chain": "solana",
                                 "provider_id": sol.provider_id})
    except Exception as e:                                           # noqa
        sol = None
        summary["errors"].append({"provider": "rpc:solana",
                                    "error": str(e)})

    # ---- DEX ----------------------------------------------------------
    dex_enabled = set(_csv("PROVIDER_DEX_ENABLED",
                             "uniswap_v3,uniswap_v2,sushiswap,pancakeswap,"
                             "jupiter,raydium,balancer_v2"))

    if "uniswap_v3" in dex_enabled:
        for chain in ("ethereum", "arbitrum", "base",
                      "optimism", "polygon", "bnb"):
            if chain in rpc_by_chain and chain in UniswapV3Quoter.QUOTER_ADDRESSES:
                try:
                    p = UniswapV3Quoter(chain=chain, rpc=rpc_by_chain[chain])
                    registry.register(p, chain=chain, priority=110)
                    summary["dex"].append({"family": "uniswap_v3",
                                             "chain": chain,
                                             "provider_id": p.provider_id})
                except Exception as e:                               # noqa
                    summary["errors"].append({
                        "provider": f"dex:uniswap_v3:{chain}",
                        "error": str(e)})

    if "uniswap_v2" in dex_enabled and "ethereum" in rpc_by_chain:
        try:
            p = UniswapV2Router(family="uniswap_v2", chain="ethereum",
                                rpc=rpc_by_chain["ethereum"])
            registry.register(p, chain="ethereum", priority=120)
            summary["dex"].append({"family": "uniswap_v2",
                                     "chain": "ethereum",
                                     "provider_id": p.provider_id})
        except Exception as e:                                       # noqa
            summary["errors"].append({"provider": "dex:uniswap_v2:ethereum",
                                        "error": str(e)})

    if "sushiswap" in dex_enabled:
        for chain in ("ethereum", "arbitrum"):
            if chain in rpc_by_chain:
                try:
                    p = UniswapV2Router(family="sushiswap", chain=chain,
                                          rpc=rpc_by_chain[chain])
                    registry.register(p, chain=chain, priority=120)
                    summary["dex"].append({"family": "sushiswap",
                                             "chain": chain,
                                             "provider_id": p.provider_id})
                except Exception as e:                               # noqa
                    summary["errors"].append({
                        "provider": f"dex:sushiswap:{chain}",
                        "error": str(e)})

    if "pancakeswap" in dex_enabled and "bnb" in rpc_by_chain:
        try:
            p = UniswapV2Router(family="pancakeswap", chain="bnb",
                                rpc=rpc_by_chain["bnb"])
            registry.register(p, chain="bnb", priority=120)
            summary["dex"].append({"family": "pancakeswap", "chain": "bnb",
                                     "provider_id": p.provider_id})
        except Exception as e:                                       # noqa
            summary["errors"].append({"provider": "dex:pancakeswap:bnb",
                                        "error": str(e)})

    if "balancer_v2" in dex_enabled and "ethereum" in rpc_by_chain:
        try:
            p = BalancerV2Vault(chain="ethereum",
                                 rpc=rpc_by_chain["ethereum"])
            registry.register(p, chain="ethereum", priority=140)
            summary["dex"].append({"family": "balancer_v2",
                                     "chain": "ethereum",
                                     "provider_id": p.provider_id})
        except Exception as e:                                       # noqa
            summary["errors"].append({"provider": "dex:balancer_v2",
                                        "error": str(e)})

    if "jupiter" in dex_enabled:
        try:
            p = JupiterQuoter()
            registry.register(p, chain="solana", priority=110)
            summary["dex"].append({"family": "jupiter", "chain": "solana",
                                     "provider_id": p.provider_id})
        except Exception as e:                                       # noqa
            summary["errors"].append({"provider": "dex:jupiter",
                                        "error": str(e)})

    if "raydium" in dex_enabled and sol is not None:
        try:
            p = RaydiumHealth(rpc=sol)
            registry.register(p, chain="solana", priority=130)
            summary["dex"].append({"family": "raydium", "chain": "solana",
                                     "provider_id": p.provider_id})
        except Exception as e:                                       # noqa
            summary["errors"].append({"provider": "dex:raydium",
                                        "error": str(e)})

    # ---- CEX ----------------------------------------------------------
    cex_enabled = set(_csv(
        "PROVIDER_CEX_ENABLED",
        "binance,bybit,okx,coinbase,kraken,kucoin"))
    for cls in ALL_CEX:
        if cls.venue in cex_enabled:
            try:
                p = cls()
                registry.register(p, chain="cex", priority=105)
                summary["cex"].append({"venue": cls.venue,
                                          "provider_id": p.provider_id})
            except Exception as e:                                   # noqa
                summary["errors"].append({"provider": f"cex:{cls.venue}",
                                            "error": str(e)})

    # ---- Quote aggregators -------------------------------------------
    quote_enabled = set(_csv("PROVIDER_QUOTE_ENABLED", "oneinch,zeroex"))
    if "oneinch" in quote_enabled:
        api = os.environ.get("PROVIDER_1INCH_API_KEY") or None
        for chain in _EVM_CHAINS:
            if chain not in rpc_by_chain and chain not in ("bnb",):
                continue
            try:
                p = OneInchQuoter(chain=chain, api_key=api)
                registry.register(p, chain=chain, priority=115)
                summary["quote"].append({"venue": "1inch", "chain": chain,
                                            "provider_id": p.provider_id})
            except Exception as e:                                   # noqa
                summary["errors"].append({
                    "provider": f"quote:1inch:{chain}",
                    "error": str(e)})

    if "zeroex" in quote_enabled:
        api = os.environ.get("PROVIDER_0X_API_KEY") or None
        for chain in _EVM_CHAINS:
            try:
                p = ZeroExQuoter(chain=chain, api_key=api)
                registry.register(p, chain=chain, priority=115)
                summary["quote"].append({"venue": "0x", "chain": chain,
                                            "provider_id": p.provider_id})
            except Exception as e:                                   # noqa
                summary["errors"].append({
                    "provider": f"quote:0x:{chain}",
                    "error": str(e)})

    # ---- Gas + metadata ----------------------------------------------
    for chain, rpc in rpc_by_chain.items():
        try:
            p = RpcDerivedGasProvider(rpc=rpc)
            registry.register(p, chain=chain, priority=100)
            summary["gas"].append({"chain": chain,
                                     "provider_id": p.provider_id})
        except Exception as e:                                       # noqa
            summary["errors"].append({"provider": f"gas:{chain}",
                                        "error": str(e)})

    try:
        p = StaticTokenMetadataProvider()
        registry.register(p, chain=None, priority=100)
        summary["metadata"].append({"provider_id": p.provider_id})
    except Exception as e:                                           # noqa
        summary["errors"].append({"provider": "metadata:static",
                                    "error": str(e)})

    summary["totals"] = {
        k: len(v) for k, v in summary.items() if isinstance(v, list)
    }
    logger.info(
        "providers.bootstrap: registered rpc=%d dex=%d cex=%d quote=%d "
        "gas=%d metadata=%d errors=%d",
        len(summary["rpc"]), len(summary["dex"]), len(summary["cex"]),
        len(summary["quote"]), len(summary["gas"]),
        len(summary["metadata"]), len(summary["errors"]))
    return summary


__all__ = ["bootstrap"]
