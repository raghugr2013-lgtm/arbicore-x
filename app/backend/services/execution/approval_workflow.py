"""Approval Workflow — Approval Required Mode state machine + proposal engine.

Parallel intelligence layer. Reads buy_price, quote_capture, drift_runner, sizing
targets — never modifies them. Never signs, never moves funds.

Cycle state machine additions (idempotent, additive):
  PROPOSED -> APPROVED -> QUOTED -> ... -> CLOSED
  PROPOSED -> REJECTED  (terminal)
  PROPOSED -> STALE     (verification > 30s old; cleanup_stale auto-promotes)
"""
from __future__ import annotations

import logging
import statistics
import time
import uuid
from datetime import datetime, timezone

from services import db
from services.execution import drift_runner as drift_runner_mod
from services.execution import sizing as sizing_mod

logger = logging.getLogger("approval_workflow")

STALENESS_S = 30                # operator decision: 30s reverify threshold
DEFAULT_MIN_ROI_PCT = 5.0       # operator decision: 5% net ROI floor
REGIME_FACTOR = {"Stable": 1.0, "Volatile": 0.7, "Extremely Volatile": 0.3}
RISK_PENALTY = {"LOW": 0, "MEDIUM": 5, "HIGH": 10, "VERY_HIGH": 20}


# ------------------------------------------------------------------
# Persistence
# ------------------------------------------------------------------
async def ensure_indexes():
    p = db.db.proposed_cycles
    await p.create_index("state")
    await p.create_index([("computed_at_ts", -1)])
    await p.create_index([("primary", -1), ("quality_score", -1)])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _utcnow_ts() -> int:
    return int(time.time())


# ------------------------------------------------------------------
# Quote batch consumption — userscript-v2 POSTs land here
# ------------------------------------------------------------------
async def consume_batch(captures: list[dict]) -> dict:
    """Persist a userscript-v2 multi-size capture batch. Each capture:
    {size_usd, effective_price, ts (ms), bdag_quoted, source}."""
    if not captures:
        return {"persisted": 0, "batch_id": None}
    batch_id = f"batch_{_utcnow_ts()}_{uuid.uuid4().hex[:8]}"
    rows = []
    for c in captures:
        try:
            row = {
                "batch_id": batch_id,
                "size_usd": float(c["size_usd"]),
                "effective_price": float(c["effective_price"]),
                "bdag_quoted": float(c.get("bdag_quoted") or 0) or None,
                "source": c.get("source") or "userscript_v2_batch",
                "captured_at": c.get("captured_at") or _now(),
                "captured_at_ts": _utcnow_ts(),
            }
            rows.append(row)
        except (KeyError, TypeError, ValueError):
            continue
    if rows:
        await db.db.quote_batches.insert_many(rows)
    return {"persisted": len(rows), "batch_id": batch_id, "sizes": [r["size_usd"] for r in rows]}


async def latest_batch() -> list[dict]:
    """Return the freshest batch's captures (most recent batch_id)."""
    newest = await db.db.quote_batches.find_one({}, {"_id": 0},
                                                sort=[("captured_at_ts", -1)])
    if not newest:
        return []
    cur = db.db.quote_batches.find({"batch_id": newest["batch_id"]},
                                   {"_id": 0}).sort("size_usd", 1)
    return await cur.to_list(20)


# ------------------------------------------------------------------
# Proposal engine
# ------------------------------------------------------------------
async def _proposal_min_roi() -> float:
    cfg = await db.db.execution_config.find_one({}, {"_id": 0}) or {}
    return float(cfg.get("proposal_min_roi_pct") or DEFAULT_MIN_ROI_PCT)


def _compute_quality(net_roi_pct: float, size_usd: float, max_safe_usd: float | None,
                     available_usd: float | None, liquidity_feasible: bool,
                     regime_label: str | None, risk_label: str | None,
                     expected_profit_usd: float, combined_survival_prob: float | None) -> float:
    """Ranks proposals against the user-specified criteria:
      - net ROI (primary driver)
      - expected profit in USD (rewards larger absolute profit when ROI is similar)
      - liquidity / profitable buyer depth (via liquidity_factor)
      - drift risk (via risk_penalty)
      - regime
      - cycle survivability (combined_survival_prob from HDA)
      - size relative to the safe ceiling (size_factor)
    """
    # size_factor: prefer fully using the safe ceiling; if HDA hasn't given one,
    # fall back to the operator's available_balance so the factor is meaningful.
    ceiling = max_safe_usd if (max_safe_usd and max_safe_usd > 0) else (
        available_usd if (available_usd and available_usd > 0) else None)
    size_factor = min(size_usd / ceiling, 1.0) if ceiling else 0.5
    liquidity_factor = 1.0 if liquidity_feasible else 0.5
    regime_factor = REGIME_FACTOR.get(regime_label or "", 0.5)
    survival_factor = float(combined_survival_prob) if (combined_survival_prob is not None) else 0.6
    risk_pen = RISK_PENALTY.get(risk_label or "", 10)
    # Core spread + 10% credit per $ of expected profit (rewards absolute profit)
    core = net_roi_pct + (expected_profit_usd / 10.0)
    return round(core * size_factor * liquidity_factor * regime_factor * survival_factor - risk_pen, 3)


async def build_proposals() -> dict:
    """Build the ranked list of actionable proposals.

    Returns:
        {
          "primary": {...}  or None,
          "secondary": [...],
          "ranked_count": int,
          "min_roi_threshold_pct": float,
          "blockers": [reasons],
          "now": iso
        }
    """
    min_roi = await _proposal_min_roi()
    blockers: list[str] = []

    # 1. Sizing context
    targets = await sizing_mod.compute_targets()
    if targets.get("blockers"):
        blockers.extend(targets["blockers"])

    # 2. Live HDA snapshot for risk + Coinstore best_bid
    hda = await drift_runner_mod.latest("BDAGUSDT", "coinstore") or {}
    cap = hda.get("opportunity_capacity") or {}
    regime_label = (hda.get("regime") or {}).get("label")
    risk_label = (hda.get("risk_score") or {}).get("label")
    dur = (hda.get("cycle_duration_map") or {})
    expected_cycle_s = dur.get("current_expected_cycle_s") or 600
    surv_row = (dur.get("rows") or {}).get(str(expected_cycle_s)) or {}
    combined_survival = surv_row.get("combined_survival_prob")

    # 3. Latest Coinstore best_bid (the SELL side)
    latest_book = await db.db.orderbook_snapshots.find_one(
        {"exchange": "coinstore"}, {"_id": 0, "derived": 1, "created_at": 1},
        sort=[("created_at", -1)])
    best_bid = ((latest_book or {}).get("derived") or {}).get("best_bid")
    if not best_bid:
        blockers.append("no_coinstore_best_bid")

    # 4. Latest verified-quote batch (sets of size -> effective_price)
    batch = await latest_batch()
    if not batch:
        blockers.append("no_verified_quote_batch")
    batch_ages = [(time.time() - row.get("captured_at_ts", 0)) for row in batch]
    youngest = min(batch_ages) if batch_ages else None
    if youngest is not None and youngest > STALENESS_S:
        blockers.append(f"verified_quote_stale ({youngest:.0f}s > {STALENESS_S}s)")

    # 5. Fee assumption — pulled from execution_config or hardcoded fallback
    cfg = await db.db.execution_config.find_one({}, {"_id": 0}) or {}
    taker_fee_pct = float(cfg.get("coinstore_taker_fee_pct") or 0.2)  # 0.2%
    transfer_fee_pct = float(cfg.get("transfer_fee_pct") or 0.1)
    withdraw_fee_pct = float(cfg.get("withdraw_fee_pct") or 0.0)
    fee_drag_pct = taker_fee_pct + transfer_fee_pct + withdraw_fee_pct

    # 6. Build a proposal per verified size
    candidates: list[dict] = []
    if best_bid and batch and youngest is not None and youngest <= STALENESS_S:
        for q in batch:
            buy_price = q["effective_price"]
            if buy_price <= 0:
                continue
            gross_pct = (best_bid - buy_price) / buy_price * 100.0
            net_pct = gross_pct - fee_drag_pct
            size_usd = q["size_usd"]
            expected_profit_usd = round(net_pct / 100.0 * size_usd, 2)
            quality = _compute_quality(
                net_pct, size_usd, targets.get("max_safe_buy_usd"),
                targets.get("available_balance_usd"),
                cap.get("feasible", False), regime_label, risk_label,
                expected_profit_usd, combined_survival)
            candidates.append({
                "proposal_id": f"prop_{q['batch_id']}_{int(size_usd)}",
                "batch_id": q["batch_id"],
                "size_usd": size_usd,
                "buy_price": buy_price,
                "buy_price_source": q.get("source"),
                "sell_price": best_bid,
                "gross_spread_pct": round(gross_pct, 4),
                "net_roi_pct": round(net_pct, 4),
                "fee_drag_pct": round(fee_drag_pct, 4),
                "expected_profit_usd": expected_profit_usd,
                "expected_cycle_s": expected_cycle_s,
                "combined_survival_prob": combined_survival,
                "regime": regime_label,
                "risk_label": risk_label,
                "risk_score": (hda.get("risk_score") or {}).get("score_0_100"),
                "liquidity_feasible": bool(cap.get("feasible", False)),
                "profitable_buyer_depth_usd": cap.get("max_executable_size_usd"),
                "quality_score": quality,
                "quote_age_s": round(time.time() - q.get("captured_at_ts", 0), 1),
                "bdag_expected": round(size_usd / buy_price, 2),
                "stale": False,
                "actionable": net_pct >= min_roi,
            })

    candidates.sort(key=lambda x: x["quality_score"], reverse=True)
    actionable = [c for c in candidates if c["actionable"]]
    primary = actionable[0] if actionable else None
    secondary = actionable[1:] if len(actionable) > 1 else []

    return {
        "primary": primary,
        "secondary": secondary,
        "ranked_count": len(candidates),
        "actionable_count": len(actionable),
        "min_roi_threshold_pct": min_roi,
        "staleness_threshold_s": STALENESS_S,
        "targets": targets,
        "blockers": blockers,
        "now": _now(),
    }


# ------------------------------------------------------------------
# Approve / Reject — operator actions
# ------------------------------------------------------------------
async def approve(proposal_id: str, size_usd: float, approve_mode: str,
                  operator_note: str | None = None) -> dict:
    """Operator approves a proposal. Creates a `arbitrage_cycles` record in
    state QUOTED (skipping PROPOSED/APPROVED meta-states for simplicity —
    the approval is logged in `approval_decisions` and the note field).
    """
    if approve_mode not in ("available", "recommended", "custom"):
        raise ValueError("approve_mode must be one of: available, recommended, custom")

    # Re-build proposals to verify the proposal_id is still actionable
    snap = await build_proposals()
    pool = ([snap["primary"]] if snap["primary"] else []) + (snap["secondary"] or [])
    proposal = next((p for p in pool if p and p["proposal_id"] == proposal_id), None)
    if not proposal:
        raise LookupError(f"proposal {proposal_id} not actionable or expired")
    if size_usd < sizing_mod.BDAG_SWAP_MIN_USD:
        raise ValueError(f"size_usd {size_usd} below BDAG floor "
                         f"${sizing_mod.BDAG_SWAP_MIN_USD}")

    # Persist the decision
    decision_id = f"appr_{_utcnow_ts()}_{uuid.uuid4().hex[:8]}"
    await db.db.approval_decisions.insert_one({
        "decision_id": decision_id,
        "decided_at": _now(),
        "decided_at_ts": _utcnow_ts(),
        "action": "approve",
        "approve_mode": approve_mode,
        "size_usd": size_usd,
        "proposal_snapshot": proposal,
        "note": operator_note,
    })

    # Auto-create an arbitrage_cycle in QUOTED state using the verified quote
    from services.execution import arbitrage_cycles
    cyc = await arbitrage_cycles.create(
        input_amount=size_usd,
        quote_price=proposal["buy_price"],
        bdag_expected=size_usd / proposal["buy_price"],
        best_bid=proposal["sell_price"],
        expected_roi_pct=proposal["net_roi_pct"],
        note=(f"ArbiCore-approved | mode={approve_mode} | proposal={proposal_id} | "
              f"decision={decision_id} | quality={proposal['quality_score']} | "
              f"{(operator_note or '').strip()}").strip(" |"),
    )
    return {"decision_id": decision_id, "cycle": cyc, "proposal_id": proposal_id}


async def reject(proposal_id: str, reason: str | None = None) -> dict:
    decision_id = f"rej_{_utcnow_ts()}_{uuid.uuid4().hex[:8]}"
    snap = await build_proposals()
    pool = ([snap["primary"]] if snap["primary"] else []) + (snap["secondary"] or [])
    proposal = next((p for p in pool if p and p["proposal_id"] == proposal_id), None)
    await db.db.approval_decisions.insert_one({
        "decision_id": decision_id,
        "decided_at": _now(),
        "decided_at_ts": _utcnow_ts(),
        "action": "reject",
        "reason": reason,
        "proposal_snapshot": proposal,
    })
    return {"decision_id": decision_id, "proposal_id": proposal_id, "reason": reason}


# ------------------------------------------------------------------
# Auto Mode — gated, currently inert
# ------------------------------------------------------------------
async def auto_mode_status() -> dict:
    cfg = await db.db.execution_config.find_one({}, {"_id": 0}) or {}
    # safety_interlock.evaluate() is the read-only check; treat any non-truthy
    # gate as "execution_disabled" so Auto Mode is safe by default.
    execution_enabled = False
    try:
        from services.execution import safety_interlock
        gate = await safety_interlock.evaluate()
        execution_enabled = bool((gate or {}).get("execution_enabled"))
    except Exception:  # noqa: BLE001
        execution_enabled = False
    enabled = bool(cfg.get("auto_mode_enabled"))
    return {
        "auto_mode_enabled_flag": enabled,
        "execution_enabled_interlock": execution_enabled,
        "auto_mode_effective": enabled and execution_enabled,
        "note": ("Auto Mode is double-gated. Even if the flag is on, the safety "
                 "interlock currently keeps execution disabled — this is the "
                 "read-only safety guarantee."),
    }


async def set_auto_mode(enabled: bool) -> dict:
    """Sets the flag only. Does NOT bypass safety_interlock."""
    await db.db.execution_config.update_one(
        {}, {"$set": {"auto_mode_enabled": bool(enabled)}}, upsert=True)
    return await auto_mode_status()
