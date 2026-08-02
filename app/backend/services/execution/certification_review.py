"""Phase E4.5 — Shadow Certification Review package (READ-ONLY evidence layer).

Composes a comprehensive, 10-section certification review from the recorded
SHADOW cycles of the most recently completed Shadow Certification Campaign. Every
recommendation carries the supporting evidence + the threshold that produced it,
so the verdict is fully transparent and auditable.

Final recommendation ∈ {READY_FOR_MICROCAPITAL_REVIEW, NEEDS_MORE_DATA, NOT_READY}.

This is reporting only. It does NOT authorize execution. No trading, no wallet,
no withdrawals, no fund movement. E5 stays blocked until the recommendation is
READY_FOR_MICROCAPITAL_REVIEW and the package is explicitly reviewed & approved.
"""
import statistics
from datetime import datetime

from core.models import now_iso
from services import db
from services.execution import certification, config

# ---- strict micro-capital readiness criteria (the bar to risk real money) ----
# NOTE: these are deliberately STRICTER than the campaign auto-stop breach guards
# (max_stuck 40% / max_variance 35% / min_recovery 70%), which only abort a run.
READINESS_CRITERIA = {
    "min_completed_cycles": 20,        # sample-size gate
    "require_positive_avg_realized": True,
    "min_completion_rate_pct": 90.0,
    "min_recovery_success_rate_pct": 95.0,
    "max_stuck_rate_pct": 10.0,
    "max_variance_pct": 15.0,
    "min_profitable_rate_pct": 80.0,
}

TERMINAL_OK = "COMPLETE"
STUCK_LABEL = {
    "STUCK_WAITING_FOR_BDAG": "BlockDAG portal did not deliver BDAG (pay→receipt leg)",
    "STUCK_WAITING_DEPOSIT": "Exchange deposit not credited (transfer→deposit leg)",
    "STUCK_SELL": "Spot sell order did not fill (sell leg)",
    "STUCK_WITHDRAWAL": "USDT withdrawal not confirmed (settlement leg)",
    "MANUAL_REVIEW": "Held for manual review (hard-freeze / operator hold)",
}


def _secs(a, b):
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except (ValueError, TypeError):
        return None


def _ever_stuck(c):
    return any(str(h.get("state", "")).startswith("STUCK_") for h in c.get("history", []))


def _stuck_states(c):
    return [h["state"] for h in c.get("history", []) if str(h.get("state", "")).startswith("STUCK_")]


def _round(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else v


# ---------------- campaign selection ----------------

TERMINAL_CAMPAIGN = {"completed", "stopped_breach", "stopped_manual"}


async def latest_completed_campaign():
    # Authoritative certification view: only campaigns that actually ran cycles.
    # Excludes dummy / zero-cycle campaigns (e.g. start→stop test fixtures that
    # otherwise pollute shadow_campaigns and shadow the real completed campaign).
    return await db.shadow_campaigns.find_one(
        {"status": {"$in": list(TERMINAL_CAMPAIGN)}, "completed_count": {"$gt": 0}},
        {"_id": 0}, sort=[("created_at", -1)])


async def _fetch_cycles(campaign):
    q = {"mode": "shadow", "created_at": {"$gte": campaign["start_at"]}}
    if campaign.get("ended_at"):
        q["created_at"]["$lte"] = campaign["ended_at"]
    return await db.execution_cycles.find(q, {"_id": 0}).to_list(5000)


# ---------------- criteria evaluation ----------------

def _crit(name, status, actual, threshold, severity, note=""):
    return {"criterion": name, "status": status, "actual": actual,
            "threshold": threshold, "severity": severity, "note": note}


def _evaluate(metrics):
    completed = metrics["completed"]
    avg_real = metrics["avg_realized_per_cycle"]
    completion = metrics["completion_rate_pct"]
    recovery = metrics["recovery_success_rate_pct"]
    ever_stuck = metrics["ever_stuck"]
    stuck_rate = metrics["stuck_rate_pct"]
    variance_pct = metrics["variance_pct"]
    profitable = metrics["profitable_rate_pct"]
    c = READINESS_CRITERIA
    out = []

    # gate — sample size
    out.append(_crit("Sample size (completed cycles)",
                     "PASS" if completed >= c["min_completed_cycles"] else "FAIL",
                     f"{completed} completed", f"≥ {c['min_completed_cycles']} completed", "gate",
                     "Enough successful cycles to trust the statistics."))

    # hard — net profitability
    if avg_real is None:
        out.append(_crit("Net profitability (avg realized)", "N/A", "n/a", "> $0 / cycle", "hard",
                         "No completed cycles with realized PnL yet."))
    else:
        out.append(_crit("Net profitability (avg realized)",
                         "PASS" if avg_real > 0 else "FAIL",
                         f"${avg_real:.2f} / cycle", "> $0 / cycle", "hard",
                         "Average shadow PnL must be net-positive after fees."))

    # soft — completion rate
    if completion is None:
        out.append(_crit("Completion rate", "N/A", "n/a", f"≥ {c['min_completion_rate_pct']}%", "soft"))
    else:
        out.append(_crit("Completion rate",
                         "PASS" if completion >= c["min_completion_rate_pct"] else "FAIL",
                         f"{completion}%", f"≥ {c['min_completion_rate_pct']}%", "soft",
                         "Share of started cycles that reached COMPLETE."))

    # hard — recovery success (N/A when nothing got stuck = favorable)
    if ever_stuck == 0:
        out.append(_crit("Recovery success rate", "N/A", "no stuck cycles",
                         f"≥ {c['min_recovery_success_rate_pct']}%", "hard",
                         "No stuck cycles occurred — recovery path was never exercised (favorable)."))
    elif recovery is None:
        out.append(_crit("Recovery success rate", "N/A", "n/a",
                         f"≥ {c['min_recovery_success_rate_pct']}%", "hard"))
    else:
        out.append(_crit("Recovery success rate",
                         "PASS" if recovery >= c["min_recovery_success_rate_pct"] else "FAIL",
                         f"{recovery}%", f"≥ {c['min_recovery_success_rate_pct']}%", "hard",
                         "Stuck cycles that auto-recovered vs aborted."))

    # hard — stuck rate
    out.append(_crit("Stuck-cycle rate",
                     "PASS" if stuck_rate <= c["max_stuck_rate_pct"] else "FAIL",
                     f"{stuck_rate}%", f"≤ {c['max_stuck_rate_pct']}%", "hard",
                     "Share of cycles that ever entered a STUCK_ state."))

    # hard — variance
    if variance_pct is None:
        out.append(_crit("PnL variance (|avg var| / avg expected)", "N/A", "n/a",
                         f"≤ {c['max_variance_pct']}%", "hard",
                         "Need ≥3 completed cycles to measure variance."))
    else:
        out.append(_crit("PnL variance (|avg var| / avg expected)",
                         "PASS" if variance_pct <= c["max_variance_pct"] else "FAIL",
                         f"{variance_pct}%", f"≤ {c['max_variance_pct']}%", "hard",
                         "How far realized PnL drifts from expected."))

    # soft — profitable rate
    if profitable is None:
        out.append(_crit("Profitable-cycle rate", "N/A", "n/a", f"≥ {c['min_profitable_rate_pct']}%", "soft"))
    else:
        out.append(_crit("Profitable-cycle rate",
                         "PASS" if profitable >= c["min_profitable_rate_pct"] else "FAIL",
                         f"{profitable}%", f"≥ {c['min_profitable_rate_pct']}%", "soft",
                         "Share of completed cycles with positive realized PnL."))
    return out


def _recommend(criteria, total):
    if total == 0:
        return "NEEDS_MORE_DATA", ["No shadow cycles were recorded in the campaign window."], []
    hard_fail = [c for c in criteria if c["severity"] == "hard" and c["status"] == "FAIL"]
    other_fail = [c for c in criteria if c["severity"] in ("soft", "gate") and c["status"] == "FAIL"]
    if hard_fail:
        return "NOT_READY", [f"{c['criterion']}: {c['actual']} (needs {c['threshold']})" for c in hard_fail], \
            [f"{c['criterion']}: {c['actual']} (needs {c['threshold']})" for c in other_fail]
    if other_fail:
        return "NEEDS_MORE_DATA", [], \
            [f"{c['criterion']}: {c['actual']} (needs {c['threshold']})" for c in other_fail]
    return "READY_FOR_MICROCAPITAL_REVIEW", [], []


# ---------------- package builder ----------------

async def build(campaign: dict, report: dict = None, cycles: list = None) -> dict:
    if report is None:
        report = campaign.get("final_report") or await certification.report(since=campaign["start_at"])
    if cycles is None:
        cycles = await _fetch_cycles(campaign)

    tp, rc, pf = report["throughput"], report["recovery"], report["profit"]
    venue_perf = report.get("venue_performance", [])
    route_perf = report.get("route_performance", [])
    rec_size = report["recommended_safe_cycle_size"]
    cfg = await config.get_config()
    max_cycle = report.get("generated_for_max_cycle_usd", cfg["limits"]["max_cycle_usd"])

    total = tp["total_shadow_cycles"]
    completed_cycles = [c for c in cycles if c["state"] == TERMINAL_OK]
    realized = [c.get("realized_shadow_pnl_quote") for c in completed_cycles
                if c.get("realized_shadow_pnl_quote") is not None]
    profitable_rate = round(sum(1 for r in realized if r > 0) / len(realized) * 100, 1) if realized else None

    avg_var = pf["average_variance_quote"]
    avg_exp = pf["average_expected_per_cycle"]
    variance_pct = round(abs(avg_var) / avg_exp * 100, 1) if (avg_var is not None and avg_exp) else None
    stuck_rate_pct = round(tp["ever_stuck"] / total * 100, 1) if total else 0.0

    metrics = {
        "completed": tp["completed"],
        "avg_realized_per_cycle": pf["average_realized_per_cycle"],
        "completion_rate_pct": tp["completion_rate_pct"],
        "recovery_success_rate_pct": rc["recovery_success_rate_pct"],
        "ever_stuck": tp["ever_stuck"],
        "stuck_rate_pct": stuck_rate_pct,
        "variance_pct": variance_pct,
        "profitable_rate_pct": profitable_rate,
    }
    criteria = _evaluate(metrics)
    recommendation, blocking, gaps = _recommend(criteria, total)
    passed = sum(1 for c in criteria if c["status"] == "PASS")
    failed = sum(1 for c in criteria if c["status"] == "FAIL")
    na = sum(1 for c in criteria if c["status"] == "N/A")

    # ---- Section 3 + 8: stuck-cycle analysis & failure modes ----
    by_state = {}
    reroute_count = 0
    for c in cycles:
        for d in c.get("shadow_decisions", []):
            if d.get("action") == "recovery_reroute":
                reroute_count += 1
        if not _ever_stuck(c):
            continue
        outcome = ("recovered" if c["state"] == TERMINAL_OK
                   else "aborted" if c["state"] == "ABORTED"
                   else "still_stuck")
        # measure time spent in each stuck segment
        hist = c.get("history", [])
        for i, h in enumerate(hist):
            st = h.get("state", "")
            if not str(st).startswith("STUCK_"):
                continue
            end = hist[i + 1]["ts"] if i + 1 < len(hist) else c.get("updated_at")
            dur = _secs(h["ts"], end)
            g = by_state.setdefault(st, {"state": st, "label": STUCK_LABEL.get(st, st),
                                         "count": 0, "recovered": 0, "aborted": 0,
                                         "still_stuck": 0, "durations": []})
            g["count"] += 1
            g[outcome] = g.get(outcome, 0) + 1
            if dur is not None:
                g["durations"].append(dur)

    stuck_by_state = []
    for st, g in by_state.items():
        durs = g.pop("durations")
        g["avg_seconds_stuck"] = round(statistics.mean(durs), 1) if durs else None
        g["recommended_action_seen"] = next(
            (c.get("recommended_action") for c in cycles
             if st in _stuck_states(c) and c.get("recommended_action")), None)
        stuck_by_state.append(g)
    stuck_by_state.sort(key=lambda g: -g["count"])

    failure_modes = []
    for g in stuck_by_state:
        sev = "high" if g["aborted"] > 0 else ("medium" if g["still_stuck"] > 0 else "low")
        failure_modes.append({
            "mode": g["label"], "stuck_state": g["state"], "occurrences": g["count"],
            "recovered": g["recovered"], "aborted": g["aborted"], "still_stuck": g["still_stuck"],
            "severity": sev,
            "mitigation": ("Auto-recovery reroute to a gate-open venue succeeded in most cases."
                           if g["recovered"] >= g["aborted"]
                           else "Recovery did not complete — investigate before risking capital."),
        })
    if rc["recovery_failures"] > 0:
        failure_modes.append({
            "mode": "Unrecovered stuck cycle (aborted while stuck)",
            "stuck_state": "ABORTED", "occurrences": rc["recovery_failures"],
            "recovered": 0, "aborted": rc["recovery_failures"], "still_stuck": 0,
            "severity": "high",
            "mitigation": "A stuck cycle could not be auto-recovered and was aborted — a hard blocker for micro-capital.",
        })

    # ---- best / worst completed cycle ----
    def _cyc_brief(c):
        return {"cycle_id": c["id"][:8], "sell_venue": c.get("sell_venue"),
                "expected": _round(c.get("expected_profit_quote")),
                "realized": _round(c.get("realized_shadow_pnl_quote"))}
    comp_with_real = [c for c in completed_cycles if c.get("realized_shadow_pnl_quote") is not None]
    best = max(comp_with_real, key=lambda c: c["realized_shadow_pnl_quote"], default=None)
    worst = min(comp_with_real, key=lambda c: c["realized_shadow_pnl_quote"], default=None)

    # ---- venue comparison (Coinstore vs BitMart) ----
    vmap = {v["key"]: v for v in venue_perf}

    def _venue_row(key):
        v = vmap.get(key)
        if not v:
            return {"key": key, "label": key.upper(), "role": "—", "cycles": 0, "completed": 0,
                    "ever_stuck": 0, "completion_rate_pct": None, "avg_expected": None,
                    "avg_realized": None, "avg_variance": None, "no_data": True}
        return {**v, "no_data": False}

    coinstore = _venue_row("coinstore")
    bitmart = _venue_row("bitmart")
    other_venues = [v for v in venue_perf if v["key"] not in ("coinstore", "bitmart")]

    sections = [
        {
            "title": "1. Final Verdict",
            "verdict": recommendation,
            "headline": _verdict_headline(recommendation),
            "campaign_id": campaign["id"], "campaign_status": campaign.get("status"),
            "window": {"start": campaign["start_at"], "end": campaign.get("ended_at")},
            "target_completed": campaign.get("target_completed"),
            "completed": tp["completed"], "total_cycles": total,
            "breach_reason": campaign.get("breach_reason"),
        },
        {
            "title": "2. Recovery Statistics",
            "ever_stuck": rc["ever_stuck"], "recovered": rc["recovered"],
            "still_stuck": rc["still_stuck"], "recovery_failures": rc["recovery_failures"],
            "recovery_success_rate_pct": rc["recovery_success_rate_pct"],
            "auto_reroutes_observed": reroute_count,
            "evidence": [_ev("Recovery success rate",
                             f"{rc['recovery_success_rate_pct']}%" if rc["recovery_success_rate_pct"] is not None
                             else "n/a (no stuck cycles)",
                             f"≥ {READINESS_CRITERIA['min_recovery_success_rate_pct']}%",
                             _status_for("recovery", criteria)),
                         _ev("Recovery failures (aborted while stuck)", rc["recovery_failures"], "= 0",
                             "PASS" if rc["recovery_failures"] == 0 else "FAIL")],
            "narrative": (f"{rc['recovered']} of {rc['ever_stuck']} ever-stuck cycle(s) auto-recovered; "
                          f"{rc['recovery_failures']} aborted while stuck."
                          if rc["ever_stuck"] else
                          "No cycle ever entered a stuck state in this window — the recovery path was not exercised."),
        },
        {
            "title": "3. Stuck-Cycle Analysis",
            "total_ever_stuck": tp["ever_stuck"], "stuck_rate_pct": stuck_rate_pct,
            "by_state": stuck_by_state, "auto_reroutes_observed": reroute_count,
            "evidence": [_ev("Stuck-cycle rate", f"{stuck_rate_pct}%",
                             f"≤ {READINESS_CRITERIA['max_stuck_rate_pct']}%",
                             _status_for("stuck", criteria))],
            "narrative": (f"{tp['ever_stuck']} cycle(s) entered a stuck state across "
                          f"{len(stuck_by_state)} distinct leg(s); auto-reroute fired {reroute_count} time(s)."
                          if tp["ever_stuck"] else "No stuck cycles recorded."),
        },
        {
            "title": "4. Expected vs Realized PnL Analysis",
            "expected_total_quote": pf["expected_total_quote"],
            "realized_total_quote": pf["realized_total_quote"],
            "avg_expected_per_cycle": pf["average_expected_per_cycle"],
            "avg_realized_per_cycle": pf["average_realized_per_cycle"],
            "avg_variance_quote": avg_var, "variance_pct": variance_pct,
            "best_cycle": _cyc_brief(best) if best else None,
            "worst_cycle": _cyc_brief(worst) if worst else None,
            "distribution": pf["after_fees_distribution"]["distribution"],
            "evidence": [_ev("Average variance", f"{variance_pct}%" if variance_pct is not None else "n/a",
                             f"≤ {READINESS_CRITERIA['max_variance_pct']}%", _status_for("variance", criteria)),
                         _ev("Avg realized PnL / cycle",
                             f"${pf['average_realized_per_cycle']:.2f}" if pf["average_realized_per_cycle"] is not None else "n/a",
                             "> $0", _status_for("profit", criteria))],
            "narrative": (f"Expected ${pf['expected_total_quote']} vs realized ${pf['realized_total_quote']} "
                          f"over {tp['completed']} completed cycle(s); average drift {variance_pct}%." ),
        },
        {
            "title": "5. Venue Comparison (Coinstore vs BitMart)",
            "coinstore": coinstore, "bitmart": bitmart, "other_venues": other_venues,
            "narrative": _venue_narrative(coinstore, bitmart),
        },
        {
            "title": "6. Route Comparison",
            "routes": route_perf,
            "narrative": (f"{len(route_perf)} route(s) exercised in shadow."
                          if route_perf else "No route performance recorded."),
        },
        {
            "title": "7. Recommended Safe Cycle Size",
            "recommended_usd": rec_size["recommended_usd"], "confidence": rec_size["confidence"],
            "rationale": rec_size["rationale"], "max_cycle_cap_usd": max_cycle,
            "certification_size_usd": max_cycle,
            "min_executable_size_usd": cfg["limits"].get("min_executable_purchase_usd"),
            "actual_executable_recommendation_usd": (
                round(max(rec_size["recommended_usd"], cfg["limits"].get("min_executable_purchase_usd") or 0), 2)
                if rec_size["recommended_usd"] is not None else cfg["limits"].get("min_executable_purchase_usd")),
            "min_executable_note": (
                f"BlockDAG Live Swap minimum purchase is ${cfg['limits'].get('min_executable_purchase_usd')}. "
                f"A live cycle cannot be placed below this; where the certified size is lower, the smallest "
                f"placeable cycle equals the minimum and must be reconciled against the certification cap."),
            "evidence": [_ev("Recommended size", f"${rec_size['recommended_usd']}",
                             f"≤ certification cap ${max_cycle}",
                             "PASS" if rec_size["recommended_usd"] <= max_cycle else "FAIL"),
                         _ev("Sizing confidence", rec_size["confidence"], "high (for READY)",
                             "PASS" if rec_size["confidence"] == "high" else "FAIL")],
        },
        {
            "title": "8. Key Failure Modes Discovered",
            "modes": failure_modes,
            "narrative": ("No failure modes were triggered in this campaign window."
                          if not failure_modes else
                          f"{len(failure_modes)} failure mode(s) observed; "
                          f"{sum(1 for m in failure_modes if m['severity'] == 'high')} high-severity."),
        },
        {
            "title": "9. Micro-Capital Readiness Assessment",
            "criteria": criteria, "passed": passed, "failed": failed, "na": na,
            "criteria_thresholds": READINESS_CRITERIA,
            "narrative": (f"{passed} criteria PASS, {failed} FAIL, {na} N/A against the strict "
                          f"micro-capital readiness bar."),
        },
        {
            "title": "10. Final Recommendation",
            "recommendation": recommendation,
            "headline": _verdict_headline(recommendation),
            "blocking_criteria": blocking, "gaps_to_close": gaps,
            "next_steps": _next_steps(recommendation, gaps, blocking),
            "guard_rails": ("This is a reporting & evidence layer only. E5 (micro-capital) remains BLOCKED. "
                            "No execution, wallet, withdrawal, or fund movement is enabled or authorized by this report."),
        },
    ]

    return {
        "phase": "E4.5 — Shadow Certification Review",
        "available": True,
        "generated_at": now_iso(),
        "recommendation": recommendation,
        "gate_context": campaign.get("gate_context") or campaign.get("gate_context_start"),
        "campaign": {
            "id": campaign["id"], "status": campaign.get("status"),
            "target_completed": campaign.get("target_completed"),
            "start_at": campaign["start_at"], "ended_at": campaign.get("ended_at"),
            "breach_reason": campaign.get("breach_reason"),
            "breach_thresholds": campaign.get("thresholds"),
            "final_verdict_report": report.get("verdict"),
        },
        "summary": {
            "total_cycles": total, "completed": tp["completed"], "aborted": tp["aborted"],
            "completion_rate_pct": tp["completion_rate_pct"],
            "ever_stuck": tp["ever_stuck"], "stuck_rate_pct": stuck_rate_pct,
            "recovery_success_rate_pct": rc["recovery_success_rate_pct"],
            "recovery_failures": rc["recovery_failures"],
            "expected_total_quote": pf["expected_total_quote"],
            "realized_total_quote": pf["realized_total_quote"],
            "variance_pct": variance_pct, "profitable_rate_pct": profitable_rate,
            "avg_realized_per_cycle": pf["average_realized_per_cycle"],
            "recommended_safe_cycle_usd": rec_size["recommended_usd"],
            "criteria_passed": passed, "criteria_failed": failed, "criteria_na": na,
        },
        "readiness_criteria": READINESS_CRITERIA,
        "sections": sections,
        "note": "Read-only evidence package from recorded shadow cycles only. Does NOT authorize execution. "
                "No trading, no wallet, no withdrawals, no fund movement.",
    }


# ---------------- helpers ----------------

def _ev(metric, value, threshold, status):
    return {"metric": metric, "value": value, "threshold": threshold, "status": status}


def _status_for(kind, criteria):
    name = {"recovery": "Recovery success rate", "stuck": "Stuck-cycle rate",
            "variance": "PnL variance (|avg var| / avg expected)",
            "profit": "Net profitability (avg realized)"}[kind]
    return next((c["status"] for c in criteria if c["criterion"] == name), "N/A")


def _verdict_headline(rec):
    return {
        "READY_FOR_MICROCAPITAL_REVIEW": "All strict readiness criteria met — recommend proceeding to "
                                         "Micro-Capital Certification REVIEW (still requires explicit human approval).",
        "NEEDS_MORE_DATA": "Promising, but the sample is too small or soft criteria are not yet met — "
                           "run more shadow cycles before deciding.",
        "NOT_READY": "One or more hard safety criteria failed — DO NOT proceed to micro-capital.",
    }[rec]


def _venue_narrative(coinstore, bitmart):
    def k(v):
        return None if v.get("no_data") else v.get("avg_realized")
    cr, br = k(coinstore), k(bitmart)
    if cr is None and br is None:
        return "Neither Coinstore nor BitMart completed a shadow cycle in this window."
    if cr is not None and (br is None or (cr >= (br or -1e9))):
        lead = "Coinstore"
    else:
        lead = "BitMart"
    return (f"Coinstore: {coinstore['completed']} completed (avg realized "
            f"{('$%.2f' % cr) if cr is not None else 'n/a'}); BitMart: {bitmart['completed']} completed "
            f"(avg realized {('$%.2f' % br) if br is not None else 'n/a'}). "
            f"{lead} shows the stronger shadow performance in this window.")


def _next_steps(rec, gaps, blocking):
    if rec == "READY_FOR_MICROCAPITAL_REVIEW":
        return ["Human review & explicit approval of this package.",
                "If approved, scope E5 to the recommended safe cycle size with whitelist + kill-switch + per-cycle cap mandatory.",
                "Keep execution/wallet flags OFF until E5 is separately approved."]
    if rec == "NEEDS_MORE_DATA":
        steps = ["Run another Shadow Certification Campaign to enlarge the sample."]
        steps += [f"Close gap — {g}" for g in gaps]
        return steps
    return ["Do NOT proceed to micro-capital."] + [f"Investigate blocker — {b}" for b in blocking]


# ---------------- markdown rendering ----------------

def _ev_lines(evidence):
    out = []
    for e in evidence:
        out.append(f"- {e['metric']} = **{e['value']}** (threshold {e['threshold']}) → **{e['status']}**")
    return out


def to_markdown(pkg: dict) -> str:
    if not pkg.get("available"):
        return f"# Shadow Certification Review\n\n_{pkg.get('message', 'No completed campaign available.')}_\n"
    c = pkg["campaign"]
    s = pkg["summary"]
    L = [
        "# Shadow Certification Review",
        f"**Recommendation: {pkg['recommendation']}**",
        "",
        f"- Campaign: `{c['id']}` ({c['status']})",
        f"- Window: {c['start_at']} → {c.get('ended_at')}",
        f"- Generated: {pkg['generated_at']}",
        f"- Target completed cycles: {c.get('target_completed')}",
        "",
        "## Snapshot",
        f"- Cycles: {s['total_cycles']} total · {s['completed']} completed · {s['aborted']} aborted "
        f"({s['completion_rate_pct']}% completion)",
        f"- Recovery: {s['recovery_success_rate_pct']}% success · {s['recovery_failures']} failure(s)",
        f"- Stuck rate: {s['stuck_rate_pct']}% · Variance: {s['variance_pct']}% · Profitable: {s['profitable_rate_pct']}%",
        f"- PnL: expected ${s['expected_total_quote']} vs realized ${s['realized_total_quote']} "
        f"(avg ${s['avg_realized_per_cycle']}/cycle)",
        f"- Recommended safe cycle size: ${s['recommended_safe_cycle_usd']}",
        f"- Readiness criteria: {s['criteria_passed']} PASS / {s['criteria_failed']} FAIL / {s['criteria_na']} N/A",
        "",
    ]
    for sec in pkg["sections"]:
        L.append(f"## {sec['title']}")
        if "verdict" in sec:
            L.append(f"**{sec['verdict']}** — {sec['headline']}")
            if sec.get("breach_reason"):
                L.append(f"> Auto-stop breach: {sec['breach_reason']}")
        if sec.get("narrative"):
            L.append(sec["narrative"])
        if sec.get("evidence"):
            L += _ev_lines(sec["evidence"])
        if sec["title"].startswith("3.") and sec.get("by_state"):
            L.append("")
            L.append("| Stuck leg | Count | Recovered | Aborted | Still stuck | Avg stuck (s) |")
            L.append("|---|---|---|---|---|---|")
            for g in sec["by_state"]:
                L.append(f"| {g['label']} | {g['count']} | {g['recovered']} | {g['aborted']} "
                         f"| {g['still_stuck']} | {g['avg_seconds_stuck']} |")
        if sec["title"].startswith("5."):
            L.append("")
            L.append("| Venue | Role | Cycles | Completed | Completion% | Avg realized | Avg variance |")
            L.append("|---|---|---|---|---|---|---|")
            for v in [sec["coinstore"], sec["bitmart"], *sec["other_venues"]]:
                L.append(f"| {str(v.get('label', v.get('key'))).upper()} | {v.get('role', '—')} "
                         f"| {v.get('cycles', 0)} | {v.get('completed', 0)} | {v.get('completion_rate_pct')} "
                         f"| {v.get('avg_realized')} | {v.get('avg_variance')} |")
        if sec["title"].startswith("6.") and sec.get("routes"):
            L.append("")
            L.append("| Route | Cycles | Completed | Avg realized |")
            L.append("|---|---|---|---|")
            for r in sec["routes"]:
                L.append(f"| {r['label']} | {r['cycles']} | {r['completed']} | {r.get('avg_realized')} |")
        if sec["title"].startswith("8.") and sec.get("modes"):
            L.append("")
            L.append("| Failure mode | Severity | Occurrences | Recovered | Aborted | Mitigation |")
            L.append("|---|---|---|---|---|---|")
            for m in sec["modes"]:
                L.append(f"| {m['mode']} | {m['severity']} | {m['occurrences']} | {m['recovered']} "
                         f"| {m['aborted']} | {m['mitigation']} |")
        if sec["title"].startswith("9.") and sec.get("criteria"):
            L.append("")
            L.append("| Criterion | Actual | Threshold | Severity | Status |")
            L.append("|---|---|---|---|---|")
            for cr in sec["criteria"]:
                L.append(f"| {cr['criterion']} | {cr['actual']} | {cr['threshold']} "
                         f"| {cr['severity']} | {cr['status']} |")
        if sec["title"].startswith("10."):
            if sec.get("blocking_criteria"):
                L.append("**Blocking criteria:**")
                L += [f"- {b}" for b in sec["blocking_criteria"]]
            if sec.get("gaps_to_close"):
                L.append("**Gaps to close:**")
                L += [f"- {g}" for g in sec["gaps_to_close"]]
            L.append("**Next steps:**")
            L += [f"- {n}" for n in sec["next_steps"]]
            L.append(f"\n> {sec['guard_rails']}")
        L.append("")
    L.append(f"---\n_{pkg['note']}_")
    return "\n".join(L)


# ---------------- public entry points ----------------

async def latest_review(regenerate: bool = False) -> dict:
    campaign = await latest_completed_campaign()
    if not campaign:
        return {"phase": "E4.5 — Shadow Certification Review", "available": False,
                "recommendation": None,
                "message": "No completed Shadow Certification Campaign yet. Start a campaign from the "
                           "Execution page and let it finish (or stop it) to generate the review package.",
                "note": "Read-only evidence layer. No execution, wallet, withdrawals, or fund movement."}
    stored = campaign.get("certification_review")
    if stored and not regenerate:
        return stored
    return await build(campaign)


async def review_for_campaign(campaign_id: str, regenerate: bool = False):
    campaign = await db.shadow_campaigns.find_one({"id": campaign_id}, {"_id": 0})
    if not campaign:
        return None
    stored = campaign.get("certification_review")
    if stored and not regenerate:
        return stored
    return await build(campaign)
