"""Phase C Wave 3 — Regime Classifier tests."""
import asyncio
import time

from arbicore.data._inmemory import (
    InMemoryOutcomeRepository,
    InMemoryRegimeSnapshotRepository,
)
from arbicore.data.outcome_repo import StateRow
from arbicore.learning.concrete.regime_classifier import (
    HIGH_VOL,
    LOW_VOL,
    TREND_STRONG,
    HeuristicRegimeClassifier,
    _classify,
    _compute_stats,
)
from arbicore.models import MarketRegime


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _state(t, sid, metric, secondary=None):
    return StateRow(subject_id=sid, opportunity_type="CEX_ARBITRAGE",
                    captured_at_ts=t, primary_metric=metric,
                    secondary_metrics=secondary or {},
                    source="t", provenance="REAL")


def test_compute_stats_returns_none_with_too_few():
    assert _compute_stats([]) is None
    assert _compute_stats([_state(0, "A", 1.0)]) is None


def test_calm_regime_low_volatility():
    states = [_state(i, "A", 100.0 + 0.001 * i) for i in range(30)]
    stats = _compute_stats(states)
    regime, tags = _classify(stats)
    assert stats.volatility < LOW_VOL
    assert "low_volatility" in tags
    assert regime is MarketRegime.CALM


def test_volatile_regime_high_volatility():
    # Alternate up/down 10% — high coefficient of variation
    states = [_state(i, "A", 100.0 + (10.0 if i % 2 else -10.0)) for i in range(30)]
    stats = _compute_stats(states)
    regime, tags = _classify(stats)
    assert stats.volatility >= HIGH_VOL
    assert "high_volatility" in tags
    assert regime is MarketRegime.VOLATILE


def test_trending_regime_strong_trend():
    states = [_state(i, "A", 100.0 + i * 0.5) for i in range(30)]
    stats = _compute_stats(states)
    regime, tags = _classify(stats)
    assert abs(stats.trend) >= TREND_STRONG
    assert ("uptrend" in tags) or ("downtrend" in tags)
    assert regime in (MarketRegime.TRENDING, MarketRegime.VOLATILE)


def test_illiquid_regime_thin_depth_dominates():
    states = [_state(i, "A", 100.0 + 0.01 * i,
                     secondary={"depth_usd": 50.0}) for i in range(30)]
    stats = _compute_stats(states)
    regime, tags = _classify(stats)
    assert stats.liquidity_proxy == 50.0
    assert "thin_liquidity" in tags
    assert regime is MarketRegime.ILLIQUID


def test_classify_for_subject_writes_snapshot():
    outcomes = InMemoryOutcomeRepository()
    regimes = InMemoryRegimeSnapshotRepository()
    t = time.time()
    for i in range(10):
        _run(outcomes.append_state_snapshot(
            _state(t - i * 60, "A", 100.0 + i * 0.5)
        ))
    classifier = HeuristicRegimeClassifier(outcomes, regimes,
                                            window_s=24*3600, min_samples=3)
    snap = _run(classifier.classify_for_subject("A", now_ts=t))
    assert snap is not None
    assert snap.dominant_regime in {r.value for r in MarketRegime}
    assert _run(regimes.count()) == 1


def test_classify_universe_returns_none_with_insufficient_data():
    outcomes = InMemoryOutcomeRepository()
    regimes = InMemoryRegimeSnapshotRepository()
    classifier = HeuristicRegimeClassifier(outcomes, regimes, min_samples=3)
    snap = _run(classifier.classify_universe(["nope"], now_ts=time.time()))
    assert snap is None
    assert _run(regimes.count()) == 0
