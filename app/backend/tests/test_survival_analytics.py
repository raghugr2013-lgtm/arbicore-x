"""Phase C Wave 3 — Survival Analytics tests."""
import asyncio
import time

import pytest

from arbicore.data._inmemory import InMemoryOutcomeRepository
from arbicore.data.outcome_repo import StateRow
from arbicore.learning.concrete.survival import SurvivalAnalytics


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _state(t, subject_id, metric):
    return StateRow(subject_id=subject_id, opportunity_type="CEX_ARBITRAGE",
                    captured_at_ts=t, primary_metric=metric,
                    source="t", provenance="REAL")


def test_for_subject_returns_none_with_fewer_than_two_states():
    repo = InMemoryOutcomeRepository()
    sa = SurvivalAnalytics(repo)
    assert _run(sa.for_subject("X")) is None


def test_alive_within_tolerance():
    """All metrics inside ±5% band → lifetime_s is None (still alive)."""
    repo = InMemoryOutcomeRepository()
    t = 1_000_000.0
    _run(repo.append_state_snapshot(_state(t, "A", 100.0)))
    _run(repo.append_state_snapshot(_state(t + 60, "A", 101.0)))
    _run(repo.append_state_snapshot(_state(t + 120, "A", 99.0)))
    sa = SurvivalAnalytics(repo, default_tolerance=0.05)
    row = _run(sa.for_subject("A"))
    assert row is not None
    assert row.lifetime_s is None
    assert row.degraded is False
    assert row.baseline_metric == 100.0


def test_degraded_records_lifetime():
    repo = InMemoryOutcomeRepository()
    t = 1_000_000.0
    _run(repo.append_state_snapshot(_state(t, "B", 100.0)))
    _run(repo.append_state_snapshot(_state(t + 60, "B", 101.0)))
    _run(repo.append_state_snapshot(_state(t + 120, "B", 110.0)))  # 10% jump
    sa = SurvivalAnalytics(repo, default_tolerance=0.05)
    row = _run(sa.for_subject("B"))
    assert row.degraded is True
    assert row.lifetime_s == 120.0


def test_distribution_aggregates_subjects():
    repo = InMemoryOutcomeRepository()
    t = 1_000_000.0
    # Two subjects: A persists, B degrades at 60s, C degrades at 30s
    for sid, end_metric, end_dt in [("A", 100.5, 60), ("B", 110.0, 60),
                                     ("C", 120.0, 30)]:
        _run(repo.append_state_snapshot(_state(t, sid, 100.0)))
        _run(repo.append_state_snapshot(_state(t + end_dt, sid, end_metric)))
    sa = SurvivalAnalytics(repo, default_tolerance=0.05)
    dist = _run(sa.distribution(["A", "B", "C"]))
    assert dist.sample_size == 3
    # 1 of 3 survived
    assert abs(dist.survived_pct - (1/3)) < 1e-3
    assert dist.median_lifetime_s is not None
