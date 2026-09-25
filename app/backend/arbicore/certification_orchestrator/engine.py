"""Deterministic Gate Engine + circuit breakers + remediation policy + state.

The engine walks G0..G5 in order. A gate is GREEN iff EVERY mandatory
requirement is GREEN. Technical/sim gates auto-advance (no human interpretation).
A ``critical`` requirement returning RED/BLOCKED trips a circuit breaker and moves
the whole system to PAUSED. Live transitions are NEVER auto-authorised.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .policy import (
    GATES, GateId, GateSpec, Verdict, LiveState, ECONOMIC_POLICY, MIN_EVIDENCE,
    ORCHESTRATOR_VERSION,
)
from .evidence import EvidenceContext, EvidenceRecord, ObservationWindow


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Circuit breakers ------------------------------------------------------- #
class CircuitBreaker:
    """Deterministic critical-violation detector. Any triggered breaker forces
    the system to a safe PAUSED/BLOCKED state instead of continuing."""

    CRITICAL_KINDS = (
        "capability_mismatch", "security_invariant_violation", "repayment_anomaly",
        "quote_route_integrity_failure", "economic_policy_violation",
        "unexpected_bytecode", "evidence_corruption", "runtime_critical_failure",
    )

    @staticmethod
    def scan(ev: EvidenceContext) -> List[Dict[str, str]]:
        trips: List[Dict[str, str]] = []
        econ = ev.get("economic_policy") or {}
        if econ:
            for k, v in ECONOMIC_POLICY.items():
                if econ.get(k) is not None and econ.get(k) != v:
                    trips.append({"kind": "economic_policy_violation",
                                  "detail": f"{k}={econ.get(k)} != frozen {v}"})
        sec = ev.get("security", {})
        if (sec.get("violations") or 0) > 0:
            trips.append({"kind": "security_invariant_violation",
                          "detail": f"{sec.get('violations')} violation(s)"})
        cap = ev.get("execution_capability", {})
        if cap.get("capability_mismatch") is True:
            trips.append({"kind": "capability_mismatch",
                          "detail": cap.get("reason", "declared != deployed")})
        if cap.get("bytecode_unexpected") is True:
            trips.append({"kind": "unexpected_bytecode",
                          "detail": "deployed bytecode does not match expected"})
        rec = ev.get("reconciliation", {})
        if (rec.get("repayment_anomalies") or 0) > 0:
            trips.append({"kind": "repayment_anomaly",
                          "detail": f"{rec.get('repayment_anomalies')} anomaly"})
        q = ev.get("quote_route", {})
        if q.get("integrity_ok") is False:
            trips.append({"kind": "quote_route_integrity_failure",
                          "detail": q.get("reason", "integrity check failed")})
        el = ev.get("evidence_ledger", {})
        if el.get("corrupted") is True:
            trips.append({"kind": "evidence_corruption", "detail": "ledger hash mismatch"})
        rt = ev.get("runtime", {})
        if rt.get("critical_failure") is True:
            trips.append({"kind": "runtime_critical_failure",
                          "detail": rt.get("reason", "runtime critical failure")})
        return trips


# --- Automatic remediation policy ------------------------------------------ #
class RemediationPolicy:
    """Whitelist of KNOWN, reversible, low-risk auto-remediations. Everything not
    on the allow-list is forbidden — and a hard deny-list is enforced regardless."""

    ALLOWED = frozenset({
        "clear_stale_generated_artifacts",
        "reinstall_missing_non_secret_dependency",
        "reset_test_environment_readiness",
        "restart_permitted_non_production_service",
    })

    FORBIDDEN = frozenset({
        "lower_economic_threshold", "weaken_security_check", "allow_unapproved_router",
        "allow_unapproved_factory", "expand_supported_chains", "expand_supported_venues",
        "bypass_simulation", "bypass_security_invariant", "change_profit_gate",
        "enable_live_execution", "enable_autoexec", "sign_transaction", "broadcast_transaction",
        "deploy_contract",
    })

    @classmethod
    def is_allowed(cls, action: str) -> bool:
        return action in cls.ALLOWED and action not in cls.FORBIDDEN


# --- Gate evaluation -------------------------------------------------------- #
@dataclass
class GateResult:
    gate_id: str
    title: str
    verdict: str
    reason: str
    requirements: List[Dict[str, Any]] = field(default_factory=list)
    blocking_requirement: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id, "title": self.title, "verdict": self.verdict,
            "reason": self.reason, "requirements": self.requirements,
            "blocking_requirement": self.blocking_requirement,
        }


def _evaluate_gate(spec: GateSpec, ev: EvidenceContext) -> GateResult:
    reqs: List[Dict[str, Any]] = []
    blocking: Optional[str] = None
    gate_verdict = Verdict.GREEN
    critical_trip = False
    for r in spec.requirements:
        verdict, reason = r.evaluator(ev)
        reqs.append({"id": r.id, "description": r.description, "verdict": verdict.value,
                     "reason": reason, "mandatory": r.mandatory, "critical": r.critical})
        if not r.mandatory:
            continue
        if verdict != Verdict.GREEN:
            # First non-green mandatory requirement decides the gate.
            if blocking is None:
                blocking = r.id
                gate_verdict = verdict if verdict in (Verdict.RED, Verdict.BLOCKED) else Verdict.UNKNOWN
            if r.critical and verdict in (Verdict.RED, Verdict.BLOCKED):
                critical_trip = True
    if critical_trip:
        gate_verdict = Verdict.BLOCKED
    reason = "all mandatory requirements GREEN" if gate_verdict == Verdict.GREEN \
        else f"blocked by '{blocking}'"
    return GateResult(spec.id.value, spec.title, gate_verdict.value, reason, reqs, blocking)


class GateEngine:
    """Deterministic orchestrator over G0..G5 + live-eligibility derivation."""

    def __init__(self, evidence: EvidenceContext,
                 windows: Optional[Dict[str, ObservationWindow]] = None,
                 authorizations: Optional[Dict[str, bool]] = None):
        self.ev = evidence if isinstance(evidence, EvidenceContext) else EvidenceContext(evidence or {})
        self.windows = windows or {}
        self.authorizations = authorizations or {}

    def evaluate(self) -> Dict[str, Any]:
        breaker_trips = CircuitBreaker.scan(self.ev)
        gate_results: List[GateResult] = []
        ledger: List[EvidenceRecord] = []
        current_gate: Optional[str] = None
        next_gate: Optional[str] = None
        first_blocker: Optional[str] = None
        prev_id: Optional[str] = None
        all_green_so_far = True

        for idx, spec in enumerate(GATES):
            gr = _evaluate_gate(spec, self.ev)
            gate_results.append(gr)
            nxt = GATES[idx + 1].id.value if idx + 1 < len(GATES) else "LIVE_ELIGIBILITY"
            ledger.append(self._record(spec.id.value, gr, prev_id, nxt).finalize())
            if all_green_so_far and gr.verdict == Verdict.GREEN.value:
                current_gate = spec.id.value          # highest contiguous-green gate
                next_gate = nxt
            elif all_green_so_far:
                # first non-green gate is where we are blocked
                all_green_so_far = False
                first_blocker = f"{spec.id.value}:{gr.blocking_requirement}"
                if next_gate is None:
                    next_gate = spec.id.value
            prev_id = spec.id.value

        if current_gate is None:
            next_gate = GATES[0].id.value

        # Circuit breaker overrides everything -> PAUSED.
        if breaker_trips:
            live_state = LiveState.PAUSED
        else:
            live_state = self._derive_live_state(all_green_so_far)

        return {
            "orchestrator_version": ORCHESTRATOR_VERSION,
            "evaluated_at": _now_iso(),
            "evidence_snapshot_hash": self.ev.snapshot_hash(),
            "gates": [g.to_dict() for g in gate_results],
            "current_gate": current_gate,
            "next_eligible_gate": next_gate,
            "first_blocker": first_blocker,
            "all_technical_gates_green": all_green_so_far and not breaker_trips,
            "circuit_breaker": {
                "tripped": bool(breaker_trips), "trips": breaker_trips,
                "state": "PAUSED" if breaker_trips else "ARMED",
            },
            "live_state": live_state.value,
            "authorization_required": self._authorization_notice(live_state),
            "observation_windows": {k: w.to_dict() for k, w in self.windows.items()},
            "evidence_ledger": [r.to_dict() for r in ledger],
        }

    def _derive_live_state(self, all_gates_green: bool) -> LiveState:
        if not all_gates_green:
            return LiveState.NOT_ELIGIBLE
        # All G0..G5 green => LIVE_ELIGIBILITY achieved. Now objective minimums.
        if not self._meets_evidence("limited_live"):
            return LiveState.LIVE_ELIGIBILITY
        # Limited-live objective minimums met => ELIGIBLE (never auto-authorised).
        if not self.authorizations.get("limited_live"):
            return LiveState.LIMITED_LIVE_ELIGIBLE
        # Operator authorised limited-live.
        if not self._meets_evidence("full_live"):
            return LiveState.LIMITED_LIVE_AUTHORIZED
        if not self.authorizations.get("full_live"):
            return LiveState.FULL_LIVE_ELIGIBLE
        return LiveState.FULL_LIVE_AUTHORIZED

    def _meets_evidence(self, tier: str) -> bool:
        req = MIN_EVIDENCE[tier]
        w = self.windows.get("24h" if tier == "limited_live" else "72h")
        if w is None:
            return False
        base = w.meets_minimums(
            min_observations=req["min_qualifying_observations"],
            min_successful=req["min_successful_simulations"],
        )
        if tier == "full_live":
            base = base and (self.ev.get("limited_live", {}).get("executions", 0)
                             >= req["min_limited_live_executions"])
        return base

    @staticmethod
    def _authorization_notice(state: LiveState) -> Optional[str]:
        if state == LiveState.LIMITED_LIVE_ELIGIBLE:
            return "operator must authorise a Limited-Live POLICY ENVELOPE (machine will NOT self-authorise)"
        if state == LiveState.FULL_LIVE_ELIGIBLE:
            return "operator must authorise a Full-Live POLICY ENVELOPE (machine will NOT self-authorise)"
        if state == LiveState.PAUSED:
            return "circuit breaker tripped — operator review required before re-arming"
        return None

    def _record(self, gate_id, gr: GateResult, prev, nxt) -> EvidenceRecord:
        return EvidenceRecord(
            gate_id=gate_id, evaluated_at=_now_iso(), result=gr.verdict,
            requirements=gr.requirements, evidence_refs=self.ev.get("evidence_refs", {}),
            evidence_snapshot_hash=self.ev.snapshot_hash(),
            test_counts=self.ev.get("tests", {}), security_findings=self.ev.get("security", {}),
            economic_status={"frozen": ECONOMIC_POLICY, "observed": self.ev.get("economic_policy", {})},
            runtime_status=self.ev.get("runtime", {}), previous_gate=prev,
            next_eligible_gate=nxt, reason=gr.reason, orchestrator_version=ORCHESTRATOR_VERSION,
        )


def evaluate_certification(evidence, windows=None, authorizations=None) -> Dict[str, Any]:
    return GateEngine(EvidenceContext(evidence or {}), windows, authorizations).evaluate()


def compute_dashboard_state(evidence, windows=None, authorizations=None) -> Dict[str, Any]:
    """Flat dashboard/state model (G0–G5 + live-eligibility + breaker + windows)."""
    full = evaluate_certification(evidence, windows, authorizations)
    gate_status = {g["gate_id"]: g["verdict"] for g in full["gates"]}
    ls = full["live_state"]
    windows_out = full["observation_windows"]
    return {
        "gates": gate_status,
        "current_gate": full["current_gate"],
        "next_gate": full["next_eligible_gate"],
        "current_blocker": full["first_blocker"],
        "live_eligibility": "LIVE_ELIGIBILITY" if ls in (
            "LIVE_ELIGIBILITY", "LIMITED_LIVE_ELIGIBLE", "LIMITED_LIVE_AUTHORIZED",
            "FULL_LIVE_ELIGIBLE", "FULL_LIVE_AUTHORIZED") else "NOT_ELIGIBLE",
        "limited_live_eligible": ls in ("LIMITED_LIVE_ELIGIBLE", "LIMITED_LIVE_AUTHORIZED",
                                        "FULL_LIVE_ELIGIBLE", "FULL_LIVE_AUTHORIZED"),
        "limited_live_authorized": ls in ("LIMITED_LIVE_AUTHORIZED", "FULL_LIVE_ELIGIBLE",
                                          "FULL_LIVE_AUTHORIZED"),
        "full_live_eligible": ls in ("FULL_LIVE_ELIGIBLE", "FULL_LIVE_AUTHORIZED"),
        "full_live_authorized": ls == "FULL_LIVE_AUTHORIZED",
        "live_state": ls,
        "authorization_required": full["authorization_required"],
        "circuit_breaker_state": full["circuit_breaker"]["state"],
        "circuit_breaker_trips": full["circuit_breaker"]["trips"],
        "evidence_age_seconds": None,
        "last_certification_run": full["evaluated_at"],
        "evidence_24h": windows_out.get("24h"),
        "evidence_72h": windows_out.get("72h"),
        "orchestrator_version": full["orchestrator_version"],
    }


__all__ = [
    "GateEngine", "CircuitBreaker", "RemediationPolicy",
    "evaluate_certification", "compute_dashboard_state", "GateResult",
]
