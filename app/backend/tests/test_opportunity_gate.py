"""Phase E4.7 — Opportunity Gate, Freshness Engine, GO-Window lifecycle, and
Safety Interlock tests (READ-ONLY, NON-EXECUTING).

Covers: the strict opportunity gate (6 conditions + 4 freshness sources), the
GO/WAIT/NO_GO verdict logic, GO-window history shape, the composite safety
interlock (READY/WAIT/BLOCKED with hard/soft downgrade), the new Telegram alert
rule kinds, campaign gate-context capture, plus auth + non-execution invariant.
"""
import os
from pathlib import Path

import pytest
import requests

from services.telegram_alerts import DEFAULT_RULES

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            _BASE = line.split("=", 1)[1].strip()
            break
assert _BASE
BASE = _BASE.rstrip("/")

GATE_VERDICTS = {"GO", "WAIT", "NO_GO"}
INTERLOCK_VERDICTS = {"READY", "WAIT", "BLOCKED"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def route_id(client):
    r = client.get(f"{BASE}/api/routes", timeout=15).json()
    routes = r if isinstance(r, list) else r.get("routes", [])
    return routes[0]["id"]


# ---------------- Opportunity Gate ----------------

class TestOpportunityGate:
    def test_gate_shape(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/opportunity/gate",
                       params={"route_id": route_id}, timeout=20).json()
        assert d["gate_verdict"] in GATE_VERDICTS
        if not d.get("available"):
            pytest.skip("no live opportunity surface")
        keys = {c["key"] for c in d["conditions"]}
        assert {"positive_roi", "roi_above_floor", "sufficient_depth", "stable_liquidity",
                "qualified_venue", "fresh_sources"} == keys

    def test_freshness_four_sources(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/opportunity/gate",
                       params={"route_id": route_id}, timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface")
        fr = d["freshness"]
        for src in ("buy_price", "order_book", "gate_status", "qualification"):
            assert src in fr and "fresh" in fr[src], src
        assert "all_fresh" in fr

    def test_go_requires_all_conditions(self, client, route_id):
        """GO verdict is only allowed when every condition passes."""
        d = client.get(f"{BASE}/api/execution/opportunity/gate",
                       params={"route_id": route_id}, timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface")
        if d["gate_verdict"] == "GO":
            assert all(c["passed"] for c in d["conditions"]), "GO with a failing condition!"
        # hard conditions failing => NO_GO
        hard_failed = [c for c in d["conditions"]
                       if c["key"] in ("positive_roi", "qualified_venue") and not c["passed"]]
        if hard_failed:
            assert d["gate_verdict"] == "NO_GO"

    def test_unavailable_route_no_go(self, client):
        d = client.get(f"{BASE}/api/execution/opportunity/gate",
                       params={"route_id": "nonexistent"}, timeout=20).json()
        assert d["gate_verdict"] == "NO_GO"
        assert d["available"] is False


# ---------------- GO-window lifecycle / history ----------------

class TestWindows:
    def test_windows_history_shape(self, client):
        d = client.get(f"{BASE}/api/execution/opportunity/windows", timeout=20).json()
        assert "windows" in d and "summary" in d
        s = d["summary"]
        for k in ("total_windows", "open", "closed", "avg_duration_s", "best_peak_roi_pct"):
            assert k in s
        for w in d["windows"]:
            for k in ("venue", "status", "opened_at", "roi_open", "roi_peak",
                      "roi_avg", "profitable_liquidity_quote", "safe_buy_size_usd",
                      "reason_opened"):
                assert k in w, k
            assert w["status"] in ("open", "closed")

    def test_monitor_running(self, client):
        d = client.get(f"{BASE}/api/execution/opportunity/status", timeout=15).json()
        assert d["monitor_running"] is True
        assert "freshness_thresholds" in d


# ---------------- Safety Interlock ----------------

class TestInterlock:
    def test_interlock_shape(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/interlock",
                       params={"route_id": route_id}, timeout=20).json()
        assert d["verdict"] in INTERLOCK_VERDICTS
        assert set(d["interlocks"]) >= {"opportunity_gate", "next_cycle_readiness",
                                        "venue_qualification", "deposit_gate", "withdrawal_gate"}
        assert len(d["checks"]) >= 8
        assert len(d["downgrade_triggers"]) == 6

    def test_interlock_verdict_consistent_with_checks(self, client, route_id):
        """Any BLOCKED check ⇒ BLOCKED; else any WAIT ⇒ WAIT; else READY."""
        d = client.get(f"{BASE}/api/execution/interlock",
                       params={"route_id": route_id}, timeout=20).json()
        statuses = {c["status"] for c in d["checks"]}
        if "BLOCKED" in statuses:
            assert d["verdict"] == "BLOCKED"
            assert d["blocked_reasons"]
        elif "WAIT" in statuses:
            assert d["verdict"] == "WAIT"
        else:
            assert d["verdict"] == "READY"

    def test_interlock_is_not_execution_authority_yet(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/interlock",
                       params={"route_id": route_id}, timeout=20).json()
        assert d["execution_gates"]["execution_enabled"] is False
        assert d["execution_gates"]["wallet_enabled"] is False


# ---------------- Telegram alert framework ----------------

class TestAlertFramework:
    def test_new_alert_kinds_registered(self):
        for kind in ("go_opened", "go_closed", "venue_qualification_changed",
                     "deposit_gate_changed", "withdrawal_gate_changed"):
            assert kind in DEFAULT_RULES and DEFAULT_RULES[kind] is True

    def test_alerts_dormant_until_configured(self, client):
        s = client.get(f"{BASE}/api/alerts/settings", timeout=15).json()
        # dormant by default — not enabled / no token
        assert s["enabled"] is False or s["token_set"] is False


# ---------------- Campaign gate-context (opportunity-gated architecture) ----------------

class TestCampaignGateContext:
    def test_running_or_recent_campaign_has_gate_context(self, client):
        st = client.get(f"{BASE}/api/execution/campaign/status", timeout=20).json()
        camp = st.get("campaign")
        if not camp:
            pytest.skip("no campaign present")
        # a freshly started campaign carries gate_context_start; finalized ones carry gate_context
        assert ("gate_context_start" in camp) or ("gate_context" in camp) or camp.get("status") == "running"


# ---------------- safety ----------------

class TestSafety:
    def test_anon_blocked(self):
        assert requests.get(f"{BASE}/api/execution/opportunity/gate", timeout=10).status_code == 401
        assert requests.get(f"{BASE}/api/execution/interlock", timeout=10).status_code == 401

    def test_execution_remains_disabled(self, client):
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert cfg["execution_enabled"] is False
        assert cfg["wallet_enabled"] is False
