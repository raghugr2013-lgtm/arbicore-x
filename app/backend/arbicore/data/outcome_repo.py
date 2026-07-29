"""ArbiCore X — OutcomeRepository ABC (Phase B).

Per-checkpoint outcome rows + rolling state snapshots. Phase B ships the ABC
and the in-memory mock. Concrete consumers (OutcomeTracker worker) are
Phase C wave 1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .horizons import default_horizon_specs


@dataclass
class OutcomeRow:
    """One per (opportunity_id, horizon_label)."""
    id: str                              # `${opportunity_id}::${horizon_label}` or uuid
    opportunity_id: str
    subject_id: Optional[str]
    horizon_label: str                   # e.g. "5m", "1h"
    horizon_s: int
    due_at: float                        # epoch seconds when row becomes evaluable
    evaluated: bool = False
    realized_metric: Optional[float] = None
    realized_outcome: Optional[Dict[str, Any]] = None
    note: Optional[str] = None
    created_at: float = 0.0
    updated_at: float = 0.0
    provenance: Optional[str] = None     # mirrors source opportunity provenance

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StateRow:
    """Rolling state snapshot, append-only, 30-day TTL."""
    subject_id: str
    opportunity_type: str                # OpportunityType.value
    captured_at_ts: float
    primary_metric: float
    secondary_metrics: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    provenance: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OutcomeRepository(ABC):
    """Outcome + state-snapshot contract."""

    @abstractmethod
    async def upsert_outcome(self, outcome: OutcomeRow, only_insert: bool = False) -> bool:
        """Insert or update an outcome row.

        only_insert=True semantics: insert-if-absent (preserves evaluated rows
        against replay corruption — pattern lifted from GemHunter
        outcomes/tracker.py:116).
        """

    @abstractmethod
    async def list_due(self, now_ts: float, limit: int = 200) -> List[OutcomeRow]:
        """All unevaluated outcomes whose due_at <= now_ts."""

    @abstractmethod
    async def list_for_subject(self,
                               subject_id: str,
                               evaluated: Optional[bool] = None,
                               provenance_filter: Optional[frozenset] = None,
                               ) -> List[OutcomeRow]:
        """All outcome rows for a subject_id (optional evaluated filter)."""

    @abstractmethod
    async def append_state_snapshot(self, state: StateRow) -> None:
        """Append-only state snapshot for a subject."""

    @abstractmethod
    async def latest_state(self, subject_id: str) -> Optional[StateRow]:
        """Most recent state snapshot for a subject."""

    @abstractmethod
    async def list_states(self,
                          subject_id: str,
                          t0: float,
                          t1: float,
                          limit: int = 1500,
                          ) -> List[StateRow]:
        """State snapshots for a subject in [t0, t1]."""

    @abstractmethod
    async def count_outcomes_by_evaluated(self) -> Dict[str, int]:
        """For /api/arbicore/health: {'evaluated': n, 'unevaluated': m}."""


def make_outcome_rows_for(opportunity_id: str,
                          subject_id: Optional[str],
                          emission_ts: float,
                          provenance: Optional[str] = None,
                          ) -> List[OutcomeRow]:
    """Phase B helper — emit one OutcomeRow per default horizon for a new opp.

    NOT called automatically anywhere in Phase B (no worker writes outcomes).
    Available to Phase C wave 1 implementers.
    """
    rows: List[OutcomeRow] = []
    for spec in default_horizon_specs():
        rows.append(OutcomeRow(
            id=f"{opportunity_id}::{spec.label}",
            opportunity_id=opportunity_id,
            subject_id=subject_id,
            horizon_label=spec.label,
            horizon_s=spec.seconds,
            due_at=float(emission_ts) + float(spec.seconds),
            created_at=float(emission_ts),
            updated_at=float(emission_ts),
            provenance=provenance,
        ))
    return rows
