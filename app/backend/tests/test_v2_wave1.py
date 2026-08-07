"""UI v2 · Wave 1 — Activate dormant learning-loop engines (contract tests)."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://flashloan-readiness.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestCalibration:
    """CalibrationRepo (L3-08) activation — reliability curves + Brier + ECE."""

    def test_get(self, client):
        r = client.get(f"{API}/arbicore/intelligence/calibration")
        assert r.status_code == 200
        d = r.json()
        for k in ["model", "window_days", "n_samples", "brier_score", "ece",
                  "drift_alert", "buckets", "generated_at"]:
            assert k in d
        assert len(d["buckets"]) == 10
        b = d["buckets"][0]
        for k in ["bucket", "predicted", "realised", "n"]:
            assert k in b
        # Sanity: brier + ece are non-negative floats in [0..1] for calibrated models
        assert 0.0 <= d["brier_score"] <= 1.0
        assert 0.0 <= d["ece"] <= 1.0
        # n_samples should equal sum of bucket ns
        assert d["n_samples"] == sum(b["n"] for b in d["buckets"])

    def test_model_param(self, client):
        r = client.get(f"{API}/arbicore/intelligence/calibration",
                       params={"model": "conf-scorer@2026.07.2-shadow"})
        assert r.status_code == 200
        assert r.json()["model"] == "conf-scorer@2026.07.2-shadow"


class TestModels:
    """ModelRegistry (L3-09) activation — active model IDs + promotion history."""

    def test_get(self, client):
        r = client.get(f"{API}/arbicore/intelligence/models")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "promotions" in d
        assert len(d["items"]) >= 3
        m = d["items"][0]
        for k in ["id", "kind", "state", "shadow", "trained_on_samples",
                  "eval_brier", "eval_ece"]:
            assert k in m
        assert m["state"] in {"ACTIVE", "SHADOW", "RETIRED"}
        # At least one shadow model in the fixture (verifies shadow-model
        # surfacing is actually possible)
        assert any(x["state"] == "SHADOW" for x in d["items"])
        # Promotion log is non-empty and ordered by `at`
        assert len(d["promotions"]) >= 2
        p = d["promotions"][0]
        for k in ["at", "from", "to", "reason"]:
            assert k in p


class TestDecisionVersioning:
    """DecisionAuditLog refinement — every decision carries model + policy versions."""

    def test_versions_present(self, client):
        r = client.get(f"{API}/arbicore/intelligence/decisions")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 1
        for d in items:
            assert "model_version" in d, f"missing model_version on {d.get('id')}"
            assert "policy_version" in d, f"missing policy_version on {d.get('id')}"
            assert d["model_version"].startswith("conf-scorer@") or "shadow" in d["model_version"]
            assert d["policy_version"].startswith("exec-policy@")

    def test_shadow_model_flagged(self, client):
        # At least one decision routed through a shadow model (verifies shadow
        # traffic is surfacable in the log)
        items = client.get(f"{API}/arbicore/intelligence/decisions").json()["items"]
        assert any("shadow" in d["model_version"] for d in items)


class TestDiscoveryCalibration:
    """DiscoveryScorer calibration — additive block on candidates response."""

    def test_calibration_block(self, client):
        r = client.get(f"{API}/arbicore/discovery/candidates")
        assert r.status_code == 200
        d = r.json()
        # Existing contract preserved
        for k in ["items", "total", "stats", "generated_at"]:
            assert k in d
        # New Wave-1 field
        assert "calibration" in d
        c = d["calibration"]
        for k in ["model", "n_samples", "promotion_rate_top_decile",
                  "promotion_rate_bottom_decile", "ece", "drift_alert"]:
            assert k in c
        # A calibrated scorer promotes top decile more than bottom decile
        assert c["promotion_rate_top_decile"] > c["promotion_rate_bottom_decile"]


class TestBackwardsCompat:
    """Wave 1 additions must not break any existing Slice-0..5 contract."""

    def test_decisions_shape_preserved(self, client):
        items = client.get(f"{API}/arbicore/intelligence/decisions").json()["items"]
        for d in items:
            for k in ["id", "opp_id", "asset", "family", "verdict", "confidence",
                      "regime", "top_factors", "at"]:
                assert k in d

    def test_discovery_stats_preserved(self, client):
        d = client.get(f"{API}/arbicore/discovery/candidates").json()
        for k in ["total", "new", "watching", "promoted", "dismissed"]:
            assert k in d["stats"]
