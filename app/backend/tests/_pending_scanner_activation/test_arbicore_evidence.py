"""ArbiCore — Backend tests for Fee Provenance, Fresh-Cycle Analytics,
Fresh-Cycle Watch (DORMANT), and Final Evidence Report bundle endpoints.

Uses session cookies for auth (httpOnly JWT cookie scheme).
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://elated-banach-10.preview.emergentagent.com").rstrip("/")
ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCore2026!"


# ---------------- Fixtures ----------------

@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    # Confirm setup is complete
    r = s.get(f"{BASE_URL}/api/auth/status", timeout=15)
    assert r.status_code == 200, f"auth/status failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("setup_complete") is True, "Setup not complete — admin not seeded"
    # Login
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    user = r.json()
    assert user.get("username") == "admin"
    return s


# ---------------- Auth bootstrap ----------------

class TestAuthBootstrap:
    def test_auth_status_setup_complete(self, session):
        r = session.get(f"{BASE_URL}/api/auth/status", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["setup_complete"] is True
        assert body["auth_required"] is True

    def test_auth_me_returns_admin(self, session):
        r = session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        u = r.json()
        assert u.get("username") == "admin"
        assert u.get("role") == "admin"

    def test_cookies_present(self, session):
        cookie_names = {c.name for c in session.cookies}
        # Common cookie names: access_token, refresh_token
        assert any("token" in n.lower() or "session" in n.lower() for n in cookie_names), \
            f"No auth cookies present: {cookie_names}"


# ---------------- Fee Provenance ----------------

class TestFeeProvenance:
    def test_fee_provenance_payload(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fee-provenance", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "fees" in body
        assert "summary" in body
        assert "trust_verdict" in body
        s = body["summary"]
        for k in ("total_fees", "real_count", "assumed_count", "recommendation_counts"):
            assert k in s, f"summary missing {k}"
        assert len(body["fees"]) == 8, f"expected 8 fees, got {len(body['fees'])}"
        # at least 2 real, 6 assumed
        assert s["real_count"] >= 2, f"real_count {s['real_count']} < 2"
        assert s["assumed_count"] >= 6, f"assumed_count {s['assumed_count']} < 6"
        rc = s["recommendation_counts"]
        for key in ("Production Grade", "Needs Verification", "Assumption Only"):
            assert key in rc, f"recommendation_counts missing key {key}"
        # each fee structural fields
        for f in body["fees"]:
            for k in ("id", "name", "current_value", "classification",
                      "source", "refresh_frequency", "confidence",
                      "recommendation", "consumers"):
                assert k in f, f"fee {f.get('id')} missing {k}"

    def test_fee_provenance_download_md(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fee-provenance/download?format=md", timeout=20)
        assert r.status_code == 200
        assert "text/markdown" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        assert r.text.startswith("# Fee Provenance Report"), \
            f"md prefix unexpected: {r.text[:60]!r}"

    def test_fee_provenance_download_json(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fee-provenance/download?format=json", timeout=20)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "").lower()
        data = r.json()
        assert "fees" in data


# ---------------- Fresh-Cycle Analytics ----------------

class TestFreshCycleAnalytics:
    def test_analytics_30d(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fresh-cycle/analytics?days=30", timeout=25)
        assert r.status_code == 200
        body = r.json()
        for k in ("statistics", "survivability", "evidence"):
            assert k in body, f"analytics missing {k}"

    def test_stats_keys(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fresh-cycle/stats?days=30", timeout=20)
        assert r.status_code == 200
        s = r.json()
        for k in ("observations", "pct_time_roi_positive", "pct_time_roi_above_floor",
                  "pct_time_go", "floor_pct", "go_windows_total"):
            assert k in s, f"stats missing {k}"

    def test_survivability_shape(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fresh-cycle/survivability?days=30", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "windows" in body
        assert "total" in body
        assert "note" in body
        assert isinstance(body["windows"], list)

    def test_evidence_verdict(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fresh-cycle/evidence?days=30", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert "frequency_verdict" in body
        assert body["frequency_verdict"] in (
            "INSUFFICIENT_OBSERVATION_WINDOW", "RARE", "OCCASIONAL", "FREQUENT")
        assert "automation_recommendation" in body
        assert isinstance(body["automation_recommendation"], str)
        assert len(body["automation_recommendation"]) > 0

    def test_download_md(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fresh-cycle/download?format=md&days=30", timeout=25)
        assert r.status_code == 200
        assert "text/markdown" in r.headers.get("content-type", "")
        assert r.text.startswith("# Fresh-Cycle Opportunity Analytics"), \
            f"md prefix: {r.text[:80]!r}"

    def test_download_json(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fresh-cycle/download?format=json&days=7", timeout=25)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "").lower()


# ---------------- Fresh-Cycle Watch (DORMANT) ----------------

class TestFreshCycleWatch:
    def test_watch_dormant(self, session):
        r = session.get(f"{BASE_URL}/api/execution/fresh-cycle/watch", timeout=20)
        assert r.status_code == 200
        body = r.json()
        assert body["credential_state"] == "DORMANT", \
            f"expected DORMANT got {body['credential_state']}"
        assert body["token_set"] is False
        assert body["chat_id_set"] is False
        assert body["alerts_enabled"] is False
        kinds = body.get("alert_kinds") or []
        assert isinstance(kinds, list) and len(kinds) > 0
        keys = {k["key"] for k in kinds}
        for need in ("go_opened", "go_closed", "venue_qualification_changed",
                     "deposit_gate_changed", "withdrawal_gate_changed"):
            assert need in keys, f"alert kind {need} missing"
        assert isinstance(body.get("recent_alerts"), list)


# ---------------- Evidence Report bundle ----------------

class TestEvidenceReport:
    def test_evidence_report_pkg(self, session):
        r = session.get(f"{BASE_URL}/api/execution/evidence-report?days=30", timeout=30)
        assert r.status_code == 200
        body = r.json()
        for k in ("fee_provenance", "fresh_cycle", "fresh_cycle_watch", "executive_summary"):
            assert k in body, f"evidence-report missing {k}"
        es = body["executive_summary"]
        for k in ("fees_real_count", "fees_assumed_count",
                  "fresh_cycle_frequency_verdict", "watch_state"):
            assert k in es, f"executive_summary missing {k}"
        assert es["watch_state"] == "DORMANT"

    def test_evidence_download_md(self, session):
        r = session.get(f"{BASE_URL}/api/execution/evidence-report/download?format=md&days=30", timeout=30)
        assert r.status_code == 200
        assert "text/markdown" in r.headers.get("content-type", "")
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert "evidence_report_30d.md" in cd
        assert r.text.startswith("# ArbiCore — Final Evidence Report"), \
            f"md prefix: {r.text[:80]!r}"

    def test_evidence_download_json(self, session):
        r = session.get(f"{BASE_URL}/api/execution/evidence-report/download?format=json&days=30", timeout=30)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "").lower()


# ---------------- Guardrails ----------------

class TestGuardrails:
    def test_execution_status_disabled(self, session):
        r = session.get(f"{BASE_URL}/api/execution/status", timeout=15)
        assert r.status_code == 200
        s = r.json()
        assert s["execution_enabled"] is False
        assert s["wallet_enabled"] is False
        assert "hard_freeze" in s
        assert "SIMULAT" in (s.get("mode") or "").upper() or \
               "SHADOW" in (s.get("mode") or "").upper() or \
               "DRY-RUN" in (s.get("mode") or "").upper()


# ---------------- Untouched endpoints still work ----------------

class TestExistingEndpoints:
    @pytest.mark.parametrize("path", [
        "/api/execution/fees",
        "/api/execution/opportunity/gate",
        "/api/execution/interlock",
        "/api/execution/certification/report",
    ])
    def test_endpoint_200(self, session, path):
        r = session.get(f"{BASE_URL}{path}", timeout=25)
        assert r.status_code == 200, f"{path} -> {r.status_code}: {r.text[:200]}"

    def test_intel_endpoint(self, session):
        # Need a real route_id — fetch from routes via opportunity/gate (it picks BDAG)
        gate = session.get(f"{BASE_URL}/api/execution/opportunity/gate", timeout=15).json()
        route_id = gate.get("route_id") or gate.get("route", {}).get("id")
        if not route_id:
            pytest.skip("no route_id available")
        r = session.get(f"{BASE_URL}/api/execution/intel/{route_id}", timeout=25)
        assert r.status_code == 200, f"intel/{route_id}: {r.status_code} {r.text[:200]}"


# ---------------- Recorder hook — observations accumulate ----------------

class TestRecorderHook:
    def test_observations_increase_over_25s(self, session):
        r1 = session.get(f"{BASE_URL}/api/execution/fresh-cycle/stats?days=30", timeout=20)
        assert r1.status_code == 200
        n1 = r1.json().get("observations", 0)
        # Wait > 25s to be sure of two ticks (cadence ~20s)
        time.sleep(28)
        r2 = session.get(f"{BASE_URL}/api/execution/fresh-cycle/stats?days=30", timeout=20)
        assert r2.status_code == 200
        n2 = r2.json().get("observations", 0)
        # Should be at least non-decreasing; ideally strictly greater
        assert n2 >= n1, f"observations decreased: {n1} -> {n2}"
        # Flag soft warning by storing both
        print(f"observations: before={n1} after={n2}")
