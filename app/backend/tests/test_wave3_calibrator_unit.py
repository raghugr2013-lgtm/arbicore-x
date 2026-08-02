"""Wave 3 · Confidence Calibrator — unit tests (pure algorithm, no HTTP).

Covers the algorithm ladder (isotonic / platt / identity), determinism,
monotone-preserving guarantee, clamp behaviour, and metric correctness.
"""
from __future__ import annotations

import math
import random

import pytest

from arbicore.learning.concrete.calibrator_isotonic import (
    IsotonicConfidenceCalibrator,
    _bucketize,
    _brier,
    _ece,
    _pav,
    compute_metrics,
)


# ---------- PAV correctness ----------

class TestPAV:
    def test_monotone_input_is_identity(self):
        xs = [0.1, 0.2, 0.3, 0.4, 0.5]
        ys = [0.1, 0.2, 0.3, 0.4, 0.5]
        xk, yk = _pav(xs, ys)
        # Monotone input yields itself as knots.
        assert len(xk) == len(xs)
        for a, b in zip(yk, ys):
            assert a == pytest.approx(b)

    def test_violator_gets_merged(self):
        # Non-monotone [0.5, 0.2, 0.8] must merge the first two into their mean.
        xs = [0.1, 0.2, 0.3]
        ys = [0.5, 0.2, 0.8]
        xk, yk = _pav(xs, ys)
        # Merged block mean = (0.5 + 0.2) / 2 = 0.35 for the first two.
        assert yk[0] == pytest.approx(0.35)
        # Subsequent value unchanged.
        assert yk[-1] == pytest.approx(0.8)
        # Non-decreasing.
        assert all(yk[i] <= yk[i + 1] for i in range(len(yk) - 1))

    def test_all_violators(self):
        xs = [0.1, 0.2, 0.3, 0.4]
        ys = [0.4, 0.3, 0.2, 0.1]
        xk, yk = _pav(xs, ys)
        # Total collapse to one block at the mean = 0.25.
        assert all(v == pytest.approx(0.25) for v in yk)

    def test_ties_averaged(self):
        xs = [0.5, 0.5, 0.5]
        ys = [0.2, 0.4, 0.9]
        xk, yk = _pav(xs, ys)
        assert xk == [0.5]
        assert yk[0] == pytest.approx((0.2 + 0.4 + 0.9) / 3)


# ---------- Isotonic calibrator ----------

def _synthetic_samples(n: int, slope: float, bias: float, seed: int = 42):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        raw = rnd.uniform(0.0, 100.0)
        p_true = max(0.0, min(1.0, slope * (raw / 100.0) + bias))
        survived = rnd.random() < p_true
        out.append((raw, survived))
    return out


class TestIsotonicCalibrator:
    def test_identity_when_empty(self):
        c = IsotonicConfidenceCalibrator()
        c.fit([])
        assert c.algorithm == "identity"
        assert c.calibrate(50.0, {}) == pytest.approx(50.0)

    def test_identity_when_below_platt(self):
        c = IsotonicConfidenceCalibrator(min_samples_isotonic=200, min_samples_platt=30)
        c.fit(_synthetic_samples(10, 1.0, 0.0))
        assert c.algorithm == "identity"

    def test_platt_between_thresholds(self):
        c = IsotonicConfidenceCalibrator(min_samples_isotonic=200, min_samples_platt=30)
        c.fit(_synthetic_samples(80, 1.0, 0.0))
        assert c.algorithm == "platt"
        assert 0.0 <= c.calibrate(50.0, {}) <= 100.0

    def test_isotonic_when_enough_samples(self):
        c = IsotonicConfidenceCalibrator(min_samples_isotonic=200, min_samples_platt=30)
        c.fit(_synthetic_samples(500, 1.0, 0.0))
        assert c.algorithm == "isotonic"

    def test_clamp_to_zero_hundred(self):
        c = IsotonicConfidenceCalibrator()
        c.fit(_synthetic_samples(500, 1.0, 0.0))
        for v in (-50.0, -1.0, 101.0, 500.0, float("nan"), float("inf")):
            out = c.calibrate(v, {})
            assert 0.0 <= out <= 100.0

    def test_deterministic_output(self):
        s = _synthetic_samples(500, 1.0, 0.0, seed=7)
        c1, c2 = IsotonicConfidenceCalibrator(), IsotonicConfidenceCalibrator()
        c1.fit(s); c2.fit(s)
        assert c1.curve() == c2.curve()
        for x in (10.0, 30.0, 55.0, 80.0, 99.0):
            assert c1.calibrate(x, {}) == c2.calibrate(x, {})

    def test_monotone_preserving(self):
        c = IsotonicConfidenceCalibrator()
        # Isotonic curve.
        c.fit(_synthetic_samples(500, 1.0, 0.0, seed=11))
        prev = -1.0
        for i in range(0, 101, 5):
            v = c.calibrate(float(i), {})
            assert v >= prev - 1e-9, f"non-monotone at {i}: {v} < {prev}"
            prev = v

    def test_curve_roundtrip(self):
        c = IsotonicConfidenceCalibrator()
        c.fit(_synthetic_samples(500, 1.0, 0.0, seed=13))
        curve = c.curve()
        c2 = IsotonicConfidenceCalibrator()
        c2.load_curve(curve)
        for x in (5.0, 45.0, 85.0):
            assert c2.calibrate(x, {}) == pytest.approx(c.calibrate(x, {}))

    def test_load_corrupt_curve_falls_back_identity(self):
        c = IsotonicConfidenceCalibrator()
        c.load_curve({"algorithm": "isotonic", "x": [1], "y": []})  # length mismatch
        assert c.algorithm == "identity"
        assert c.calibrate(42.0, {}) == pytest.approx(42.0)
        c.load_curve({"algorithm": "unknown_gibberish"})
        assert c.algorithm == "identity"


# ---------- Metrics ----------

class TestMetrics:
    def test_bucketize_shape(self):
        buckets = _bucketize([], 10)
        assert len(buckets) == 10
        assert buckets[0]["bucket"] == "0.0-0.1"
        assert buckets[-1]["bucket"] == "0.9-1.0"

    def test_brier_perfect(self):
        # Predicting 1.0 for every survivor → Brier == 0.
        samples = [(100.0, True), (100.0, True), (0.0, False)]
        assert _brier(samples) == pytest.approx(0.0)

    def test_brier_worst(self):
        # Predicting 0.0 for every survivor → Brier == 1.0.
        samples = [(0.0, True), (0.0, True)]
        assert _brier(samples) == pytest.approx(1.0)

    def test_ece_zero_when_perfectly_aligned(self):
        # Predicted probability equals realised in every bucket.
        buckets = [{"bucket": "0.0-0.1", "predicted": 0.05, "realised": 0.05, "n": 10}]
        assert _ece(buckets) == pytest.approx(0.0)

    def test_compute_metrics_shape(self):
        m = compute_metrics(_synthetic_samples(200, 1.0, 0.0, seed=1), n_buckets=10)
        for k in ("n_samples", "brier_score", "ece", "buckets"):
            assert k in m
        assert len(m["buckets"]) == 10
        assert 0.0 <= m["brier_score"] <= 1.0
        assert 0.0 <= m["ece"] <= 1.0
