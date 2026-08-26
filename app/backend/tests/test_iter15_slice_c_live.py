"""Live external-ingress verification for v2.11.8 Slice C endpoints."""
from __future__ import annotations

import os
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") or \
       "https://arbitrum-launch-1.preview.emergentagent.com"

VALIDATION_ENDPOINTS = [
    "/api/arbicore/validation/report",
    "/api/arbicore/validation/evidence",
    "/api/arbicore/validation/evidence/does-not-exist-xyz",
    "/api/arbicore/validation/metrics",
]

# Pre-existing validation subpaths (must NOT collide)
LEGACY_VALIDATION = [
    "/api/arbicore/validation/summary",
    "/api/arbicore/validation/recurrence",
    "/api/arbicore/validation/calibration",
    "/api/arbicore/validation/venue_ranking",
    "/api/arbicore/validation/regime",
    "/api/arbicore/validation/daily_status",
]


def _login():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "hotfix-v293"},
               timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


class TestUnauthenticated:
    def test_all_new_endpoints_return_401(self):
        for ep in VALIDATION_ENDPOINTS:
            r = requests.get(f"{BASE}{ep}", timeout=15)
            assert r.status_code == 401, f"{ep}: {r.status_code}"
            body = r.json()
            assert body.get("detail") == "not_authenticated", f"{ep}: {body}"

    def test_legacy_validation_endpoints_reachable(self):
        # Pre-existing legacy validation subpaths may have their own auth
        # policy — just verify no path-collision breaks them (never 404).
        for ep in LEGACY_VALIDATION:
            r = requests.get(f"{BASE}{ep}", timeout=15)
            assert r.status_code != 404, f"{ep}: 404 (path collision!)"


class TestAuthenticatedReport:
    def test_report_contract(self):
        s = _login()
        r = s.get(f"{BASE}/api/arbicore/validation/report", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert isinstance(d.get("total"), int)
        assert isinstance(d.get("executable_rate"), float)
        assert "generated_at" in d
        expected_outcomes = {
            "EXECUTABLE", "REJECTED", "UNPROFITABLE", "LIQUIDITY_FAILURE",
            "GAS_FAILURE", "ROUTE_FAILURE", "RISK_FAILURE", "SIMULATION_FAILURE",
        }
        assert set(d["histogram"].keys()) == expected_outcomes, d["histogram"]
        assert set(d["rates"].keys()) == expected_outcomes
        for k, v in d["histogram"].items():
            assert isinstance(v, int) and v >= 0, (k, v)
        # EXECUTABLE rate must equal executable_rate
        assert d["rates"]["EXECUTABLE"] == d["executable_rate"]
        # When total == 0, all rates == 0.0
        if d["total"] == 0:
            for k, v in d["rates"].items():
                assert v == 0.0, (k, v)


class TestAuthenticatedEvidence:
    def test_evidence_list_contract(self):
        s = _login()
        r = s.get(f"{BASE}/api/arbicore/validation/evidence", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "items" in d and isinstance(d["items"], list)
        assert isinstance(d["total"], int)
        assert "generated_at" in d
        # Query params should not error
        r2 = s.get(f"{BASE}/api/arbicore/validation/evidence",
                   params={"outcome": "EXECUTABLE"}, timeout=15)
        assert r2.status_code == 200
        r3 = s.get(f"{BASE}/api/arbicore/validation/evidence",
                   params={"strategy": "any_strategy"}, timeout=15)
        assert r3.status_code == 200

    def test_evidence_unknown_id(self):
        s = _login()
        r = s.get(f"{BASE}/api/arbicore/validation/evidence/does-not-exist-xyz",
                   timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("found") is False
        assert d.get("validation_id") == "does-not-exist-xyz"
        assert "generated_at" in d


class TestAuthenticatedMetrics:
    def test_metrics_runner_disabled(self):
        # Runner is off by default in preview.
        s = _login()
        r = s.get(f"{BASE}/api/arbicore/validation/metrics", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("runner_enabled") is False, d
        assert d.get("metrics_source") == "disabled", d
        assert d.get("runner", {}).get("is_running") is False
        assert "generated_at" in d


class TestDashboardPulse:
    def test_pulse_includes_paper_validation(self):
        s = _login()
        r = s.get(f"{BASE}/api/arbicore/dashboard/pulse", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        pv = d.get("paper_validation")
        assert pv is not None, f"paper_validation missing: keys={list(d.keys())}"
        assert isinstance(pv.get("total"), int)
        assert isinstance(pv.get("executable_rate"), float)
        assert isinstance(pv.get("runner_running"), bool)
        assert isinstance(pv.get("outcome_counts"), dict)


class TestLegacyValidationSubpathsStillWork:
    def test_legacy_endpoints_200_when_authed(self):
        s = _login()
        for ep in LEGACY_VALIDATION:
            r = s.get(f"{BASE}{ep}", timeout=15)
            assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"
