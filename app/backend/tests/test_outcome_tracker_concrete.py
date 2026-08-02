"""Phase C Wave 1 — OutcomeTracker concrete (uses in-memory mocks)."""
import asyncio
import time

import pytest

from arbicore.data._inmemory import (
    InMemoryOutcomeRepository,
)
from arbicore.data.state_observer import (
    OpportunityState,
    StateObserver,
    StateObserverRegistry,
)
from arbicore.learning.concrete.outcome_tracker import OutcomeTracker
from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    OpportunityType,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _opp(**kw):
    base = dict(
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        asset="A/B",
        subject_id="subject-1",
        source_data_quality=DataProvenance.REAL,
        buy_venue="venue-x",
        sell_venue="venue-y",
    )
    base.update(kw)
    return CanonicalOpportunity(**base)


def test_record_emission_seeds_horizon_rows():
    repo = InMemoryOutcomeRepository()
    reg = StateObserverRegistry()
    tracker = OutcomeTracker(repo, reg)
    seeded = _run(tracker.record_emission(_opp(opportunity_id="opp-A")))
    assert seeded == 5  # 5m, 15m, 1h, 6h, 24h
    rows = _run(repo.list_for_subject("subject-1"))
    assert len(rows) == 5
    assert tracker.stats["emissions_recorded"] == 1


def test_record_emission_skipped_for_simulated():
    repo = InMemoryOutcomeRepository()
    reg = StateObserverRegistry()
    tracker = OutcomeTracker(repo, reg)
    seeded = _run(tracker.record_emission(
        _opp(opportunity_id="opp-sim", source_data_quality=DataProvenance.SIMULATED),
    ))
    assert seeded == 0
    assert tracker.stats["rows_skipped_provenance"] == 1


def test_record_emission_replay_safe():
    """Replaying record_emission for the same opportunity does not duplicate rows."""
    repo = InMemoryOutcomeRepository()
    reg = StateObserverRegistry()
    tracker = OutcomeTracker(repo, reg)
    _run(tracker.record_emission(_opp(opportunity_id="opp-replay")))
    second = _run(tracker.record_emission(_opp(opportunity_id="opp-replay")))
    # only_insert=True → second call writes 0 new rows.
    assert second == 0
    rows = _run(repo.list_for_subject("subject-1"))
    assert len(rows) == 5


class _StubObserver(StateObserver):
    opportunity_type = OpportunityType.CEX_ARBITRAGE

    def __init__(self, metric):
        self.metric = metric

    async def fetch_state(self, opp):
        return OpportunityState(
            subject_id=opp.subject_id or "?",
            opportunity_type=self.opportunity_type,
            captured_at_ts=time.time(),
            primary_metric=self.metric,
            provenance=DataProvenance.REAL,
            source="generic_observer",
        )


def test_evaluator_marks_no_data_when_no_state_snapshots():
    repo = InMemoryOutcomeRepository()
    reg = StateObserverRegistry()
    tracker = OutcomeTracker(repo, reg)
    _run(tracker.record_emission(_opp(opportunity_id="opp-ND")))
    # Force due_at into the past so list_due returns all rows.
    rows = _run(repo.list_for_subject("subject-1"))
    for r in rows:
        r.due_at = time.time() - 1
        _run(repo.upsert_outcome(r))
    result = _run(tracker.evaluate_due(now_ts=time.time()))
    assert result["evaluated"] == 0
    assert result["null_observer"] == 5
    assert tracker.stats["rows_skipped_null_observer"] == 5


def test_evaluator_uses_state_snapshots_for_success():
    """When state snapshots exist, evaluator computes delta and marks success."""
    from arbicore.data.outcome_repo import StateRow
    repo = InMemoryOutcomeRepository()
    reg = StateObserverRegistry()
    tracker = OutcomeTracker(repo, reg)
    # Emit
    _run(tracker.record_emission(_opp(opportunity_id="opp-S")))
    # Add a baseline state at t-100 and a current state at t with higher metric
    t = time.time()
    _run(repo.append_state_snapshot(StateRow(
        subject_id="subject-1", opportunity_type="CEX_ARBITRAGE",
        captured_at_ts=t - 100, primary_metric=1.0,
        source="generic", provenance="REAL",
    )))
    _run(repo.append_state_snapshot(StateRow(
        subject_id="subject-1", opportunity_type="CEX_ARBITRAGE",
        captured_at_ts=t, primary_metric=1.5,
        source="generic", provenance="REAL",
    )))
    rows = _run(repo.list_for_subject("subject-1"))
    for r in rows:
        r.due_at = t - 1
        _run(repo.upsert_outcome(r))
    result = _run(tracker.evaluate_due(now_ts=t))
    assert result["evaluated"] == 5
    # All marked evaluated with succeeded=True (positive delta)
    rows = _run(repo.list_for_subject("subject-1"))
    assert all(r.evaluated for r in rows)
    assert all(r.realized_outcome["succeeded"] for r in rows)
