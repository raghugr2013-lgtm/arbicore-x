"""Evidence context, machine-readable evidence records, observation windows.

Pure data + hashing. No network, no mutation of the trading system.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_hash(payload: Any) -> str:
    """Deterministic SHA-256 over a JSON-normalised payload."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


class EvidenceContext(dict):
    """A plain dict of evidence namespaces (toolchain/git/economic_policy/
    tests/security/runtime/execution_capability/simulation/paper/evidence_ledger).

    Absent namespaces/keys are fail-closed by the policy predicates. Using a
    dict keeps the engine deterministic and trivially serialisable/hashable."""

    def snapshot_hash(self) -> str:
        return evidence_hash(dict(self))


@dataclass
class EvidenceRecord:
    """One machine-readable gate-evaluation record (append-only ledger row)."""
    gate_id: str
    evaluated_at: str
    result: str                       # GREEN / RED / BLOCKED / UNKNOWN
    requirements: List[Dict[str, Any]]
    evidence_refs: Dict[str, Any]
    evidence_snapshot_hash: str
    test_counts: Dict[str, Any]
    security_findings: Dict[str, Any]
    economic_status: Dict[str, Any]
    runtime_status: Dict[str, Any]
    previous_gate: Optional[str]
    next_eligible_gate: Optional[str]
    reason: str
    orchestrator_version: str
    record_hash: str = ""

    def finalize(self) -> "EvidenceRecord":
        body = {k: v for k, v in asdict(self).items() if k != "record_hash"}
        self.record_hash = evidence_hash(body)
        return self

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ObservationWindow:
    """Reliability observation window — NOT an elapsed-time hard gate.

    Records qualifying observations and anomaly counters. ``recommended_hours``
    is advisory context only; ``meets_minimums`` never depends on elapsed wall
    time — only on objective observation counts + zero critical anomalies."""
    label: str                                  # "24h" / "72h"
    recommended_hours: int
    started_at: str = field(default_factory=_now_iso)
    elapsed_hours: float = 0.0
    qualifying_observations: int = 0
    successful_simulations: int = 0
    failed_simulations: int = 0
    economic_violations: int = 0
    security_violations: int = 0
    circuit_breaker_events: int = 0
    reconciliation_anomalies: int = 0
    evidence_complete: bool = False

    def meets_minimums(self, *, min_observations: int, min_successful: int) -> bool:
        return (
            self.qualifying_observations >= min_observations
            and self.successful_simulations >= min_successful
            and self.economic_violations == 0
            and self.security_violations == 0
            and self.reconciliation_anomalies == 0
            and self.circuit_breaker_events == 0
            and self.evidence_complete
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


__all__ = [
    "EvidenceContext", "EvidenceRecord", "ObservationWindow", "evidence_hash",
]
