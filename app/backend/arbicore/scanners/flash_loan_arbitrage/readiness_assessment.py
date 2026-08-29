"""Assemble candidate-level Limited-Live readiness from an evidence bundle plus
the live readiness controls (executor capability, Balancer flash-loan liquidity,
borrow-size feasibility, exact-transaction atomic simulation, freshness).

Pure/deterministic: the caller (the VPS audit runner) performs the live reads
and passes the results in; this module maps them onto the mandatory-control
vocabulary and produces the single fail-closed
:func:`evaluate_limited_live_eligibility` decision, preserving the exact
``audit_run_id`` / ``scanner_tick_id`` / ``candidate_id`` provenance.

Nothing here signs, broadcasts, or enables Limited-Live.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ...execution.limited_live_eligibility import (
    LimitedLiveDecision, evaluate_limited_live_eligibility,
)
from .borrow_sizing import BorrowSizeDecision
from .executor_capability import ExecutorCapability, ExecutorCapabilityStatus
from .provider_liquidity import ProviderLiquidity, ProviderStatus


@dataclass
class ReadinessControls:
    """Live control results fetched by the caller (all default to the
    fail-closed value so an unfetched control can never pass)."""
    executor_capability: Optional[ExecutorCapability] = None
    balancer_liquidity: Optional[ProviderLiquidity] = None
    borrow_size: Optional[BorrowSizeDecision] = None
    atomic_sim: Dict[str, Any] = field(default_factory=dict)
    freshness_ok: bool = False
    mode_allows: bool = False
    kill_switch_ok: bool = False


def _provenance(bundle: Dict[str, Any]) -> Dict[str, Any]:
    d = bundle.get("diagnostics") or {}
    return {
        "audit_run_id": d.get("audit_run_id"),
        "scanner_tick_id": d.get("scanner_tick_id"),
        "worker_id": d.get("worker_id"),
        "candidate_id": d.get("candidate_id"),
    }


def _provenance_complete(prov: Dict[str, Any]) -> bool:
    return bool(prov.get("audit_run_id")
                and prov.get("scanner_tick_id") is not None
                and prov.get("candidate_id"))


def assess_candidate_readiness(
    bundle: Dict[str, Any], controls: ReadinessControls,
) -> Dict[str, Any]:
    """Return a persistable readiness record + the Limited-Live decision.

    Every mapping is fail-closed: a missing gate/quote/economics field, a
    non-CONFIRMED status, an unverifiable executor/liquidity/sim, an
    infeasible size, or stale state all resolve to a NON-PASS control.
    """
    gates = bundle.get("gates") or {}
    quotes = bundle.get("quotes") or {}
    econ = bundle.get("economics") or {}
    prov = _provenance(bundle)

    def gate_status(name: str) -> str:
        return (gates.get(name) or {}).get("status") or "NOT_EVALUATED"

    net = econ.get("atomic_profit_usd")
    economics_ok = isinstance(net, (int, float)) and net > 0 \
        and gate_status("gate_7") == "PASS"

    cap = controls.executor_capability
    executor_pass = (cap is not None
                     and cap.status == ExecutorCapabilityStatus.SUPPORTED)

    bal = controls.balancer_liquidity
    balancer_pass = (bal is not None
                     and bal.status == ProviderStatus.ON_CHAIN_CONFIRMED)

    size = controls.borrow_size
    size_pass = size is not None and size.ok

    sim = controls.atomic_sim or {}
    sim_pass = bool(sim.get("available") and sim.get("passed"))

    control_inputs: Dict[str, Any] = {
        "quote_complete": quotes.get("route_quote_status") == "ok",
        "economics_ok": economics_ok,
        "gate_7": gate_status("gate_7"),
        "liquidity_verified": gate_status("gate_8"),
        "gate_8": gate_status("gate_8"),
        "executor_capability": cap.status.value if cap else "UNVERIFIABLE",
        "gate_9": gate_status("gate_9"),
        "borrow_size_feasible": bool(size_pass),
        "balancer_liquidity": bal.status.value if bal else "UNKNOWN",
        "atomic_simulation": bool(sim_pass),
        "freshness_ok": bool(controls.freshness_ok),
        "provenance_complete": _provenance_complete(prov),
        "verification_confirmed": (
            bundle.get("source_component") == "flash_loan_arb_verifier"
            and bundle.get("verification_status") == "CONFIRMED"),
        "mode_allows": bool(controls.mode_allows),
        "kill_switch_ok": bool(controls.kill_switch_ok),
    }

    decision: LimitedLiveDecision = evaluate_limited_live_eligibility(control_inputs)

    return {
        "provenance": prov,
        "bundle_id": bundle.get("bundle_id"),
        "verification_status": bundle.get("verification_status"),
        "controls": control_inputs,
        "executor_capability": cap.to_dict() if cap else None,
        "balancer_liquidity": bal.to_dict() if bal else None,
        "borrow_size": size.to_dict() if size else None,
        "atomic_simulation": {
            "available": bool(sim.get("available")),
            "passed": bool(sim.get("passed")),
            "reason": sim.get("reason"),
            "block_tag": sim.get("block_tag"),
            "signed": False, "broadcast": False,
        },
        "freshness_ok": bool(controls.freshness_ok),
        "limited_live": decision.to_dict(),
        "signed": False, "broadcast": False, "limited_live_enabled": False,
    }


__all__ = ["ReadinessControls", "assess_candidate_readiness"]
