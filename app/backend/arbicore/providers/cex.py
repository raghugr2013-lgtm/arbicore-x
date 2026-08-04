"""Phase 5 — Live CEX ticker providers (Stage 2 · v2.5.0).

Six real read-only clients for the public REST endpoints of Binance,
Bybit, OKX, Coinbase, Kraken and KuCoin. No auth. No trading endpoints.

Each provider satisfies the same shape:

    class SomeCEXProvider:
        provider_id: str
        kind: ProviderKind = ProviderKind.QUOTE_AGGREGATOR
        chain: str = "cex"
        venue: str          # 'binance', 'bybit', ...

        async def get_ticker(self, symbol: str) -> Dict[str, Any]
        async def get_orderbook(self, symbol: str, depth: int = 10) -> Dict
        async def health_probe(self) -> Dict[str, Any]

The registry treats them as ``QUOTE_AGGREGATOR`` for ranking purposes
(they aggregate a whole market's price into one bid/ask spread).

``symbol`` is the design-system-internal canonical pair, e.g.
``"BTC/USDT"``. Each provider maps this to its venue-specific symbol
convention internally.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import httpx

from .base import ProviderError, ProviderKind

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 6.0


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


class _CEXBase:
    """Shared HTTP + error-mapping surface."""

    kind = ProviderKind.QUOTE_AGGREGATOR
    chain = "cex"
    venue: str = "unknown"
    base_url: str = ""

    def __init__(self, provider_id: Optional[str] = None,
                 timeout: float = _DEFAULT_TIMEOUT) -> None:
        self.provider_id = provider_id or f"cex_{self.venue}_v1"
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url, timeout=self._timeout,
                headers={"User-Agent": "arbicore-x/2.5.0 (+live-market)"})
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _get(self, path: str,
                    params: Optional[Dict[str, Any]] = None) -> Any:
        client = await self._http()
        try:
            r = await client.get(path, params=params)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as e:
            raise ProviderError(
                f"{self.venue} {path} -> {e.response.status_code}",
                retryable=(e.response.status_code >= 500),
                provider_id=self.provider_id) from e
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.venue} {path} network: {e}",
                                retryable=True,
                                provider_id=self.provider_id) from e

    # subclasses override these three
    def _sym(self, canonical: str) -> str:                          # noqa
        raise NotImplementedError
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:      # noqa
        raise NotImplementedError
    async def get_orderbook(self, symbol: str,
                             depth: int = 10) -> Dict[str, Any]:    # noqa
        raise NotImplementedError

    # generic aggregator contract expected by the registry
    async def aggregate_quote(self, token_in: str, token_out: str,
                               amount_in: int) -> Dict[str, Any]:
        """CEX 'quote' = current mid-price snapshot for token_in/token_out."""
        canonical = f"{token_in.upper()}/{token_out.upper()}"
        t = await self.get_ticker(canonical)
        mid = (t["bid"] + t["ask"]) / 2 if t["bid"] and t["ask"] else t["last"]
        return {
            "venue": self.venue, "symbol": canonical,
            "mid": mid, "bid": t["bid"], "ask": t["ask"],
            "spread_bps": t["spread_bps"], "last": t["last"],
            "volume_24h_base": t.get("volume_24h_base"),
            "ts": t.get("ts"),
        }

    async def health_probe(self) -> Dict[str, Any]:
        t0 = time.time()
        try:
            await self.get_ticker("BTC/USDT")
            latency = (time.time() - t0) * 1000
            return {"provider_id": self.provider_id, "venue": self.venue,
                     "ok": True, "latency_ms": round(latency, 2)}
        except Exception as e:                                       # noqa
            return {"provider_id": self.provider_id, "venue": self.venue,
                     "ok": False, "error": str(e)[:200]}


# =============================================================================
# Binance   — https://api.binance.com/api/v3
# =============================================================================
class BinanceProvider(_CEXBase):
    venue = "binance"
    base_url = "https://api.binance.com"

    def _sym(self, canonical: str) -> str:
        return canonical.replace("/", "").upper()

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        s = self._sym(symbol)
        book = await self._get("/api/v3/ticker/bookTicker",
                                 params={"symbol": s})
        stat = await self._get("/api/v3/ticker/24hr",
                                 params={"symbol": s})
        bid = _to_float(book.get("bidPrice"))
        ask = _to_float(book.get("askPrice"))
        last = _to_float(stat.get("lastPrice") or (bid + ask) / 2)
        spread_bps = ((ask - bid) / ((ask + bid) / 2) * 10_000
                      if (ask and bid) else 0.0)
        return {"venue": self.venue, "symbol": symbol,
                "bid": bid, "ask": ask, "last": last,
                "spread_bps": round(spread_bps, 2),
                "volume_24h_base": _to_float(stat.get("volume")),
                "ts": stat.get("closeTime")}

    async def get_orderbook(self, symbol: str,
                             depth: int = 10) -> Dict[str, Any]:
        s = self._sym(symbol)
        d = await self._get("/api/v3/depth",
                              params={"symbol": s, "limit": depth})
        return {
            "venue": self.venue, "symbol": symbol,
            "bids": [[_to_float(p), _to_float(q)] for p, q in d.get("bids", [])],
            "asks": [[_to_float(p), _to_float(q)] for p, q in d.get("asks", [])],
        }


# =============================================================================
# Bybit  — https://api.bybit.com/v5
# =============================================================================
class BybitProvider(_CEXBase):
    venue = "bybit"
    base_url = "https://api.bybit.com"

    def _sym(self, canonical: str) -> str:
        return canonical.replace("/", "").upper()

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        s = self._sym(symbol)
        r = await self._get("/v5/market/tickers",
                             params={"category": "spot", "symbol": s})
        lst = (r.get("result", {}) or {}).get("list", [])
        row = lst[0] if lst else {}
        bid = _to_float(row.get("bid1Price"))
        ask = _to_float(row.get("ask1Price"))
        last = _to_float(row.get("lastPrice") or (bid + ask) / 2)
        spread_bps = ((ask - bid) / ((ask + bid) / 2) * 10_000
                      if (ask and bid) else 0.0)
        return {"venue": self.venue, "symbol": symbol,
                "bid": bid, "ask": ask, "last": last,
                "spread_bps": round(spread_bps, 2),
                "volume_24h_base": _to_float(row.get("volume24h")),
                "ts": None}

    async def get_orderbook(self, symbol: str,
                             depth: int = 10) -> Dict[str, Any]:
        s = self._sym(symbol)
        r = await self._get("/v5/market/orderbook",
                              params={"category": "spot", "symbol": s,
                                       "limit": depth})
        res = r.get("result", {}) or {}
        return {
            "venue": self.venue, "symbol": symbol,
            "bids": [[_to_float(p), _to_float(q)] for p, q in res.get("b", [])],
            "asks": [[_to_float(p), _to_float(q)] for p, q in res.get("a", [])],
        }


# =============================================================================
# OKX    — https://www.okx.com/api/v5
# =============================================================================
class OKXProvider(_CEXBase):
    venue = "okx"
    base_url = "https://www.okx.com"

    def _sym(self, canonical: str) -> str:
        # OKX uses BASE-QUOTE, and its quote for USDT stablecoin pairs is USDT
        return canonical.replace("/", "-").upper()

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        s = self._sym(symbol)
        r = await self._get("/api/v5/market/ticker", params={"instId": s})
        rows = r.get("data") or []
        row = rows[0] if rows else {}
        bid = _to_float(row.get("bidPx"))
        ask = _to_float(row.get("askPx"))
        last = _to_float(row.get("last") or (bid + ask) / 2)
        spread_bps = ((ask - bid) / ((ask + bid) / 2) * 10_000
                      if (ask and bid) else 0.0)
        return {"venue": self.venue, "symbol": symbol,
                "bid": bid, "ask": ask, "last": last,
                "spread_bps": round(spread_bps, 2),
                "volume_24h_base": _to_float(row.get("vol24h")),
                "ts": row.get("ts")}

    async def get_orderbook(self, symbol: str,
                             depth: int = 10) -> Dict[str, Any]:
        s = self._sym(symbol)
        r = await self._get("/api/v5/market/books",
                              params={"instId": s, "sz": depth})
        row = (r.get("data") or [{}])[0]
        def _rows(k: str):
            return [[_to_float(x[0]), _to_float(x[1])] for x in row.get(k, [])]
        return {"venue": self.venue, "symbol": symbol,
                "bids": _rows("bids"), "asks": _rows("asks")}


# =============================================================================
# Coinbase Exchange (advanced)  — https://api.exchange.coinbase.com
# =============================================================================
class CoinbaseProvider(_CEXBase):
    venue = "coinbase"
    base_url = "https://api.exchange.coinbase.com"

    def _sym(self, canonical: str) -> str:
        # Coinbase uses BASE-QUOTE. USDT quotes are limited; USD is canonical.
        b, q = canonical.split("/")
        if q == "USDT":
            q = "USD"
        return f"{b}-{q}".upper()

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        s = self._sym(symbol)
        t = await self._get(f"/products/{s}/ticker")
        stat = await self._get(f"/products/{s}/stats")
        bid = _to_float(t.get("bid"))
        ask = _to_float(t.get("ask"))
        last = _to_float(t.get("price") or (bid + ask) / 2)
        spread_bps = ((ask - bid) / ((ask + bid) / 2) * 10_000
                      if (ask and bid) else 0.0)
        return {"venue": self.venue, "symbol": symbol,
                "bid": bid, "ask": ask, "last": last,
                "spread_bps": round(spread_bps, 2),
                "volume_24h_base": _to_float(stat.get("volume")),
                "ts": t.get("time")}

    async def get_orderbook(self, symbol: str,
                             depth: int = 10) -> Dict[str, Any]:
        s = self._sym(symbol)
        # level=2 = aggregated top of book, up to 50 rows
        r = await self._get(f"/products/{s}/book", params={"level": 2})
        return {
            "venue": self.venue, "symbol": symbol,
            "bids": [[_to_float(p), _to_float(q)]
                      for p, q, *_ in (r.get("bids") or [])[:depth]],
            "asks": [[_to_float(p), _to_float(q)]
                      for p, q, *_ in (r.get("asks") or [])[:depth]],
        }


# =============================================================================
# Kraken — https://api.kraken.com/0/public
# =============================================================================
class KrakenProvider(_CEXBase):
    venue = "kraken"
    base_url = "https://api.kraken.com"

    # kraken normalises pairs to XBT for BTC; USDT quotes exist as XBTUSDT etc.
    _PAIR_OVERRIDES = {
        "BTC/USDT": "XBTUSDT",
        "BTC/USD": "XBTUSD",
        "ETH/USDT": "ETHUSDT",
        "ETH/USD": "ETHUSD",
    }

    def _sym(self, canonical: str) -> str:
        return self._PAIR_OVERRIDES.get(
            canonical.upper(), canonical.replace("/", "").upper())

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        s = self._sym(symbol)
        r = await self._get("/0/public/Ticker", params={"pair": s})
        result = r.get("result", {}) or {}
        if not result:
            raise ProviderError(f"kraken empty result for {symbol}",
                                 provider_id=self.provider_id)
        row = next(iter(result.values()))
        bid = _to_float((row.get("b") or [0])[0])
        ask = _to_float((row.get("a") or [0])[0])
        last = _to_float((row.get("c") or [0])[0] or (bid + ask) / 2)
        spread_bps = ((ask - bid) / ((ask + bid) / 2) * 10_000
                      if (ask and bid) else 0.0)
        vol = _to_float((row.get("v") or [0, 0])[1])   # 24h volume
        return {"venue": self.venue, "symbol": symbol,
                "bid": bid, "ask": ask, "last": last,
                "spread_bps": round(spread_bps, 2),
                "volume_24h_base": vol, "ts": None}

    async def get_orderbook(self, symbol: str,
                             depth: int = 10) -> Dict[str, Any]:
        s = self._sym(symbol)
        r = await self._get("/0/public/Depth",
                              params={"pair": s, "count": depth})
        result = r.get("result", {}) or {}
        if not result:
            return {"venue": self.venue, "symbol": symbol,
                    "bids": [], "asks": []}
        row = next(iter(result.values()))
        return {"venue": self.venue, "symbol": symbol,
                "bids": [[_to_float(p), _to_float(q)]
                          for p, q, *_ in row.get("bids", [])],
                "asks": [[_to_float(p), _to_float(q)]
                          for p, q, *_ in row.get("asks", [])]}


# =============================================================================
# KuCoin — https://api.kucoin.com/api/v1
# =============================================================================
class KucoinProvider(_CEXBase):
    venue = "kucoin"
    base_url = "https://api.kucoin.com"

    def _sym(self, canonical: str) -> str:
        return canonical.replace("/", "-").upper()

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        s = self._sym(symbol)
        r = await self._get("/api/v1/market/orderbook/level1",
                             params={"symbol": s})
        row = r.get("data") or {}
        stat = await self._get("/api/v1/market/stats", params={"symbol": s})
        srow = stat.get("data") or {}
        bid = _to_float(row.get("bestBid"))
        ask = _to_float(row.get("bestAsk"))
        last = _to_float(row.get("price") or (bid + ask) / 2)
        spread_bps = ((ask - bid) / ((ask + bid) / 2) * 10_000
                      if (ask and bid) else 0.0)
        return {"venue": self.venue, "symbol": symbol,
                "bid": bid, "ask": ask, "last": last,
                "spread_bps": round(spread_bps, 2),
                "volume_24h_base": _to_float(srow.get("vol")),
                "ts": row.get("time")}

    async def get_orderbook(self, symbol: str,
                             depth: int = 10) -> Dict[str, Any]:
        s = self._sym(symbol)
        # KuCoin serves up to 100 aggregated levels on the public endpoint
        r = await self._get("/api/v1/market/orderbook/level2_100",
                              params={"symbol": s})
        d = r.get("data") or {}
        return {
            "venue": self.venue, "symbol": symbol,
            "bids": [[_to_float(p), _to_float(q)]
                      for p, q in (d.get("bids") or [])[:depth]],
            "asks": [[_to_float(p), _to_float(q)]
                      for p, q in (d.get("asks") or [])[:depth]],
        }


ALL_CEX = [BinanceProvider, BybitProvider, OKXProvider,
           CoinbaseProvider, KrakenProvider, KucoinProvider]

__all__ = [
    "BinanceProvider", "BybitProvider", "OKXProvider",
    "CoinbaseProvider", "KrakenProvider", "KucoinProvider",
    "ALL_CEX",
]
