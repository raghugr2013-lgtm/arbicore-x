"""Fresh-Cycle Opportunity Analytics (READ-ONLY).

The Fresh Cycle ROI model is the SOLE execution authority. This layer continuously
records the live fresh-cycle state (swap price, best bid/ask, fresh ROI, profitable
liquidity, max safe buy, GO/WAIT/NO_GO) into `fresh_cycle_observations`, derives
GO-window survivability from the stream, and answers the core question:

    "How often does a REAL executable fresh-cycle opportunity actually occur?"

so the operator has statistical evidence BEFORE any E5 automation. The recorder is
driven by the existing opportunity-gate monitor tick. No execution, no fund movement.
"""
import statistics
from datetime import datetime, timedelta, timezone

from core.models import new_id, now_iso
from services import db
from services.collector import collector


def _age(ts):
    if not ts:
        return None
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds()
    except (ValueError, TypeError):
        return None


def _between(a, b):
    try:
        return round((datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds(), 1)
    except (ValueError, TypeError):
        return None


# ---------------- recorder (called by the gate monitor every tick) ----------------
async def record(gate: dict):
    if not gate or not gate.get("available"):
        return
    dr = gate.get("dual_roi") or {}
    fc = dr.get("fresh_cycle") or {}
    rid, venue = gate.get("route_id"), gate.get("venue")
    best_ask = None
    m = (collector.cache.get(rid, {}) or {}).get(venue) or {}
    asks = ((m.get("orderbook") or {}).get("asks")) or []
    if asks:
        best_ask = asks[0][0]
    roi = fc.get("roi_pct")
    verdict = gate.get("gate_verdict")
    floor = gate.get("min_roi_pct")
    obs = {
        "id": new_id(), "route_id": rid, "route_name": gate.get("route_name"), "venue": venue,
        "live_swap_price": fc.get("buy_price"),
        "best_bid": gate.get("best_bid"), "best_ask": best_ask,
        "fresh_roi_pct": roi, "net_roi_pct": roi,
        "profitable_liquidity_quote": gate.get("profitable_liquidity_quote"),
        "max_safe_buy_usd": gate.get("max_safe_buy_usd"),
        "verdict": verdict,
        "fresh_go": verdict == "GO",
        "roi_above_floor": bool(roi is not None and floor is not None and roi >= floor),
        "floor_pct": floor,
        "created_at": now_iso(),
    }
    await db.fresh_cycle_observations.insert_one(obs)


# ---------------- GO-window derivation from the observation stream ----------------
def _finalize(cur, closed):
    rois = [r for r in cur["rois"] if r is not None]
    dur = _between(cur["start"], cur["end"]) if closed else _age(cur["start"])
    return {
        "start_time": cur["start"], "end_time": cur["end"] if closed else None,
        "duration_s": round(dur, 1) if dur is not None else None,
        "peak_roi_pct": max(rois) if rois else None,
        "avg_roi_pct": round(statistics.mean(rois), 3) if rois else None,
        "max_safe_buy_usd": max(cur["safe"]) if cur["safe"] else None,
        "venue": cur["venue"], "samples": cur["samples"],
        "status": "closed" if closed else "open",
    }


def _derive_windows(obs):
    windows, cur = [], None
    for o in obs:
        if o.get("fresh_go"):
            if cur is None:
                cur = {"start": o["created_at"], "end": o["created_at"], "venue": o["venue"],
                       "rois": [], "safe": [], "samples": 0}
            cur["rois"].append(o.get("fresh_roi_pct"))
            if o.get("max_safe_buy_usd") is not None:
                cur["safe"].append(o["max_safe_buy_usd"])
            cur["samples"] += 1
            cur["end"] = o["created_at"]
        elif cur is not None:
            windows.append(_finalize(cur, closed=True))
            cur = None
    if cur is not None:
        windows.append(_finalize(cur, closed=False))
    return windows


async def _observations(days):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    return await db.fresh_cycle_observations.find(
        {"created_at": {"$gte": since}}, {"_id": 0}, sort=[("created_at", 1)]).to_list(200000)


# ---------------- statistics ----------------
async def stats(days: int = 30) -> dict:
    obs = await _observations(days)
    n = len(obs)
    base = {"observations": n, "sample_window_days": days}
    if not n:
        return {**base, "empty": True,
                "note": "No fresh-cycle observations recorded yet — the monitor records one per ~20s tick."}
    rois = [o["fresh_roi_pct"] for o in obs if o.get("fresh_roi_pct") is not None]
    positive = [r for r in rois if r > 0]
    above_floor = [o for o in obs if o.get("roi_above_floor")]
    go = [o for o in obs if o.get("fresh_go")]
    windows = _derive_windows(obs)
    durations = [w["duration_s"] for w in windows if w["status"] == "closed" and w["duration_s"]]
    safe_in_go = [w["max_safe_buy_usd"] for w in windows if w.get("max_safe_buy_usd") is not None]
    first_at, last_at = obs[0]["created_at"], obs[-1]["created_at"]
    span_s = _between(first_at, last_at) or 0
    span_days = span_s / 86400 if span_s else 0
    return {
        **base,
        "first_observation_at": first_at, "last_observation_at": last_at,
        "observation_span_hours": round(span_s / 3600, 2),
        "pct_time_roi_positive": round(len(positive) / len(rois) * 100, 2) if rois else 0.0,
        "pct_time_roi_above_floor": round(len(above_floor) / n * 100, 2),
        "pct_time_go": round(len(go) / n * 100, 2),
        "avg_positive_roi_pct": round(statistics.mean(positive), 3) if positive else None,
        "max_roi_pct": max(rois) if rois else None,
        "floor_pct": obs[-1].get("floor_pct"),
        "go_windows_total": len(windows),
        "longest_go_window_s": max(durations) if durations else None,
        "avg_go_window_s": round(statistics.mean(durations), 1) if durations else None,
        "avg_max_safe_buy_usd_in_go_windows": round(statistics.mean(safe_in_go), 2) if safe_in_go else None,
        "go_windows_per_day": round(len(windows) / span_days, 2) if span_days > 0 else None,
        "go_windows_per_week": round(len(windows) / span_days * 7, 2) if span_days > 0 else None,
    }


async def survivability(days: int = 30, limit: int = 200) -> dict:
    obs = await _observations(days)
    windows = _derive_windows(obs)
    windows = list(reversed(windows))[:limit]
    return {"windows": windows, "total": len(windows),
            "note": "GO windows derived from consecutive fresh-cycle GO observations (~20s sampling granularity)."}


# ---------------- the core evidence answer ----------------
MIN_SPAN_H = 24       # need at least a day of continuous observation
MIN_OBS = 100         # ...and a meaningful sample

# Review-readiness gates (per operator brief — 2026-06-14)
TARGET_DAYS = 7
TARGET_OBS = 10_000
SIG_GO_WINDOWS = 30          # ≥30 closed GO windows → statistically significant evidence
SIG_PCT_ABOVE_FLOOR = 5.0    # ≥5% time ROI above floor with ≥MIN_OBS samples


async def observation_window() -> dict:
    """Lifetime observation accounting + review-readiness gates.

    Three independent triggers; whichever fires first opens the first formal
    review (per operator brief):
        (a) 7 continuous days of observation
        (b) 10,000 observations recorded
        (c) statistically significant GO-window evidence
    """
    n = await db.fresh_cycle_observations.count_documents({})
    first = await db.fresh_cycle_observations.find_one({}, {"_id": 0, "created_at": 1},
                                                      sort=[("created_at", 1)])
    last = await db.fresh_cycle_observations.find_one({}, {"_id": 0, "created_at": 1},
                                                     sort=[("created_at", -1)])
    start_at = (first or {}).get("created_at")
    last_at = (last or {}).get("created_at")
    if start_at:
        try:
            elapsed_s = (datetime.now(timezone.utc) - datetime.fromisoformat(start_at)).total_seconds()
        except (ValueError, TypeError):
            elapsed_s = 0.0
    else:
        elapsed_s = 0.0
    elapsed_days = elapsed_s / 86400 if elapsed_s else 0.0

    # statistically-significant GO-window evidence (uses the lifetime stream)
    lifetime = await stats(days=365)  # safe upper bound; TTL caps at 90d
    go_windows = lifetime.get("go_windows_total", 0) or 0
    pct_above = lifetime.get("pct_time_roi_above_floor", 0) or 0
    obs_for_stat = lifetime.get("observations", 0) or 0
    statistically_significant = bool(
        go_windows >= SIG_GO_WINDOWS or
        (obs_for_stat >= MIN_OBS and pct_above >= SIG_PCT_ABOVE_FLOOR)
    )

    days_trigger = elapsed_days >= TARGET_DAYS
    obs_trigger = n >= TARGET_OBS

    ready = bool(days_trigger or obs_trigger or statistically_significant)
    if days_trigger:
        which = "7-day observation window reached"
    elif obs_trigger:
        which = "10,000 observation count reached"
    elif statistically_significant:
        which = "statistically significant GO-window evidence reached"
    else:
        which = None

    pct = lambda v, t: round(min(100.0, (v / t) * 100), 2) if t else 0.0  # noqa: E731

    return {
        "phase": "Observation Window (read-only)",
        "observation_start_time": start_at,
        "last_observation_at": last_at,
        "observation_duration_seconds": round(elapsed_s, 1),
        "observation_duration_days": round(elapsed_days, 3),
        "observation_count": n,
        "target": {
            "days": TARGET_DAYS,
            "observations": TARGET_OBS,
            "significant_go_windows": SIG_GO_WINDOWS,
            "significant_pct_above_floor": SIG_PCT_ABOVE_FLOOR,
        },
        "progress": {
            "days_pct": pct(elapsed_days, TARGET_DAYS),
            "observations_pct": pct(n, TARGET_OBS),
            "go_windows_pct": pct(go_windows, SIG_GO_WINDOWS),
            "go_windows_total": go_windows,
            "pct_time_roi_above_floor": pct_above,
        },
        "triggers": {
            "days": days_trigger,
            "observations": obs_trigger,
            "statistically_significant": statistically_significant,
        },
        "ready_for_first_formal_review": ready,
        "review_trigger_satisfied": which,
        "note": ("System is in DATA-COLLECTION mode. The first formal review opens when ANY one of: "
                 "(a) 7 days of observation; (b) 10,000 observations; or (c) statistically significant "
                 "GO-window evidence. No execution, no fund movement, no Telegram, no E5."),
        "generated_at": now_iso(),
    }


# Formal recommendation taxonomy (per operator brief — used by the formal review)
def _formal_recommendation(s: dict, ow: dict) -> dict:
    if not ow.get("ready_for_first_formal_review"):
        return {
            "level": "Not Recommended",
            "rationale": ("Observation window not yet sufficient for a formal recommendation. "
                          "Continue recording."),
            "ready_for_formal_review": False,
        }
    above = s.get("pct_time_roi_above_floor", 0) or 0
    windows = s.get("go_windows_total", 0) or 0
    avg_dur = s.get("avg_go_window_s") or 0
    if above < 1 and windows < 3:
        level = "Not Recommended"
        rationale = ("Fresh ROI clears the floor <1% of the time and almost no GO windows "
                     "formed — the live swap price sits at/above the bid most of the time.")
    elif above < 5 or avg_dur < 60:
        level = "Occasional Manual Opportunity"
        rationale = ("Opportunities exist but are sporadic and/or windows too short for "
                     "reliable manual execution; automation premature.")
    elif above < 15:
        level = "Worth Monitoring"
        rationale = ("Material % of time spent above the floor with reasonable GO durations — "
                     "keep observing for another window before committing to automation.")
    else:
        level = "Suitable For Automation"
        rationale = ("Fresh ROI clears the floor frequently with sustained GO durations — "
                     "E5 automation is statistically justified (still requires whitelist + "
                     "kill-switch + per-cycle cap before going live).")
    return {"level": level, "rationale": rationale, "ready_for_formal_review": True}


async def evidence(days: int = 30) -> dict:
    s = await stats(days)
    n = s.get("observations", 0)
    span_h = s.get("observation_span_hours", 0) or 0
    above = s.get("pct_time_roi_above_floor", 0) or 0
    per_day = s.get("go_windows_per_day")

    if s.get("empty") or n < MIN_OBS or span_h < MIN_SPAN_H:
        verdict = "INSUFFICIENT_OBSERVATION_WINDOW"
        recommendation = (f"Keep observing. Only {n} observations over {span_h}h so far — a credible answer needs "
                          f"≥{MIN_OBS} observations across ≥{MIN_SPAN_H}h (ideally ≥7 continuous days). E5 automation "
                          f"is NOT justified on this sample.")
    elif above < 1:
        verdict = "RARE"
        recommendation = ("Fresh executable opportunities are RARE — fresh ROI clears the floor <1% of the time. "
                          "Automation is NOT justified; the live swap price sits at/above the bid most of the time.")
    elif above < 10:
        verdict = "OCCASIONAL"
        recommendation = ("Fresh opportunities are OCCASIONAL. Automation could be justified ONLY with tight GO-window "
                          "capture and low fixed costs; validate window durations are long enough to execute.")
    else:
        verdict = "FREQUENT"
        recommendation = ("Fresh opportunities are FREQUENT enough to consider automation — proceed to the E5 control "
                          "build (whitelist + kill-switch + per-cycle cap) and a manual verification loop first.")

    ow = await observation_window()
    formal = _formal_recommendation(s, ow)

    return {
        "phase": "Fresh-Cycle Opportunity Evidence (read-only)",
        "question": "How often does a real executable fresh-cycle opportunity actually occur?",
        "observation_window": ow,
        "formal_recommendation": formal,
        "answer": {
            "observations": n,
            "observation_span_hours": span_h,
            "pct_time_fresh_roi_positive": s.get("pct_time_roi_positive"),
            "pct_time_fresh_roi_above_floor": above,
            "pct_time_go": s.get("pct_time_go"),
            "avg_positive_roi_pct": s.get("avg_positive_roi_pct"),
            "max_roi_pct": s.get("max_roi_pct"),
            "go_windows_total": s.get("go_windows_total"),
            "go_windows_per_day": per_day,
            "go_windows_per_week": s.get("go_windows_per_week"),
            "avg_go_window_s": s.get("avg_go_window_s"),
            "longest_go_window_s": s.get("longest_go_window_s"),
            "avg_max_safe_buy_usd_in_go_windows": s.get("avg_max_safe_buy_usd_in_go_windows"),
        },
        "frequency_verdict": verdict,
        "automation_recommendation": recommendation,
        "generated_at": now_iso(),
        "note": "Read-only statistical evidence. No execution, no fund movement. E5 stays BLOCKED.",
    }


async def analytics(days: int = 30) -> dict:
    return {
        "observation_window": await observation_window(),
        "statistics": await stats(days),
        "survivability": await survivability(days),
        "evidence": await evidence(days),
    }
