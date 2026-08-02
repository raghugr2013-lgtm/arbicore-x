"""Hold Probability scaffold v1 — pure statistics, no AI.

Method (empirical delta distribution):
1. Take the self-collected best-bid series for (route, exchange) over a lookback window.
2. For every point t, find the bid at t + transfer_horizon; record Δ% = (bid_{t+T} − bid_t)/bid_t.
3. Hold probability for a position with breakeven cushion d% = fraction of historical
   Δ samples ≥ −d  (i.e. P that the bid does not fall through breakeven during transfer).
Honest about sample size: below MIN_SAMPLES the dashboard shows 'collecting'.
"""
from datetime import datetime, timedelta, timezone

from core.models import now_iso
from services import db

MIN_SAMPLES = 30
MAX_SAMPLES = 5000


def _q(sorted_vals, p):
    if not sorted_vals:
        return None
    idx = min(int(p * len(sorted_vals)), len(sorted_vals) - 1)
    return round(sorted_vals[idx], 3)


async def compute_delta_stats(route_id: str, exchange: str, horizon_min: float, lookback_h: float = 24) -> dict:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=lookback_h)).isoformat()
    docs = await db.evaluations.find(
        {"route_id": route_id, "exchange": exchange, "ts": {"$gte": cutoff}},
        {"_id": 0, "ts": 1, "market.best_bid": 1},
    ).sort("ts", 1).to_list(25000)

    series = []
    for d in docs:
        bid = (d.get("market") or {}).get("best_bid")
        if bid:
            try:
                series.append((datetime.fromisoformat(d["ts"]), bid))
            except ValueError:
                continue

    horizon = timedelta(minutes=horizon_min)
    tolerance = horizon_min * 60 * 0.5
    deltas = []
    j = 0
    for t, b in series:
        target = t + horizon
        while j < len(series) and series[j][0] < target:
            j += 1
        if j >= len(series):
            break
        t2, b2 = series[j]
        if (t2 - target).total_seconds() <= tolerance and b > 0:
            deltas.append((b2 - b) / b * 100)

    if len(deltas) > MAX_SAMPLES:
        step = len(deltas) / MAX_SAMPLES
        deltas = [deltas[int(i * step)] for i in range(MAX_SAMPLES)]
    deltas.sort()
    return {
        "deltas": deltas,
        "sample_count": len(deltas),
        "horizon_min": horizon_min,
        "lookback_h": lookback_h,
        "quantiles": {"p10": _q(deltas, 0.10), "p50": _q(deltas, 0.50), "p90": _q(deltas, 0.90)},
        "series_points": len(series),
        "computed_at": now_iso(),
    }
