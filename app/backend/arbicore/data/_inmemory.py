"""ArbiCore X — In-memory mock repositories (Phase B test fixtures).

These satisfy the ABCs in arbicore/data/*. They are used by contract tests
and by any caller that wants to wire ArbiCore X without Mongo.
"""
from __future__ import annotations

import time
import uuid
from typing import Dict, List, Optional, Tuple

from ..models.canonical import CanonicalOpportunity
from ..models.enums import DataProvenance, OpportunityStatus, OpportunityType
from .metrics_repo import MetricsRepository, SignalMetric, WalletMetric
from .opportunity_repo import OpportunityRepository, validate_for_upsert
from .outcome_repo import OutcomeRepository, OutcomeRow, StateRow
from .regime_snapshot_repo import RegimeSnapshot, RegimeSnapshotRepository


def _now_ts() -> float:
    return time.time()


def _matches_filter(opp: CanonicalOpportunity, f: dict) -> bool:
    if not f:
        return True
    if "opportunity_type" in f:
        target = f["opportunity_type"]
        if isinstance(target, OpportunityType):
            if opp.opportunity_type is not target:
                return False
        else:
            if opp.opportunity_type.value != str(target):
                return False
    if "status" in f:
        target = f["status"]
        if isinstance(target, OpportunityStatus):
            if opp.status is not target:
                return False
        else:
            if opp.status.value != str(target):
                return False
    if "subject_id" in f:
        if opp.subject_id != f["subject_id"]:
            return False
    if "since" in f:
        # since is epoch seconds; compare against created_at iso parse for
        # simplicity — fall back to lifecycle marker if unparsable.
        try:
            import datetime as _dt
            opp_ts = _dt.datetime.fromisoformat(opp.created_at).timestamp()
        except Exception:
            opp_ts = 0.0
        if opp_ts < float(f["since"]):
            return False
    return True


class InMemoryOpportunityRepository(OpportunityRepository):
    def __init__(self) -> None:
        self._store: Dict[str, CanonicalOpportunity] = {}

    async def upsert(self, opp: CanonicalOpportunity) -> bool:
        validate_for_upsert(opp)
        if not opp.opportunity_id:
            opp.opportunity_id = uuid.uuid4().hex
        self._store[opp.opportunity_id] = opp
        return True

    async def get(self, opportunity_id: str) -> Optional[CanonicalOpportunity]:
        return self._store.get(opportunity_id)

    async def list_for_subject(self,
                               subject_id: str,
                               limit: int = 50,
                               provenance_filter: Optional[frozenset] = None,
                               ) -> List[CanonicalOpportunity]:
        out: List[CanonicalOpportunity] = []
        for opp in self._store.values():
            if opp.subject_id != subject_id:
                continue
            if provenance_filter is not None and opp.source_data_quality not in provenance_filter:
                continue
            out.append(opp)
        out.sort(key=lambda o: o.created_at, reverse=True)
        return out[:limit]

    async def find(self,
                   filter: dict,
                   limit: int = 100,
                   provenance_filter: Optional[frozenset] = None,
                   ) -> List[CanonicalOpportunity]:
        out: List[CanonicalOpportunity] = []
        for opp in self._store.values():
            if not _matches_filter(opp, filter):
                continue
            if provenance_filter is not None and opp.source_data_quality not in provenance_filter:
                continue
            out.append(opp)
        out.sort(key=lambda o: o.created_at, reverse=True)
        return out[:limit]

    async def count_by_type_status(self) -> dict:
        counts: Dict[str, Dict[str, int]] = {}
        for opp in self._store.values():
            t = opp.opportunity_type.value
            s = opp.status.value
            counts.setdefault(t, {})
            counts[t][s] = counts[t].get(s, 0) + 1
        return counts

    # Test conveniences
    def _all(self) -> List[CanonicalOpportunity]:
        return list(self._store.values())

    def _clear(self) -> None:
        self._store.clear()


class InMemoryOutcomeRepository(OutcomeRepository):
    def __init__(self) -> None:
        self._outcomes: Dict[str, OutcomeRow] = {}
        self._states: List[StateRow] = []

    async def upsert_outcome(self, outcome: OutcomeRow, only_insert: bool = False) -> bool:
        existing = self._outcomes.get(outcome.id)
        if only_insert and existing is not None:
            return False
        outcome.updated_at = _now_ts()
        if existing is None:
            outcome.created_at = outcome.created_at or _now_ts()
        self._outcomes[outcome.id] = outcome
        return True

    async def list_due(self, now_ts: float, limit: int = 200) -> List[OutcomeRow]:
        out = [o for o in self._outcomes.values()
               if (not o.evaluated) and o.due_at <= now_ts]
        out.sort(key=lambda r: r.due_at)
        return out[:limit]

    async def list_for_subject(self,
                               subject_id: str,
                               evaluated: Optional[bool] = None,
                               provenance_filter: Optional[frozenset] = None,
                               ) -> List[OutcomeRow]:
        out = []
        for o in self._outcomes.values():
            if o.subject_id != subject_id:
                continue
            if evaluated is not None and o.evaluated != evaluated:
                continue
            if provenance_filter is not None:
                provset = {p.value for p in provenance_filter}
                if o.provenance not in provset:
                    continue
            out.append(o)
        out.sort(key=lambda r: r.due_at, reverse=True)
        return out

    async def append_state_snapshot(self, state: StateRow) -> None:
        self._states.append(state)

    async def latest_state(self, subject_id: str) -> Optional[StateRow]:
        states = [s for s in self._states if s.subject_id == subject_id]
        if not states:
            return None
        return max(states, key=lambda s: s.captured_at_ts)

    async def list_states(self,
                          subject_id: str,
                          t0: float,
                          t1: float,
                          limit: int = 1500,
                          ) -> List[StateRow]:
        out = [s for s in self._states
               if s.subject_id == subject_id and t0 <= s.captured_at_ts <= t1]
        out.sort(key=lambda s: s.captured_at_ts)
        return out[:limit]

    async def count_outcomes_by_evaluated(self) -> Dict[str, int]:
        ev = sum(1 for o in self._outcomes.values() if o.evaluated)
        return {"evaluated": ev, "unevaluated": len(self._outcomes) - ev}


class InMemoryMetricsRepository(MetricsRepository):
    def __init__(self) -> None:
        self._signals: Dict[Tuple[str, Optional[str], str], SignalMetric] = {}
        self._wallets: Dict[str, WalletMetric] = {}

    async def upsert_signal_metric(self, metric: SignalMetric) -> bool:
        key = (metric.signal_id, metric.subject_id, metric.horizon_label)
        self._signals[key] = metric
        return True

    async def list_signal_metrics(self,
                                  signal_id: Optional[str] = None,
                                  subject_id: Optional[str] = None,
                                  limit: int = 200,
                                  ) -> List[SignalMetric]:
        out = []
        for m in self._signals.values():
            if signal_id is not None and m.signal_id != signal_id:
                continue
            if subject_id is not None and m.subject_id != subject_id:
                continue
            out.append(m)
        out.sort(key=lambda m: m.aggregated_at, reverse=True)
        return out[:limit]

    async def upsert_wallet_metric(self, metric: WalletMetric) -> bool:
        self._wallets[metric.wallet_id] = metric
        return True

    async def list_wallet_metrics(self,
                                  entity_id: Optional[str] = None,
                                  limit: int = 200,
                                  ) -> List[WalletMetric]:
        out = list(self._wallets.values())
        if entity_id is not None:
            out = [m for m in out if m.entity_id == entity_id]
        out.sort(key=lambda m: m.updated_at, reverse=True)
        return out[:limit]

    async def counts(self) -> Dict[str, int]:
        return {"signals": len(self._signals), "wallets": len(self._wallets)}


class InMemoryRegimeSnapshotRepository(RegimeSnapshotRepository):
    def __init__(self) -> None:
        self._snaps: List[RegimeSnapshot] = []

    async def append(self, snapshot: RegimeSnapshot) -> bool:
        self._snaps.append(snapshot)
        return True

    async def latest(self) -> Optional[RegimeSnapshot]:
        if not self._snaps:
            return None
        return max(self._snaps, key=lambda s: s.captured_at)

    async def list_since(self, t0: float, limit: int = 500) -> List[RegimeSnapshot]:
        out = [s for s in self._snaps if s.captured_at >= t0]
        out.sort(key=lambda s: s.captured_at, reverse=True)
        return out[:limit]

    async def count(self) -> int:
        return len(self._snaps)


__all__ = [
    "InMemoryOpportunityRepository",
    "InMemoryOutcomeRepository",
    "InMemoryMetricsRepository",
    "InMemoryRegimeSnapshotRepository",
]
