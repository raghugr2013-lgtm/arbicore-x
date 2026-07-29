import time
from typing import List, Optional

from connectors.base import ExchangeConnector
from core.errors import MalformedResponse, SymbolNotListed
from core.models import Candle, FeeInfo, OrderBook, Ticker
from services.ws_manager import ws_manager

BASE = "https://sapi.xt.com"
_INTERVALS = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "1h", 240: "4h", 1440: "1d"}


class XTConnector(ExchangeConnector):
    key = "xt"
    name = "XT"
    capabilities = {
        "public_market_data": True, "public_fee_info": True, "websocket": True,
        "ws_channels": ["ticker", "depth50"],
        "trading_api": True, "withdrawal_api": True, "deposit_monitoring": True,
        "phase": "3 (live + ws)",
    }

    def map_symbol(self, base, quote):
        return f"{base.lower()}_{quote.lower()}"

    def _unwrap(self, data):
        if not isinstance(data, dict) or data.get("rc") != 0:
            mc = data.get("mc") if isinstance(data, dict) else "?"
            if mc in ("SYMBOL_NOT_EXIST", "SYMBOL_001", "INVALID_SYMBOL"):
                raise SymbolNotListed(f"xt: {mc}")
            raise MalformedResponse(f"xt: rc!=0 ({mc})")
        return data["result"]

    async def get_ticker(self, base, quote) -> Ticker:
        ws = ws_manager.get_ticker(self.key, base, quote)
        if ws:
            return Ticker(**ws)
        _, data = await self._get(f"{BASE}/v4/public/ticker/24h", {"symbol": self.map_symbol(base, quote)})
        result = self._unwrap(data)
        if not result:
            raise SymbolNotListed(f"xt: {base}/{quote} not listed")
        t = result[0]
        return Ticker(
            exchange=self.key, base=base, quote=quote,
            last=float(t["c"]), open_24h=float(t["o"]), high_24h=float(t["h"]), low_24h=float(t["l"]),
            volume_24h_base=float(t["q"]), volume_24h_quote=float(t["v"]),
        )

    async def get_orderbook(self, base, quote, limit=50) -> OrderBook:
        ws = ws_manager.get_orderbook(self.key, base, quote)
        if ws:
            return OrderBook(**{**ws, "bids": ws["bids"][:limit], "asks": ws["asks"][:limit]})
        _, data = await self._get(f"{BASE}/v4/public/depth", {"symbol": self.map_symbol(base, quote), "limit": limit})
        r = self._unwrap(data)
        return OrderBook(
            exchange=self.key, base=base, quote=quote,
            bids=[[float(p), float(q)] for p, q in r.get("bids", [])],
            asks=[[float(p), float(q)] for p, q in r.get("asks", [])],
        )

    async def get_candles(self, base, quote, interval_min=5, limit=100) -> List[Candle]:
        _, data = await self._get(f"{BASE}/v4/public/kline", {
            "symbol": self.map_symbol(base, quote), "interval": _INTERVALS[interval_min], "limit": limit})
        r = self._unwrap(data)
        return [Candle(open_time=int(k["t"]) // 1000, o=float(k["o"]), h=float(k["h"]), l=float(k["l"]),
                       c=float(k["c"]), volume_base=float(k["q"]), volume_quote=float(k["v"]),
                       interval_min=interval_min) for k in r]

    async def get_fee_info(self, currency) -> Optional[FeeInfo]:
        now = time.time()
        if self._fee_cache is None or now - self._fee_cache_ts > 240:
            _, data = await self._get(f"{BASE}/v4/public/wallet/support/currency")
            self._fee_cache = self._unwrap(data)
            self._fee_cache_ts = now
        for c in self._fee_cache:
            if c.get("currency", "").lower() == currency.lower():
                chains = c.get("supportChains") or []
                if not chains:
                    return None
                ch = chains[0]
                return FeeInfo(
                    exchange=self.key, currency=currency.upper(), chain=ch.get("chain"),
                    taker_fee_pct=0.2, maker_fee_pct=0.2,
                    withdraw_fee=ch.get("withdrawFeeAmount"), withdraw_min=ch.get("withdrawMinAmount"),
                    deposit_confirmations=ch.get("depositConfirmations"),
                    deposit_enabled=ch.get("depositEnabled"), withdraw_enabled=ch.get("withdrawEnabled"),
                )
        return None
