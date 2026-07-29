"""Phase C Wave 1 — MetricsAggregator smoke test.

Inserts synthetic evaluated outcome rows into the in-memory mock-equivalent
path (we go directly via MetricsRepository.upsert_signal_metric to verify
the round-trip rather than spin up a full Mongo aggregation pipeline).
"""
import asyncio
import time

import pytest

from arbicore.data._inmemory import InMemoryMetricsRepository
from arbicore.data.metrics_repo import SignalMetric


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_signal_metric_negative_score_impact_allowed():
    """Per GemHunter audit: score_impact may be negative — verify storage layer
    accepts and retrieves a negative value cleanly."""
    repo = InMemoryMetricsRepository()
    metric = SignalMetric(
        signal_id="dummy_neg_signal",
        subject_id="subject-1",
        horizon_label="1h",
        sample_count=20,
        score_impact_sum=-7.2,
        score_impact_mean=-0.36,
        win_rate=0.3,
        aggregated_at=time.time(),
    )
    _run(repo.upsert_signal_metric(metric))
    rows = _run(repo.list_signal_metrics(signal_id="dummy_neg_signal"))
    assert len(rows) == 1
    assert rows[0].score_impact_mean == -0.36
    assert rows[0].win_rate == 0.3


def test_signal_metric_filter_by_subject_id():
    repo = InMemoryMetricsRepository()
    _run(repo.upsert_signal_metric(SignalMetric(
        signal_id="s1", subject_id="A", horizon_label="5m",
        sample_count=1, score_impact_sum=0.1, score_impact_mean=0.1,
        win_rate=1.0, aggregated_at=time.time(),
    )))
    _run(repo.upsert_signal_metric(SignalMetric(
        signal_id="s1", subject_id="B", horizon_label="5m",
        sample_count=1, score_impact_sum=-0.1, score_impact_mean=-0.1,
        win_rate=0.0, aggregated_at=time.time(),
    )))
    a = _run(repo.list_signal_metrics(subject_id="A"))
    b = _run(repo.list_signal_metrics(subject_id="B"))
    assert len(a) == 1 and a[0].subject_id == "A"
    assert len(b) == 1 and b[0].subject_id == "B"
