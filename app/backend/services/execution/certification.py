"""Phase E4 — Shadow Certification Report (READ-ONLY analytics).

Evidence-based readiness assessment computed purely from the recorded SHADOW
execution cycles (mode='shadow'). Summarizes throughput, recovery success,
expected-vs-realized profit, profit-after-fees distribution, per-venue and
per-route performance, and a recommended safe micro-capital cycle size to inform
(but not authorize) E5. No execution, no fund movement.
"""
import statistics

from services import db
from services.execution import config, venue_registry

TERMINAL_OK = "COMPLETE"


def _ever_stuck(c):
    return any(str(h.get("state", "")).startswith("STUCK_") for h in c.get("history", []))


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.mean(xs), 4) if xs else None


def _bucket(pnl):
    if pnl is None:
        return "unknown"
    if pnl < 0:
        return "loss (<$0)"
    if pnl < 2:
        return "$0–2"
    if pnl < 5:
        return "$2–5"
    if pnl < 10:
        return "$5–10"
    return "$10+"


BUCKETS = ["loss (<$0)", "$0–2", "$2–5", "$5–10", "$10+"]


def _recommended_size(completed, total, max_cycle):
    n = len(completed)
    realized = [c.get("realized_shadow_pnl_quote") for c in completed
                if c.get("realized_shadow_pnl_quote") is not None]
    if n < 3 or not realized:
        return {"recommended_usd": round(min(5.0, max_cycle), 2), "confidence": "insufficient_data",
                "rationale": f"only {n} completed shadow cycle(s) with realized PnL (need ≥3) — "
                             f"gather more shadow runs before sizing."}
    avg_real = statistics.mean(realized)
    pos_rate = sum(1 for r in realized if r > 0) / len(realized)
    completion_rate = n / total if total else 0
    if avg_real <= 0:
        return {"recommended_usd": 0.0, "confidence": "blocked",
                "rationale": f"average realized PnL is ${avg_real:.2f}/cycle (non-positive) over "
                             f"{n} cycles — DO NOT proceed to micro-capital."}
    factor = max(0.0, min(1.0, completion_rate)) * max(0.0, min(1.0, pos_rate))
    rec = round(min(max_cycle * factor, max_cycle), 2)
    if rec < 5:
        rec = round(min(5.0, max_cycle), 2)
    conf = "high" if (n >= 10 and completion_rate >= 0.9 and pos_rate >= 0.8) else "medium"
    return {"recommended_usd": rec, "confidence": conf,
            "rationale": f"completion {completion_rate*100:.0f}%, profitable {pos_rate*100:.0f}%, "
                         f"avg realized ${avg_real:.2f}/cycle across {n} completed cycles; "
                         f"capped at certification max_cycle ${max_cycle}."}


async def report(since: str = None) -> dict:
    q = {"mode": "shadow"}
    if since:
        q["created_at"] = {"$gte": since}
    cycles = await db.execution_cycles.find(q, {"_id": 0}).to_list(5000)
    total = len(cycles)
    completed = [c for c in cycles if c["state"] == TERMINAL_OK]
    aborted = [c for c in cycles if c["state"] == "ABORTED"]
    currently_stuck = [c for c in cycles if c.get("stuck")]
    ever_stuck = [c for c in cycles if _ever_stuck(c)]
    recovered = [c for c in ever_stuck if not c.get("stuck")]
    recovery_failures = [c for c in ever_stuck if c["state"] == "ABORTED"]
    recovery_rate = round(len(recovered) / len(ever_stuck) * 100, 1) if ever_stuck else None

    exp = [c.get("expected_profit_quote") for c in completed]
    real = [c.get("realized_shadow_pnl_quote") for c in completed]
    variances = [round((c.get("realized_shadow_pnl_quote") or 0) - (c.get("expected_profit_quote") or 0), 4)
                 for c in completed
                 if c.get("realized_shadow_pnl_quote") is not None and c.get("expected_profit_quote") is not None]

    dist = {b: 0 for b in BUCKETS}
    dist["unknown"] = 0
    for c in completed:
        dist[_bucket(c.get("realized_shadow_pnl_quote"))] += 1
    real_vals = [r for r in real if r is not None]
    profit_summary = {
        "count": len(real_vals),
        "min": round(min(real_vals), 4) if real_vals else None,
        "max": round(max(real_vals), 4) if real_vals else None,
        "mean": _mean(real_vals),
        "median": round(statistics.median(real_vals), 4) if real_vals else None,
        "distribution": dist,
    }

    # per-venue / per-route performance
    def perf(items, key, label_key=None):
        groups = {}
        for c in items:
            k = c.get(key) or "—"
            groups.setdefault(k, []).append(c)
        out = []
        for k, cs in groups.items():
            comp = [c for c in cs if c["state"] == TERMINAL_OK]
            comp_real = [c.get("realized_shadow_pnl_quote") for c in comp]
            out.append({
                "key": k,
                "label": (cs[0].get(label_key) if label_key else str(k).upper()) or str(k),
                "cycles": len(cs), "completed": len(comp),
                "ever_stuck": sum(1 for c in cs if _ever_stuck(c)),
                "completion_rate_pct": round(len(comp) / len(cs) * 100, 1) if cs else None,
                "avg_expected": _mean([c.get("expected_profit_quote") for c in comp]),
                "avg_realized": _mean(comp_real),
                "avg_variance": _mean([(c.get("realized_shadow_pnl_quote") or 0) - (c.get("expected_profit_quote") or 0)
                                       for c in comp if c.get("realized_shadow_pnl_quote") is not None]),
            })
        out.sort(key=lambda r: -(r["completed"]))
        return out

    cfg = await config.get_config()
    max_cycle = cfg["limits"]["max_cycle_usd"]
    role_map = await venue_registry.get_role_map()
    venue_perf = perf(cycles, "sell_venue")
    for v in venue_perf:
        v["role"] = role_map.get(v["key"], "—")

    rec = _recommended_size(completed, total, max_cycle)

    # overall verdict
    if total < 3:
        verdict = "INSUFFICIENT_DATA"
    elif rec["confidence"] == "blocked":
        verdict = "NOT_READY"
    elif rec["confidence"] == "high":
        verdict = "READY_FOR_MICROCAPITAL_REVIEW"
    else:
        verdict = "PROMISING_NEEDS_MORE_DATA"

    return {
        "phase": "E4 — Shadow Certification Report",
        "verdict": verdict,
        "generated_for_max_cycle_usd": max_cycle,
        "throughput": {
            "total_shadow_cycles": total, "completed": len(completed),
            "aborted": len(aborted), "currently_stuck": len(currently_stuck),
            "ever_stuck": len(ever_stuck),
            "completion_rate_pct": round(len(completed) / total * 100, 1) if total else None,
        },
        "recovery": {
            "ever_stuck": len(ever_stuck), "recovered": len(recovered),
            "still_stuck": len(currently_stuck), "recovery_failures": len(recovery_failures),
            "recovery_success_rate_pct": recovery_rate,
        },
        "profit": {
            "expected_total_quote": round(sum(e for e in exp if e is not None), 4),
            "realized_total_quote": round(sum(r for r in real_vals), 4) if real_vals else 0,
            "average_variance_quote": _mean(variances),
            "average_expected_per_cycle": _mean(exp),
            "average_realized_per_cycle": _mean(real_vals),
            "after_fees_distribution": profit_summary,
        },
        "venue_performance": venue_perf,
        "route_performance": perf(cycles, "route_id", "route_name"),
        "recommended_safe_cycle_size": rec,
        "note": "Evidence-based readiness assessment from recorded shadow cycles only. "
                "Informational — does NOT authorize micro-capital execution. No fund movement.",
    }
