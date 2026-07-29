"""Phase C Wave 2 — AdaptiveWeightProvider tests."""
import asyncio
import time

import pytest

from arbicore.data._inmemory import InMemoryMetricsRepository
from arbicore.data.metrics_repo import SignalMetric
from arbicore.learning.concrete.adaptive_weights import (
    MAX_WEIGHT,
    MIN_WEIGHT,
    NEUTRAL_WEIGHT,
    MongoBackedAdaptiveWeights,
    adaptive_weight,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_neutral_when_no_samples():
    assert adaptive_weight(0.9, 0) == NEUTRAL_WEIGHT
    assert adaptive_weight(0.1, 0) == NEUTRAL_WEIGHT


def test_neutral_when_win_rate_is_half():
    assert adaptive_weight(0.5, 100) == NEUTRAL_WEIGHT
    assert adaptive_weight(0.5, 1000) == NEUTRAL_WEIGHT


def test_high_win_rate_increases_weight():
    w_small = adaptive_weight(0.9, 5)
    w_large = adaptive_weight(0.9, 1000)
    assert w_small > NEUTRAL_WEIGHT
    assert w_large > w_small
    assert w_large <= MAX_WEIGHT


def test_low_win_rate_decreases_weight():
    w_small = adaptive_weight(0.1, 5)
    w_large = adaptive_weight(0.1, 1000)
    assert w_small < NEUTRAL_WEIGHT
    assert w_large < w_small
    assert w_large >= MIN_WEIGHT


def test_weights_clamped():
    assert adaptive_weight(0.99, 1_000_000) <= MAX_WEIGHT
    assert adaptive_weight(0.01, 1_000_000) >= MIN_WEIGHT


def test_provider_refresh_aggregates_across_subjects():
    repo = InMemoryMetricsRepository()
    # Same signal_id, two subjects, both with 100 trials.
    _run(repo.upsert_signal_metric(SignalMetric(
        signal_id="s1", subject_id="A", horizon_label="1h",
        sample_count=100, score_impact_sum=0.0, score_impact_mean=0.0,
        win_rate=0.8, aggregated_at=time.time(),
    )))
    _run(repo.upsert_signal_metric(SignalMetric(
        signal_id="s1", subject_id="B", horizon_label="1h",
        sample_count=100, score_impact_sum=0.0, score_impact_mean=0.0,
        win_rate=0.6, aggregated_at=time.time(),
    )))
    provider = MongoBackedAdaptiveWeights(repo)
    weights = _run(provider.refresh())
    # Aggregated win-rate = (0.8*100 + 0.6*100) / 200 = 0.7
    # Expected weight > 1.0 (positive signal), clamped under 2.0
    assert NEUTRAL_WEIGHT < weights["s1"] <= MAX_WEIGHT


def test_get_weight_returns_neutral_for_unknown_signal():
    repo = InMemoryMetricsRepository()
    provider = MongoBackedAdaptiveWeights(repo)
    _run(provider.refresh())
    assert provider.get_weight("never_seen") == NEUTRAL_WEIGHT


def test_update_weights_provenance_gate_noop():
    """Public ABC method must not raise. Non-eligible provenance = no-op."""
    from arbicore.models import DataProvenance
    provider = MongoBackedAdaptiveWeights(InMemoryMetricsRepository())
    provider.update_weights({"provenance": DataProvenance.SIMULATED})
    provider.update_weights({"provenance": DataProvenance.REAL})
    # Cache state unchanged
    assert provider.get_weights({}) == {}
