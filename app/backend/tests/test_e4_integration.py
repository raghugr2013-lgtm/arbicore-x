"""Phase E4 — Real API Integration Preparation + Shadow Certification Report tests.

READ-ONLY: verifies the integration-readiness composition (connectivity, capability,
checklist, health), the read-only credential-validation flow (with a throwaway key
that fails signature — no real creds, no fund movement), the connectivity monitor,
and the shadow certification report aggregation. No trading, no withdrawals.
"""
import os
from pathlib import Path

import pytest
import requests

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    envp = Path("/app/frontend/.env")
    if envp.exists():
        for line in envp.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                _BASE = line.split("=", 1)[1].strip()
                break
assert _BASE
BASE = _BASE.rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


class TestIntegrationStatus:
    def test_status_shape(self, client):
        r = client.get(f"{BASE}/api/execution/integration/status", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "E4" in d["phase"]
        venues = {v["exchange"]: v for v in d["venues"]}
        assert "coinstore" in venues  # primary execution venue
        cs = venues["coinstore"]
        assert cs["role"] == "primary"
        assert cs["verdict"] in {"NEEDS_READONLY_KEY", "READ_VERIFIED", "KEY_ERROR", "CONNECTIVITY_ERROR"}
        caps = {c["cap"]: c for c in cs["capabilities"]}
        assert caps["public_market_data"]["status"] in {"verified", "failed"}
        # write capabilities must NOT be 'verified' in E4 (never probed)
        assert caps["spot_trade"]["status"] in {"declared_untested", "unknown_untested"}
        assert caps["withdrawal"]["status"] in {"declared_untested", "unknown_untested"}
        assert isinstance(cs["checklist"], list) and len(cs["checklist"]) >= 4
        assert "rest_success_rate_pct" in cs["health"]

    def test_readiness_endpoint(self, client):
        r = client.get(f"{BASE}/api/execution/integration/readiness/coinstore", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["exchange"] == "coinstore"
        assert "permission_note" in d
        # the write-scope checklist item must be explicitly not-verified
        write_item = [c for c in d["checklist"] if "Write scopes" in c["item"]]
        assert write_item and write_item[0]["status"] == "n/a"

    def test_monitor(self, client):
        r = client.get(f"{BASE}/api/execution/integration/monitor", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["running"] is True
        assert "coinstore" in d["venues"]

    def test_status_anon_blocked(self):
        r = requests.get(f"{BASE}/api/execution/integration/status", timeout=10)
        assert r.status_code == 401


class TestVerify:
    def test_verify_404(self, client):
        r = client.post(f"{BASE}/api/execution/integration/verify/nope", timeout=20)
        assert r.status_code == 404

    def test_verify_throwaway_key_readonly(self, client):
        """Add a throwaway Coinstore key, verify (signature fails — no real creds),
        confirm write is never tested, then delete. No fund movement."""
        add = client.post(f"{BASE}/api/vault/keys",
                          json={"exchange": "coinstore", "label": "e4-pytest",
                                "api_key": "pytestkey123", "api_secret": "pytestsecret123"}, timeout=15)
        assert add.status_code == 200, add.text
        kid = add.json()["id"]
        try:
            r = client.post(f"{BASE}/api/execution/integration/verify/{kid}", timeout=20)
            assert r.status_code == 200, r.text
            d = r.json()
            assert d["connectivity"]["ok"] in (True, False)
            assert d["write_permission_tested"] is False
            assert d["read_permission_verified"] is False  # fake creds
            assert "credential_validation" in d
        finally:
            client.delete(f"{BASE}/api/vault/keys/{kid}", timeout=15)


class TestCertificationReport:
    def test_report_shape(self, client):
        r = client.get(f"{BASE}/api/execution/certification/report", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["verdict"] in {"INSUFFICIENT_DATA", "NOT_READY",
                                "PROMISING_NEEDS_MORE_DATA", "READY_FOR_MICROCAPITAL_REVIEW"}
        for k in ("throughput", "recovery", "profit", "venue_performance",
                  "route_performance", "recommended_safe_cycle_size"):
            assert k in d, k
        assert "total_shadow_cycles" in d["throughput"]
        assert "recovery_success_rate_pct" in d["recovery"]
        assert "after_fees_distribution" in d["profit"]
        rec = d["recommended_safe_cycle_size"]
        assert "recommended_usd" in rec and "confidence" in rec and "rationale" in rec
        # safety: recommendation never exceeds the certification max cycle size
        assert rec["recommended_usd"] <= d["generated_for_max_cycle_usd"]

    def test_report_anon_blocked(self):
        r = requests.get(f"{BASE}/api/execution/certification/report", timeout=10)
        assert r.status_code == 401
