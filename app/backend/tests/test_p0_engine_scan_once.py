"""Tests for the autonomous flash-loan opportunity engine endpoints.

Covers:
  - POST /api/arbicore/engine/scan-once (auth gate + shape)
  - GET  /api/arbicore/engine/history
  - GET  /api/arbicore/engine/opportunities
  - GET  /api/arbicore/engine/readiness-matrix
  - SAFETY: no signing/broadcast material in any response
  - Regression on /api/arbicore/control/decide-opportunity,
                  /api/arbicore/control/live-quote,
                  /api/arbicore/control/readiness
"""
import json
import os
import re
import pytest
import requests

def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    try:
        with open("/app/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE_URL = _load_backend_url()
USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"

VALID_OPP_TYPES = {
    "same_dex_fee_tier", "cross_dex", "triangular",
    "stablecoin_triangular", "multi_hop",
}
VALID_QUOTE_STATUSES = {"REAL", "STALE", "UNAVAILABLE"}
FORBIDDEN_SUBSTRINGS = [
    "private_key", "signed_tx", "raw_tx",
    "eth_sendtransaction", "eth_sendrawtransaction", "personal_sign",
]


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def scan_result(auth_session):
    r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/scan-once",
                          json={"limit": 5}, timeout=180)
    assert r.status_code == 200, f"scan-once failed: {r.status_code} {r.text[:500]}"
    return r.json()


# ---------- AUTH GATE ----------
class TestAuthGate:
    def test_scan_once_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/arbicore/engine/scan-once",
                          json={"limit": 1}, timeout=30)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text[:200]}"


# ---------- SCAN-ONCE ----------
class TestScanOnce:
    def test_top_level_shape(self, scan_result):
        d = scan_result
        assert d.get("execution_performed") is False
        assert d.get("shadow_safe") is True
        assert d.get("routes_enumerated", 0) > 0, f"routes_enumerated={d.get('routes_enumerated')}"
        assert d.get("routes_evaluated", 0) >= 1, f"routes_evaluated={d.get('routes_evaluated')}"
        assert isinstance(d.get("opportunities"), list) and len(d["opportunities"]) >= 1

    def test_opportunity_shape(self, scan_result):
        for opp in scan_result["opportunities"]:
            assert opp.get("opportunity_type") in VALID_OPP_TYPES, \
                f"bad opportunity_type: {opp.get('opportunity_type')}"
            qp = opp.get("quote_provenance") or {}
            assert qp.get("quote_status") in VALID_QUOTE_STATUSES, \
                f"bad quote_status: {qp.get('quote_status')}"
            dec = opp.get("decision") or {}
            assert "simulation" in dec, f"decision missing simulation: keys={list(dec.keys())}"
            assert "ev" in dec or "expected_value" in dec or "expected_value_usd" in dec, \
                f"decision missing ev-family field: keys={list(dec.keys())}"

    def test_no_signing_broadcast_material(self, scan_result):
        blob = json.dumps(scan_result).lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in blob, f"forbidden substring '{needle}' found in scan response"


# ---------- HISTORY / OPPORTUNITIES ----------
class TestDecisionHistory:
    def test_history_persisted(self, auth_session, scan_result):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/history?limit=50", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("count", 0) >= 1
        stats = d.get("stats") or {}
        assert stats.get("total", 0) >= 1
        assert isinstance(d.get("history"), list) and d["history"]
        expected = {"route_id", "opportunity_type", "quote_status",
                    "gross_spread_bps", "net_profit_usd", "confidence",
                    "expected_value_usd", "simulation_passed",
                    "would_execute", "reason"}
        row = d["history"][0]
        missing = expected - set(row.keys())
        assert not missing, f"history row missing fields: {missing}; got keys={list(row.keys())}"

    def test_opportunities_endpoint(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/opportunities?limit=25", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("count", 0) >= 1
        assert isinstance(d.get("opportunities"), list) and d["opportunities"]
        assert (d.get("stats") or {}).get("total", 0) >= 1

    def test_no_signing_material_in_history(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/history?limit=50", timeout=30)
        blob = json.dumps(r.json()).lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in blob


# ---------- READINESS MATRIX ----------
class TestReadinessMatrix:
    @pytest.fixture(scope="class")
    def matrix(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=30)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    def test_overall_status(self, matrix):
        assert matrix.get("overall_status") in {"RED", "YELLOW", "GREEN"}

    def test_capabilities_present(self, matrix):
        required = {
            "CONFIGURATION_RPC", "DISCOVERY_ENGINE", "ROUTE_ENGINE", "OPP_TYPES",
            "QUOTES_LIVE", "PROFITABILITY", "CONFIDENCE_V2", "EXPECTED_VALUE",
            "SIZE_OPTIMIZER", "SIMULATION_GATE", "DECISION_HISTORY", "FORK_VALIDATION",
        }
        caps = matrix.get("capabilities") or matrix.get("matrix") or []
        # Support either dict or list of rows
        if isinstance(caps, dict):
            names = set(caps.keys())
        else:
            names = {row.get("capability") or row.get("name") for row in caps}
        missing = required - names
        assert not missing, f"missing capabilities: {missing}; got={names}"

    def test_red_yellow_rows_have_blocker_action_owner(self, matrix):
        caps = matrix.get("capabilities") or matrix.get("matrix") or []
        rows = list(caps.values()) if isinstance(caps, dict) else caps
        for row in rows:
            status = row.get("status")
            if status in {"RED", "YELLOW"}:
                assert row.get("blocker"), f"row {row.get('capability')} missing blocker"
                assert row.get("action"), f"row {row.get('capability')} missing action"
                owner = row.get("owner")
                assert owner in {"USER", "ENGINEERING"}, \
                    f"row {row.get('capability')} bad owner: {owner}"

    def test_modes(self, matrix):
        modes = matrix.get("modes") or {}
        required = {"SHADOW", "PAPER", "PROFIT_ENGINE", "LIMITED_LIVE", "FULL_AUTOMATION"}
        missing = required - set(modes.keys())
        assert not missing, f"missing modes: {missing}"
        assert modes["LIMITED_LIVE"].get("can_activate") is False
        assert modes["FULL_AUTOMATION"].get("can_activate") is False
        assert modes["SHADOW"].get("can_activate") is True
        assert modes["PAPER"].get("can_activate") is True
        assert modes["PROFIT_ENGINE"].get("can_activate") is True

    def test_no_signing_material(self, matrix):
        blob = json.dumps(matrix).lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in blob


# ---------- REGRESSION on prior endpoints ----------
class TestRegression:
    def test_control_readiness(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/control/readiness", timeout=30)
        assert r.status_code == 200, r.text[:300]

    def test_control_live_quote(self, auth_session):
        # WETH/USDC on Base — classic pair the live-quote endpoint accepts
        payload = {
            "token_in": "0x4200000000000000000000000000000000000006",  # WETH
            "token_out": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
            "amount_in_usd": 1000,
        }
        r = auth_session.post(f"{BASE_URL}/api/arbicore/control/live-quote",
                              json=payload, timeout=60)
        # Accept 200 or 4xx-with-body but never 5xx
        assert r.status_code < 500, f"live-quote 5xx: {r.status_code} {r.text[:300]}"

    def test_control_decide_opportunity(self, auth_session):
        # Minimal decide-opportunity request; endpoint should not 5xx.
        payload = {"opportunity": {"route_id": "test", "gross_spread_bps": 5}}
        r = auth_session.post(f"{BASE_URL}/api/arbicore/control/decide-opportunity",
                              json=payload, timeout=60)
        assert r.status_code < 500, f"decide-opportunity 5xx: {r.status_code} {r.text[:300]}"
