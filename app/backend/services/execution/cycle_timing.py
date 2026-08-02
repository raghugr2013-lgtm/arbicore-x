"""Cycle Timing Engine + Risk Decay Engine (READ-ONLY).

Reads closed cycles (`arbitrage_cycles` collection) — the milestones are
auto-stamped by the Wallet Observer (Iter8 + Iter9). For each cycle we:

  1. Compute stage durations from consecutive milestone timestamps.
  2. Pull Coinstore best-bid history (`orderbook_snapshots`, exchange='coinstore')
     across the cycle window and measure the actual price drift over the cycle's
     lifetime.
  3. Aggregate timing + drift across history → average/worst/P95.
  4. Forecast risk-adjusted profit for a new opportunity by applying the
     historical drift distribution to its expected gross profit.

No execution, no signing, no fund movement.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

from core.models import now_iso
from services import db
from services.execution import arbitrage_cycles

COLL_CYCLES = arbitrage_cycles.COLL
COLL_SNAPS = "orderbook_snapshots"

# Stage definitions — each stage is a transition between two consecutive
# milestones. Stages with missing endpoints are dropped from the aggregate.
STAGE_PAIRS: list[tuple[str, str, str]] = [
    ("quote_to_swap_submit",    "quote_at",                "swap_submitted_at"),
    ("swap_settlement",         "swap_submitted_at",       "swap_confirmed_at"),
    ("wallet_credit",           "swap_confirmed_at",       "bdag_received_at"),
    ("transfer_send",           "bdag_received_at",        "transfer_submitted_at"),
    ("transfer_to_coinstore",   "transfer_submitted_at",   "deposit_confirmed_at"),
    ("ready_to_sell",           "deposit_confirmed_at",    "sell_executed_at"),
    ("withdraw_to_wallet",      "sell_executed_at",        "withdrawal_completed_at"),
]


# ---------------------------- helpers ----------------------------------------

def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None


def _duration_s(a: str | None, b: str | None) -> float | None:
    da, db_ = _parse(a), _parse(b)
    if not (da and db_):
        return None
    secs = (db_ - da).total_seconds()
    return round(secs, 1) if secs >= 0 else None


def _percentile(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    k = max(0, min(len(s) - 1, int(round(p / 100.0 * (len(s) - 1)))))
    return s[k]


def _stat_block(xs: list[float]) -> dict:
    if not xs:
        return {"count": 0}
    return {
        "count": len(xs),
        "avg": round(statistics.mean(xs), 3),
        "median": round(statistics.median(xs), 3),
        "p95": _percentile(xs, 95),
        "worst": max(xs),
        "best": min(xs),
        "stdev": round(statistics.pstdev(xs), 3) if len(xs) > 1 else None,
    }


def _signed_stat_block(xs: list[float]) -> dict:
    """For drift values where MORE NEGATIVE = WORSE. We surface both ends."""
    if not xs:
        return {"count": 0}
    return {
        "count": len(xs),
        "avg": round(statistics.mean(xs), 4),
        "median": round(statistics.median(xs), 4),
        "p5": _percentile(xs, 5),
        "p25": _percentile(xs, 25),
        "p75": _percentile(xs, 75),
        "p95": _percentile(xs, 95),
        "worst": min(xs),     # most negative drift = worst
        "best": max(xs),
        "stdev": round(statistics.pstdev(xs), 4) if len(xs) > 1 else None,
    }


# ---------------------------- per-cycle calculations -------------------------

def stage_durations_for_cycle(cycle: dict) -> list[dict]:
    rows = []
    for name, a, b in STAGE_PAIRS:
        rows.append({
            "stage": name,
            "from_field": a, "to_field": b,
            "from_at": cycle.get(a),
            "to_at": cycle.get(b),
            "duration_s": _duration_s(cycle.get(a), cycle.get(b)),
        })
    return rows


async def _coinstore_bid_samples(route_id: str | None,
                                  start_iso: str | None,
                                  end_iso: str | None) -> list[dict]:
    """Pull Coinstore orderbook best-bid samples inside [start, end]."""
    if not (start_iso and end_iso):
        return []
    q: dict = {"exchange": "coinstore",
               "created_at": {"$gte": start_iso, "$lte": end_iso}}
    if route_id:
        q["route_id"] = route_id
    cur = db.db[COLL_SNAPS].find(q, {"_id": 0, "ts": 1, "created_at": 1,
                                     "derived.best_bid": 1},
                                  sort=[("created_at", 1)])
    samples = []
    async for s in cur:
        bb = (s.get("derived") or {}).get("best_bid")
        if bb is not None:
            samples.append({"ts": s.get("ts") or s.get("created_at"),
                            "best_bid": float(bb)})
    return samples


def _drift_from_samples(bid_at_quote: float | None,
                        samples: list[dict]) -> dict:
    """Return drift metrics (in %) computed against bid_at_quote.
       - end_drift_pct: last sample vs anchor
       - worst_drift_pct: most-negative sample vs anchor
       - best_drift_pct: most-positive sample vs anchor
       - max_abs_drift_pct
    """
    if not bid_at_quote or bid_at_quote <= 0 or not samples:
        return {"available": False, "samples": len(samples)}
    bids = [s["best_bid"] for s in samples]
    end = bids[-1]
    lo, hi = min(bids), max(bids)
    end_pct = (end - bid_at_quote) / bid_at_quote * 100
    worst_pct = (lo - bid_at_quote) / bid_at_quote * 100
    best_pct = (hi - bid_at_quote) / bid_at_quote * 100
    return {
        "available": True,
        "anchor_bid": bid_at_quote,
        "first_sample_bid": samples[0]["best_bid"],
        "last_sample_bid": end,
        "min_sample_bid": lo,
        "max_sample_bid": hi,
        "samples": len(samples),
        "end_drift_pct": round(end_pct, 4),
        "worst_drift_pct": round(worst_pct, 4),
        "best_drift_pct": round(best_pct, 4),
        "max_abs_drift_pct": round(max(abs(worst_pct), abs(best_pct)), 4),
    }


async def per_cycle_report(cycle: dict) -> dict:
    stages = stage_durations_for_cycle(cycle)
    bid_q = cycle.get("best_bid_at_quote")
    samples = await _coinstore_bid_samples(
        route_id=cycle.get("route_id"),
        start_iso=cycle.get("quote_at"),
        end_iso=(cycle.get("withdrawal_completed_at") or cycle.get("updated_at")),
    )
    drift = _drift_from_samples(bid_q, samples)
    total_dur = _duration_s(cycle.get("quote_at"),
                            cycle.get("withdrawal_completed_at"))
    return {
        "cycle_id": cycle.get("id"),
        "state": cycle.get("state"),
        "quote_at": cycle.get("quote_at"),
        "withdrawal_completed_at": cycle.get("withdrawal_completed_at"),
        "total_duration_s": total_dur,
        "stages": stages,
        "drift": drift,
        "realized_roi_pct": (cycle.get("actuals") or {}).get("realized_roi_pct"),
        "net_profit_usd": (cycle.get("actuals") or {}).get("net_profit_usd"),
        "expected_roi_pct": cycle.get("expected_roi_pct"),
        "best_bid_at_quote": bid_q,
        "best_bid_at_sell": (cycle.get("actuals") or {}).get("best_bid_at_sell"),
    }


# ---------------------------- aggregates -------------------------------------

async def _list_closed_cycles(limit: int = 500) -> list[dict]:
    return await db.db[COLL_CYCLES].find(
        {"state": "CLOSED"}, {"_id": 0}, sort=[("created_at", -1)],
    ).to_list(limit)


def _stage_aggregates(per_cycle_rows: list[dict]) -> list[dict]:
    """Roll up by stage across all per-cycle rows."""
    by_stage: dict[str, list[float]] = {name: [] for name, _, _ in STAGE_PAIRS}
    for r in per_cycle_rows:
        for s in r["stages"]:
            d = s.get("duration_s")
            if d is not None:
                by_stage[s["stage"]].append(d)
    return [
        {"stage": name, **_stat_block(by_stage[name])}
        for name, _, _ in STAGE_PAIRS
    ]


def _drift_aggregates(per_cycle_rows: list[dict]) -> dict:
    end_drifts: list[float] = []
    worst_drifts: list[float] = []
    best_drifts: list[float] = []
    for r in per_cycle_rows:
        d = r.get("drift") or {}
        if not d.get("available"):
            continue
        end_drifts.append(d["end_drift_pct"])
        worst_drifts.append(d["worst_drift_pct"])
        best_drifts.append(d["best_drift_pct"])
    return {
        "end_drift_pct": _signed_stat_block(end_drifts),
        "worst_drift_pct": _signed_stat_block(worst_drifts),
        "best_drift_pct": _signed_stat_block(best_drifts),
        "samples_used": len(end_drifts),
    }


def _total_duration_block(per_cycle_rows: list[dict]) -> dict:
    durs = [r["total_duration_s"] for r in per_cycle_rows
            if r["total_duration_s"] is not None]
    return _stat_block(durs)


# ---------------------------- forecast / risk-adjusted -----------------------

def _expected_spread_pct(captured_price: float, best_bid: float) -> float:
    return (best_bid - captured_price) / captured_price * 100


def forecast(captured_price: float | None, best_bid: float | None,
             investment_usd: float | None,
             drift_agg: dict, duration_block: dict,
             taker_fee_pct: float = 0.20,
             bdag_transfer_fee_base: float = 0.0) -> dict:
    """Apply historical drift distribution to a hypothetical opportunity.

    Returns expected drift, worst observed drift, risk-adjusted profit, and
    the probability the profit disappears before cycle completion
    (= % of historical cycles whose worst_drift_pct exceeded the spread).
    """
    if not (captured_price and best_bid and investment_usd):
        return {"available": False,
                "note": "Need captured_price, best_bid and investment_usd."}
    spread_pct = _expected_spread_pct(captured_price, best_bid)
    bdag_bought = investment_usd / captured_price - bdag_transfer_fee_base
    gross_proceeds_usd = bdag_bought * best_bid
    trading_fee_usd = gross_proceeds_usd * taker_fee_pct / 100.0
    expected_profit_usd = gross_proceeds_usd - trading_fee_usd - investment_usd

    worst_block = drift_agg.get("worst_drift_pct") or {}
    end_block = drift_agg.get("end_drift_pct") or {}
    expected_drift_pct = end_block.get("avg")          # observed end-of-cycle drift
    worst_observed_pct = worst_block.get("worst")      # most-negative historical
    p95_worst_pct = worst_block.get("p5")              # 5th-pct = bad-tail proxy

    def _usd_haircut(pct):
        return (pct / 100.0) * gross_proceeds_usd if pct is not None else None

    risk_adj_profit_avg = (
        expected_profit_usd + _usd_haircut(expected_drift_pct)
        if expected_drift_pct is not None else None
    )
    risk_adj_profit_p5 = (
        expected_profit_usd + _usd_haircut(p95_worst_pct)
        if p95_worst_pct is not None else None
    )
    risk_adj_profit_worst = (
        expected_profit_usd + _usd_haircut(worst_observed_pct)
        if worst_observed_pct is not None else None
    )

    # Probability profit disappears = fraction of historical cycles whose
    # worst observed drift (most-negative) is more negative than -spread_pct.
    breakeven_drift_pct = -spread_pct   # if bid drops by spread_pct, profit gone
    prob_disappears = None
    samples_n = worst_block.get("count") or 0
    if samples_n and breakeven_drift_pct is not None:
        # Without raw samples we approximate via percentile boundary.
        # Use stored stats: if worst_block.worst >= breakeven → prob 0
        #                   if worst_block.p5 <= breakeven   → prob ≥ 5%
        #                   if worst_block.median <= breakeven → prob ≥ 50%
        # For a precise value caller can request /forecast/raw which returns samples.
        ladder = [
            ("worst", worst_block.get("worst"), 1.0),
            ("p5",    worst_block.get("p5"),    0.05),
            ("median", worst_block.get("median"), 0.50),
            ("p95",   worst_block.get("p95"),   0.95),
            ("best",  worst_block.get("best"),  0.0),  # best of worst = least-negative
        ]
        # find smallest fraction whose threshold is more negative than breakeven
        cands = [frac for _, val, frac in ladder
                 if val is not None and val <= breakeven_drift_pct]
        prob_disappears = round(min(cands), 4) if cands else 0.0

    return {
        "available": True,
        "captured_price": captured_price,
        "best_bid": best_bid,
        "investment_usd": investment_usd,
        "spread_pct": round(spread_pct, 4),
        "expected_gross_proceeds_usd": round(gross_proceeds_usd, 4),
        "expected_profit_usd": round(expected_profit_usd, 4),
        "trading_fee_usd": round(trading_fee_usd, 4),
        "expected_cycle_duration_s_avg": duration_block.get("avg"),
        "expected_cycle_duration_s_p95": duration_block.get("p95"),
        "expected_drift_pct": expected_drift_pct,
        "worst_observed_drift_pct": worst_observed_pct,
        "p5_worst_drift_pct": p95_worst_pct,
        "breakeven_drift_pct": round(breakeven_drift_pct, 4),
        "risk_adjusted_profit_avg_usd": (round(risk_adj_profit_avg, 4)
                                          if risk_adj_profit_avg is not None else None),
        "risk_adjusted_profit_p5_usd": (round(risk_adj_profit_p5, 4)
                                         if risk_adj_profit_p5 is not None else None),
        "risk_adjusted_profit_worst_usd": (round(risk_adj_profit_worst, 4)
                                             if risk_adj_profit_worst is not None else None),
        "probability_profit_disappears": prob_disappears,
        "history_samples_used": samples_n,
        "note": ("Probability of profit disappearing is a percentile-bracket "
                 "estimate using the historical distribution of worst observed "
                 "drift per cycle. With <20 cycles the estimate is coarse — "
                 "treat as a directional risk gauge."),
    }


# ---------------------------- entrypoints ------------------------------------

async def build_report(limit: int = 200) -> dict:
    """Headline report — stage timing + drift distribution + per-cycle rows."""
    cycles = await _list_closed_cycles(limit=limit)
    per_cycle: list[dict] = []
    for c in cycles:
        per_cycle.append(await per_cycle_report(c))
    durations_total = _total_duration_block(per_cycle)
    stage_agg = _stage_aggregates(per_cycle)
    drift_agg = _drift_aggregates(per_cycle)
    return {
        "phase": "Cycle Timing + Risk Decay (read-only)",
        "generated_at": now_iso(),
        "closed_cycles_used": len(per_cycle),
        "total_duration_s": durations_total,
        "stage_durations_s": stage_agg,
        "drift_distribution_pct": drift_agg,
        "per_cycle": per_cycle,
        "guardrails": {"execution_enabled": False, "wallet_enabled": False,
                       "transaction_signing": False, "autonomous_execution": False,
                       "fund_movement": False},
        "note": ("Drift is measured against Coinstore best_bid history "
                 "(orderbook_snapshots) anchored to each cycle's best_bid_at_quote."),
    }


async def forecast_now(captured_price: float, best_bid: float,
                       investment_usd: float,
                       taker_fee_pct: float = 0.20,
                       bdag_transfer_fee_base: float = 0.0) -> dict:
    """Public entrypoint: compute the risk-adjusted forecast for a new
    opportunity using the latest aggregate drift + duration history."""
    cycles = await _list_closed_cycles(limit=200)
    per_cycle: list[dict] = [await per_cycle_report(c) for c in cycles]
    drift_agg = _drift_aggregates(per_cycle)
    duration_block = _total_duration_block(per_cycle)
    f = forecast(captured_price, best_bid, investment_usd,
                 drift_agg=drift_agg, duration_block=duration_block,
                 taker_fee_pct=taker_fee_pct,
                 bdag_transfer_fee_base=bdag_transfer_fee_base)
    f["generated_at"] = now_iso()
    f["history_block"] = {"closed_cycles_used": len(per_cycle),
                          "duration": duration_block, "drift": drift_agg}
    f["guardrails"] = {"execution_enabled": False, "wallet_enabled": False,
                       "transaction_signing": False, "autonomous_execution": False,
                       "fund_movement": False}
    return f


# Convenience function for Operator Console integration
async def aggregate_only() -> dict:
    """Lightweight call (no per_cycle rows) used by the Operator Console."""
    cycles = await _list_closed_cycles(limit=200)
    per_cycle: list[dict] = [await per_cycle_report(c) for c in cycles]
    return {
        "closed_cycles_used": len(per_cycle),
        "total_duration_s": _total_duration_block(per_cycle),
        "stage_durations_s": _stage_aggregates(per_cycle),
        "drift_distribution_pct": _drift_aggregates(per_cycle),
    }
