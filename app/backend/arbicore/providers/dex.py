"""DEX read-only providers (Stage 2 · v2.5.0).

Two families:

  * **On-chain quoter** — the Uniswap-V3-style ``QuoterV2.quoteExactInputSingle``
    view function. Sushi V3, Pancake V3, and Uniswap V3 (mainnet / Arb / Base)
    all share identical calldata. We encode the args with ``eth_abi`` and
    do a single ``eth_call`` via the RPC provider.
  * **V2 router** — ``getAmountsOut(uint256, address[])`` on the classic
    Uniswap-V2 router (also used by Sushi V2 and Pancake V2).
  * **Solana** — Jupiter uses a REST quote endpoint; Raydium is a
    health-only stub (proper AMM decoding is a follow-up).
  * **Curve** — ``get_dy(int128,int128,uint256)`` on the pool contract.
  * **Balancer V2** — Vault ``queryBatchSwap`` (view — no state change).

Every provider satisfies ``DEXProvider`` (see ``providers/base.py``).
None of them broadcast a transaction. Every call is view-only.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from eth_abi import decode as _abi_decode
from eth_abi import encode as _abi_encode
from eth_utils import keccak

from .base import ProviderError, ProviderKind
from .rpc import EthJsonRpcProvider, SolanaRpcProvider

logger = logging.getLogger(__name__)


def _fnsig(sig: str) -> str:
    return "0x" + keccak(text=sig).hex()[:8]


# =============================================================================
# Uniswap V3 (and family) — QuoterV2
# =============================================================================
class UniswapV3Quoter:
    """QuoterV2.quoteExactInputSingle(struct) -> (uint256 amountOut, ...)

    Same calldata / same address across Uniswap V3 on mainnet / Arb /
    Optimism / Polygon / BNB. Family variant addresses are held in
    ``QUOTER_ADDRESSES``.
    """

    kind = ProviderKind.DEX
    dex_family = "uniswap_v3"

    # QuoterV2 on multiple chains.
    QUOTER_ADDRESSES: Dict[str, str] = {
        "ethereum": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
        "arbitrum": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
        "base":     "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a",
        "optimism": "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
        "polygon":  "0x61fFE014bA17989E743c5F6cB21bF9697530B21e",
        "bnb":      "0x78D78E420Da98ad378D7799bE8f4AF69033EB077",
    }

    # quoteExactInputSingle(( address, address, uint256, uint24, uint160 ))
    _SIG = _fnsig("quoteExactInputSingle((address,address,uint256,uint24,uint160))")

    def __init__(self, *, chain: str, rpc: EthJsonRpcProvider,
                 provider_id: Optional[str] = None) -> None:
        self.chain = chain
        self._rpc = rpc
        self.provider_id = provider_id or f"dex_uniswap_v3_{chain}"
        addr = self.QUOTER_ADDRESSES.get(chain)
        if not addr:
            raise ProviderError(
                f"UniswapV3Quoter has no address for chain={chain}",
                retryable=False, provider_id=self.provider_id)
        self._to = addr

    async def get_quote(self, token_in: str, token_out: str,
                         amount_in: int, fee_tier: int = 3000,
                         ) -> Dict[str, Any]:
        # struct fields
        args = _abi_encode(
            ["(address,address,uint256,uint24,uint160)"],
            [(_addr(token_in), _addr(token_out), int(amount_in),
              int(fee_tier), 0)],
        )
        calldata = self._SIG + args.hex()
        raw = await self._rpc.eth_call({"to": self._to, "data": calldata})
        # returns (uint256 amountOut, uint160 sqrtPriceX96After, uint32 initializedTicksCrossed, uint256 gasEstimate)
        amount_out, sqrt_after, ticks, gas_est = _abi_decode(
            ["uint256", "uint160", "uint32", "uint256"], bytes.fromhex(raw[2:]))
        return {
            "family": self.dex_family, "chain": self.chain,
            "token_in": token_in, "token_out": token_out,
            "amount_in": amount_in, "amount_out": int(amount_out),
            "fee_tier_bps": fee_tier // 100, "gas_estimate": int(gas_est),
            "sqrt_price_x96_after": int(sqrt_after),
            "ticks_crossed": int(ticks),
        }

    async def get_pool(self, token_in: str, token_out: str,
                        fee_tier: Optional[int] = None
                        ) -> Optional[Dict[str, Any]]:
        # V3 pool lookup requires the factory; providing a lightweight
        # placeholder for the DEXProvider protocol contract.
        return {"family": self.dex_family, "chain": self.chain,
                 "token_in": token_in, "token_out": token_out,
                 "fee_tier": fee_tier or 3000, "note": "resolved on quote"}

    async def health_probe(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            _ = await self._rpc.eth_get_block_number()
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True,
                     "latency_ms": round((time.time() - t0) * 1000, 2)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


# =============================================================================
# Uniswap V2 (also Sushi V2, Pancake V2) — Router.getAmountsOut
# =============================================================================
class UniswapV2Router:
    """Router.getAmountsOut(amountIn, path) view."""

    kind = ProviderKind.DEX

    _SIG = _fnsig("getAmountsOut(uint256,address[])")

    # (chain, family) -> router address
    _ROUTERS: Dict[str, str] = {
        "uniswap_v2:ethereum":  "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        "sushiswap:ethereum":   "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
        "sushiswap:arbitrum":   "0x1b02dA8Cb0d097eB8D57A175b88c7D8b47997506",
        "pancakeswap:bnb":      "0x10ED43C718714eb63d5aA57B78B54704E256024E",
    }

    def __init__(self, *, family: str, chain: str,
                 rpc: EthJsonRpcProvider,
                 provider_id: Optional[str] = None) -> None:
        self.dex_family = family
        self.chain = chain
        self._rpc = rpc
        self.provider_id = provider_id or f"dex_{family}_{chain}"
        addr = self._ROUTERS.get(f"{family}:{chain}")
        if not addr:
            raise ProviderError(
                f"{family} v2 router unknown for chain={chain}",
                retryable=False, provider_id=self.provider_id)
        self._to = addr

    async def get_pool(self, token_in: str, token_out: str,
                        fee_tier: Optional[int] = None
                        ) -> Optional[Dict[str, Any]]:
        return {"family": self.dex_family, "chain": self.chain,
                 "token_in": token_in, "token_out": token_out}

    async def get_quote(self, token_in: str, token_out: str,
                         amount_in: int, **_ignore) -> Dict[str, Any]:
        path = [_addr(token_in), _addr(token_out)]
        args = _abi_encode(["uint256", "address[]"], [int(amount_in), path])
        raw = await self._rpc.eth_call(
            {"to": self._to, "data": self._SIG + args.hex()})
        (amounts,) = _abi_decode(["uint256[]"], bytes.fromhex(raw[2:]))
        amount_out = int(amounts[-1]) if amounts else 0
        return {
            "family": self.dex_family, "chain": self.chain,
            "token_in": token_in, "token_out": token_out,
            "amount_in": amount_in, "amount_out": amount_out,
            "path": path, "fee_tier_bps": 30,
        }

    async def health_probe(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            _ = await self._rpc.eth_get_block_number()
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True,
                     "latency_ms": round((time.time() - t0) * 1000, 2)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


# =============================================================================
# Curve — pool.get_dy(int128, int128, uint256) view
# =============================================================================
class CurvePool:
    """One instance per pool. Requires the pool's canonical address."""

    kind = ProviderKind.DEX
    dex_family = "curve"

    _SIG = _fnsig("get_dy(int128,int128,uint256)")

    def __init__(self, *, chain: str, pool_address: str,
                 rpc: EthJsonRpcProvider,
                 provider_id: Optional[str] = None) -> None:
        self.chain = chain
        self._rpc = rpc
        self._to = pool_address
        self.provider_id = provider_id or f"dex_curve_{chain}_{pool_address[-6:]}"

    async def get_pool(self, *_a, **_k):
        return {"family": self.dex_family, "chain": self.chain,
                 "pool": self._to}

    async def get_quote(self, token_in: str, token_out: str,
                         amount_in: int, *, i: int = 0, j: int = 1,
                         **_ignore) -> Dict[str, Any]:
        args = _abi_encode(["int128", "int128", "uint256"],
                            [int(i), int(j), int(amount_in)])
        raw = await self._rpc.eth_call(
            {"to": self._to, "data": self._SIG + args.hex()})
        (out,) = _abi_decode(["uint256"], bytes.fromhex(raw[2:]))
        return {"family": self.dex_family, "chain": self.chain,
                 "token_in": token_in, "token_out": token_out,
                 "amount_in": amount_in, "amount_out": int(out),
                 "pool": self._to, "i": i, "j": j}

    async def health_probe(self) -> Dict[str, Any]:
        try:
            _ = await self._rpc.eth_get_block_number()
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


# =============================================================================
# Balancer V2 — Vault (health-only in v2.5.0; queryBatchSwap follow-up)
# =============================================================================
class BalancerV2Vault:
    kind = ProviderKind.DEX
    dex_family = "balancer_v2"

    _VAULT_MAINNET = "0xBA12222222228d8Ba445958a75a0704d566BF2C8"

    def __init__(self, *, chain: str, rpc: EthJsonRpcProvider,
                 provider_id: Optional[str] = None) -> None:
        self.chain = chain
        self._rpc = rpc
        self.provider_id = provider_id or f"dex_balancer_v2_{chain}"

    async def get_pool(self, *_a, **_k):
        return {"family": self.dex_family, "chain": self.chain}

    async def get_quote(self, token_in: str, token_out: str,
                         amount_in: int, **_ignore) -> Dict[str, Any]:
        # queryBatchSwap requires the pool id — deferred to a follow-up
        # slice. Advertised here so the registry lists Balancer.
        raise ProviderError(
            "balancer_v2 queryBatchSwap needs pool_id + tokens — "
            "attach a full BalancerV2 quote adapter in a follow-up slice",
            retryable=False, provider_id=self.provider_id)

    async def health_probe(self) -> Dict[str, Any]:
        try:
            _ = await self._rpc.eth_get_block_number()
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True, "vault": self._VAULT_MAINNET}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


# =============================================================================
# Solana — Jupiter (REST) + Raydium (health-only)
# =============================================================================
class JupiterQuoter:
    """Jupiter Aggregator public REST — Solana quote API."""

    kind = ProviderKind.DEX
    dex_family = "jupiter"
    chain = "solana"
    BASE = "https://quote-api.jup.ag/v6"

    def __init__(self, provider_id: str = "dex_jupiter_solana",
                 timeout: float = 8.0) -> None:
        self.provider_id = provider_id
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE, timeout=self._timeout,
                headers={"User-Agent": "arbicore-x/2.5.0 (+jupiter)"})
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_pool(self, *_a, **_k):
        return {"family": self.dex_family, "chain": self.chain}

    async def get_quote(self, token_in: str, token_out: str,
                         amount_in: int, slippage_bps: int = 50,
                         **_ignore) -> Dict[str, Any]:
        client = await self._http()
        try:
            r = await client.get("/quote", params={
                "inputMint": token_in, "outputMint": token_out,
                "amount": int(amount_in), "slippageBps": int(slippage_bps),
                "onlyDirectRoutes": "false",
            })
            r.raise_for_status()
            body = r.json()
        except httpx.HTTPError as e:
            raise ProviderError(f"jupiter /quote: {e}",
                                 retryable=True,
                                 provider_id=self.provider_id) from e
        return {
            "family": self.dex_family, "chain": self.chain,
            "token_in": token_in, "token_out": token_out,
            "amount_in": amount_in,
            "amount_out": int(body.get("outAmount", 0) or 0),
            "route_hops": len(body.get("routePlan") or []),
            "price_impact_pct": float(body.get("priceImpactPct") or 0.0),
            "raw": {k: body[k] for k in
                     ("otherAmountThreshold", "slippageBps") if k in body},
        }

    async def health_probe(self) -> Dict[str, Any]:
        # 1 USDC (6 decimals) → SOL as a canary
        USDC = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
        SOL = "So11111111111111111111111111111111111111112"
        t0 = time.time()
        try:
            q = await self.get_quote(USDC, SOL, 1_000_000)
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": True, "sample_out": q.get("amount_out"),
                     "latency_ms": round((time.time() - t0) * 1000, 2)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "chain": self.chain,
                     "ok": False, "error": str(e)[:200]}


class RaydiumHealth:
    """Health-only Raydium scaffold — pool state decoding is a follow-up."""

    kind = ProviderKind.DEX
    dex_family = "raydium"
    chain = "solana"

    def __init__(self, *, rpc: SolanaRpcProvider,
                 provider_id: str = "dex_raydium_solana") -> None:
        self._rpc = rpc
        self.provider_id = provider_id

    async def get_pool(self, *_a, **_k):
        return {"family": self.dex_family, "chain": self.chain,
                 "note": "pool decoding pending"}

    async def get_quote(self, *_a, **_k) -> Dict[str, Any]:
        raise ProviderError(
            "raydium pool quote requires on-chain AMM state decoding — "
            "attach a full raydium quoter in a follow-up slice",
            retryable=False, provider_id=self.provider_id)

    async def health_probe(self) -> Dict[str, Any]:
        return await self._rpc.health_probe()


def _addr(a: str) -> str:
    # eth_abi wants checksummed or lower-case 0x-prefixed hex; normalise
    a = a.strip()
    if not a.startswith("0x"):
        a = "0x" + a
    return a.lower()


__all__ = [
    "UniswapV3Quoter", "UniswapV2Router", "CurvePool",
    "BalancerV2Vault", "JupiterQuoter", "RaydiumHealth",
]
