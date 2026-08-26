"""Phase-2 hardening · Per-chain native-token price oracle (fail-closed).

Answers ONE question for the economics/gas layer: "What is the current USD price
of this chain's NATIVE gas token (ETH / POL / BNB), and is it TRUSTWORTHY?"

Rules (never violated):
  * primary → secondary source strategy; first positive price wins.
  * a short TTL cache smooths transient source outages.
  * if all sources fail, a cached price is served ONLY while within
    ``max_stale_s`` and is explicitly marked ``stale=True``.
  * beyond ``max_stale_s`` (or with no cache) the oracle FAILS CLOSED:
    ``ok=False, price_usd=None`` — it NEVER returns 0 and NEVER fabricates.
  * a non-positive / NaN price from a source is rejected, not trusted.

Sources are injectable async callables ``(symbol) -> Optional[float]`` so the
oracle is fully unit-testable offline. Concrete CoinGecko / Binance sources are
provided for live use (VPS / sandbox).
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional

# chain -> (native symbol, coingecko id, binance ticker)
CHAIN_NATIVE: Dict[str, Dict[str, str]] = {
    "ethereum": {"symbol": "ETH", "coingecko": "ethereum", "binance": "ETHUSDT"},
    "arbitrum": {"symbol": "ETH", "coingecko": "ethereum", "binance": "ETHUSDT"},
    "optimism": {"symbol": "ETH", "coingecko": "ethereum", "binance": "ETHUSDT"},
    "base": {"symbol": "ETH", "coingecko": "ethereum", "binance": "ETHUSDT"},
    "polygon": {"symbol": "POL", "coingecko": "matic-network", "binance": "POLUSDT"},
    "bnb": {"symbol": "BNB", "coingecko": "binancecoin", "binance": "BNBUSDT"},
}

PriceSource = Callable[[str], Awaitable[Optional[float]]]


def _valid(price: Optional[float]) -> Optional[float]:
    if price is None:
        return None
    try:
        p = float(price)
    except (TypeError, ValueError):
        return None
    if p <= 0 or math.isnan(p) or math.isinf(p):
        return None  # non-positive / NaN ⇒ rejected, never trusted
    return p


@dataclass
class NativePriceResult:
    chain: str
    symbol: str
    price_usd: Optional[float]
    ok: bool
    stale: bool = False
    age_s: Optional[float] = None
    source: Optional[str] = None
    reason: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {"chain": self.chain, "symbol": self.symbol,
                "price_usd": self.price_usd, "ok": self.ok, "stale": self.stale,
                "age_s": self.age_s, "source": self.source, "reason": self.reason}


@dataclass
class _CacheEntry:
    price: float
    ts: float
    source: str


class NativePriceOracle:
    def __init__(self, sources: Optional[List[tuple[str, PriceSource]]] = None,
                 *, ttl_s: float = 60.0, max_stale_s: float = 300.0,
                 clock: Callable[[], float] = time.time) -> None:
        self._sources = sources or []
        self._ttl_s = ttl_s
        self._max_stale_s = max_stale_s
        self._clock = clock
        self._cache: Dict[str, _CacheEntry] = {}

    async def get_native_usd(self, chain: str) -> NativePriceResult:
        c = (chain or "").lower()
        meta = CHAIN_NATIVE.get(c)
        if not meta:
            return NativePriceResult(c, "?", None, ok=False,
                                     reason="unsupported_chain")
        symbol = meta["symbol"]
        now = self._clock()

        # Fresh cache short-circuit.
        cached = self._cache.get(symbol)
        if cached and (now - cached.ts) <= self._ttl_s:
            return NativePriceResult(c, symbol, cached.price, ok=True,
                                     stale=False, age_s=now - cached.ts,
                                     source=f"{cached.source}:cache",
                                     reason="fresh_cache")

        # Try live sources in order.
        for name, src in self._sources:
            try:
                price = _valid(await src(symbol))
            except Exception:  # noqa: BLE001 — source failure ⇒ try next
                price = None
            if price is not None:
                self._cache[symbol] = _CacheEntry(price, now, name)
                return NativePriceResult(c, symbol, price, ok=True, stale=False,
                                         age_s=0.0, source=name, reason="live")

        # All sources failed — serve stale cache within the stale window only.
        if cached is not None:
            age = now - cached.ts
            if age <= self._max_stale_s:
                return NativePriceResult(c, symbol, cached.price, ok=True,
                                         stale=True, age_s=age,
                                         source=f"{cached.source}:stale",
                                         reason="stale_cache_within_window")
            return NativePriceResult(c, symbol, None, ok=False, stale=True,
                                     age_s=age, reason="cache_expired_fail_closed")
        return NativePriceResult(c, symbol, None, ok=False,
                                 reason="no_source_no_cache_fail_closed")


# --------------------------------------------------------------------------
# Concrete live sources (read-only HTTP; used on VPS / sandbox).
# --------------------------------------------------------------------------
def coingecko_source(timeout: float = 10.0) -> tuple[str, PriceSource]:
    async def _fetch(symbol: str) -> Optional[float]:
        cg = next((m["coingecko"] for m in CHAIN_NATIVE.values()
                   if m["symbol"] == symbol), None)
        if not cg:
            return None
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get("https://api.coingecko.com/api/v3/simple/price",
                            params={"ids": cg, "vs_currencies": "usd"})
            return float(r.json()[cg]["usd"])
    return ("coingecko", _fetch)


def binance_source(timeout: float = 10.0) -> tuple[str, PriceSource]:
    async def _fetch(symbol: str) -> Optional[float]:
        tkr = next((m["binance"] for m in CHAIN_NATIVE.values()
                    if m["symbol"] == symbol), None)
        if not tkr:
            return None
        import httpx
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.get("https://api.binance.com/api/v3/ticker/price",
                            params={"symbol": tkr})
            return float(r.json()["price"])
    return ("binance", _fetch)


def default_live_oracle() -> NativePriceOracle:
    """CoinGecko primary, Binance secondary — for live validation."""
    return NativePriceOracle([coingecko_source(), binance_source()])


__all__ = [
    "NativePriceOracle", "NativePriceResult", "CHAIN_NATIVE",
    "coingecko_source", "binance_source", "default_live_oracle",
]
