from typing import List

from connectors.base import ExchangeConnector
from core.errors import MalformedResponse, SymbolNotListed
from core.models import Candle, OrderBook, Ticker

BASE = "https://api.mexc.com"
_INTERVALS = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "60m", 240: "4h", 1440: "1d"}


class MEXCConnector(ExchangeConnector):
    key = "mexc"
    name = "MEXC"
    capabilities = {
        "public_market_data": True, "public_fee_info": False, "websocket": False,
        "trading_api": True, "withdrawal_api": True, "deposit_monitoring": True,
        "phase": "1 (live; BDAG not yet listed)",
    }

    def map_symbol(self, base, quote):
        return f"{base.upper()}{quote.upper()}"

    def _check(self, status, data):
        if isinstance(data, dict) and data.get("code") in (-1121, -1100):
            raise SymbolNotListed(f"mexc: invalid symbol")
        if status >= 400:
            raise MalformedResponse(f"mexc: HTTP {status} {str(data)[:120]}")
        return data

    async def get_ticker(self, base, quote) -> Ticker:
        status, data = await self._get(f"{BASE}/api/v3/ticker/24hr", {"symbol": self.map_symbol(base, quote)})
        t = self._check(status, data)
        return Ticker(
            exchange=self.key, base=base, quote=quote,
            last=float(t["lastPrice"]),
            bid=float(t["bidPrice"]) if t.get("bidPrice") else None,
            ask=float(t["askPrice"]) if t.get("askPrice") else None,
            open_24h=float(t["openPrice"]), high_24h=float(t["highPrice"]), low_24h=float(t["lowPrice"]),
            volume_24h_base=float(t["volume"]), volume_24h_quote=float(t["quoteVolume"]),
        )

    async def get_orderbook(self, base, quote, limit=50) -> OrderBook:
        status, data = await self._get(f"{BASE}/api/v3/depth", {"symbol": self.map_symbol(base, quote), "limit": limit})
        d = self._check(status, data)
        return OrderBook(
            exchange=self.key, base=base, quote=quote,
            bids=[[float(p), float(q)] for p, q in d.get("bids", [])],
            asks=[[float(p), float(q)] for p, q in d.get("asks", [])],
        )

    async def get_candles(self, base, quote, interval_min=5, limit=100) -> List[Candle]:
        status, data = await self._get(f"{BASE}/api/v3/klines", {
            "symbol": self.map_symbol(base, quote), "interval": _INTERVALS[interval_min], "limit": limit})
        rows = self._check(status, data)
        return [Candle(open_time=int(k[0]) // 1000, o=float(k[1]), h=float(k[2]), l=float(k[3]),
                       c=float(k[4]), volume_base=float(k[5]),
                       volume_quote=float(k[7]) if len(k) > 7 else None,
                       interval_min=interval_min) for k in rows]
