"""Minimal in-memory repository shims used by Wave 1B-α.

The upstream Mongo-backed repositories under ``arbicore/data/mongo/`` depend
on a legacy ``services.db`` module which does not exist in the ArbiCore X
canonical runtime layout. Wave 1B-α therefore does NOT reuse those mongo
repos — it plugs in these lightweight, self-contained implementations so
that ``EntityScorer`` and ``HeuristicRegimeClassifier`` can construct and
run without pulling the legacy runtime into scope.

All state lives in-process; there is no persistence beyond the current
process lifetime. This is intentional for Wave 1B-α: the intelligence
pipeline's *durable* evidence path is MID (through :class:`MidEvidenceBridge`)
— these repos exist only to satisfy the engines' constructor contracts and
give them enough scratch state to run.

Wave 1B-β will replace these with real MID-backed shims once scanners are
publishing state rows to MID.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ...data.metrics_repo import (
    MetricsRepository, SignalMetric, WalletMetric,
)
from ...data.outcome_repo import OutcomeRepository, OutcomeRow, StateRow
from ...data.regime_snapshot_repo import (
    RegimeSnapshot, RegimeSnapshotRepository,
)


class InMemoryMetricsRepository(MetricsRepository):
    """Wave 1B-α — enough to make ``EntityScorer`` and any consumer that
    only reads ``list_wallet_metrics`` / ``upsert_wallet_metric`` succeed."""

    def __init__(self) -> None:
        self._signals: Dict[str, SignalMetric] = {}
        self._wallets: Dict[str, WalletMetric] = {}

    async def upsert_signal_metric(self, metric: SignalMetric) -> bool:
        self._signals[metric.signal_id] = metric
        return True

    async def list_signal_metrics(self, signal_id: Optional[str] = None,
                                  subject_id: Optional[str] = None,
                                  limit: int = 200) -> List[SignalMetric]:
        rows = list(self._signals.values())
        if signal_id:
            rows = [r for r in rows if r.signal_id == signal_id]
        if subject_id:
            rows = [r for r in rows if r.subject_id == subject_id]
        return rows[:limit]

    async def upsert_wallet_metric(self, metric: WalletMetric) -> bool:
        self._wallets[metric.wallet_id] = metric
        return True

    async def list_wallet_metrics(self, entity_id: Optional[str] = None,
                                  limit: int = 200) -> List[WalletMetric]:
        rows = list(self._wallets.values())
        if entity_id:
            rows = [r for r in rows if r.entity_id == entity_id
                    or r.wallet_id == entity_id]
        return rows[:limit]

    async def counts(self) -> Dict[str, int]:
        return {
            "signal_metrics": len(self._signals),
            "wallet_metrics": len(self._wallets),
        }


class InMemoryOutcomeRepository(OutcomeRepository):
    """Wave 1B-α — supports ``list_states`` which is the only method the
    regime classifier calls. All other ABC methods return trivial defaults
    so the class remains instantiable."""

    def __init__(self) -> None:
        self._outcomes: Dict[str, OutcomeRow] = {}
        self._states: List[StateRow] = []

    async def upsert_outcome(self, outcome: OutcomeRow,
                             only_insert: bool = False) -> bool:
        if only_insert and outcome.id in self._outcomes:
            return False
        self._outcomes[outcome.id] = outcome
        return True

    async def list_due(self, now_ts: float,
                       limit: int = 200) -> List[OutcomeRow]:
        rows = [r for r in self._outcomes.values()
                if not r.evaluated and r.due_at <= now_ts]
        return rows[:limit]

    async def list_for_subject(
        self,
        subject_id: str,
        evaluated: Optional[bool] = None,
        provenance_filter: Optional[frozenset] = None,
    ) -> List[OutcomeRow]:
        rows = [r for r in self._outcomes.values()
                if r.subject_id == subject_id]
        if evaluated is not None:
            rows = [r for r in rows if r.evaluated == evaluated]
        if provenance_filter is not None:
            rows = [r for r in rows if r.provenance in provenance_filter]
        return rows

    async def append_state_snapshot(self, state: StateRow) -> None:
        self._states.append(state)
        if len(self._states) > 5000:
            self._states = self._states[-5000:]

    async def latest_state(self, subject_id: str) -> Optional[StateRow]:
        rows = [s for s in self._states if s.subject_id == subject_id]
        if not rows:
            return None
        rows.sort(key=lambda s: s.captured_at_ts)
        return rows[-1]

    async def list_states(self, subject_id: str,
                          t0: float, t1: float,
                          limit: int = 1500) -> List[StateRow]:
        rows = [s for s in self._states
                if s.subject_id == subject_id
                and t0 <= s.captured_at_ts <= t1]
        rows.sort(key=lambda s: s.captured_at_ts)
        return rows[:limit]

    async def count_outcomes_by_evaluated(self) -> Dict[str, int]:
        evaluated = sum(1 for r in self._outcomes.values() if r.evaluated)
        return {
            "evaluated": evaluated,
            "unevaluated": len(self._outcomes) - evaluated,
        }


class InMemoryRegimeSnapshotRepository(RegimeSnapshotRepository):
    """Wave 1B-α — the classifier appends here; the bridge separately
    mirrors every snapshot into MID."""

    def __init__(self) -> None:
        self._rows: List[RegimeSnapshot] = []

    async def append(self, snapshot: RegimeSnapshot) -> bool:
        self._rows.append(snapshot)
        if len(self._rows) > 2000:
            self._rows = self._rows[-2000:]
        return True

    async def latest(self) -> Optional[RegimeSnapshot]:
        return self._rows[-1] if self._rows else None

    async def list_since(self, t0: float,
                          limit: int = 500) -> List[RegimeSnapshot]:
        rows = [r for r in self._rows if r.captured_at >= t0]
        return rows[-limit:]

    async def count(self) -> int:
        return len(self._rows)
