"""Quote aggregators, gas provider, token metadata (Stage 2 · v2.5.0)."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from .base import ProviderError, ProviderKind
from .rpc import EthJsonRpcProvider

logger = logging.getLogger(__name__)


# =============================================================================
# 1inch v5.2 — GET /swap/v5.2/{chain_id}/quote
# =============================================================================
class OneInchQuoter:
    kind = ProviderKind.QUOTE_AGGREGATOR
    venue = "1inch"

    CHAIN_IDS: Dict[str, int] = {
        "ethereum": 1, "arbitrum": 42161, "base": 8453,
        "optimism": 10, "polygon": 137, "bnb": 56,
    }

    def __init__(self, *, chain: str,
                 api_key: Optional[str] = None,
                 provider_id: Optional[str] = None,
                 timeout: float = 8.0) -> None:
        self.chain = chain
        cid = self.CHAIN_IDS.get(chain)
        if cid is None:
            raise ProviderError(f"1inch unsupported chain={chain}",
                                 retryable=False)
        self.chain_id = cid
        self._api_key = api_key
        self._timeout = timeout
        self.provider_id = provider_id or f"quote_1inch_{chain}"
        self._client: Optional[httpx.AsyncClient] = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"User-Agent": "arbicore-x/2.5.0 (+1inch)",
                        "Accept": "application/json"}
            if self._api_key:
                headers["Authorization"] = f"Bearer {self._api_key}"
            self._client = httpx.AsyncClient(
                base_url="https://api.1inch.dev",
                timeout=self._timeout, headers=headers)
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def aggregate_quote(self, token_in: str, token_out: str,
                               amount_in: int) -> Dict[str, Any]:
        client = await self._http()
        params = {"src": token_in, "dst": token_out, "amount": str(int(amount_in))}
        try:
            r = await client.get(
                f"/swap/v5.2/{self.chain_id}/quote", params=params)
            r.raise_for_status()
            body = r.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"1inch quote {self.chain} -> {e.response.status_code}",
                retryable=(e.response.status_code >= 500),
                provider_id=self.provider_id) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"1inch quote {self.chain}: {e}",
                                retryable=True,
                                provider_id=self.provider_id) from e
        return {
            "venue": self.venue, "chain": self.chain,
            "token_in": token_in, "token_out": token_out,
            "amount_in": int(amount_in),
            "amount_out": int(body.get("toAmount") or 0),
            "estimated_gas": int(body.get("estimatedGas") or 0),
        }

    async def health_probe(self) -> Dict[str, Any]:
        # Deep health probe requires a real request; that consumes rate-limit.
        # Cheap probe: HEAD /
        try:
            client = await self._http()
            t0 = time.time()
            r = await client.get(f"/swap/v5.2/{self.chain_id}/healthcheck")
            ok = r.status_code < 500
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": ok, "status": r.status_code,
                     "latency_ms": round((time.time() - t0) * 1000, 2),
                     "auth_configured": bool(self._api_key)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200],
                     "auth_configured": bool(self._api_key)}


# =============================================================================
# 0x — GET /swap/v1/price  (v1 is still open for read-only pricing)
# =============================================================================
class ZeroExQuoter:
    kind = ProviderKind.QUOTE_AGGREGATOR
    venue = "0x"

    HOSTS: Dict[str, str] = {
        "ethereum": "https://api.0x.org",
        "arbitrum": "https://arbitrum.api.0x.org",
        "base":     "https://base.api.0x.org",
        "optimism": "https://optimism.api.0x.org",
        "polygon":  "https://polygon.api.0x.org",
        "bnb":      "https://bsc.api.0x.org",
    }

    def __init__(self, *, chain: str, api_key: Optional[str] = None,
                 provider_id: Optional[str] = None,
                 timeout: float = 8.0) -> None:
        base = self.HOSTS.get(chain)
        if not base:
            raise ProviderError(f"0x unsupported chain={chain}",
                                 retryable=False)
        self.chain = chain
        self._api_key = api_key
        self.provider_id = provider_id or f"quote_0x_{chain}"
        headers = {"User-Agent": "arbicore-x/2.5.0 (+0x)"}
        if api_key:
            headers["0x-api-key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=base, timeout=timeout, headers=headers)

    async def close(self) -> None:
        await self._client.aclose()

    async def aggregate_quote(self, token_in: str, token_out: str,
                               amount_in: int) -> Dict[str, Any]:
        params = {"sellToken": token_in, "buyToken": token_out,
                   "sellAmount": str(int(amount_in))}
        try:
            r = await self._client.get("/swap/v1/price", params=params)
            r.raise_for_status()
            body = r.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"0x price {self.chain} -> {e.response.status_code}",
                retryable=(e.response.status_code >= 500),
                provider_id=self.provider_id) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"0x price {self.chain}: {e}",
                                 retryable=True,
                                 provider_id=self.provider_id) from e
        return {
            "venue": self.venue, "chain": self.chain,
            "token_in": token_in, "token_out": token_out,
            "amount_in": int(amount_in),
            "amount_out": int(float(body.get("buyAmount") or 0)),
            "price": float(body.get("price") or 0.0),
            "estimated_gas": int(body.get("gas") or 0),
        }

    async def health_probe(self) -> Dict[str, Any]:
        # 0x has no dedicated healthcheck — use a cheap price probe with tiny WETH -> USDC
        try:
            t0 = time.time()
            r = await self._client.get("/swap/v1/sources")
            ok = r.status_code < 500
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": ok, "status": r.status_code,
                     "latency_ms": round((time.time() - t0) * 1000, 2),
                     "auth_configured": bool(self._api_key)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200],
                     "auth_configured": bool(self._api_key)}


# =============================================================================
# Gas provider — derived from RPC provider
# =============================================================================
class RpcDerivedGasProvider:
    kind = ProviderKind.GAS

    def __init__(self, *, rpc: EthJsonRpcProvider,
                 provider_id: Optional[str] = None) -> None:
        self._rpc = rpc
        self.chain = rpc.chain
        self.provider_id = provider_id or f"gas_{rpc.chain}"

    async def suggest_gas(self) -> Dict[str, Any]:
        base = await self._rpc.eth_get_gas_price()
        prio = await self._rpc.eth_max_priority_fee_per_gas()
        try:
            fh = await self._rpc.eth_get_fee_history(5, "latest", [20, 50, 80])
            base_fees = fh.get("baseFeePerGas") or []
            base_history = [int(x, 16) for x in base_fees if x]
        except Exception:                                            # noqa
            base_history = []
        # Percentile median from fee history if available
        median_prio = prio
        if fh_rewards := (fh.get("reward") if isinstance(
                locals().get("fh"), dict) else None):
            try:
                p50 = [int(row[1], 16) for row in fh_rewards
                        if row and row[1]]
                if p50:
                    median_prio = sum(p50) // len(p50)
            except Exception:                                        # noqa
                pass
        return {
            "provider_id": self.provider_id, "chain": self.chain,
            "base_fee_wei": base,
            "priority_fee_wei": prio,
            "median_priority_fee_wei": median_prio,
            "base_fee_gwei": round(base / 1e9, 4),
            "priority_fee_gwei": (round(prio / 1e9, 4)
                                    if prio is not None else None),
            "base_fee_history_wei": base_history,
        }

    async def health_probe(self) -> Dict[str, Any]:
        try:
            g = await self.suggest_gas()
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True, "base_fee_gwei": g.get("base_fee_gwei")}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


# =============================================================================
# Token metadata — bundled well-known tokens (offline; deterministic)
# =============================================================================
class StaticTokenMetadataProvider:
    """A curated, bundled registry of well-known token metadata.

    Zero network dependency. Suitable for cross-referencing addresses to
    canonical symbols during quote enrichment. A follow-up slice can add
    on-chain ``symbol()`` / ``decimals()`` lookups for unknown tokens.
    """

    kind = ProviderKind.TOKEN_METADATA
    provider_id = "metadata_static_v1"

    _TOKENS: Dict[str, Dict[str, Any]] = {
        # ethereum
        ("ethereum", "weth"): {"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2", "symbol": "WETH", "name": "Wrapped Ether", "decimals": 18, "verified": True},
        ("ethereum", "wbtc"): {"address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", "symbol": "WBTC", "name": "Wrapped BTC", "decimals":  8, "verified": True},
        ("ethereum", "usdc"): {"address": "0xa0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48", "symbol": "USDC", "name": "USD Coin",    "decimals":  6, "verified": True},
        ("ethereum", "usdt"): {"address": "0xdAC17F958D2ee523a2206206994597C13D831ec7", "symbol": "USDT", "name": "Tether USD",  "decimals":  6, "verified": True},
        ("ethereum", "dai"):  {"address": "0x6B175474E89094C44Da98b954EedeAC495271d0F", "symbol": "DAI",  "name": "Dai",         "decimals": 18, "verified": True},
        # arbitrum
        ("arbitrum", "weth"): {"address": "0x82aF49447D8a07e3bd95BD0d56f35241523fBab1", "symbol": "WETH", "decimals": 18, "verified": True},
        ("arbitrum", "usdc"): {"address": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "symbol": "USDC", "decimals":  6, "verified": True},
        ("arbitrum", "arb"):  {"address": "0x912CE59144191C1204E64559FE8253a0e49E6548", "symbol": "ARB",  "decimals": 18, "verified": True},
        # base
        ("base", "weth"): {"address": "0x4200000000000000000000000000000000000006", "symbol": "WETH", "decimals": 18, "verified": True},
        ("base", "usdc"): {"address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", "symbol": "USDC", "decimals":  6, "verified": True},
        # polygon
        ("polygon", "wmatic"): {"address": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270", "symbol": "WMATIC", "decimals": 18, "verified": True},
        ("polygon", "usdc"):   {"address": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359", "symbol": "USDC",   "decimals":  6, "verified": True},
        # optimism
        ("optimism", "weth"): {"address": "0x4200000000000000000000000000000000000006", "symbol": "WETH", "decimals": 18, "verified": True},
        ("optimism", "op"):   {"address": "0x4200000000000000000000000000000000000042", "symbol": "OP",   "decimals": 18, "verified": True},
        # bnb
        ("bnb", "wbnb"): {"address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", "symbol": "WBNB", "decimals": 18, "verified": True},
        ("bnb", "busd"): {"address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56", "symbol": "BUSD", "decimals": 18, "verified": True},
        # solana
        ("solana", "sol"):  {"address": "So11111111111111111111111111111111111111112", "symbol": "SOL",  "decimals": 9, "verified": True},
        ("solana", "usdc"): {"address": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", "symbol": "USDC", "decimals": 6, "verified": True},
    }

    def _by_addr(self) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        for (chain, sym), row in self._TOKENS.items():
            key = f"{chain}:{row['address'].lower()}"
            row_copy = {**row, "chain": chain, "symbol": row.get(
                "symbol") or sym.upper()}
            out[key] = row_copy
        return out

    async def get_token(self, chain: str,
                         address: str) -> Optional[Dict[str, Any]]:
        return self._by_addr().get(f"{chain}:{address.strip().lower()}")

    async def health_probe(self) -> Dict[str, Any]:
        return {"provider_id": self.provider_id,
                 "backend": "static", "ok": True,
                 "tokens_available": len(self._TOKENS)}


__all__ = [
    "OneInchQuoter", "ZeroExQuoter",
    "RpcDerivedGasProvider",
    "StaticTokenMetadataProvider",
]
