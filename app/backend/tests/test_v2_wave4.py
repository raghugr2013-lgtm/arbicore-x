"""Wave 4 · Adaptive Weights (OBSERVE) — HTTP contract tests.

Verifies:
  * The 4 new read-only endpoints exist and return the promised shape.
  * OBSERVE-mode invariants — mode is always ``"OBSERVE"``, no
    endpoint mutates scoring, identity-baseline bootstrap surfaces
    cleanly when there are no observations yet.
  * Existing Wave 1/2/3 endpoints remain untouched.
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://exec-readiness-x.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestWeightsCurrent:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/weights/current")
        assert r.status_code == 200
        d = r.json()
        for k in ("mode", "provider_version", "count", "weights",
                  "neutral_default", "min", "max", "note", "generated_at"):
            assert k in d, f"missing {k}"
        assert d["mode"] == "OBSERVE"
        assert d["neutral_default"] == 1.0
        assert d["min"] == 0.1
        assert d["max"] == 2.0
        assert isinstance(d["weights"], dict)
        # count matches weight dict size.
        assert d["count"] == len(d["weights"])

    def test_identity_bootstrap_or_recommendation(self, client):
        d = client.get(f"{API}/arbicore/intelligence/weights/current").json()
        if d["count"] == 0:
            # Identity baseline path — must clearly indicate awaiting data.
            assert "insufficient" in d["note"].lower() or "awaiting" in d["note"].lower()
        else:
            # If recommendations exist they must be clamped in [min, max].
            for _, w in d["weights"].items():
                assert d["min"] <= w <= d["max"]


class TestWeightsRecommendations:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/weights/recommendations")
        assert r.status_code == 200
        d = r.json()
        for k in ("mode", "provider_version", "n_signals", "aggregate_confidence",
                  "recommendations", "note", "generated_at"):
            assert k in d
        assert d["mode"] == "OBSERVE"
        assert isinstance(d["recommendations"], list)

    def test_recommendation_row_shape_when_present(self, client):
        d = client.get(f"{API}/arbicore/intelligence/weights/recommendations").json()
        for r in d["recommendations"]:
            for k in ("signal_id", "baseline_weight", "recommended_weight",
                      "delta", "delta_pct", "confidence", "expected_score_impact",
                      "evidence"):
                assert k in r, f"missing recommendation field {k}"
            for k in ("sample_count", "win_rate"):
                assert k in r["evidence"], f"missing evidence field {k}"

    def test_min_confidence_filter(self, client):
        r = client.get(
            f"{API}/arbicore/intelligence/weights/recommendations",
            params={"min_confidence": 0.99},
        )
        assert r.status_code == 200
        d = r.json()
        # With a very high floor everything filtered — n_signals matches len.
        assert d["n_signals"] == len(d["recommendations"])
        for row in d["recommendations"]:
            assert row["confidence"] >= 0.99


class TestWeightsStatus:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/weights/status")
        assert r.status_code == 200
        d = r.json()
        assert "worker" in d and "generated_at" in d
        w = d["worker"]
        for k in ("running", "interval_s", "iterations", "last_run_at",
                  "last_result", "last_error", "mode", "config"):
            assert k in w
        assert w["mode"] == "OBSERVE"
        cfg = w["config"]
        for k in ("prior_trials", "neutral_weight", "min_weight", "max_weight",
                  "max_delta_scale", "min_samples_for_recommendation",
                  "min_confidence_floor", "max_signals_scanned"):
            assert k in cfg

    def test_worker_running(self, client):
        d = client.get(f"{API}/arbicore/intelligence/weights/status").json()
        assert d["worker"]["running"] is True


class TestWeightsHistory:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/weights/history")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "generated_at" in d
        assert isinstance(d["items"], list)


class TestBackwardCompatibility:
    """Wave-4 must not touch Wave-1/2/3 contracts."""

    def test_calibration_endpoint_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        for k in ("model", "window_days", "n_samples", "brier_score", "ece",
                  "drift_alert", "buckets", "generated_at"):
            assert k in d

    def test_models_endpoint_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/models").json()
        assert "items" in d
        assert "promotions" in d

    def test_decisions_endpoint_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/decisions").json()
        assert "items" in d
        assert d["items"]
        # Wave-3 field still present, no new required fields injected.
        for item in d["items"]:
            assert "calibrator_version" in item
