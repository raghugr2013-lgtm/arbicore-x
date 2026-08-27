"""Wave 3 · Confidence Calibration — HTTP contract tests.

Verifies that:
  * Wave-1 endpoint shape remains untouched (backward compatibility).
  * Wave-3 additive fields (algorithm, calibrator_version, supersedes)
    are present.
  * New status + history endpoints return the expected surface.
  * Decision-log entries carry ``calibrator_version``.
"""
from __future__ import annotations

import os

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://elated-banach-10.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestCalibrationEndpointBackwardCompatible:
    """Wave-1 contract keys MUST all still be present."""

    def test_wave1_keys_present(self, client):
        r = client.get(f"{API}/arbicore/intelligence/calibration")
        assert r.status_code == 200
        d = r.json()
        for k in ["model", "window_days", "n_samples", "brier_score", "ece",
                  "drift_alert", "buckets", "generated_at"]:
            assert k in d, f"missing wave-1 key {k}"
        assert len(d["buckets"]) == 10
        for b in d["buckets"]:
            for k in ["bucket", "predicted", "realised", "n"]:
                assert k in b

    def test_bucket_totals_match(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        assert d["n_samples"] == sum(b["n"] for b in d["buckets"])

    def test_ece_and_brier_bounded(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        assert 0.0 <= d["brier_score"] <= 1.0
        assert 0.0 <= d["ece"] <= 1.0


class TestCalibrationEndpointWave3Additions:
    """Wave-3 additive keys — safe to add per the frozen contract policy."""

    def test_algorithm_field(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        assert d.get("algorithm") in {"identity", "platt", "isotonic"}

    def test_calibrator_version_field(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        assert isinstance(d.get("calibrator_version"), str)
        assert d["calibrator_version"]  # non-empty

    def test_supersedes_key(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        assert "supersedes" in d


class TestCalibrationStatus:
    """Worker liveness + last-tick surface for operators."""

    def test_status_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/calibration/status")
        assert r.status_code == 200
        d = r.json()
        assert "worker" in d and "generated_at" in d
        w = d["worker"]
        for k in ["running", "interval_s", "iterations", "last_run_at",
                  "last_result", "last_error", "drift_on", "config"]:
            assert k in w, f"missing worker key {k}"
        cfg = w["config"]
        for k in ["window_days", "min_samples_isotonic", "min_samples_platt",
                  "promotion_ece_slack", "n_buckets"]:
            assert k in cfg

    def test_worker_is_running(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration/status").json()
        assert d["worker"]["running"] is True


class TestCalibrationHistory:
    def test_history_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/calibration/history")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "generated_at" in d
        assert isinstance(d["items"], list)


class TestDecisionsCarryCalibratorVersion:
    """Wave-3 refinement — every decision-log entry carries calibrator_version."""

    def test_decisions_have_calibrator_version(self, client):
        r = client.get(f"{API}/arbicore/intelligence/decisions")
        assert r.status_code == 200
        d = r.json()
        assert d["items"], "decisions log unexpectedly empty"
        for item in d["items"]:
            assert "calibrator_version" in item, f"decision {item.get('id')} missing calibrator_version"
            assert isinstance(item["calibrator_version"], str)
            # Model_version + policy_version (Wave-1) still present.
            assert "model_version" in item
            assert "policy_version" in item
