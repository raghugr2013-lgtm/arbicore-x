import time
from typing import List

from connectors.base import ExchangeConnector
from core.errors import MalformedResponse, SymbolNotListed
from core.models import Candle, OrderBook, Ticker

BASE = "https://api.coinstore.com/api"
_PERIODS = {1: "1min", 5: "5min", 15: "15min", 30: "30min", 60: "60min", 240: "4hour", 1440: "1day"}


class CoinstoreConnector(ExchangeConnector):
    key = "coinstore"
    name = "Coinstore"
    capabilities = {
        "public_market_data": True, "public_fee_info": False, "websocket": True,
        "trading_api": True, "withdrawal_api": True, "deposit_monitoring": True,
        "phase": "2 (live — promoted by capability audit)",
    }

    def __init__(self):
        super().__init__()
        self._tickers_cache = None
        self._tickers_ts = 0.0

    def map_symbol(self, base, quote):
        return f"{base.upper()}{quote.upper()}"

    def _unwrap(self, data):
        if not isinstance(data, dict) or data.get("code") not in (0, "0"):
            raise MalformedResponse(f"coinstore: code={data.get('code') if isinstance(data, dict) else '?'}")
        return data.get("data")

    async def get_ticker(self, base, quote) -> Ticker:
        now = time.time()
        if self._tickers_cache is None or now - self._tickers_ts > 4:
            _, data = await self._get(f"{BASE}/v1/market/tickers")
            self._tickers_cache = self._unwrap(data)
            self._tickers_ts = now
        sym = self.map_symbol(base, quote)
        t = next((x for x in self._tickers_cache if x.get("symbol") == sym), None)
        if not t:
            raise SymbolNotListed(f"coinstore: {sym} not listed")
        # coinstore field naming: volume=base units, amount=quote units (verified vs live data)
        return Ticker(
            exchange=self.key, base=base, quote=quote,
            last=float(t["close"]),
            bid=float(t["bid"]) if t.get("bid") else None,
            ask=float(t["ask"]) if t.get("ask") else None,
            open_24h=float(t["open"]), high_24h=float(t["high"]), low_24h=float(t["low"]),
            volume_24h_base=float(t["volume"]), volume_24h_quote=float(t["amount"]),
        )

    async def get_orderbook(self, base, quote, limit=50) -> OrderBook:
        sym = self.map_symbol(base, quote)
        _, data = await self._get(f"{BASE}/v1/market/depth/{sym}", {"depth": min(limit, 100)})
        d = self._unwrap(data)
        if d is None:
            raise SymbolNotListed(f"coinstore: {sym} not listed")
        return OrderBook(
            exchange=self.key, base=base, quote=quote,
            bids=[[float(r[0]), float(r[1])] for r in d.get("b", [])],
            asks=[[float(r[0]), float(r[1])] for r in d.get("a", [])],
        )

    async def get_candles(self, base, quote, interval_min=5, limit=100) -> List[Candle]:
        sym = self.map_symbol(base, quote)
        _, data = await self._get(f"{BASE}/v1/market/kline/{sym}",
                                  {"period": _PERIODS[interval_min], "size": limit})
        d = self._unwrap(data)
        items = (d or {}).get("item") or []
        return [Candle(open_time=int(k["startTime"]), o=float(k["open"]), h=float(k["high"]),
                       l=float(k["low"]), c=float(k["close"]),
                       volume_base=float(k["volume"]) if k.get("volume") else None,
                       volume_quote=float(k["amount"]) if k.get("amount") else None,
                       interval_min=interval_min) for k in items]
