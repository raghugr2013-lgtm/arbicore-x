"""M2.5 · Multi-token USD price feed (on-chain, fail-closed, provenance-tagged).

Prices the real Base route tokens for Gate 8 using GENUINE on-chain quotes via
the existing :class:`QuoterRegistry` — never a fabricated or fallback price.

Valuation policy (operator-configured, NOT market data):
  * ``ARBICORE_USD_NUMERAIRE`` (default USDC) is the USD numéraire.
  * ``ARBICORE_STABLE_PEG_USD`` (default 1.0) is the numéraire's declared USD
    value. This is an explicit valuation anchor, not a price feed.

Every non-anchor token's USD price is derived from a real on-chain quote:
  * direct   T → USDC
  * two-hop  T → WETH → USDC
denominated in the numéraire. Configured stablecoins are peg-guarded: if the
measured on-chain price deviates from the peg beyond
``ARBICORE_STABLE_PEG_BAND_BPS`` the price is REJECTED (None → Gate 8 denies).

Freshness: a price is rejected (None) when its resolving block trails the chain
head by more than ``ARBICORE_PRICE_MAX_BLOCK_LAG`` blocks, or when head is
unverifiable while a head source is configured. A short TTL
(``ARBICORE_PRICE_TTL_S``) caches hits and (briefly) misses.

INVARIANTS: zero fabricated prices; any missing/stale/unverifiable/out-of-band
token price → None → Gate 8 fails closed. Full provenance is retained per token
for the evidence bundle.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

CHAIN = "base"


@dataclass
class PricePoint:
    token: str
    price_usd: Optional[float]
    source: str          # configured_numeraire | onchain_usdc_direct |
                          # onchain_usdc_via_weth | unavailable
    status: str          # ok | no_path | quote_failed | peg_out_of_band |
                          # stale | stale_unverifiable | not_evaluated
    path: List[str] = field(default_factory=list)
    pools: List[str] = field(default_factory=list)
    quoter: Optional[str] = None
    block: Optional[int] = None
    head_block: Optional[int] = None
    stale: bool = False
    ts: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OnChainUsdPriceFeed:
    """USDC-denominated, fail-closed multi-token USD price source.

    ``quote_route_fn(hops) -> {final_out_wei, block, quoter} | None`` wraps a
    real QuoterRegistry (returns None on any non-``ok`` route). ``pools`` is the
    canonical registry pool list (real UniV3 addresses used for routing).
    ``head_block_fn`` (optional) supplies the chain head for staleness checks.
    """

    def __init__(
        self, *,
        quote_route_fn: Callable[[List[Dict[str, Any]]], Awaitable[Optional[Dict[str, Any]]]],
        pools: List[Any],
        head_block_fn: Optional[Callable[[], Awaitable[Optional[int]]]] = None,
        numeraire: str = "USDC",
        stable_peg_usd: float = 1.0,
        stables: Tuple[str, ...] = ("USDC", "USDT", "DAI", "USDbC"),
        peg_band_bps: float = 200.0,
        ttl_s: float = 12.0,
        max_block_lag: int = 5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._quote_route_fn = quote_route_fn
        self._head_block_fn = head_block_fn
        self._numeraire = numeraire.upper()
        self._peg = float(stable_peg_usd)
        self._stables = {s.upper() for s in stables}
        self._band_bps = float(peg_band_bps)
        self._ttl = float(ttl_s)
        self._miss_ttl = min(float(ttl_s), 5.0)
        self._max_lag = int(max_block_lag)
        self._clock = clock
        self._addr, self._dec = self._token_maps(pools)
        self._pair_pool = self._pair_index(pools)   # frozenset({A,B}) -> spec
        self._cache: Dict[str, Tuple[float, PricePoint]] = {}
        self._prov: Dict[str, PricePoint] = {}
        self._head_cache: Tuple[float, Optional[int]] = (0.0, None)

    # ---- registry-derived routing metadata ----------------------------------
    @staticmethod
    def _token_maps(pools) -> Tuple[Dict[str, str], Dict[str, int]]:
        addr: Dict[str, str] = {}
        dec: Dict[str, int] = {}
        for p in pools:
            for sym, a, d in (
                (p.token0_symbol, p.token0_address, p.token0_decimals),
                (p.token1_symbol, p.token1_address, p.token1_decimals)):
                if sym and a:
                    addr.setdefault(sym.upper(), a)
                    dec.setdefault(sym.upper(), int(d))
        return addr, dec

    @staticmethod
    def _pair_index(pools) -> Dict[frozenset, Dict[str, Any]]:
        """Best (lowest-fee) REAL UniV3 pool per unordered token pair. Only
        deterministic-verified UniV3 pools (real address + QuoterV2) are used
        for pricing; runtime_getpool / Aerodrome pools are excluded until
        resolved on the VPS (fail-closed, never fabricated)."""
        from ..discovery import base_pool_registry as reg
        out: Dict[frozenset, Dict[str, Any]] = {}
        for p in pools:
            if p.dex != "uniswap_v3":
                continue
            if getattr(p, "address_resolution", None) != reg.DETERMINISTIC_VERIFIED:
                continue
            if not p.address or p.fee_bps is None:
                continue
            key = frozenset({p.token0_symbol.upper(), p.token1_symbol.upper()})
            spec = {"address": p.address, "fee_bps": int(p.fee_bps),
                    "dex": p.dex}
            cur = out.get(key)
            if cur is None or spec["fee_bps"] < cur["fee_bps"]:
                out[key] = spec
        return out

    # ---- head-block (staleness) ---------------------------------------------
    async def _head_block(self) -> Optional[int]:
        if self._head_block_fn is None:
            return None
        now = self._clock()
        exp, val = self._head_cache
        if now < exp:
            return val
        try:
            val = await self._head_block_fn()
        except Exception:  # noqa: BLE001
            val = None
        self._head_cache = (now + 2.0, val)
        return val

    # ---- one on-chain hop spec ----------------------------------------------
    def _hop(self, token_in_sym: str, token_out_sym: str,
             amount_in_wei: Optional[int]) -> Optional[Dict[str, Any]]:
        spec = self._pair_pool.get(
            frozenset({token_in_sym, token_out_sym}))
        if spec is None:
            return None
        h = {"dex": spec["dex"],
             "token_in": self._addr[token_in_sym],
             "token_out": self._addr[token_out_sym],
             "fee": int(spec["fee_bps"]) * 100,   # bps → ppm for UniV3 QuoterV2
             "_pool": spec["address"]}
        if amount_in_wei is not None:
            h["amount_in_wei"] = int(amount_in_wei)
        return h

    async def _quote_usdc(self, token: str) -> Optional[Dict[str, Any]]:
        """Return {out_usdc_wei, block, quoter, source, path, pools} or None."""
        num = self._numeraire
        unit = 10 ** self._dec[token]
        # direct T → USDC
        direct = self._hop(token, num, unit)
        if direct is not None:
            q = await self._quote_route_fn([direct])
            if q and q.get("final_out_wei"):
                return {"out": int(q["final_out_wei"]), "block": q.get("block"),
                        "quoter": q.get("quoter"),
                        "source": "onchain_usdc_direct",
                        "path": [token, num], "pools": [direct["_pool"]]}
            return None
        # two-hop T → WETH → USDC
        if token != "WETH":
            h1 = self._hop(token, "WETH", unit)
            h2 = self._hop("WETH", num, None)   # chained amount_in
            if h1 is not None and h2 is not None:
                q = await self._quote_route_fn([h1, h2])
                if q and q.get("final_out_wei"):
                    return {"out": int(q["final_out_wei"]),
                            "block": q.get("block"), "quoter": q.get("quoter"),
                            "source": "onchain_usdc_via_weth",
                            "path": [token, "WETH", num],
                            "pools": [h1["_pool"], h2["_pool"]]}
        return None

    def _record(self, pp: PricePoint) -> Optional[float]:
        ttl = self._ttl if pp.status == "ok" else self._miss_ttl
        self._cache[pp.token] = (self._clock() + ttl, pp)
        self._prov[pp.token] = pp
        return pp.price_usd

    # ---- public price source (matches make_base_price_fn's price_source) -----
    async def price_source(self, token: str) -> Optional[float]:
        sym = str(token).upper()
        now = self._clock()
        hit = self._cache.get(sym)
        if hit is not None and now < hit[0]:
            self._prov[sym] = hit[1]
            return hit[1].price_usd

        # numéraire → configured valuation anchor (not a market quote)
        if sym == self._numeraire:
            return self._record(PricePoint(
                token=sym, price_usd=self._peg, source="configured_numeraire",
                status="ok", path=[sym], ts=_now_iso()))

        if sym not in self._addr:
            return self._record(PricePoint(
                token=sym, price_usd=None, source="unavailable",
                status="no_path", ts=_now_iso()))

        try:
            res = await self._quote_usdc(sym)
        except Exception:  # noqa: BLE001 — never fabricate on error
            res = None
        if res is None:
            return self._record(PricePoint(
                token=sym, price_usd=None, source="unavailable",
                status="quote_failed", ts=_now_iso()))

        price = res["out"] / (10 ** self._dec[self._numeraire]) * self._peg
        pp = PricePoint(
            token=sym, price_usd=price, source=res["source"], status="ok",
            path=res["path"], pools=res["pools"], quoter=res.get("quoter"),
            block=res.get("block"), ts=_now_iso())

        # stablecoin peg guard (numéraire already short-circuited above)
        if sym in self._stables and price is not None:
            dev_bps = abs(price - self._peg) / self._peg * 10_000.0
            if dev_bps > self._band_bps:
                pp.price_usd = None
                pp.status = "peg_out_of_band"
                return self._record(pp)

        # freshness / staleness
        head = await self._head_block()
        pp.head_block = head
        if self._head_block_fn is not None:
            if head is None:
                pp.price_usd = None
                pp.status = "stale_unverifiable"
                pp.stale = True
                return self._record(pp)
            if pp.block is not None and (head - pp.block) > self._max_lag:
                pp.price_usd = None
                pp.status = "stale"
                pp.stale = True
                return self._record(pp)
        return self._record(pp)

    # ---- provenance for the evidence bundle ----------------------------------
    def provenance_for(self, tokens: List[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        seen = set()
        for t in tokens or []:
            sym = str(t).upper()
            if sym in seen:
                continue
            seen.add(sym)
            pp = self._prov.get(sym)
            out.append(pp.to_dict() if pp is not None else PricePoint(
                token=sym, price_usd=None, source="unavailable",
                status="not_evaluated", ts=_now_iso()).to_dict())
        return out


# ── env-driven builder (VPS); fail-closed to None ───────────────────────────
def _cfg_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "") or default)
    except (TypeError, ValueError):
        return default


def _cfg_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, "") or default)
    except (TypeError, ValueError):
        return default


def m2_5_enabled() -> bool:
    return bool((os.environ.get("ARBICORE_USD_NUMERAIRE") or "").strip())


def build_base_price_feed_from_env(quoter_registry=None):
    """Build the M2.5 :class:`OnChainUsdPriceFeed` from operator env, or None.

    Requires ``ARBICORE_USD_NUMERAIRE`` (M2.5 enable switch) and a Base RPC.
    Reuses the passed live ``QuoterRegistry`` (else constructs one that reads
    ``ARBICORE_RPC_URL``). Returns None → composition falls back to the
    native-only source (Gate 8 stays fail-closed)."""
    if not m2_5_enabled():
        return None
    from ..config.persistent import resolve_rpc_url_from_env
    url = resolve_rpc_url_from_env("base")
    if not url:
        return None
    if quoter_registry is None:
        from ..execution.quoter import QuoterRegistry
        quoter_registry = QuoterRegistry()
    from .runtime import _load_canonical_base_pools

    async def quote_route_fn(hops):
        rq = await quoter_registry.quote_route(chain=CHAIN, hops=hops)
        if getattr(rq, "status", None) != "ok":
            return None
        blocks = [h.block_number for h in rq.hops if h.block_number is not None]
        return {"final_out_wei": rq.final_amount_out_wei,
                "block": (min(blocks) if blocks else None),
                "quoter": (rq.hops[0].quoter_contract if rq.hops else None)}

    async def head_block_fn():
        from ..providers.rpc import EthJsonRpcProvider
        return await EthJsonRpcProvider(chain=CHAIN, url=url).eth_get_block_number()

    stables = tuple(s.strip().upper() for s in
                    (os.environ.get("ARBICORE_STABLES") or "USDC,USDT,DAI,USDbC").split(",")
                    if s.strip())
    return OnChainUsdPriceFeed(
        quote_route_fn=quote_route_fn,
        pools=_load_canonical_base_pools(),
        head_block_fn=head_block_fn,
        numeraire=(os.environ.get("ARBICORE_USD_NUMERAIRE") or "USDC"),
        stable_peg_usd=_cfg_float("ARBICORE_STABLE_PEG_USD", 1.0),
        stables=stables,
        peg_band_bps=_cfg_float("ARBICORE_STABLE_PEG_BAND_BPS", 200.0),
        ttl_s=_cfg_float("ARBICORE_PRICE_TTL_S", 12.0),
        max_block_lag=_cfg_int("ARBICORE_PRICE_MAX_BLOCK_LAG", 5),
    )


__all__ = ["OnChainUsdPriceFeed", "PricePoint",
           "build_base_price_feed_from_env", "m2_5_enabled"]
