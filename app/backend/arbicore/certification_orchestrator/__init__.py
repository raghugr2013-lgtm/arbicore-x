"""ArbiCore X — Certification / Gate Orchestrator (deterministic).

DESIGN LAW (non-negotiable): the AI/LLM is NEVER the authority that decides a
gate colour. Every PASS/FAIL/BLOCKED verdict in this package is produced by pure,
deterministic policy evaluation over machine-readable evidence. AI may diagnose,
summarise, or propose remediation elsewhere — but it does not set gate state.

This package is ADDITIVE and READ-ONLY with respect to the trading system:
  * It NEVER signs, broadcasts, deploys, or enables any live mode.
  * It NEVER lowers economic thresholds or weakens a security invariant.
  * A missing/ambiguous piece of evidence is fail-closed (RED/BLOCKED), never
    optimistically assumed GREEN.
"""
from .policy import (
    GateId, Verdict, LiveState, ECONOMIC_POLICY, GATES, ORCHESTRATOR_VERSION,
)
from .evidence import (
    EvidenceContext, EvidenceRecord, ObservationWindow, evidence_hash,
)
from .engine import (
    GateEngine, CircuitBreaker, RemediationPolicy, evaluate_certification,
    compute_dashboard_state,
)

__all__ = [
    "GateId", "Verdict", "LiveState", "ECONOMIC_POLICY", "GATES",
    "ORCHESTRATOR_VERSION", "EvidenceContext", "EvidenceRecord",
    "ObservationWindow", "evidence_hash", "GateEngine", "CircuitBreaker",
    "RemediationPolicy", "evaluate_certification", "compute_dashboard_state",
]
