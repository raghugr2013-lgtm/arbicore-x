"""Evaluation pipeline — orchestrates all engines over the latest normalized
snapshots for one route and persists an explainable evaluation document.
"""
import time
from bisect import bisect_left
from datetime import datetime, timezone

from core.models import new_id, now_iso
from engines import capacity as cap_engine
from engines import confidence as confidence_engine
from engines import safety, spread, verdict as verdict_engine


def _age_s(ts_iso):
    if not ts_iso:
        return None
    try:
        dt = datetime.fromisoformat(ts_iso)
        return round((datetime.now(timezone.utc) - dt).total_seconds(), 1)
    except ValueError:
        return None


def _depth_quote_within(bids, asks, mid, pct):
    lo, hi = mid * (1 - pct / 100), mid * (1 + pct / 100)
    bid_d = sum(p * q for p, q in bids if p >= lo)
    ask_d = sum(p * q for p, q in asks if p <= hi)
    return bid_d, ask_d


def run_evaluation(route: dict, market: dict, network_health: dict, has_transfer_history: bool,
                   hold_stats: dict = None, connector_caps: dict = None) -> dict:
    """market = collector cache entry for the primary exchange:
    {ticker: Ticker|None, orderbook: OrderBook|None, fee: FeeInfo|None,
     candles: [Candle]|None, listed: bool, errors: {...}}
    """
    risk = route.get("risk_profile", {})
    primary = route["exit"]["exchange"]
    mb = route.get("manual_buy") or {}
    buy_price = mb.get("price")
    qty = mb.get("qty")

    ticker = market.get("ticker")
    ob = market.get("orderbook")
    fee = market.get("fee")
    candles = market.get("candles") or []
    listed = market.get("listed", False)

    taker = (fee.get("taker_fee_pct") if fee else None) or 0.2
    gas_asset = risk.get("transfer_gas_asset", 0.0)
    fixed_q = risk.get("fixed_fees_quote", 1.0)

    bids = ob.get("bids", []) if ob else []
    asks = ob.get("asks", []) if ob else []
    best_bid = bids[0][0] if bids else None
    best_ask = asks[0][0] if asks else None
    mid = (best_bid + best_ask) / 2 if best_bid and best_ask else (ticker or {}).get("last")
    spread_bps = (best_ask - best_bid) / mid * 10000 if best_bid and best_ask and mid else None

    curve = spread.slippage_curve(bids) if bids else []

    sp = {"gross_pct": None, "net_pct": None, "vwap": None, "best_bid": best_bid}
    be = {"price": None, "distance_pct": None}
    if buy_price and qty and bids:
        sp = spread.spread_metrics(buy_price, qty, bids, taker, gas_asset, fixed_q)
        be = spread.breakeven(buy_price, qty, taker, gas_asset, fixed_q, best_bid)

    cap = cap_engine.compute_capacity(curve, buy_price or (mid or 0), taker,
                                      (ticker or {}).get("volume_24h_base"), risk)

    # net spread at min size (gate G4)
    net_at_min = None
    if buy_price and cap.get("min_buy") and bids:
        net_at_min = spread.spread_metrics(buy_price, cap["min_buy"], bids, taker, gas_asset, fixed_q)["net_pct"]
    elif sp.get("net_pct") is not None:
        net_at_min = sp["net_pct"]

    bid_d2, _ = _depth_quote_within(bids, asks, mid, 2.0) if (bids and mid) else (None, None)

    liq = safety.liquidity_score(bid_d2, (ticker or {}).get("volume_24h_quote"), spread_bps)
    vol = safety.volatility_score([c["c"] for c in candles], candles[0]["interval_min"] if candles else 5,
                                  be.get("distance_pct"), risk.get("est_transfer_minutes", 30))
    tr = safety.transfer_risk_score(
        fee.get("deposit_enabled") if fee else None,
        fee.get("withdraw_enabled") if fee else None,
        fee.get("deposit_confirmations") if fee else None,
        risk.get("est_transfer_minutes", 30),
        network_health.get("healthy") if network_health else None,
        has_transfer_history,
    )
    subs = {
        "spread": safety.spread_score(sp.get("net_pct")),
        "liquidity": liq["score"],
        "volatility": vol["score"],
        "transfer_risk": tr["score"],
    }
    overall = safety.overall(subs, risk.get("weights", {}))

    rec = None
    if cap.get("recommended_raw") is not None:
        rec = cap["recommended_raw"] * cap_engine.safety_multiplier(overall)

    gates = verdict_engine.evaluate_gates(
        fee.get("deposit_enabled") if fee else None,
        listed and ticker is not None,
        _age_s((ticker or {}).get("ts")),
        _age_s((ob or {}).get("ts")),
        net_at_min,
    )
    v = verdict_engine.verdict(gates, overall, subs, risk)

    # Hold Probability scaffold v1 — empirical delta distribution (statistics only)
    hold = {"probability": None, "sample_count": (hold_stats or {}).get("sample_count", 0),
            "horizon_min": risk.get("est_transfer_minutes", 30),
            "lookback_h": (hold_stats or {}).get("lookback_h"),
            "method": "empirical_delta_v1", "status": "collecting",
            "quantiles": (hold_stats or {}).get("quantiles")}
    deltas = (hold_stats or {}).get("deltas") or []
    if len(deltas) >= 30 and be.get("distance_pct") is not None:
        idx = bisect_left(deltas, -be["distance_pct"])
        hold.update(probability=round((len(deltas) - idx) / len(deltas), 4), status="active")

    conf = confidence_engine.compute(subs, gates, {**cap, "recommended": rec},
                                     hold.get("probability"), connector_caps or {})

    return {
        "id": new_id(),
        "route_id": route["id"],
        "exchange": primary,
        "ts": now_iso(),
        "mode": route.get("mode", "live"),
        "market": {
            "last": (ticker or {}).get("last"), "best_bid": best_bid, "best_ask": best_ask,
            "mid": mid, "spread_bps": spread_bps,
            "volume_24h_quote": (ticker or {}).get("volume_24h_quote"),
            "ticker_age_s": _age_s((ticker or {}).get("ts")),
            "depth_age_s": _age_s((ob or {}).get("ts")),
        },
        "inputs": {"buy_price": buy_price, "qty": qty, "price_source": mb.get("price_source"),
                   "taker_fee_pct": taker, "fixed_fees_quote": fixed_q},
        "spread": {"gross_pct": sp.get("gross_pct"), "net_pct": sp.get("net_pct"),
                   "vwap_at_qty": sp.get("vwap"), "net_at_min_size_pct": net_at_min},
        "breakeven": be,
        "capacity": {**cap, "recommended": rec,
                     "safety_multiplier": cap_engine.safety_multiplier(overall)},
        "slippage_curve": curve[:30],
        "scores": {**subs, "overall": overall},
        "score_inputs": {"liquidity": liq["inputs"], "volatility": vol["inputs"], "transfer": tr["inputs"]},
        "gates": gates,
        "verdict": v["verdict"],
        "reasons": v["reasons"],
        "hold_probability": hold,
        "confidence": conf,
    }
