from typing import List, Optional

from connectors.base import ExchangeConnector
from core.errors import MalformedResponse, SymbolNotListed
from core.models import Candle, FeeInfo, OrderBook, Ticker

BASE = "https://api.gateio.ws/api/v4"
_INTERVALS = {1: "1m", 5: "5m", 15: "15m", 30: "30m", 60: "1h", 240: "4h", 1440: "1d"}


class GateConnector(ExchangeConnector):
    key = "gate"
    name = "Gate"
    capabilities = {
        "public_market_data": True, "public_fee_info": True, "websocket": False,
        "trading_api": True, "withdrawal_api": True, "deposit_monitoring": True,
        "phase": "1 (live; BDAG not yet listed)",
    }

    def map_symbol(self, base, quote):
        return f"{base.upper()}_{quote.upper()}"

    def _check(self, status, data):
        if isinstance(data, dict) and data.get("label") in ("INVALID_CURRENCY", "INVALID_CURRENCY_PAIR"):
            raise SymbolNotListed("gate: invalid currency/pair")
        if status >= 400:
            raise MalformedResponse(f"gate: HTTP {status} {str(data)[:120]}")
        return data

    async def get_ticker(self, base, quote) -> Ticker:
        status, data = await self._get(f"{BASE}/spot/tickers", {"currency_pair": self.map_symbol(base, quote)})
        rows = self._check(status, data)
        if not rows:
            raise SymbolNotListed(f"gate: {base}/{quote} not listed")
        t = rows[0]
        return Ticker(
            exchange=self.key, base=base, quote=quote,
            last=float(t["last"]),
            bid=float(t["highest_bid"]) if t.get("highest_bid") else None,
            ask=float(t["lowest_ask"]) if t.get("lowest_ask") else None,
            high_24h=float(t["high_24h"]), low_24h=float(t["low_24h"]),
            volume_24h_base=float(t["base_volume"]), volume_24h_quote=float(t["quote_volume"]),
        )

    async def get_orderbook(self, base, quote, limit=50) -> OrderBook:
        status, data = await self._get(f"{BASE}/spot/order_book", {
            "currency_pair": self.map_symbol(base, quote), "limit": min(limit, 100)})
        d = self._check(status, data)
        return OrderBook(
            exchange=self.key, base=base, quote=quote,
            bids=[[float(p), float(q)] for p, q in d.get("bids", [])],
            asks=[[float(p), float(q)] for p, q in d.get("asks", [])],
        )

    async def get_candles(self, base, quote, interval_min=5, limit=100) -> List[Candle]:
        status, data = await self._get(f"{BASE}/spot/candlesticks", {
            "currency_pair": self.map_symbol(base, quote), "interval": _INTERVALS[interval_min], "limit": limit})
        rows = self._check(status, data)
        out = []
        for k in rows:
            # [ts, quote_vol, close, high, low, open, base_vol, ...]
            out.append(Candle(open_time=int(k[0]), o=float(k[5]), h=float(k[3]), l=float(k[4]),
                              c=float(k[2]), volume_quote=float(k[1]),
                              volume_base=float(k[6]) if len(k) > 6 else None,
                              interval_min=interval_min))
        return out

    async def get_fee_info(self, currency) -> Optional[FeeInfo]:
        try:
            status, data = await self._get(f"{BASE}/spot/currencies/{currency.upper()}")
            d = self._check(status, data)
        except SymbolNotListed:
            return None
        chains = d.get("chains") or []
        dep_ok = wd_ok = None
        chain_name = None
        if chains:
            ch = chains[0]
            chain_name = ch.get("name")
            dep_ok = not ch.get("deposit_disabled", False)
            wd_ok = not ch.get("withdraw_disabled", False)
        else:
            dep_ok = not d.get("deposit_disabled", False)
            wd_ok = not d.get("withdraw_disabled", False)
        return FeeInfo(exchange=self.key, currency=currency.upper(), chain=chain_name,
                       taker_fee_pct=0.2, maker_fee_pct=0.2,
                       deposit_enabled=dep_ok, withdraw_enabled=wd_ok)
