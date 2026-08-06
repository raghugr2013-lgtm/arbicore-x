"""Paper-Validation evidence model (v2.11.8).

Every opportunity that transits the OpportunityPipeline produces
exactly one :class:`EvidenceBundle`.  The bundle is:

* **immutable** — created once, never mutated.  Downstream analysis
  (Shadow Certification, Limited Live promotion) creates *linked*
  records rather than modifying the original.
* **canonically identified** by ``validation_id``, a v4 UUID assigned
  at pipeline entry.  The same ID appears on every journal event so
  the bundle + journal are joinable.
* **per-stage traced** with :class:`StageMetric` — start / end / duration
  / result / failure reason for every stage the pipeline touched.
* **terminal-outcome-only** — the :class:`PaperOutcome` field is
  assigned once, at completion.  Intermediate stages do NOT populate it.

Persistence is handled by :class:`~arbicore.paper.repo.PaperEvidenceRepository`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .outcomes import PaperOutcome


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_validation_id() -> str:
    """Canonical Paper Validation identifier (UUID v4, no prefix).

    Rendered without a prefix so it composes freely into log lines and
    dashboards; the caller adds context via journal events + evidence
    bundles.
    """
    return str(uuid.uuid4())


@dataclass(frozen=True)
class StageMetric:
    """Per-stage timing + result record.

    Frozen — once created it cannot be mutated.  Every field is a
    primitive so :func:`dataclasses.asdict` produces a Mongo-safe dict
    without any custom encoder.
    """

    stage: str
    started_at: str          # ISO-8601 UTC
    ended_at: str            # ISO-8601 UTC
    duration_ms: float
    ok: bool
    detail: str = ""
    failure_reason: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceBundle:
    """Immutable Paper Validation record for a single opportunity.

    The frozen dataclass guarantees no accidental mutation in Python.
    Persistence (see :class:`PaperEvidenceRepository`) enforces the
    same rule at the storage layer — bundles are ``insert_one``-only,
    never ``update`` / ``upsert``.
    """

    validation_id: str
    opportunity_id: str
    strategy: str
    mode: str

    #: The eight-value terminal verdict.  Assigned exactly once, by
    #: :func:`~arbicore.paper.classifier.classify_outcome`, at pipeline
    #: completion.
    outcome: PaperOutcome
    outcome_reason: str

    stages: List[Dict[str, Any]] = field(default_factory=list)

    scanner_family: Optional[str]  = None
    plan_id: Optional[str]         = None
    #: When the Simulation stage runs (Slice B onwards) this records
    #: which backend produced the verdict — ``eth_call`` for real RPC
    #: simulation, ``heuristic`` for the documented offline dry-run,
    #: ``None`` when the stage did not run.
    simulation_backend: Optional[str] = None

    #: Serialised primary inputs the pipeline consumed — kept small so
    #: the bundle stays under ~16 KB.  Full opportunity payloads live
    #: in ``arbicore_opportunities``; the ``opportunity_id`` above is
    #: the join key.
    inputs: Dict[str, Any] = field(default_factory=dict)

    #: Pipeline's PipelineResult.action ("broadcast" | "shadow" | "deny" |
    #: "reject" | "observe").  Preserved so existing callers keep their
    #: contract; the canonical verdict is ``outcome``.
    pipeline_action: str = ""

    #: ISO-8601 UTC — matches ``EvidenceBundle`` creation time (same as
    #: the moment the outcome is classified).
    created_at: str = field(default_factory=_iso_now)

    #: Version tag for the schema — bump when a *breaking* field changes.
    schema_version: str = "v2.11.8"

    def to_mongo(self) -> Dict[str, Any]:
        d = asdict(self)
        d["outcome"] = self.outcome.value
        return d

    @staticmethod
    def from_mongo(doc: Dict[str, Any]) -> "EvidenceBundle":
        outcome_raw = doc.get("outcome")
        outcome = (outcome_raw if isinstance(outcome_raw, PaperOutcome)
                   else PaperOutcome(outcome_raw))
        return EvidenceBundle(
            validation_id      = doc["validation_id"],
            opportunity_id     = doc["opportunity_id"],
            strategy           = doc.get("strategy", ""),
            mode               = doc.get("mode", ""),
            outcome            = outcome,
            outcome_reason     = doc.get("outcome_reason", ""),
            stages             = list(doc.get("stages") or []),
            scanner_family     = doc.get("scanner_family"),
            plan_id            = doc.get("plan_id"),
            simulation_backend = doc.get("simulation_backend"),
            inputs             = dict(doc.get("inputs") or {}),
            pipeline_action    = doc.get("pipeline_action", ""),
            created_at         = doc.get("created_at") or _iso_now(),
            schema_version     = doc.get("schema_version") or "v2.11.8",
        )
