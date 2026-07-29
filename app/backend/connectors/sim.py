"""Simulation connector — same interface as live exchanges, deterministic
seeded random-walk data. Selected by the registry when route.mode == 'simulation'.
Per-exchange price offsets create realistic cross-venue dispersion.
"""
import math
import random
import time
from typing import List, Optional

from core.models import Candle, FeeInfo, OrderBook, Ticker

_EXCHANGE_OFFSET = {"xt": 1.0, "mexc": 1.012, "gate": 0.994, "bitmart": 1.03, "coinstore": 1.018}

# module-level scenario, updated by the collector from route.sim_config
_SCENARIO = {
    "base_price": 0.00004, "daily_vol_pct": 18.0, "spread_bps": 60,
    "depth_quote_1pct": 4000.0, "volume_24h_quote": 250000.0,
    "deposit_enabled": True, "withdraw_enabled": True, "seed": 7,
}


def set_scenario(cfg: dict):
    _SCENARIO.update({k: v for k, v in (cfg or {}).items() if v is not None})


class SimExchangeConnector:
    name = "Simulation"
    capabilities = {"public_market_data": True, "public_fee_info": True, "simulated": True}

    def __init__(self, key: str):
        self.key = key

    def _mid(self, t_bucket: int) -> float:
        """Seeded random walk: hourly anchor + minute-level wiggle."""
        s = _SCENARIO
        base = s["base_price"] * _EXCHANGE_OFFSET.get(self.key, 1.0)
        rng = random.Random(f"{s['seed']}-{self.key}-{t_bucket // 60}")
        hourly_drift = rng.gauss(0, s["daily_vol_pct"] / 100 / math.sqrt(24))
        rng2 = random.Random(f"{s['seed']}-{self.key}-{t_bucket}")
        minute_wiggle = rng2.gauss(0, s["daily_vol_pct"] / 100 / math.sqrt(24 * 60))
        return base * (1 + hourly_drift + minute_wiggle)

    async def close(self):
        pass

    async def get_ticker(self, base, quote) -> Ticker:
        t = int(time.time() // 60)
        mid = self._mid(t)
        half = mid * _SCENARIO["spread_bps"] / 10000 / 2
        return Ticker(
            exchange=self.key, base=base, quote=quote, last=mid,
            bid=mid - half, ask=mid + half,
            open_24h=self._mid(t - 1440), high_24h=mid * 1.06, low_24h=mid * 0.94,
            volume_24h_base=_SCENARIO["volume_24h_quote"] / mid,
            volume_24h_quote=_SCENARIO["volume_24h_quote"],
            source="sim",
        )

    async def get_orderbook(self, base, quote, limit=50) -> OrderBook:
        t = int(time.time() // 60)
        mid = self._mid(t)
        half = mid * _SCENARIO["spread_bps"] / 10000 / 2
        rng = random.Random(f"{_SCENARIO['seed']}-book-{self.key}-{t}")
        # qty per level so that ~depth_quote_1pct sits within 1% of mid
        levels_in_1pct = max(3, int(0.01 * mid / max(mid * 0.0008, 1e-12)))
        per_level_quote = _SCENARIO["depth_quote_1pct"] / levels_in_1pct
        bids, asks = [], []
        for i in range(limit):
            step = mid * 0.0008 * (i + 1) * (1 + 0.3 * rng.random())
            q_b = per_level_quote * (0.6 + rng.random()) / max(mid, 1e-12)
            q_a = per_level_quote * (0.6 + rng.random()) / max(mid, 1e-12)
            bids.append([mid - half - step, q_b])
            asks.append([mid + half + step, q_a])
        return OrderBook(exchange=self.key, base=base, quote=quote, bids=bids, asks=asks, source="sim")

    async def get_candles(self, base, quote, interval_min=5, limit=100) -> List[Candle]:
        now = int(time.time())
        out = []
        for i in range(limit, 0, -1):
            t0 = now - i * interval_min * 60
            bucket = t0 // 60
            o = self._mid(bucket)
            c = self._mid(bucket + interval_min)
            hi, lo = max(o, c) * 1.004, min(o, c) * 0.996
            vol_q = _SCENARIO["volume_24h_quote"] / (1440 / interval_min)
            out.append(Candle(open_time=t0, o=o, h=hi, l=lo, c=c,
                              volume_quote=vol_q, volume_base=vol_q / max(c, 1e-12),
                              interval_min=interval_min))
        return out

    async def get_fee_info(self, currency) -> Optional[FeeInfo]:
        return FeeInfo(
            exchange=self.key, currency=currency.upper(), chain="SIM",
            taker_fee_pct=0.2, maker_fee_pct=0.2,
            withdraw_fee=25000.0, withdraw_min=250000.0, deposit_confirmations=10,
            deposit_enabled=_SCENARIO["deposit_enabled"],
            withdraw_enabled=_SCENARIO["withdraw_enabled"],
            source="sim",
        )
