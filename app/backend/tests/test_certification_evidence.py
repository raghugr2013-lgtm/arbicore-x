"""Certification Evidence Package tests (READ-ONLY).

Validates the 8-section evidence package assembled from the completed
opportunity-gated certification campaign: Final Verdict, Threshold Audit,
Opportunity Gate Statistics, GO Window History Summary, Safety Interlock
Summary, Venue Qualification Snapshot, Recommended Capital Size, Remaining
Evidence Gaps — plus the Markdown/JSON exports and auth.
"""
import os
from pathlib import Path

import pytest
import requests

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            _BASE = line.split("=", 1)[1].strip()
            break
assert _BASE
BASE = _BASE.rstrip("/")

SECTIONS = ["1_final_verdict", "2_threshold_audit", "3_opportunity_gate_statistics",
            "4_go_window_history_summary", "5_safety_interlock_summary",
            "6_venue_qualification_snapshot", "7_recommended_capital_size",
            "8_remaining_evidence_gaps"]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def pkg(client):
    return client.get(f"{BASE}/api/execution/certification/evidence", timeout=30).json()


class TestEvidencePackage:
    def test_available_and_eight_sections(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no certification campaign present")
        assert set(pkg["sections"]) == set(SECTIONS)
        assert pkg["architecture"] == "opportunity-gated (E4.7)"

    def test_final_verdict(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        fv = pkg["sections"]["1_final_verdict"]
        assert fv["verdict"] == pkg["verdict"]
        assert fv["completed"] is not None and fv["target"] is not None

    def test_threshold_audit_has_criteria(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        ta = pkg["sections"]["2_threshold_audit"]
        assert ta["criteria"], "threshold criteria missing"
        for c in ta["criteria"]:
            assert "criterion" in c and "status" in c and "threshold" in c

    def test_gate_statistics(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        og = pkg["sections"]["3_opportunity_gate_statistics"]
        for k in ("current_gate_verdict", "go_windows_total", "best_peak_roi_pct"):
            assert k in og

    def test_interlock_summary_has_launch_and_finalize(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        il = pkg["sections"]["5_safety_interlock_summary"]
        assert il["current_verdict"] in ("READY", "WAIT", "BLOCKED")
        # opportunity-gated campaign captured launch + finalize interlock context
        sc = il.get("campaign_start_context") or {}
        fc = il.get("campaign_finalize_context") or {}
        assert sc.get("interlock_verdict") or fc.get("interlock_verdict"), \
            "expected at least one gate context snapshot"

    def test_venue_snapshot(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        vs = pkg["sections"]["6_venue_qualification_snapshot"]
        assert vs["counts"]["execution_approved"] == 1
        assert (vs.get("primary_execution_venue") or {}).get("name") == "Coinstore"

    def test_recommended_capital(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        cap = pkg["sections"]["7_recommended_capital_size"]
        assert cap["certified_recommended_usd"] is not None
        assert cap["per_cycle_cap_usd"] is not None

    def test_remaining_gaps_include_e5_controls(self, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        gaps = pkg["sections"]["8_remaining_evidence_gaps"]["outstanding"]
        blob = " ".join(gaps).lower()
        assert "whitelist" in blob and "kill-switch" in blob

    def test_markdown_export(self, client, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        r = client.get(f"{BASE}/api/execution/certification/evidence/download",
                       params={"format": "md"}, timeout=20)
        assert r.status_code == 200
        assert "Certification Evidence Package" in r.text
        for h in ("1. Final Verdict", "2. Threshold Audit", "5. Safety Interlock Summary",
                  "8. Remaining Evidence Gaps"):
            assert h in r.text

    def test_json_export(self, client, pkg):
        if not pkg.get("available"):
            pytest.skip("no campaign")
        r = client.get(f"{BASE}/api/execution/certification/evidence/download",
                       params={"format": "json"}, timeout=20)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")


class TestSafety:
    def test_anon_blocked(self):
        assert requests.get(f"{BASE}/api/execution/certification/evidence", timeout=10).status_code == 401

    def test_execution_remains_disabled(self, client):
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert cfg["execution_enabled"] is False
        assert cfg["wallet_enabled"] is False
