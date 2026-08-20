"""ArbiCore X · Phase 10.10.8 — Live On-Chain Quoter.

Canonical production quoter for the profitability pipeline.  Every
autonomous discovery / certification / broadcast decision routes
through this module so ``economics.effective_out_wei`` reflects an
actual on-chain price and not a break-even placeholder.

Design principles
=================

* **Deterministic when live, transparent when not.**  Every quote
  carries provenance: the exact contract address queried, the block
  it resolved against, the RPC host, and the wall-clock timestamp.
  When any hop fails to quote we surface ``status='fallback:*'`` so
  the downstream policy engine can decide whether to WAIT or IGNORE.

* **Chain-safe eth_call.**  Uses the same read-only ``ARBICORE_RPC_URL``
  the broadcaster already validates; never touches a signer path.

* **Cache TTL.**  Public quoter contracts on Base cost ~$0 in trace-
  credits but they DO add latency (~150-300 ms per hop) — a 5 s TTL
  cache means a 60 s scanner tick with 40 candidates costs ~40 quote
  calls the first round then near-zero within-window repeats.

* **Zero break-even fallback in the happy path.**  Only when the RPC
  is genuinely unreachable or the DEX returns a revert do we degrade
  to the deterministic estimate — and even then the caller sees
  ``economics.quote_source == 'fallback:break_even'`` in every
  downstream report.

* **Adapter registry.**  Adding Curve, Camelot, or Solidly-fork DEXs
  is an additive act — new adapter class + one line in the registry.
  Never a rewrite of the profitability engine.

Supported DEXs (Phase 10.10.8)
------------------------------
* Uniswap V3 (all fee tiers) via QuoterV2
* Aerodrome SlipStream (concentrated-liquidity) via QuoterV2
* Aerodrome (volatile / stable classic AMM) via Router.getAmountsOut

Contract addresses (Base Mainnet, chain_id=8453)
------------------------------------------------
* Uniswap V3 QuoterV2         0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a
* Aerodrome SlipStream Quoter  0x254cF9E1E6e233aa1AC962CB9B05b2cfeAaE15b0
* Aerodrome Classic Router     0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43
"""
from __future__ import annotations

import logging
import os
import time
import asyncio
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple

import httpx
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import function_signature_to_4byte_selector, to_checksum_address

logger = logging.getLogger("arbicore.execution.quoter")


# --------------------------------------------------------------------------- #
# Contract catalog                                                            #
# --------------------------------------------------------------------------- #

# All addresses checksummed at import so downstream eth_call params are
# rejected early if a typo slips in.
BASE_UNIV3_QUOTER_V2       = to_checksum_address("0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a")
# Base Sepolia (chain_id 84532) — additive; used only by the operator
# opportunity probe. Does NOT affect mainnet 'base' economics.
BASE_SEPOLIA_UNIV3_QUOTER_V2 = to_checksum_address("0xC5290058841028F1614F3A6F0F5816cAd0df5E27")
BASE_AERO_SLIPSTREAM_QUOTER = to_checksum_address("0x254cF9E1E6e233aa1AC962CB9B05b2cfeAaE15b0")
BASE_AERO_CLASSIC_ROUTER    = to_checksum_address("0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43")


# Selector cache — computed once at import.
_SEL = {
    # Uniswap V3 QuoterV2.quoteExactInputSingle((tokenIn,tokenOut,amountIn,fee,sqrtPriceLimitX96))
    #   returns (amountOut, sqrtPriceX96After, initializedTicksCrossed, gasEstimate)
    "univ3_quoteExactInputSingle": "0x" + function_signature_to_4byte_selector(
        "quoteExactInputSingle((address,address,uint256,uint24,uint160))"
    ).hex(),
    # Aerodrome SlipStream QuoterV2 mirrors Uniswap V3 API — same selector but
    # the tuple takes a tickSpacing instead of fee.  Aerodrome V3 signature:
    #   quoteExactInputSingle((tokenIn,tokenOut,amountIn,tickSpacing,sqrtPriceLimitX96))
    "aeroSs_quoteExactInputSingle": "0x" + function_signature_to_4byte_selector(
        "quoteExactInputSingle((address,address,uint256,int24,uint160))"
    ).hex(),
    # Aerodrome classic Router.getAmountsOut(uint256, (address,address,bool,address)[])
    #   Route = (from, to, stable, factory)
    "aero_getAmountsOut": "0x" + function_signature_to_4byte_selector(
        "getAmountsOut(uint256,(address,address,bool,address)[])"
    ).hex(),
}


# --------------------------------------------------------------------------- #
# Data model                                                                  #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HopQuote:
    """Live quote for a single swap hop."""
    hop_index: int
    dex: str
    token_in: str
    token_out: str
    amount_in_wei: int
    amount_out_wei: int
    sqrt_price_x96_after: Optional[int]
    gas_estimate_units: Optional[int]
    price_impact_bps: Optional[int]
    quoter_contract: str
    rpc_host: str
    block_number: Optional[int]
    status: str                        # 'ok' | 'fallback:revert' | 'fallback:rpc_error' | 'fallback:no_adapter'
    error: Optional[str]
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # ``sqrt_price_x96_after`` is a uint160 that can exceed MongoDB's
        # int64 storage limit — stringify to keep receipts persistable.
        if isinstance(d.get("sqrt_price_x96_after"), int):
            d["sqrt_price_x96_after"] = str(d["sqrt_price_x96_after"])
        return d


@dataclass(frozen=True)
class RouteQuote:
    """Full-route quote assembled by chaining per-hop quotes."""
    chain: str
    hops: List[HopQuote]
    final_amount_out_wei: int
    aggregate_price_impact_bps: Optional[int]
    aggregate_gas_estimate_units: Optional[int]
    status: str                        # 'ok' | 'partial' | 'fallback:break_even'
    generated_at: str
    ttl_seconds: int

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["hops"] = [h.to_dict() if isinstance(h, HopQuote) else h for h in self.hops]
        return d

    @property
    def is_live(self) -> bool:
        return self.status == "ok"


# --------------------------------------------------------------------------- #
# Backend protocol + registry                                                 #
# --------------------------------------------------------------------------- #

class QuoterBackend(Protocol):
    dex: str

    async def quote_hop(
        self, *, hop_index: int, chain: str, token_in: str, token_out: str,
        amount_in_wei: int, hop_spec: Dict[str, Any], rpc_url: str,
    ) -> HopQuote: ...


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_host(url: Optional[str]) -> str:
    if not url:
        return "unknown"
    try:
        from urllib.parse import urlparse as _up
        return _up(url).hostname or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


# --------------------------------------------------------------------------- #
# JSON-RPC helper — used by every backend                                     #
# --------------------------------------------------------------------------- #

# Global client-side throttle + retry so the free public Base RPC does not
# trip `-32016 over rate limit`. Shared across all quoter backends.
_RPC_MIN_INTERVAL_S = float(os.environ.get("ARBICORE_RPC_MIN_INTERVAL_MS", "140")) / 1000.0
_RPC_MAX_RETRIES = int(os.environ.get("ARBICORE_RPC_MAX_RETRIES", "4"))
_RPC_LOCK = asyncio.Lock()
_RPC_LAST_TS = {"t": 0.0}


def _is_rate_limited(err: Optional[Dict[str, Any]]) -> bool:
    if not err:
        return False
    code = err.get("code")
    msg = str(err.get("message", "")).lower()
    return code == -32016 or "rate limit" in msg or "too many requests" in msg


async def _throttle() -> None:
    """Serialise RPC calls with a minimum inter-request interval."""
    async with _RPC_LOCK:
        now = asyncio.get_event_loop().time()
        wait = _RPC_MIN_INTERVAL_S - (now - _RPC_LAST_TS["t"])
        if wait > 0:
            await asyncio.sleep(wait)
        _RPC_LAST_TS["t"] = asyncio.get_event_loop().time()


async def _eth_call(
    rpc_url: str, *, to: str, data: str, block: str = "latest", timeout: float = 12.0,
    with_block_number: bool = True,
) -> Tuple[Optional[str], Optional[int], Optional[Dict[str, Any]]]:
    """One-shot read-only ``eth_call`` — returns (result_hex, block_number, error_dict).

    Applies a global throttle and retries on RPC rate-limit (-32016 / HTTP 429)
    with exponential backoff. ``block_number`` provenance is batched in the same
    request (no extra round-trip)."""
    if with_block_number:
        payload = [
            {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
             "params": [{"to": to, "data": data}, block]},
            {"jsonrpc": "2.0", "id": 2, "method": "eth_blockNumber", "params": []},
        ]
    else:
        payload = [{"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                    "params": [{"to": to, "data": data}, block]}]

    last_err: Optional[Dict[str, Any]] = None
    for attempt in range(_RPC_MAX_RETRIES + 1):
        await _throttle()
        try:
            async with httpx.AsyncClient(timeout=timeout) as c:
                r = await c.post(rpc_url, json=payload)
            if getattr(r, "status_code", 200) == 429:
                last_err = {"code": -32016, "message": "HTTP 429 rate limited"}
                await asyncio.sleep(0.3 * (2 ** attempt))
                continue
            r.raise_for_status()
            body = r.json()
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                last_err = {"code": -32016, "message": "HTTP 429 rate limited"}
                await asyncio.sleep(0.3 * (2 ** attempt))
                continue
            raise
        if not isinstance(body, list):
            body = [body]
        call_resp = next((b for b in body if b.get("id") == 1), None) or {}
        block_resp = next((b for b in body if b.get("id") == 2), None) or {}
        if "error" in call_resp:
            err = call_resp["error"]
            if _is_rate_limited(err) and attempt < _RPC_MAX_RETRIES:
                last_err = err
                await asyncio.sleep(0.3 * (2 ** attempt))
                continue
            return None, None, err
        bn_hex = (block_resp or {}).get("result")
        block_number = int(bn_hex, 16) if isinstance(bn_hex, str) and bn_hex.startswith("0x") else None
        return call_resp.get("result"), block_number, None
    return None, None, (last_err or {"code": -32016, "message": "rate limited (retries exhausted)"})


# --------------------------------------------------------------------------- #
# Uniswap V3 QuoterV2 backend                                                 #
# --------------------------------------------------------------------------- #

class UniV3QuoterV2:
    """Live quoter for Uniswap V3 pools on Base (all fee tiers)."""
    dex = "uniswap_v3"

    _CONTRACT_BY_CHAIN: Dict[str, str] = {
        "base": BASE_UNIV3_QUOTER_V2,
        "base-sepolia": BASE_SEPOLIA_UNIV3_QUOTER_V2,
    }

    async def quote_hop(
        self, *, hop_index: int, chain: str, token_in: str, token_out: str,
        amount_in_wei: int, hop_spec: Dict[str, Any], rpc_url: str,
    ) -> HopQuote:
        contract = self._CONTRACT_BY_CHAIN.get(chain)
        if not contract:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, "unknown", _redact_host(rpc_url),
                                  "fallback:no_adapter",
                                  f"no UniV3 QuoterV2 address for chain '{chain}'")
        # fee tier — accept either raw ppm (500, 3000, 10000) or bps (5, 30, 100)
        fee_raw = int(hop_spec.get("fee") or hop_spec.get("fee_tier_ppm")
                       or (int(hop_spec.get("fee_tier_bps") or 0) * 100))
        if fee_raw == 0:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:no_adapter", "fee tier missing / zero")
        # Encode tuple param: (tokenIn, tokenOut, amountIn, fee, sqrtPriceLimitX96)
        params_encoded = abi_encode(
            ["(address,address,uint256,uint24,uint160)"],
            [(to_checksum_address(token_in), to_checksum_address(token_out),
              int(amount_in_wei), int(fee_raw), 0)],
        )
        data = _SEL["univ3_quoteExactInputSingle"] + params_encoded.hex()

        try:
            result_hex, block_number, err = await _eth_call(rpc_url, to=contract, data=data)
        except Exception as exc:  # noqa: BLE001
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:rpc_error", f"{type(exc).__name__}: {exc}")
        if err:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:revert",
                                  f"code={err.get('code')} {err.get('message','')[:120]}")
        try:
            amount_out, sqrt_after, _ticks, gas_est = abi_decode(
                ["uint256", "uint160", "uint32", "uint256"],
                bytes.fromhex(result_hex[2:]),
            )
        except Exception as exc:  # noqa: BLE001
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:rpc_error", f"decode error: {exc}")
        # Price impact — informational only (needs pool state to be exact;
        # here we return None and let higher layers derive from quoted vs
        # spot if desired).
        return HopQuote(
            hop_index=hop_index, dex=self.dex,
            token_in=to_checksum_address(token_in),
            token_out=to_checksum_address(token_out),
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=int(amount_out),
            sqrt_price_x96_after=int(sqrt_after),
            gas_estimate_units=int(gas_est),
            price_impact_bps=None,
            quoter_contract=contract,
            rpc_host=_redact_host(rpc_url),
            block_number=block_number,
            status="ok", error=None, generated_at=_now_iso(),
        )


# --------------------------------------------------------------------------- #
# Aerodrome SlipStream backend (CL — same shape as UniV3 with tickSpacing)   #
# --------------------------------------------------------------------------- #

class AerodromeSlipStreamQuoter:
    dex = "aerodrome_slipstream"

    _CONTRACT_BY_CHAIN: Dict[str, str] = {
        "base": BASE_AERO_SLIPSTREAM_QUOTER,
    }

    async def quote_hop(
        self, *, hop_index: int, chain: str, token_in: str, token_out: str,
        amount_in_wei: int, hop_spec: Dict[str, Any], rpc_url: str,
    ) -> HopQuote:
        contract = self._CONTRACT_BY_CHAIN.get(chain)
        if not contract:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, "unknown", _redact_host(rpc_url),
                                  "fallback:no_adapter",
                                  f"no SlipStream quoter for chain '{chain}'")
        tick_spacing = int(hop_spec.get("tick_spacing") or hop_spec.get("tickSpacing") or 0)
        if tick_spacing == 0:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:no_adapter", "tick_spacing missing")
        params_encoded = abi_encode(
            ["(address,address,uint256,int24,uint160)"],
            [(to_checksum_address(token_in), to_checksum_address(token_out),
              int(amount_in_wei), int(tick_spacing), 0)],
        )
        data = _SEL["aeroSs_quoteExactInputSingle"] + params_encoded.hex()
        try:
            result_hex, block_number, err = await _eth_call(rpc_url, to=contract, data=data)
        except Exception as exc:  # noqa: BLE001
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:rpc_error", f"{type(exc).__name__}: {exc}")
        if err:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:revert",
                                  f"code={err.get('code')} {err.get('message','')[:120]}")
        try:
            amount_out, sqrt_after, _ticks, gas_est = abi_decode(
                ["uint256", "uint160", "uint32", "uint256"],
                bytes.fromhex(result_hex[2:]),
            )
        except Exception as exc:  # noqa: BLE001
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, contract, _redact_host(rpc_url),
                                  "fallback:rpc_error", f"decode error: {exc}")
        return HopQuote(
            hop_index=hop_index, dex=self.dex,
            token_in=to_checksum_address(token_in),
            token_out=to_checksum_address(token_out),
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=int(amount_out),
            sqrt_price_x96_after=int(sqrt_after),
            gas_estimate_units=int(gas_est),
            price_impact_bps=None,
            quoter_contract=contract,
            rpc_host=_redact_host(rpc_url),
            block_number=block_number,
            status="ok", error=None, generated_at=_now_iso(),
        )


# --------------------------------------------------------------------------- #
# Aerodrome classic AMM backend                                               #
# --------------------------------------------------------------------------- #

class AerodromeClassicQuoter:
    dex = "aerodrome"

    _ROUTER_BY_CHAIN: Dict[str, str] = {
        "base": BASE_AERO_CLASSIC_ROUTER,
    }
    # The default factory returned by the Router (needed by the Route tuple).
    _DEFAULT_FACTORY_BY_CHAIN: Dict[str, str] = {
        "base": to_checksum_address("0x420DD381b31aEf6683db6B902084cB0FFECe40Da"),
    }

    async def quote_hop(
        self, *, hop_index: int, chain: str, token_in: str, token_out: str,
        amount_in_wei: int, hop_spec: Dict[str, Any], rpc_url: str,
    ) -> HopQuote:
        router = self._ROUTER_BY_CHAIN.get(chain)
        factory = self._DEFAULT_FACTORY_BY_CHAIN.get(chain)
        if not router or not factory:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, "unknown", _redact_host(rpc_url),
                                  "fallback:no_adapter",
                                  f"no Aerodrome classic router for chain '{chain}'")
        # Volatile pool by default; hop_spec.stable=True selects the stable pool.
        is_stable = bool(hop_spec.get("stable") or False)
        route_tuple = (
            to_checksum_address(token_in),
            to_checksum_address(token_out),
            is_stable,
            factory,
        )
        params_encoded = abi_encode(
            ["uint256", "(address,address,bool,address)[]"],
            [int(amount_in_wei), [route_tuple]],
        )
        data = _SEL["aero_getAmountsOut"] + params_encoded.hex()
        try:
            result_hex, block_number, err = await _eth_call(rpc_url, to=router, data=data)
        except Exception as exc:  # noqa: BLE001
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, router, _redact_host(rpc_url),
                                  "fallback:rpc_error", f"{type(exc).__name__}: {exc}")
        if err:
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, router, _redact_host(rpc_url),
                                  "fallback:revert",
                                  f"code={err.get('code')} {err.get('message','')[:120]}")
        try:
            # returns uint256[]; index 0 is input, last is final output
            (amounts,) = abi_decode(["uint256[]"], bytes.fromhex(result_hex[2:]))
        except Exception as exc:  # noqa: BLE001
            return _fallback_hop(hop_index, self.dex, token_in, token_out,
                                  amount_in_wei, router, _redact_host(rpc_url),
                                  "fallback:rpc_error", f"decode error: {exc}")
        amount_out = int(amounts[-1]) if amounts else 0
        return HopQuote(
            hop_index=hop_index, dex=self.dex,
            token_in=to_checksum_address(token_in),
            token_out=to_checksum_address(token_out),
            amount_in_wei=int(amount_in_wei),
            amount_out_wei=amount_out,
            sqrt_price_x96_after=None,
            gas_estimate_units=None,
            price_impact_bps=None,
            quoter_contract=router,
            rpc_host=_redact_host(rpc_url),
            block_number=block_number,
            status="ok", error=None, generated_at=_now_iso(),
        )


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

def _fallback_hop(hop_index: int, dex: str, token_in: str, token_out: str,
                   amount_in_wei: int, contract: str, rpc_host: str,
                   status: str, error: str) -> HopQuote:
    return HopQuote(
        hop_index=hop_index, dex=dex,
        token_in=token_in, token_out=token_out,
        amount_in_wei=int(amount_in_wei), amount_out_wei=0,
        sqrt_price_x96_after=None, gas_estimate_units=None,
        price_impact_bps=None, quoter_contract=contract,
        rpc_host=rpc_host, block_number=None,
        status=status, error=error, generated_at=_now_iso(),
    )


# --------------------------------------------------------------------------- #
# QuoterRegistry — the object the rest of ArbiCore consumes                   #
# --------------------------------------------------------------------------- #

class QuoterRegistry:
    """Route quotes across heterogeneous DEXs with TTL caching.

    Any autonomous component (discovery, certification, auto-pilot,
    Manual Composer) obtains route quotes through this registry.  It
    is the single source of truth for live economics inputs.
    """

    def __init__(
        self, *,
        backends: Optional[List[QuoterBackend]] = None,
        cache_ttl_s: float = 5.0,
        rpc_url_env: str = "ARBICORE_RPC_URL",
    ):
        default_backends: List[QuoterBackend] = [
            UniV3QuoterV2(),
            AerodromeSlipStreamQuoter(),
            AerodromeClassicQuoter(),
        ]
        self._backends: Dict[str, QuoterBackend] = {
            b.dex: b for b in (backends or default_backends)
        }
        self._cache_ttl = float(cache_ttl_s)
        self._cache: Dict[Tuple, Tuple[float, HopQuote]] = {}
        self._rpc_url_env = rpc_url_env

    # ---- introspection --------------------------------------------------

    def supports(self, dex: str) -> bool:
        return dex in self._backends

    @property
    def supported_dexes(self) -> List[str]:
        return sorted(self._backends)

    def _rpc_url(self) -> Optional[str]:
        return os.environ.get(self._rpc_url_env)

    def _cache_key(self, chain: str, hop: Dict[str, Any]) -> Tuple:
        return (
            chain, (hop.get("dex") or "").lower(),
            (hop.get("token_in") or hop.get("tokenIn") or "").lower(),
            (hop.get("token_out") or hop.get("tokenOut") or "").lower(),
            int(hop.get("amount_in_wei") or hop.get("amountIn") or 0),
            int(hop.get("fee") or hop.get("fee_tier_ppm") or 0),
            int(hop.get("tick_spacing") or hop.get("tickSpacing") or 0),
            bool(hop.get("stable") or False),
        )

    # ---- primary entrypoint --------------------------------------------

    async def quote_route(
        self, *, chain: str, hops: List[Dict[str, Any]],
        rpc_url: Optional[str] = None,
    ) -> RouteQuote:
        """Chain-quote a route: each hop's ``amount_in_wei`` is derived
        from the previous hop's ``amount_out_wei`` (with the first hop
        taking ``amount_in_wei`` from the caller).

        A hop can override this pipe by supplying an explicit
        ``amount_in_wei`` — used by the Manual Composer.

        Returns a :class:`RouteQuote` whose ``final_amount_out_wei`` is
        the last quoted hop's output.  Status is:

        * ``ok``      — every hop returned a live quote
        * ``partial`` — at least one hop degraded to fallback but the
                        overall chain still produced a numeric answer
                        (fallback hops passthrough amountIn as amountOut)
        * ``fallback:break_even`` — the route could not be quoted at all
        """
        rpc = rpc_url or self._rpc_url()
        results: List[HopQuote] = []
        if not rpc:
            for i, h in enumerate(hops):
                results.append(_fallback_hop(
                    i, h.get("dex") or "?", h.get("token_in") or h.get("tokenIn") or "",
                    h.get("token_out") or h.get("tokenOut") or "",
                    int(h.get("amount_in_wei") or h.get("amountIn") or 0),
                    "n/a", "unknown", "fallback:rpc_error",
                    "ARBICORE_RPC_URL not configured",
                ))
            return RouteQuote(
                chain=chain, hops=results,
                final_amount_out_wei=0,
                aggregate_price_impact_bps=None,
                aggregate_gas_estimate_units=None,
                status="fallback:break_even",
                generated_at=_now_iso(), ttl_seconds=int(self._cache_ttl),
            )

        current_amount_in = None
        aggregate_gas: Optional[int] = 0
        any_fallback = False

        for i, h in enumerate(hops):
            dex = (h.get("dex") or "").lower()
            token_in  = h.get("token_in")  or h.get("tokenIn")
            token_out = h.get("token_out") or h.get("tokenOut")
            explicit_in = h.get("amount_in_wei") or h.get("amountIn")
            amount_in = int(current_amount_in if current_amount_in is not None
                             else (explicit_in or 0))
            backend = self._backends.get(dex)
            if backend is None:
                q = _fallback_hop(i, dex or "?", token_in or "", token_out or "",
                                   amount_in, "n/a", _redact_host(rpc),
                                   "fallback:no_adapter",
                                   f"no adapter registered for dex='{dex}'")
                results.append(q); any_fallback = True
                current_amount_in = amount_in
                continue

            # Cache lookup
            key = self._cache_key(chain, {**h, "amount_in_wei": amount_in})
            cached = self._cache.get(key)
            now = time.time()
            if cached and (now - cached[0]) < self._cache_ttl:
                q = cached[1]
            else:
                q = await backend.quote_hop(
                    hop_index=i, chain=chain,
                    token_in=token_in, token_out=token_out,
                    amount_in_wei=amount_in,
                    hop_spec=h, rpc_url=rpc,
                )
                self._cache[key] = (now, q)

            results.append(q)
            if q.status == "ok":
                current_amount_in = q.amount_out_wei
                if aggregate_gas is not None and q.gas_estimate_units is not None:
                    aggregate_gas += q.gas_estimate_units
                else:
                    aggregate_gas = None
            else:
                any_fallback = True
                # passthrough so the chain doesn't terminate; downstream
                # policy sees the fallback marker and can WAIT/IGNORE.
                current_amount_in = amount_in

        final_amount_out = int(current_amount_in or 0)
        if all(q.status.startswith("fallback:") for q in results):
            status = "fallback:break_even"
        elif any_fallback:
            status = "partial"
        else:
            status = "ok"

        return RouteQuote(
            chain=chain, hops=results,
            final_amount_out_wei=final_amount_out,
            aggregate_price_impact_bps=None,
            aggregate_gas_estimate_units=aggregate_gas,
            status=status,
            generated_at=_now_iso(),
            ttl_seconds=int(self._cache_ttl),
        )

    # ---- convenience: quote from a plan-dict ---------------------------

    async def quote_plan(
        self, plan: Dict[str, Any], *, rpc_url: Optional[str] = None,
    ) -> RouteQuote:
        """Extract the swap hops from a plan doc and route-quote them."""
        chain = plan.get("chain") or "base"
        steps = plan.get("steps") or []
        hops: List[Dict[str, Any]] = []
        for i, s in enumerate(steps):
            if (s or {}).get("kind") != "swap":
                continue
            args = (s or {}).get("args") or []
            if not args or not isinstance(args[0], dict):
                continue
            p = args[0]
            hops.append({
                "dex": (s.get("provider") or s.get("dex") or "").lower(),
                "token_in":  p.get("tokenIn")  or p.get("token_in"),
                "token_out": p.get("tokenOut") or p.get("token_out"),
                # first hop uses the plan's borrow amount; subsequent hops
                # get chained from prior output — quote_route handles both.
                "amount_in_wei": (int(p.get("amountIn") or p.get("amount_in_wei") or 0)
                                   if i == 0 or i == 1 else None),
                "fee": p.get("fee") or p.get("fee_tier_ppm"),
                "tick_spacing": p.get("tickSpacing") or p.get("tick_spacing"),
                "stable": p.get("stable"),
            })
        # First swap's amount-in: derive from borrow if not explicit
        if hops and not hops[0].get("amount_in_wei"):
            hops[0]["amount_in_wei"] = int(plan.get("borrow_amount_wei") or 0)
        return await self.quote_route(chain=chain, hops=hops, rpc_url=rpc_url)
