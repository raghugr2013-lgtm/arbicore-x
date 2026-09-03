"""Wave 5 · Evidence Bundle Signing — HTTP contract tests.

Since the preview backend currently has signing enabled with a v1 key
(per the deployment env), most bundles are signed.  Tests are written
to be robust to both signed and unsigned states so the suite stays
green regardless of operator configuration.
"""
from __future__ import annotations

import copy
import os

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://arbicore-canonical-1.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestEvidenceStatus:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/evidence/status")
        assert r.status_code == 200
        d = r.json()
        assert "worker" in d and "generated_at" in d
        w = d["worker"]
        for k in ("running", "interval_s", "iterations", "signer"):
            assert k in w
        s = w["signer"]
        for k in ("enabled", "active_key_version", "algorithms_available",
                  "success_count", "failure_count", "last_signed_at",
                  "unsigned_reason", "keys_registered"):
            assert k in s
        assert "ed25519" in s["algorithms_available"]

    def test_worker_running(self, client):
        d = client.get(f"{API}/arbicore/intelligence/evidence/status").json()
        assert d["worker"]["running"] is True


class TestEvidenceKeys:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/evidence/keys")
        assert r.status_code == 200
        d = r.json()
        assert "active_key_version" in d and "keys" in d
        assert isinstance(d["keys"], list)
        for k in d["keys"]:
            for f in ("version", "algorithm", "public_key_b64",
                      "signing_enabled", "is_active"):
                assert f in k
            # Secrets NEVER leak.
            assert "secret" not in k
            assert "secret_b64" not in k


class TestEvidenceCurrent:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/evidence/current",
                       params={"source": "adaptive_weights"})
        assert r.status_code == 200
        d = r.json()
        for k in ("bundle", "source", "signer_enabled",
                  "unsigned_reason", "generated_at"):
            assert k in d
        assert d["source"] == "adaptive_weights"
        if d["bundle"]:
            for f in ("bundle_id", "bundle_version", "source_component",
                      "source_model_id", "created_at", "payload",
                      "evidence_hash", "signature", "signing_algorithm",
                      "signing_key_version", "verification_status"):
                assert f in d["bundle"], f"missing bundle field {f}"


class TestEvidenceHistory:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/intelligence/evidence/history",
                       params={"limit": 5})
        assert r.status_code == 200
        d = r.json()
        for k in ("items", "count", "generated_at"):
            assert k in d
        assert isinstance(d["items"], list)
        assert d["count"] == len(d["items"])

    def test_source_filter(self, client):
        r = client.get(f"{API}/arbicore/intelligence/evidence/history",
                       params={"source": "adaptive_weights", "limit": 3})
        assert r.status_code == 200
        for item in r.json()["items"]:
            assert item["source_component"] == "adaptive_weights"


class TestEvidenceVerify:
    def _latest_bundle(self, client):
        r = client.get(f"{API}/arbicore/intelligence/evidence/current",
                       params={"source": "adaptive_weights"})
        return r.json()["bundle"]

    def test_verify_endpoint_exists(self, client):
        b = self._latest_bundle(client)
        if b is None:
            pytest.skip("no bundles yet in preview")
        r = client.post(f"{API}/arbicore/intelligence/evidence/verify", json=b)
        assert r.status_code == 200
        d = r.json()
        for k in ("verified", "algorithm", "key_version",
                  "evidence_hash", "bundle_hash_matches", "generated_at"):
            assert k in d

    def test_verify_signed_bundle(self, client):
        b = self._latest_bundle(client)
        if b is None or b.get("verification_status") != "signed":
            pytest.skip("no signed bundles in preview")
        r = client.post(f"{API}/arbicore/intelligence/evidence/verify", json=b)
        d = r.json()
        assert d["verified"] is True
        assert d["bundle_hash_matches"] is True

    def test_verify_detects_payload_tamper(self, client):
        b = self._latest_bundle(client)
        if b is None or b.get("verification_status") != "signed":
            pytest.skip("no signed bundles in preview")
        tampered = copy.deepcopy(b)
        tampered["payload"] = {"mutated": True}
        r = client.post(f"{API}/arbicore/intelligence/evidence/verify",
                        json=tampered)
        d = r.json()
        assert d["verified"] is False
        assert d["bundle_hash_matches"] is False

    def test_verify_unsigned_bundle_reports_reason(self, client):
        # Build an unsigned bundle client-side.
        bundle = {
            "bundle_id": "evb-test-1",
            "bundle_version": "v1",
            "source_component": "test",
            "source_model_id": "test-1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "payload": {"foo": 1},
            "signing_algorithm": None,
            "signing_key_version": None,
            "signature": None,
            "verification_status": "unsigned",
        }
        # evidence_hash is optional here — the endpoint recomputes.
        r = client.post(f"{API}/arbicore/intelligence/evidence/verify",
                        json=bundle)
        d = r.json()
        assert d["verified"] is False
        assert d["reason"] == "unsigned"


class TestBackwardCompatibility:
    def test_calibration_still_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/calibration").json()
        for k in ("model", "window_days", "n_samples", "brier_score",
                  "ece", "drift_alert", "buckets", "generated_at"):
            assert k in d

    def test_weights_still_intact(self, client):
        d = client.get(f"{API}/arbicore/intelligence/weights/current").json()
        for k in ("mode", "provider_version", "count", "weights",
                  "neutral_default", "min", "max", "generated_at"):
            assert k in d

    def test_decisions_still_carry_calibrator_version(self, client):
        d = client.get(f"{API}/arbicore/intelligence/decisions").json()
        for item in d["items"]:
            assert "calibrator_version" in item
