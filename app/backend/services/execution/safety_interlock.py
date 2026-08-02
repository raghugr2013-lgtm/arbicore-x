"""Phase E4.7 — Safety Interlock Layer (READ-ONLY, the final authority for E5 entry).

Fuses four independent safety engines into ONE verdict — READY / WAIT / BLOCKED:
  • Next-Cycle Readiness Engine   (production_workflow)
  • Opportunity Gate              (opportunity_gate — GO/WAIT/NO_GO + freshness)
  • Exchange Qualification Engine (exchange_intelligence — venue qualification)
  • Venue Status Monitor          (live deposit/withdraw gates)

It AUTOMATICALLY downgrades readiness the moment any safety condition breaks:
venue de-qualifies, deposit/withdraw gate closes, profitable depth disappears,
ROI drops below threshold, or stale pricing is detected.

This layer is designed to be the single guard the future E5 executor must consult
before opening any cycle. It is read-only and authorizes NOTHING today — E5 stays
blocked. No execution, no API keys, no wallet actions, no fund movement.
"""
from core.models import now_iso
from services.execution import (config, exchange_intelligence, opportunity_gate,
                                production_workflow)
from services import db


async def _bdag_route(route_id=None):
    if route_id:
        return await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    return await db.routes_col.find_one({"purchase.asset": "BDAG"}, {"_id": 0})


def _ck(key, label, status, detail, severity):
    """status ∈ READY|WAIT|BLOCKED. severity hard=can BLOCK, soft=can WAIT."""
    return {"key": key, "label": label, "status": status, "detail": detail, "severity": severity}


async def evaluate(route_id: str = None) -> dict:
    route = await _bdag_route(route_id)
    rid = (route or {}).get("id")
    cfg = await config.get_config()

    gate = await opportunity_gate.evaluate(rid) if rid else {"available": False, "gate_verdict": "NO_GO"}
    readiness = await production_workflow.next_cycle_readiness(route_id=rid)
    venue = gate.get("venue")
    qrec = await exchange_intelligence.get_one(venue) if venue else None

    checks = []
    blocked_reasons = []
    wait_reasons = []

    # --- 1. Venue qualification (HARD) ---
    if qrec is None:
        checks.append(_ck("venue_qualified", "Venue qualified", "BLOCKED", "no qualified venue", "hard"))
        blocked_reasons.append("no qualified sell venue")
    elif qrec["status"] == "disabled":
        checks.append(_ck("venue_qualified", "Venue qualified", "BLOCKED",
                          f"{venue} is DISABLED", "hard"))
        blocked_reasons.append(f"{venue} venue de-qualified (disabled)")
    elif qrec["status"] == "execution_approved":
        checks.append(_ck("venue_qualified", "Venue qualified", "READY",
                          f"{venue} execution-approved", "hard"))
    else:
        checks.append(_ck("venue_qualified", "Venue qualified", "WAIT",
                          f"{venue} monitor-only (not yet operator-verified)", "soft"))
        wait_reasons.append(f"{venue} is monitor-only — not execution-approved")

    # --- 2. Deposit gate (HARD) ---
    dep = (qrec or {}).get("deposit_status")
    if dep in ("closed", "suspended"):
        checks.append(_ck("deposit_gate", "Deposit gate open", "BLOCKED", f"deposit {dep}", "hard"))
        blocked_reasons.append("deposit gate closed")
    else:
        checks.append(_ck("deposit_gate", "Deposit gate open", "READY", f"deposit {dep}", "hard"))

    # --- 3. Withdrawal gate (HARD) ---
    wd = (qrec or {}).get("withdrawal_status")
    if wd in ("closed", "suspended"):
        checks.append(_ck("withdrawal_gate", "Withdrawal gate open", "BLOCKED", f"withdrawal {wd}", "hard"))
        blocked_reasons.append("withdrawal gate closed")
    else:
        checks.append(_ck("withdrawal_gate", "Withdrawal gate open", "READY", f"withdrawal {wd}", "hard"))

    # --- 4. Profitable depth (HARD) ---
    depth = gate.get("profitable_liquidity_quote")
    if not gate.get("available") or not depth:
        checks.append(_ck("profitable_depth", "Profitable depth present", "BLOCKED",
                          "no profitable buyer depth", "hard"))
        blocked_reasons.append("profitable depth disappeared")
    else:
        checks.append(_ck("profitable_depth", "Profitable depth present", "READY",
                          f"${depth} profitable", "hard"))

    # --- 5. Fresh pricing (HARD) ---
    fresh = (gate.get("freshness") or {}).get("all_fresh", False)
    if not fresh and gate.get("available"):
        stale = (gate.get("freshness") or {}).get("stale_sources", [])
        checks.append(_ck("fresh_pricing", "Fresh pricing", "BLOCKED",
                          f"stale: {', '.join(stale)}", "hard"))
        blocked_reasons.append("stale pricing detected")
    else:
        checks.append(_ck("fresh_pricing", "Fresh pricing", "READY", "all sources fresh", "hard"))

    # --- 6. ROI above threshold (SOFT) ---
    roi = gate.get("roi_pct")
    min_roi = gate.get("min_roi_pct")
    if roi is None or roi <= 0:
        checks.append(_ck("roi_threshold", "ROI above threshold", "BLOCKED",
                          f"ROI {roi}", "hard"))
        blocked_reasons.append("ROI non-positive")
    elif min_roi is not None and roi < min_roi:
        checks.append(_ck("roi_threshold", "ROI above threshold", "WAIT",
                          f"ROI {roi}% < floor {min_roi}%", "soft"))
        wait_reasons.append(f"ROI {roi}% below floor {min_roi}%")
    else:
        checks.append(_ck("roi_threshold", "ROI above threshold", "READY",
                          f"ROI {roi}% ≥ floor {min_roi}%", "soft"))

    # --- 7. Opportunity gate GO (SOFT) ---
    gv = gate.get("gate_verdict")
    if gv == "GO":
        checks.append(_ck("opportunity_go", "Opportunity gate GO", "READY", "gate GO", "soft"))
    elif gv == "WAIT":
        checks.append(_ck("opportunity_go", "Opportunity gate GO", "WAIT", "gate WAIT", "soft"))
        wait_reasons.append("opportunity gate is WAIT")
    else:
        checks.append(_ck("opportunity_go", "Opportunity gate GO", "BLOCKED", "gate NO_GO", "hard"))
        if "ROI non-positive" not in blocked_reasons:
            blocked_reasons.append("opportunity gate NO_GO")

    # --- 8. Next-cycle readiness (SOFT) ---
    rv = readiness.get("verdict")
    if rv == "READY":
        checks.append(_ck("next_cycle_ready", "Next-cycle readiness", "READY", "system clean", "soft"))
    elif rv in ("NO_HISTORY",):
        checks.append(_ck("next_cycle_ready", "Next-cycle readiness", "WAIT", rv, "soft"))
        wait_reasons.append("no completed-cycle history yet")
    elif rv == "BLOCKED":
        checks.append(_ck("next_cycle_ready", "Next-cycle readiness", "BLOCKED", "assets in transit", "hard"))
        blocked_reasons.append("assets in transit (previous cycle not settled)")
    else:
        checks.append(_ck("next_cycle_ready", "Next-cycle readiness", "WAIT", rv, "soft"))
        wait_reasons.append(f"next-cycle readiness {rv}")

    # --- compose final verdict ---
    if blocked_reasons:
        verdict = "BLOCKED"
    elif wait_reasons:
        verdict = "WAIT"
    else:
        verdict = "READY"

    return {
        "phase": "E4.7 — Safety Interlock (final authority for E5 entry)",
        "verdict": verdict, "route_id": rid, "route_name": (route or {}).get("name"),
        "venue": venue,
        "freshness": gate.get("freshness"),
        "data_fresh": (gate.get("freshness") or {}).get("all_fresh"),
        "interlocks": {
            "opportunity_gate": gate.get("gate_verdict"),
            "next_cycle_readiness": readiness.get("verdict"),
            "venue_qualification": (qrec or {}).get("status"),
            "deposit_gate": dep, "withdrawal_gate": wd,
        },
        "checks": checks,
        "blocked_reasons": blocked_reasons,
        "wait_reasons": wait_reasons,
        "downgrade_triggers": [
            "venue de-qualified", "deposit gate closed", "withdrawal gate closed",
            "profitable depth disappeared", "ROI below threshold", "stale pricing detected",
        ],
        "execution_gates": {"execution_enabled": cfg["execution_enabled"],
                            "wallet_enabled": cfg["wallet_enabled"]},
        "authority_note": "Final readiness authority for FUTURE E5 entry. READY here authorizes NOTHING today — "
                          "E5 remains BLOCKED. Read-only; no execution, no API keys, no wallet, no fund movement.",
        "generated_at": now_iso(),
    }
