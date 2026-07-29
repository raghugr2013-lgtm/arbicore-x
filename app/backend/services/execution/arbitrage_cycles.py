"""Arbitrage Cycle Evidence Records (READ-ONLY tracking; no execution).

Every real BDAG → Coinstore cycle the operator runs is tracked here. The
12-field evidence record per cycle is the foundation for the future risk
engine and automation decisions.

State machine:
  DRAFT → QUOTED → SWAP_SUBMITTED → SWAP_CONFIRMED → BDAG_RECEIVED
        → TRANSFER_SUBMITTED → DEPOSIT_CONFIRMED → SOLD → WITHDRAWN → CLOSED
  Any pre-SWAP_SUBMITTED state can also be ABORTED.

No signing, no submission, no fund movement. Operator stamps each transition.
"""
from core.models import new_id, now_iso
from services import db

COLL = "arbitrage_cycles"
MILESTONES = [
    "quote_at", "swap_submitted_at", "swap_confirmed_at",
    "bdag_received_at", "transfer_submitted_at", "deposit_confirmed_at",
    "sell_executed_at", "withdrawal_completed_at",
]
TERMINAL = ("CLOSED", "ABORTED")


async def ensure_indexes():
    await db.db[COLL].create_index([("created_at", -1)])
    await db.db[COLL].create_index([("state", 1), ("created_at", -1)])


async def create(input_amount: float, quote_price: float, bdag_expected: float,
                 best_bid: float, expected_roi_pct: float, note: str = None) -> dict:
    doc = {
        "id": new_id(),
        "state": "QUOTED",
        "input_amount_usd": float(input_amount),
        "quote_price": float(quote_price),
        "quote_at": now_iso(),
        "bdag_expected": float(bdag_expected),
        "best_bid_at_quote": float(best_bid) if best_bid is not None else None,
        "expected_roi_pct": float(expected_roi_pct) if expected_roi_pct is not None else None,
        **{m: None for m in MILESTONES if m != "quote_at"},
        "actuals": {"bdag_received": None, "sell_price_avg": None,
                    "usdt_received": None, "net_profit_usd": None,
                    "realized_roi_pct": None, "total_cycle_duration_s": None,
                    "drift_pct_at_sell": None},
        "note": note,
        "aborted_reason": None,
        "created_at": now_iso(), "updated_at": now_iso(),
    }
    await db.db[COLL].insert_one(dict(doc))
    return doc


async def transition(cycle_id: str, to_state: str, **fields) -> dict:
    cycle = await db.db[COLL].find_one({"id": cycle_id}, {"_id": 0})
    if not cycle:
        raise ValueError("cycle not found")
    if cycle["state"] in TERMINAL:
        raise ValueError(f"cycle is terminal ({cycle['state']})")
    update = {"state": to_state, "updated_at": now_iso()}
    # auto-stamp the matching milestone if not set
    stamp_map = {
        "SWAP_SUBMITTED": "swap_submitted_at", "SWAP_CONFIRMED": "swap_confirmed_at",
        "BDAG_RECEIVED": "bdag_received_at", "TRANSFER_SUBMITTED": "transfer_submitted_at",
        "DEPOSIT_CONFIRMED": "deposit_confirmed_at", "SOLD": "sell_executed_at",
        "WITHDRAWN": "withdrawal_completed_at",
    }
    if to_state in stamp_map and not cycle.get(stamp_map[to_state]):
        update[stamp_map[to_state]] = now_iso()
    # allow caller to inject actuals + arbitrary fields
    for k, v in (fields or {}).items():
        if k.startswith("actuals."):
            actuals = dict(update.get("actuals") or cycle.get("actuals") or {})
            actuals[k.split(".", 1)[1]] = v
            update["actuals"] = actuals
        elif k in MILESTONES or k in ("note", "aborted_reason"):
            update[k] = v
    # close-out: compute duration when reaching CLOSED
    if to_state == "CLOSED":
        try:
            from datetime import datetime
            t0 = datetime.fromisoformat(cycle["quote_at"])
            tN = datetime.fromisoformat(update.get("withdrawal_completed_at")
                                        or cycle.get("withdrawal_completed_at")
                                        or now_iso())
            dur = round((tN - t0).total_seconds(), 1)
            actuals = dict(update.get("actuals") or cycle.get("actuals") or {})
            actuals["total_cycle_duration_s"] = dur
            update["actuals"] = actuals
        except (ValueError, TypeError):
            pass
    await db.db[COLL].update_one({"id": cycle_id}, {"$set": update})
    return await db.db[COLL].find_one({"id": cycle_id}, {"_id": 0})


async def abort(cycle_id: str, reason: str = None) -> dict:
    return await transition(cycle_id, "ABORTED", aborted_reason=reason or "operator")


async def get(cycle_id: str) -> dict:
    return await db.db[COLL].find_one({"id": cycle_id}, {"_id": 0})


async def list_cycles(limit: int = 50) -> list:
    return await db.db[COLL].find({}, {"_id": 0},
                                  sort=[("created_at", -1)]).to_list(max(1, min(limit, 200)))


async def stats() -> dict:
    docs = await db.db[COLL].find({"state": "CLOSED"}, {"_id": 0}).to_list(200)
    if not docs:
        return {"closed_count": 0, "note": "No closed cycles yet — record one to seed the risk engine."}
    import statistics
    dur = [d["actuals"].get("total_cycle_duration_s")
           for d in docs if (d.get("actuals") or {}).get("total_cycle_duration_s")]
    rois = [d["actuals"].get("realized_roi_pct")
            for d in docs if (d.get("actuals") or {}).get("realized_roi_pct") is not None]
    drifts = [d["actuals"].get("drift_pct_at_sell")
              for d in docs if (d.get("actuals") or {}).get("drift_pct_at_sell") is not None]
    s = {"closed_count": len(docs)}
    if dur:
        s["duration_s"] = {"avg": round(statistics.mean(dur), 1),
                           "median": round(statistics.median(dur), 1),
                           "p95": round(sorted(dur)[max(0, int(len(dur) * 0.95) - 1)], 1),
                           "worst": max(dur)}
    if rois:
        s["realized_roi_pct"] = {"avg": round(statistics.mean(rois), 3),
                                 "median": round(statistics.median(rois), 3),
                                 "worst": min(rois), "best": max(rois)}
    if drifts:
        s["drift_pct_at_sell"] = {"avg": round(statistics.mean(drifts), 3),
                                  "worst": max(drifts), "best": min(drifts)}
    return s


async def replay_report() -> dict:
    """Cycle Replay Report — per-closed-cycle row + aggregate decision metrics.
    Drift % = (best_bid_at_sell - best_bid_at_quote) / best_bid_at_quote * 100.
    Profit expected = input_amount * expected_roi_pct / 100 (if both set).
    """
    import statistics
    docs = await db.db[COLL].find({"state": "CLOSED"}, {"_id": 0},
                                  sort=[("created_at", -1)]).to_list(500)
    rows = []
    for d in docs:
        a = d.get("actuals") or {}
        bid_q = d.get("best_bid_at_quote")
        bid_s = a.get("best_bid_at_sell")
        drift_pct = (
            round((bid_s - bid_q) / bid_q * 100, 4)
            if (bid_q and bid_s) else a.get("drift_pct_at_sell")
        )
        profit_exp = (
            round(d["input_amount_usd"] * (d.get("expected_roi_pct") or 0) / 100, 6)
            if d.get("expected_roi_pct") is not None else None
        )
        rows.append({
            "id": d["id"], "quote_at": d.get("quote_at"),
            "withdrawal_completed_at": d.get("withdrawal_completed_at"),
            "input_amount_usd": d["input_amount_usd"],
            "quote_price": d.get("quote_price"),
            "best_bid_at_quote": bid_q, "best_bid_at_sell": bid_s,
            "expected_roi_pct": d.get("expected_roi_pct"),
            "realized_roi_pct": a.get("realized_roi_pct"),
            "profit_expected_usd": profit_exp,
            "profit_realized_usd": a.get("net_profit_usd"),
            "duration_s": a.get("total_cycle_duration_s"),
            "drift_pct": drift_pct,
            "won": (a.get("realized_roi_pct") is not None and a["realized_roi_pct"] > 0),
            "note": d.get("note"),
        })
    n = len(rows)
    wins = [r for r in rows if r["won"]]
    rois = [r["realized_roi_pct"] for r in rows if r["realized_roi_pct"] is not None]
    durs = [r["duration_s"] for r in rows if r["duration_s"] is not None]
    drifts = [r["drift_pct"] for r in rows if r["drift_pct"] is not None]
    agg = {
        "closed_count": n,
        "wins": len(wins),
        "win_rate_pct": round(len(wins) / n * 100, 2) if n else None,
        "avg_realized_roi_pct": round(statistics.mean(rois), 3) if rois else None,
        "median_realized_roi_pct": round(statistics.median(rois), 3) if rois else None,
        "avg_duration_s": round(statistics.mean(durs), 1) if durs else None,
        "median_duration_s": round(statistics.median(durs), 1) if durs else None,
        "p95_duration_s": round(sorted(durs)[max(0, int(len(durs) * 0.95) - 1)], 1) if durs else None,
        "worst_drift_pct": min(drifts) if drifts else None,
        "best_drift_pct": max(drifts) if drifts else None,
        "avg_drift_pct": round(statistics.mean(drifts), 3) if drifts else None,
    }
    return {
        "phase": "Cycle Replay Report (read-only foundation for future automation)",
        "generated_at": now_iso(),
        "aggregate": agg,
        "rows": rows,
        "note": "Drift % uses best_bid_at_sell (recorded at SOLD transition) vs best_bid_at_quote.",
    }


async def status() -> dict:
    return {"phase": "Arbitrage Cycle Evidence (read-only tracking)",
            "generated_at": now_iso(),
            "cycles": await list_cycles(20),
            "statistics": await stats(),
            "milestones": MILESTONES,
            "note": "No signing, no submission, no fund movement. Operator stamps each transition."}
