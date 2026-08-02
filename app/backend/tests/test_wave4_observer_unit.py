"""Wave 4 · Adaptive Weights — unit tests (pure functions).

Covers:
    * ``adaptive_weight()`` primitive: n=0 → 1.0; wr=0.5 → 1.0; clamp;
      determinism; monotonicity in win_rate.
    * ``confidence_score()``: n=0 → 0.0; asymptote → 1.0; monotone in n.
    * ``AdaptiveWeightsObserver.compute_recommendation()`` — evidence
      bundle shape, insufficient-samples path, delta/impact math, sort
      order.
"""
from __future__ import annotations

import pytest

from arbicore.config.adaptive_weights_config import AdaptiveWeightsConfig
from arbicore.learning.concrete.adaptive_weights_observer import (
    AdaptiveWeightsObserver,
    _expected_score_impact,
    adaptive_weight,
    confidence_score,
)


def _cfg(**over) -> AdaptiveWeightsConfig:
    base = dict(
        mode="OBSERVE",
        prior_trials=20,
        neutral_weight=1.0,
        min_weight=0.1,
        max_weight=2.0,
        max_delta_scale=4.0,
        min_samples_for_recommendation=30,
        min_confidence_floor=0.10,
        tick_interval_s=3600,
        retired_ttl_days=30,
        max_signals_scanned=500,
        provider_version="adaptive_weights_observer@1",
    )
    base.update(over)
    return AdaptiveWeightsConfig(**base)


# ---------- adaptive_weight primitive ----------

class TestAdaptiveWeightPrimitive:
    def test_no_samples_returns_neutral(self):
        assert adaptive_weight(0.9, 0) == pytest.approx(1.0)
        assert adaptive_weight(0.1, 0) == pytest.approx(1.0)

    def test_win_rate_half_returns_neutral(self):
        for n in (1, 10, 100, 10_000):
            assert adaptive_weight(0.5, n) == pytest.approx(1.0)

    def test_clamp_to_min_and_max(self):
        # Extreme win rates → asymptotic to [min, max].
        assert adaptive_weight(1.0, 10_000) <= 2.0 + 1e-9
        assert adaptive_weight(0.0, 10_000) >= 0.1 - 1e-9

    def test_monotone_in_win_rate(self):
        prev = -1e9
        for wr in [0.0, 0.2, 0.4, 0.5, 0.6, 0.8, 1.0]:
            w = adaptive_weight(wr, 200)
            assert w >= prev - 1e-9, f"non-monotone at wr={wr}"
            prev = w

    def test_deterministic(self):
        for _ in range(5):
            assert adaptive_weight(0.72, 84) == adaptive_weight(0.72, 84)

    def test_custom_bounds_respected(self):
        w = adaptive_weight(0.99, 1000, min_weight=0.5, max_weight=1.5)
        assert 0.5 <= w <= 1.5


# ---------- confidence_score ----------

class TestConfidenceScore:
    def test_zero_samples_is_zero(self):
        assert confidence_score(0) == 0.0

    def test_asymptote_high_samples(self):
        assert confidence_score(10_000) > 0.99

    def test_monotone_in_samples(self):
        prev = -1.0
        for n in (0, 5, 20, 50, 200, 1000):
            c = confidence_score(n)
            assert c >= prev
            prev = c


# ---------- expected_score_impact ----------

class TestExpectedScoreImpact:
    def test_zero_samples_zero_impact(self):
        assert _expected_score_impact(1.5, 1.0, 0, 0.9) == 0.0

    def test_zero_delta_zero_impact(self):
        assert _expected_score_impact(1.0, 1.0, 100, 0.9) == 0.0

    def test_win_rate_half_zero_impact(self):
        assert _expected_score_impact(1.5, 1.0, 100, 0.5) == 0.0

    def test_positive_delta_and_win_rate_positive_impact(self):
        assert _expected_score_impact(1.5, 1.0, 100, 0.8) > 0

    def test_negative_delta_and_win_rate_negative_impact(self):
        assert _expected_score_impact(0.5, 1.0, 100, 0.2) > 0  # both negative → positive product
        assert _expected_score_impact(0.5, 1.0, 100, 0.8) < 0

    def test_bounded_range(self):
        for wr in (0.0, 0.5, 1.0):
            v = _expected_score_impact(2.0, 1.0, 100, wr)
            assert -1.0 <= v <= 1.0


# ---------- Observer aggregation ----------

class TestObserver:
    def test_empty_input_identity_snapshot(self):
        obs = AdaptiveWeightsObserver(_cfg())
        snap = obs.compute_recommendation([])
        assert snap["mode"] == "OBSERVE"
        assert snap["n_signals"] == 0
        assert snap["recommendations"] == []
        assert snap["aggregate_confidence"] == 0.0
        assert "awaiting" in snap["note"] or "insufficient" in snap["note"]

    def test_insufficient_samples_marks_pending(self):
        obs = AdaptiveWeightsObserver(_cfg(min_samples_for_recommendation=50))
        rows = [{"signal_id": "spread_edge", "win_rate": 0.7, "sample_count": 10}]
        snap = obs.compute_recommendation(rows)
        assert snap["n_signals"] == 1
        r = snap["recommendations"][0]
        # Identity baseline while awaiting samples.
        assert r["recommended_weight"] == 1.0
        assert r["baseline_weight"] == 1.0
        assert r["delta"] == 0.0
        assert r["confidence"] == 0.0
        assert r["evidence"]["insufficient_samples"] is True
        assert r["evidence"]["min_samples_required"] == 50

    def test_sufficient_samples_produces_recommendation(self):
        obs = AdaptiveWeightsObserver(_cfg(min_samples_for_recommendation=30))
        rows = [{"signal_id": "spread_edge", "win_rate": 0.75, "sample_count": 200}]
        snap = obs.compute_recommendation(rows)
        r = snap["recommendations"][0]
        assert r["recommended_weight"] > 1.0  # win rate > 0.5 → uplift
        assert r["delta"] > 0.0
        assert r["confidence"] > 0.0
        assert r["expected_score_impact"] > 0.0
        assert r["evidence"]["sample_count"] == 200
        assert r["evidence"]["win_rate"] == 0.75
        assert "insufficient_samples" not in r["evidence"]

    def test_aggregation_across_multiple_rows(self):
        obs = AdaptiveWeightsObserver(_cfg(min_samples_for_recommendation=30))
        rows = [
            {"signal_id": "gas_vol", "win_rate": 0.6, "sample_count": 100},
            {"signal_id": "gas_vol", "win_rate": 0.4, "sample_count": 100},
        ]
        snap = obs.compute_recommendation(rows)
        r = snap["recommendations"][0]
        # Weighted mean win rate = 0.5 → neutral weight = 1.0
        assert r["recommended_weight"] == pytest.approx(1.0)
        assert r["evidence"]["sample_count"] == 200

    def test_sort_by_absolute_delta_desc(self):
        obs = AdaptiveWeightsObserver(_cfg(min_samples_for_recommendation=30))
        rows = [
            {"signal_id": "small_edge", "win_rate": 0.55, "sample_count": 100},
            {"signal_id": "big_edge", "win_rate": 0.85, "sample_count": 100},
            {"signal_id": "big_drag", "win_rate": 0.15, "sample_count": 100},
        ]
        snap = obs.compute_recommendation(rows)
        deltas = [abs(r["delta"]) for r in snap["recommendations"]]
        assert deltas == sorted(deltas, reverse=True)

    def test_mode_always_observe(self):
        obs = AdaptiveWeightsObserver(_cfg())
        rows = [{"signal_id": "x", "win_rate": 0.9, "sample_count": 500}]
        assert obs.compute_recommendation(rows)["mode"] == "OBSERVE"

    def test_get_weights_wave1_shape(self):
        obs = AdaptiveWeightsObserver(_cfg())
        # Load a snapshot so get_weights() has something to return.
        obs.load_snapshot({
            "recommendations": [
                {"signal_id": "a", "recommended_weight": 1.35},
                {"signal_id": "b", "recommended_weight": 0.7},
            ],
        })
        w = obs.get_weights({})
        assert w == {"a": 1.35, "b": 0.7}

    def test_update_weights_is_no_op(self):
        obs = AdaptiveWeightsObserver(_cfg())
        # Must not raise, must not mutate snapshot.
        before = obs.snapshot()
        obs.update_weights({"any": "payload"})
        assert obs.snapshot() == before

    def test_deterministic_snapshot(self):
        obs1 = AdaptiveWeightsObserver(_cfg())
        obs2 = AdaptiveWeightsObserver(_cfg())
        rows = [
            {"signal_id": "s1", "win_rate": 0.62, "sample_count": 340},
            {"signal_id": "s2", "win_rate": 0.41, "sample_count": 210},
        ]
        s1 = obs1.compute_recommendation(rows)
        s2 = obs2.compute_recommendation(rows)
        # Wipe timestamps for equality check.
        for s in (s1, s2):
            s.pop("generated_at", None)
        assert s1 == s2

    def test_snapshot_roundtrip(self):
        obs = AdaptiveWeightsObserver(_cfg())
        rows = [{"signal_id": "spread", "win_rate": 0.7, "sample_count": 500}]
        snap = obs.compute_recommendation(rows)
        obs.load_snapshot(snap)
        assert obs.snapshot()["n_signals"] == snap["n_signals"]
        assert obs.get_weights({})["spread"] == pytest.approx(
            snap["recommendations"][0]["recommended_weight"])
