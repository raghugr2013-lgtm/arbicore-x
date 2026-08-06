"""Shadow Certification models (v2.11.9).

Two frozen dataclasses form the canonical record:

* :class:`ShadowCertificationCycle` — one immutable snapshot per cycle.
  Links to zero-or-more :class:`~arbicore.paper.evidence.EvidenceBundle`
  records via ``validation_ids``.
* :class:`ShadowCertificationRun`   — the wrapper aggregate.  A run is
  created in ``RUNNING`` state, accumulates cycles, and is finalised
  exactly once into a terminal :class:`CertificationStatus`.

Immutability contract:

* :class:`ShadowCertificationCycle` is ``frozen=True``; once appended
  to a run it cannot be mutated.
* :class:`ShadowCertificationRun` is ``frozen=True``; append + finalise
  operations return a *new* run instance rather than mutating.  The
  repository update method persists the new instance under the same
  ``run_id``.

This matches the Paper Validation Framework immutability pattern.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .thresholds import (
    CertificationStatus,
    CertificationThresholds,
    CycleStatus,
    TERMINAL_STATUSES,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return f"shadowcert-{uuid.uuid4()}"


def new_cycle_id() -> str:
    return f"shadowcyc-{uuid.uuid4()}"


@dataclass(frozen=True)
class ShadowCertificationCycle:
    """One immutable certification cycle snapshot.

    All rate / percentile fields are cycle-scoped (delta since previous
    cycle), *not* cumulative — the run aggregates them at finalise time.
    """

    cycle_id: str
    cycle_index: int
    started_at: str            # ISO-8601 UTC
    completed_at: str          # ISO-8601 UTC
    duration_ms: float

    #: EvidenceBundle IDs recorded during this cycle window.
    validation_ids: List[str] = field(default_factory=list)

    #: Aggregated counts within this cycle.
    opportunities_seen: int = 0
    opportunities_processed: int = 0
    executable_count: int = 0

    #: Delta outcome histogram (this cycle only).
    outcome_counts: Dict[str, int] = field(default_factory=dict)

    #: Per-stage p95 duration in ms observed in this cycle.
    stage_p95_ms: Dict[str, float] = field(default_factory=dict)

    #: Infra probe results for this cycle.
    infra_health: Dict[str, Any] = field(default_factory=dict)

    #: Cycle-level runner exceptions delta.
    runner_exceptions: int = 0

    #: Cycle grade + human-readable reasons for the grade.
    cycle_status: str = CycleStatus.PASS.value
    cycle_reasons: List[str] = field(default_factory=list)

    #: Optional flags — e.g. ``low_volume`` (below min_opps_per_cycle).
    flags: List[str] = field(default_factory=list)

    @property
    def executable_rate(self) -> float:
        if self.opportunities_processed <= 0:
            return 0.0
        return self.executable_count / float(self.opportunities_processed)

    def to_mongo(self) -> Dict[str, Any]:
        d = {
            "cycle_id": self.cycle_id,
            "cycle_index": self.cycle_index,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_ms": self.duration_ms,
            "validation_ids": list(self.validation_ids),
            "opportunities_seen": self.opportunities_seen,
            "opportunities_processed": self.opportunities_processed,
            "executable_count": self.executable_count,
            "outcome_counts": dict(self.outcome_counts),
            "stage_p95_ms": dict(self.stage_p95_ms),
            "infra_health": dict(self.infra_health),
            "runner_exceptions": self.runner_exceptions,
            "cycle_status": self.cycle_status,
            "cycle_reasons": list(self.cycle_reasons),
            "flags": list(self.flags),
        }
        return d

    @classmethod
    def from_mongo(cls, d: Dict[str, Any]) -> "ShadowCertificationCycle":
        return cls(
            cycle_id=str(d.get("cycle_id") or ""),
            cycle_index=int(d.get("cycle_index") or 0),
            started_at=str(d.get("started_at") or ""),
            completed_at=str(d.get("completed_at") or ""),
            duration_ms=float(d.get("duration_ms") or 0.0),
            validation_ids=list(d.get("validation_ids") or []),
            opportunities_seen=int(d.get("opportunities_seen") or 0),
            opportunities_processed=int(d.get("opportunities_processed") or 0),
            executable_count=int(d.get("executable_count") or 0),
            outcome_counts=dict(d.get("outcome_counts") or {}),
            stage_p95_ms=dict(d.get("stage_p95_ms") or {}),
            infra_health=dict(d.get("infra_health") or {}),
            runner_exceptions=int(d.get("runner_exceptions") or 0),
            cycle_status=str(d.get("cycle_status") or CycleStatus.PASS.value),
            cycle_reasons=list(d.get("cycle_reasons") or []),
            flags=list(d.get("flags") or []),
        )


@dataclass(frozen=True)
class ShadowCertificationRun:
    """Immutable Shadow Certification run aggregate.

    Public constructors:
      * :meth:`start` — first-class factory (fresh RUNNING run).
      * :meth:`with_cycle` — append a cycle, return a new run instance.
      * :meth:`finalise` — compute the terminal status, return a new run.
      * :meth:`abort` — operator-triggered ABORT, return a new run.
    """

    run_id: str
    started_at: str
    completed_at: Optional[str]
    status: str                     # CertificationStatus.value
    target_cycles: int
    thresholds: Dict[str, Any]      # CertificationThresholds.to_dict()
    cycles: List[ShadowCertificationCycle] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    pass_reasons: List[str] = field(default_factory=list)
    warning_reasons: List[str] = field(default_factory=list)
    fail_reasons: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    schema_version: str = "shadow_cert_v1"

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------
    @classmethod
    def start(
        cls,
        *,
        thresholds: CertificationThresholds,
        run_id: Optional[str] = None,
    ) -> "ShadowCertificationRun":
        return cls(
            run_id=run_id or new_run_id(),
            started_at=_iso_now(),
            completed_at=None,
            status=CertificationStatus.RUNNING.value,
            target_cycles=thresholds.target_cycles,
            thresholds=thresholds.to_dict(),
            cycles=[],
            summary={},
            pass_reasons=[],
            warning_reasons=[],
            fail_reasons=[],
            notes=[],
        )

    # ------------------------------------------------------------------
    # State-transition helpers (all return NEW instances)
    # ------------------------------------------------------------------
    def _assert_running(self) -> None:
        if self.status != CertificationStatus.RUNNING.value:
            raise ValueError(
                f"ShadowCertificationRun {self.run_id} is not RUNNING "
                f"(status={self.status})"
            )

    def with_cycle(
        self, cycle: ShadowCertificationCycle
    ) -> "ShadowCertificationRun":
        self._assert_running()
        return ShadowCertificationRun(
            run_id=self.run_id,
            started_at=self.started_at,
            completed_at=self.completed_at,
            status=self.status,
            target_cycles=self.target_cycles,
            thresholds=self.thresholds,
            cycles=list(self.cycles) + [cycle],
            summary=self.summary,
            pass_reasons=self.pass_reasons,
            warning_reasons=self.warning_reasons,
            fail_reasons=self.fail_reasons,
            notes=self.notes,
            schema_version=self.schema_version,
        )

    def finalise(
        self,
        *,
        status: CertificationStatus,
        summary: Dict[str, Any],
        pass_reasons: List[str],
        warning_reasons: List[str],
        fail_reasons: List[str],
    ) -> "ShadowCertificationRun":
        if status not in TERMINAL_STATUSES:
            raise ValueError(f"cannot finalise into non-terminal status {status}")
        if self.status != CertificationStatus.RUNNING.value:
            raise ValueError(
                f"ShadowCertificationRun {self.run_id} already terminal "
                f"({self.status})"
            )
        return ShadowCertificationRun(
            run_id=self.run_id,
            started_at=self.started_at,
            completed_at=_iso_now(),
            status=status.value,
            target_cycles=self.target_cycles,
            thresholds=self.thresholds,
            cycles=list(self.cycles),
            summary=dict(summary),
            pass_reasons=list(pass_reasons),
            warning_reasons=list(warning_reasons),
            fail_reasons=list(fail_reasons),
            notes=list(self.notes),
            schema_version=self.schema_version,
        )

    def abort(self, reason: str) -> "ShadowCertificationRun":
        if self.status != CertificationStatus.RUNNING.value:
            return self  # idempotent — already terminal
        return ShadowCertificationRun(
            run_id=self.run_id,
            started_at=self.started_at,
            completed_at=_iso_now(),
            status=CertificationStatus.ABORTED.value,
            target_cycles=self.target_cycles,
            thresholds=self.thresholds,
            cycles=list(self.cycles),
            summary=dict(self.summary),
            pass_reasons=list(self.pass_reasons),
            warning_reasons=list(self.warning_reasons),
            fail_reasons=list(self.fail_reasons) + [f"aborted: {reason}"],
            notes=list(self.notes) + [f"aborted: {reason}"],
            schema_version=self.schema_version,
        )

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
    @property
    def is_terminal(self) -> bool:
        try:
            return CertificationStatus(self.status) in TERMINAL_STATUSES
        except ValueError:
            return False

    @property
    def cycles_completed(self) -> int:
        return len(self.cycles)

    def cumulative_outcome_counts(self) -> Dict[str, int]:
        agg: Dict[str, int] = {}
        for c in self.cycles:
            for k, v in c.outcome_counts.items():
                agg[k] = agg.get(k, 0) + int(v)
        return agg

    def cumulative_totals(self) -> Tuple[int, int, int]:
        """Returns (opps_seen, opps_processed, executable_count)."""
        s = p = e = 0
        for c in self.cycles:
            s += c.opportunities_seen
            p += c.opportunities_processed
            e += c.executable_count
        return s, p, e

    def cumulative_executable_rate(self) -> float:
        _, p, e = self.cumulative_totals()
        if p <= 0:
            return 0.0
        return e / float(p)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------
    def to_mongo(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "status": self.status,
            "target_cycles": self.target_cycles,
            "thresholds": dict(self.thresholds),
            "cycles": [c.to_mongo() for c in self.cycles],
            "summary": dict(self.summary),
            "pass_reasons": list(self.pass_reasons),
            "warning_reasons": list(self.warning_reasons),
            "fail_reasons": list(self.fail_reasons),
            "notes": list(self.notes),
            "schema_version": self.schema_version,
        }

    def to_report(self) -> Dict[str, Any]:
        """Operator-facing report shape."""
        s, p, e = self.cumulative_totals()
        return {
            "run_id": self.run_id,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "target_cycles": self.target_cycles,
            "cycles_completed": self.cycles_completed,
            "thresholds": dict(self.thresholds),
            "summary": dict(self.summary),
            "cumulative": {
                "opportunities_seen": s,
                "opportunities_processed": p,
                "executable_count": e,
                "executable_rate": (e / float(p)) if p > 0 else 0.0,
                "outcome_counts": self.cumulative_outcome_counts(),
            },
            "cycles": [c.to_mongo() for c in self.cycles],
            "pass_reasons": list(self.pass_reasons),
            "warning_reasons": list(self.warning_reasons),
            "fail_reasons": list(self.fail_reasons),
            "notes": list(self.notes),
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_mongo(cls, d: Dict[str, Any]) -> "ShadowCertificationRun":
        return cls(
            run_id=str(d.get("run_id") or ""),
            started_at=str(d.get("started_at") or ""),
            completed_at=(str(d["completed_at"])
                          if d.get("completed_at") else None),
            status=str(d.get("status") or CertificationStatus.RUNNING.value),
            target_cycles=int(d.get("target_cycles") or 20),
            thresholds=dict(d.get("thresholds") or {}),
            cycles=[ShadowCertificationCycle.from_mongo(c)
                    for c in (d.get("cycles") or [])],
            summary=dict(d.get("summary") or {}),
            pass_reasons=list(d.get("pass_reasons") or []),
            warning_reasons=list(d.get("warning_reasons") or []),
            fail_reasons=list(d.get("fail_reasons") or []),
            notes=list(d.get("notes") or []),
            schema_version=str(d.get("schema_version") or "shadow_cert_v1"),
        )
