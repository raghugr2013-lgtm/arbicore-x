import uuid
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


# ---------- Normalized market models (the lingua franca) ----------

class Ticker(BaseModel):
    exchange: str
    base: str
    quote: str
    last: float
    bid: Optional[float] = None
    ask: Optional[float] = None
    open_24h: Optional[float] = None
    high_24h: Optional[float] = None
    low_24h: Optional[float] = None
    volume_24h_base: Optional[float] = None
    volume_24h_quote: Optional[float] = None
    ts: str = Field(default_factory=now_iso)
    source: str = "live"


class OrderBook(BaseModel):
    exchange: str
    base: str
    quote: str
    bids: List[List[float]]  # [[price, qty], ...] best first
    asks: List[List[float]]
    ts: str = Field(default_factory=now_iso)
    source: str = "live"


class Candle(BaseModel):
    open_time: int  # epoch seconds
    o: float
    h: float
    l: float
    c: float
    volume_base: Optional[float] = None
    volume_quote: Optional[float] = None
    interval_min: int = 5


class FeeInfo(BaseModel):
    exchange: str
    currency: str
    chain: Optional[str] = None
    taker_fee_pct: Optional[float] = None
    maker_fee_pct: Optional[float] = None
    withdraw_fee: Optional[float] = None
    withdraw_min: Optional[float] = None
    deposit_confirmations: Optional[int] = None
    deposit_enabled: Optional[bool] = None  # None = unknown
    withdraw_enabled: Optional[bool] = None
    ts: str = Field(default_factory=now_iso)
    source: str = "live"


# ---------- Route configuration ----------

DEFAULT_RISK_PROFILE = {
    "max_slippage_pct": 1.0,
    "participation_cap_pct": 2.0,
    "min_net_spread_pct": 2.0,
    "fee_share_cap": 0.25,
    "fixed_fees_quote": 1.0,            # settlement withdrawal + misc fixed costs in quote terms
    "transfer_gas_asset": 0.0,          # on-chain gas paid in asset units
    "est_transfer_minutes": 30,
    "weights": {"spread": 0.30, "liquidity": 0.25, "volatility": 0.20, "transfer": 0.25},
    "go_threshold": 70,
    "wait_threshold": 45,
    "subscore_floor": 40,
}

DEFAULT_SIM_CONFIG = {
    "base_price": 0.00004,
    "daily_vol_pct": 18.0,
    "spread_bps": 60,
    "depth_quote_1pct": 4000.0,         # $ depth within 1% of mid per side
    "volume_24h_quote": 250000.0,
    "deposit_enabled": True,
    "withdraw_enabled": True,
    "seed": 7,
}
