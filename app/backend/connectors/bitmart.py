import time
from typing import List, Optional

from connectors.base import ExchangeConnector
from core.errors import MalformedResponse, SymbolNotListed
from core.models import Candle, FeeInfo, OrderBook, Ticker
from services.ws_manager import ws_manager

BASE = "https://api-cloud.bitmart.com"
_STEPS = {1: 1, 5: 5, 15: 15, 30: 30, 60: 60, 240: 240, 1440: 1440}


class BitMartConnector(ExchangeConnector):
    key = "bitmart"
    name = "BitMart"
    capabilities = {
        "public_market_data": True, "public_fee_info": True, "websocket": True,
        "ws_channels": ["spot/ticker", "spot/depth50"],
        "trading_api": True, "withdrawal_api": True, "deposit_monitoring": True,
        "phase": "3 (live + ws — only fully executable BDAG route today)",
    }

    def map_symbol(self, base, quote):
        return f"{base.upper()}_{quote.upper()}"

    def _unwrap(self, status, data):
        code = data.get("code") if isinstance(data, dict) else None
        if code in (30000, 50005, 51000, 30001) or (isinstance(data, dict) and "not found" in str(data.get("message", "")).lower()):
            raise SymbolNotListed("bitmart: symbol not found")
        if code != 1000:
            raise MalformedResponse(f"bitmart: code={code} {str(data)[:120]}")
        return data.get("data")

    async def get_ticker(self, base, quote) -> Ticker:
        ws = ws_manager.get_ticker(self.key, base, quote)
        if ws:
            return Ticker(**ws)
        status, data = await self._get(f"{BASE}/spot/quotation/v3/ticker", {"symbol": self.map_symbol(base, quote)})
        t = self._unwrap(status, data)
        if not t or not t.get("last"):
            raise SymbolNotListed(f"bitmart: {base}/{quote} not listed")
        return Ticker(
            exchange=self.key, base=base, quote=quote,
            last=float(t["last"]),
            bid=float(t["bid_px"]) if t.get("bid_px") else None,
            ask=float(t["ask_px"]) if t.get("ask_px") else None,
            open_24h=float(t["open_24h"]), high_24h=float(t["high_24h"]), low_24h=float(t["low_24h"]),
            volume_24h_base=float(t["v_24h"]), volume_24h_quote=float(t["qv_24h"]),
        )

    async def get_orderbook(self, base, quote, limit=50) -> OrderBook:
        ws = ws_manager.get_orderbook(self.key, base, quote)
        if ws:
            return OrderBook(**{**ws, "bids": ws["bids"][:limit], "asks": ws["asks"][:limit]})
        status, data = await self._get(f"{BASE}/spot/quotation/v3/books", {
            "symbol": self.map_symbol(base, quote), "limit": min(limit, 50)})
        d = self._unwrap(status, data)
        return OrderBook(
            exchange=self.key, base=base, quote=quote,
            bids=[[float(p), float(q)] for p, q in d.get("bids", [])],
            asks=[[float(p), float(q)] for p, q in d.get("asks", [])],
        )

    async def get_candles(self, base, quote, interval_min=5, limit=100) -> List[Candle]:
        status, data = await self._get(f"{BASE}/spot/quotation/v3/klines", {
            "symbol": self.map_symbol(base, quote), "step": _STEPS[interval_min], "limit": limit})
        rows = self._unwrap(status, data)
        # [t, open, high, low, close, volume(base), amount(quote)]
        return [Candle(open_time=int(k[0]), o=float(k[1]), h=float(k[2]), l=float(k[3]), c=float(k[4]),
                       volume_base=float(k[5]), volume_quote=float(k[6]), interval_min=interval_min)
                for k in rows]

    async def get_fee_info(self, currency) -> Optional[FeeInfo]:
        now = time.time()
        if self._fee_cache is None or now - self._fee_cache_ts > 240:
            status, data = await self._get(f"{BASE}/account/v1/currencies")
            self._fee_cache = self._unwrap(status, data).get("currencies", [])
            self._fee_cache_ts = now
        cur = currency.upper()
        for c in self._fee_cache:
            cid = str(c.get("currency", c.get("id", "")))
            if cid.upper() == cur or cid.upper().startswith(cur + "-"):
                return FeeInfo(
                    exchange=self.key, currency=cur, chain=c.get("network"),
                    taker_fee_pct=0.25, maker_fee_pct=0.25,
                    withdraw_fee=float(c["withdraw_fee"]) if c.get("withdraw_fee") else None,
                    withdraw_min=float(c["withdraw_minsize"]) if c.get("withdraw_minsize") else None,
                    deposit_enabled=c.get("deposit_enabled"), withdraw_enabled=c.get("withdraw_enabled"),
                )
        return None
