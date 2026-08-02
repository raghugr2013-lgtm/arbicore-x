"""Certification Evidence Package assembler (READ-ONLY).

Composes the frozen certification campaign + the E4.7 opportunity-gated layer into
the operator-requested 8-section evidence package:

  1. Final Verdict
  2. Threshold Audit
  3. Opportunity Gate Statistics
  4. GO Window History Summary
  5. Safety Interlock Summary
  6. Venue Qualification Snapshot
  7. Recommended Capital Size
  8. Remaining Evidence Gaps

It only READS existing engines (certification review, opportunity gate, safety
interlock, exchange qualification, sizing) — it modifies none of them. NO
execution, no fund movement.
"""
from core.models import now_iso
from services import db
from services.execution import (arbitrage_intel, certification_review,
                                exchange_intelligence, safety_interlock)
from services.execution.opportunity_gate import opportunity_monitor, evaluate as gate_eval

CERTIFIED = "READY_FOR_MICROCAPITAL_REVIEW"


def _section(review, prefix):
    for s in review.get("sections", []):
        if (s.get("title") or "").startswith(prefix):
            return s
    return {}


async def _bdag_route():
    return await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0})


async def build(campaign_id: str = None) -> dict:
    if campaign_id:
        review = await certification_review.review_for_campaign(campaign_id, regenerate=False)
    else:
        review = await certification_review.latest_review(regenerate=False)
    if not review or not review.get("available"):
        return {"available": False, "note": "No certification campaign available to build evidence from."}

    route = await _bdag_route()
    rid = (route or {}).get("id")
    gate = await gate_eval(rid) if rid else {}
    interlock = await safety_interlock.evaluate(rid)
    hist = await opportunity_monitor.history(200)
    registry = await exchange_intelligence.registry()
    camp = review.get("campaign") or {}
    camp_doc = await db.shadow_campaigns.find_one({"id": camp.get("id")}, {"_id": 0}) or {}

    sec1 = _section(review, "1.")
    sec7 = _section(review, "7.")
    sec9 = _section(review, "9.")
    sec10 = _section(review, "10.")
    summary = review.get("summary") or {}
    verdict = review.get("recommendation")

    # --- 1. Final Verdict ---
    final_verdict = {
        "verdict": verdict, "certified": verdict == CERTIFIED,
        "headline": sec1.get("headline"),
        "campaign_id": sec1.get("campaign_id") or camp.get("id"),
        "campaign_status": sec1.get("campaign_status") or camp.get("status"),
        "window": sec1.get("window"),
        "completed": sec1.get("completed"), "target": sec1.get("target_completed"),
        "completion_rate_pct": summary.get("completion_rate_pct"),
        "variance_pct": summary.get("variance_pct"),
        "profitable_rate_pct": summary.get("profitable_rate_pct"),
        "stuck_rate_pct": summary.get("stuck_rate_pct"),
    }

    # --- 2. Threshold Audit ---
    threshold_audit = {
        "criteria": sec9.get("criteria"),
        "passed": sec9.get("passed"), "failed": sec9.get("failed"), "na": sec9.get("na"),
        "thresholds": review.get("readiness_criteria"),
        "all_thresholds_met": not sec9.get("failed"),
    }

    # --- 3. Opportunity Gate Statistics ---
    hs = hist.get("summary") or {}
    opp_stats = {
        "current_gate_verdict": gate.get("gate_verdict"),
        "current_venue": gate.get("venue"),
        "current_roi_pct": gate.get("roi_pct"),
        "current_profitable_depth_usd": gate.get("profitable_liquidity_quote"),
        "current_conditions": [{"key": c["key"], "passed": c["passed"]}
                               for c in (gate.get("conditions") or [])],
        "data_fresh_now": (gate.get("freshness") or {}).get("all_fresh"),
        "go_windows_total": hs.get("total_windows"),
        "go_windows_open": hs.get("open"),
        "go_windows_closed": hs.get("closed"),
        "avg_window_duration_s": hs.get("avg_duration_s"),
        "max_window_duration_s": hs.get("max_duration_s"),
        "avg_peak_roi_pct": hs.get("avg_peak_roi_pct"),
        "best_peak_roi_pct": hs.get("best_peak_roi_pct"),
    }

    # --- 4. GO Window History Summary ---
    go_history = {
        "summary": hs,
        "recent_windows": [
            {"venue": w["venue"], "status": w["status"], "opened_at": w["opened_at"],
             "closed_at": w.get("closed_at"), "duration_s": w.get("duration_s"),
             "roi_open": w.get("roi_open"), "roi_peak": w.get("roi_peak"),
             "roi_avg": w.get("roi_avg"), "safe_buy_size_usd": w.get("safe_buy_size_usd"),
             "reason_opened": w.get("reason_opened"), "reason_closed": w.get("reason_closed")}
            for w in (hist.get("windows") or [])[:15]],
    }

    # --- 5. Safety Interlock Summary ---
    interlock_summary = {
        "current_verdict": interlock.get("verdict"),
        "interlocks": interlock.get("interlocks"),
        "checks": [{"key": c["key"], "status": c["status"], "detail": c["detail"]}
                   for c in (interlock.get("checks") or [])],
        "blocked_reasons": interlock.get("blocked_reasons"),
        "wait_reasons": interlock.get("wait_reasons"),
        "downgrade_triggers": interlock.get("downgrade_triggers"),
        "campaign_start_context": camp_doc.get("gate_context_start"),
        "campaign_finalize_context": review.get("gate_context") or camp_doc.get("gate_context"),
    }

    # --- 6. Venue Qualification Snapshot ---
    by_ex = {r["exchange"]: r for r in registry["exchanges"]}
    cert_venue = gate.get("venue")

    def _qual(ex):
        r = by_ex.get(ex)
        if not r:
            return None
        return {"name": r["name"], "status": r["status"],
                "execution_approved": r["execution_approved"],
                "india_accessibility": r["india_accessibility"],
                "deposit_status": r["deposit_status"], "withdrawal_status": r["withdrawal_status"],
                "deposit_reliability": r["deposit_reliability"], "withdrawal_reliability": r["withdrawal_reliability"],
                "api_availability": r["api_availability"], "trust_score": r["trust_score"],
                "qualification_pct": r["qualification"]["qualification_pct"],
                "fully_qualified": r["qualification"]["fully_qualified"]}

    venue_snapshot = {
        "classification": registry["classification"], "counts": registry["counts"],
        "primary_execution_venue": _qual("coinstore"),
        "promotion_candidates": [_qual(ex) for ex in ("bitmart", "xt", "pionex", "ascendex")
                                 if by_ex.get(ex) and by_ex[ex]["status"] == "monitor_only"],
        "sell_venue_at_certification": _qual(cert_venue) if cert_venue else None,
    }

    # --- 7. Recommended Capital Size ---
    msb = gate.get("max_safe_buy_usd")
    es = gate.get("executable_sizing") or {}
    cert_size = es.get("certification_size_usd") or sec7.get("max_cycle_cap_usd")
    min_exec = es.get("min_executable_size_usd")
    actual_exec = es.get("actual_executable_recommendation_usd")
    capital = {
        "certification_size_usd": cert_size,
        "certified_recommended_usd": sec7.get("recommended_usd"),
        "min_executable_size_usd": min_exec,
        "actual_executable_recommendation_usd": actual_exec,
        "executable_actionable": es.get("actionable"),
        "min_exceeds_certification_cap": es.get("min_exceeds_certification_cap"),
        "executable_notes": es.get("notes"),
        "confidence": sec7.get("confidence"),
        "rationale": sec7.get("rationale"),
        "per_cycle_cap_usd": sec7.get("max_cycle_cap_usd"),
        "live_max_safe_buy_usd": msb,
        "live_recommended_buy_usd": gate.get("recommended_buy_usd"),
        "guidance": (f"Certification size is ${cert_size}/cycle, but the BlockDAG Live Swap minimum purchase is "
                     f"${min_exec} — so the smallest ACTUALLY-PLACEABLE cycle is ${actual_exec}. "
                     + ("This EXCEEDS the certified cap; the certification cap must be raised (with evidence) "
                        "before any live cycle can be both placeable and certified. "
                        if es.get("min_exceeds_certification_cap") else "")
                     + f"Live liquidity supports a max safe size of ~${msb} before profitability degrades."),
    }

    # --- 8. Remaining Evidence Gaps ---
    gaps = {
        "blocking_criteria": sec10.get("blocking_criteria"),
        "gaps_to_close": sec10.get("gaps_to_close"),
        "next_steps": sec10.get("next_steps"),
        "guard_rails": sec10.get("guard_rails"),
        "interlock_wait_reasons": interlock.get("wait_reasons"),
        "interlock_blocked_reasons": interlock.get("blocked_reasons"),
        "outstanding": _outstanding(verdict, interlock, sec10),
    }

    return {
        "phase": "Certification Evidence Package (E4.7 opportunity-gated, read-only)",
        "generated_at": now_iso(), "available": True,
        "verdict": verdict, "certified": verdict == CERTIFIED,
        "campaign_id": camp.get("id"), "architecture": "opportunity-gated (E4.7)",
        "sections": {
            "1_final_verdict": final_verdict,
            "2_threshold_audit": threshold_audit,
            "3_opportunity_gate_statistics": opp_stats,
            "4_go_window_history_summary": go_history,
            "5_safety_interlock_summary": interlock_summary,
            "6_venue_qualification_snapshot": venue_snapshot,
            "7_recommended_capital_size": capital,
            "8_remaining_evidence_gaps": gaps,
        },
        "note": "Read-only evidence composed from frozen certification + E4.7 gated layer. "
                "READY_FOR_MICROCAPITAL_REVIEW authorizes a REVIEW, not execution. E5 remains blocked; "
                "no execution, no API keys, no wallet actions, no fund movement.",
    }


def _outstanding(verdict, interlock, sec10):
    items = []
    if verdict != CERTIFIED:
        items.append("Certification verdict is not READY_FOR_MICROCAPITAL_REVIEW.")
    items += list(sec10.get("gaps_to_close") or [])
    # E5 mandatory controls always outstanding until E5 build
    items += [
        "Withdrawal-address whitelist not yet configured (mandatory E5 control).",
        "Kill-switch + per-cycle cap enforcement live-wired only at E5 build.",
        "One manual ~$20 India loop on the chosen sell venue before any automated execution.",
    ]
    if interlock.get("wait_reasons"):
        items.append("Interlock currently WAIT: " + "; ".join(interlock["wait_reasons"]))
    return items


def to_markdown(pkg: dict) -> str:
    if not pkg.get("available"):
        return "# Certification Evidence Package\n\n_No campaign available._\n"
    s = pkg["sections"]
    L = [f"# Certification Evidence Package — {pkg['verdict']}",
         f"_Generated {pkg['generated_at']} · architecture: {pkg['architecture']} · read-only, non-executing_\n"]

    fv = s["1_final_verdict"]
    L += ["## 1. Final Verdict",
          f"- **Verdict:** {fv['verdict']} {'✅ CERTIFIED' if fv['certified'] else ''}",
          f"- {fv.get('headline','')}",
          f"- Completed {fv['completed']}/{fv['target']} · completion {fv['completion_rate_pct']}% · "
          f"variance {fv['variance_pct']}% · profitable {fv['profitable_rate_pct']}% · stuck {fv['stuck_rate_pct']}%\n"]

    ta = s["2_threshold_audit"]
    L += ["## 2. Threshold Audit",
          f"- Passed: {ta['passed']} · Failed: {ta['failed']} · N/A: {ta['na']} · "
          f"All met: {ta['all_thresholds_met']}"]
    for c in (ta.get("criteria") or []):
        st = c.get("status")
        mark = "✅" if st == "PASS" else ("—" if st in ("N/A", "NA", None) else "❌")
        L.append(f"  - {mark} {c.get('criterion')}: {c.get('actual')} vs {c.get('threshold')}")
    L.append("")

    og = s["3_opportunity_gate_statistics"]
    L += ["## 3. Opportunity Gate Statistics",
          f"- Current gate: **{og['current_gate_verdict']}** on {og['current_venue']} "
          f"(ROI {og['current_roi_pct']}%, profitable depth ${og['current_profitable_depth_usd']}, "
          f"data fresh: {og['data_fresh_now']})",
          f"- GO windows: {og['go_windows_total']} total ({og['go_windows_open']} open / {og['go_windows_closed']} closed) · "
          f"avg dur {og['avg_window_duration_s']}s · max {og['max_window_duration_s']}s",
          f"- ROI across windows: avg peak {og['avg_peak_roi_pct']}% · best peak {og['best_peak_roi_pct']}%\n"]

    gh = s["4_go_window_history_summary"]["summary"]
    L += ["## 4. GO Window History Summary",
          f"- {gh.get('total_windows')} windows · {gh.get('closed')} closed · "
          f"avg duration {gh.get('avg_duration_s')}s · best peak ROI {gh.get('best_peak_roi_pct')}%\n"]

    il = s["5_safety_interlock_summary"]
    L += ["## 5. Safety Interlock Summary",
          f"- Current verdict: **{il['current_verdict']}** · interlocks: {il['interlocks']}"]
    if il.get("wait_reasons"):
        L.append(f"  - WAIT: {'; '.join(il['wait_reasons'])}")
    if il.get("blocked_reasons"):
        L.append(f"  - BLOCKED: {'; '.join(il['blocked_reasons'])}")
    sc = il.get("campaign_start_context") or {}
    fc = il.get("campaign_finalize_context") or {}
    L += [f"  - Campaign launch context: interlock {sc.get('interlock_verdict')} / gate {sc.get('gate_verdict')} on {sc.get('venue')}",
          f"  - Campaign finalize context: interlock {fc.get('interlock_verdict')} / gate {fc.get('gate_verdict')} on {fc.get('venue')}\n"]

    vs = s["6_venue_qualification_snapshot"]
    pv = vs.get("primary_execution_venue") or {}
    L += ["## 6. Venue Qualification Snapshot",
          f"- Classification: {vs['counts']}",
          f"- Primary: {pv.get('name')} — {pv.get('qualification_pct')}% qualified "
          f"(dep rel {pv.get('deposit_reliability')}, wd rel {pv.get('withdrawal_reliability')}, trust {pv.get('trust_score')})"]
    for c in (vs.get("promotion_candidates") or []):
        L.append(f"  - Candidate {c['name']}: {c['qualification_pct']}% qualified, status {c['status']}")
    L.append("")

    cap = s["7_recommended_capital_size"]
    L += ["## 7. Recommended Capital Size",
          f"- **Certification size:** ${cap.get('certification_size_usd')} per cycle "
          f"(certified recommended ${cap['certified_recommended_usd']}, confidence {cap['confidence']})",
          f"- **Minimum executable size:** ${cap.get('min_executable_size_usd')} (BlockDAG Live Swap minimum purchase)",
          f"- **Actual executable recommendation:** ${cap.get('actual_executable_recommendation_usd')}"
          f"{' ⚠ EXCEEDS certification cap' if cap.get('min_exceeds_certification_cap') else ''}",
          f"- Live max safe buy: ${cap['live_max_safe_buy_usd']}",
          f"- {cap['guidance']}\n"]

    gaps = s["8_remaining_evidence_gaps"]
    L += ["## 8. Remaining Evidence Gaps"]
    for g in (gaps.get("outstanding") or []):
        L.append(f"- {g}")
    L += ["", "---", "_Read-only evidence. E5 remains blocked. No execution, no API keys, no fund movement._"]
    return "\n".join(L)
