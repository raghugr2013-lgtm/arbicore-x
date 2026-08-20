"""P0 tests for iteration 6:
  - Continuous scanner autostart + start/stop/status
  - scan-once opportunity shape: liquidity_usd, liquidity_source, marginal_spread_bps
  - GET /engine/checkpoint consolidated shape
  - GET /engine/recurring?min_seen=2
  - GET /engine/readiness-matrix (LIQUIDITY_DEPTH GREEN, SCANNER GREEN)
  - SAFETY: no signing/broadcast material
  - Auth gate on scan-once + checkpoint
  - End state: scanner RUNNING, mode SHADOW, kill switch DISENGAGED
"""
import json
import os
import time
import pytest
import requests


def _load_backend_url():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if v:
        return v.rstrip("/")
    for path in ("/app/app/frontend/.env", "/app/frontend/.env"):
        try:
            with open(path) as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        return line.split("=", 1)[1].strip().rstrip("/")
        except Exception:
            pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE_URL = _load_backend_url()
USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"

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
                          json={"limit": 6}, timeout=180)
    assert r.status_code == 200, f"scan-once failed: {r.status_code} {r.text[:500]}"
    return r.json()


# ---------- AUTH GATE ----------
class TestAuthGate:
    def test_scan_once_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/arbicore/engine/scan-once",
                          json={"limit": 1}, timeout=30)
        assert r.status_code == 401, f"got {r.status_code}"

    def test_checkpoint_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/arbicore/engine/checkpoint", timeout=30)
        assert r.status_code == 401, f"got {r.status_code}"


# ---------- SCANNER START/STOP/STATUS ----------
class TestScanner:
    def test_status_autostarted(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/scanner/status", timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("running") is True, f"scanner should be autostarted running=True, got {d}"
        # cumulative scan stats fields (loose — accept any of these families)
        keys = set(d.keys())
        assert keys & {"scans_completed", "total_scans", "cumulative_scans",
                       "scan_count", "stats", "cumulative_stats", "cumulative"}, \
            f"no cumulative stats keys in scanner status: {keys}"

    def test_stop_then_start(self, auth_session):
        r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/scanner/stop", timeout=30)
        assert r.status_code == 200, r.text[:300]
        st = auth_session.get(f"{BASE_URL}/api/arbicore/engine/scanner/status", timeout=30).json()
        assert st.get("running") is False, f"after stop, running should be false: {st}"

        r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/scanner/start", timeout=30)
        assert r.status_code == 200, r.text[:300]
        st = auth_session.get(f"{BASE_URL}/api/arbicore/engine/scanner/status", timeout=30).json()
        assert st.get("running") is True, f"after start, running should be true: {st}"


# ---------- SCAN-ONCE new fields ----------
class TestScanOnceFields:
    def test_top_level(self, scan_result):
        d = scan_result
        assert d.get("execution_performed") is False
        assert d.get("shadow_safe") is True
        assert isinstance(d.get("opportunities"), list) and d["opportunities"], \
            "no opportunities returned"

    def test_liquidity_and_marginal_fields(self, scan_result):
        for opp in scan_result["opportunities"]:
            assert "liquidity_usd" in opp, f"missing liquidity_usd in opp keys={list(opp.keys())}"
            assert "liquidity_source" in opp, f"missing liquidity_source keys={list(opp.keys())}"
            src = opp["liquidity_source"] or ""
            assert isinstance(src, str) and (src.startswith("live_probe") or src.startswith("default")), \
                f"bad liquidity_source={src}"
            assert "marginal_spread_bps" in opp, f"missing marginal_spread_bps"
            dec = opp.get("decision") or {}
            assert dec, "opp missing full decision object"

    def test_no_signing_material(self, scan_result):
        blob = json.dumps(scan_result).lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in blob


# ---------- CHECKPOINT ----------
class TestCheckpoint:
    @pytest.fixture(scope="class")
    def cp(self, auth_session, scan_result):
        # scan_result ensures at least one scan has run
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/checkpoint", timeout=60)
        assert r.status_code == 200, r.text[:500]
        return r.json()

    def test_required_fields(self, cp):
        required = {
            "routes_scanned_records", "positive_after_costs", "executable",
            "opportunity_type_coverage", "top_opportunities",
            "rejection_reasons", "dynamic_sizing_results", "simulation_results",
            "recurring_routes", "decision_history", "scanner",
            "readiness_matrix", "limited_live_blockers",
        }
        missing = required - set(cp.keys())
        assert not missing, f"checkpoint missing fields: {missing}; got={list(cp.keys())}"

    def test_opp_type_coverage(self, cp):
        cov = cp.get("opportunity_type_coverage") or {}
        # Accept dict-of-counts or list-of-strings
        if isinstance(cov, dict):
            names = set(cov.keys())
        else:
            names = set(cov)
        assert {"triangular", "same_dex_fee_tier", "cross_dex"} & names, \
            f"expected coverage to include triangular/same_dex_fee_tier/cross_dex, got {names}"

    def test_limited_live_blockers_shape(self, cp):
        blockers = cp.get("limited_live_blockers") or []
        assert isinstance(blockers, list)
        for b in blockers:
            assert b.get("blocker"), f"blocker missing 'blocker': {b}"
            assert b.get("action"), f"blocker missing 'action': {b}"
            owner = b.get("owner")
            assert owner in {"USER", "ENGINEERING"}, f"bad owner: {owner} in {b}"

    def test_readiness_and_scanner_embedded(self, cp):
        rm = cp.get("readiness_matrix") or {}
        assert rm.get("overall_status") in {"RED", "YELLOW", "GREEN"}
        sc = cp.get("scanner") or {}
        assert "running" in sc, f"scanner block missing 'running': {sc}"

    def test_no_signing_material(self, cp):
        blob = json.dumps(cp).lower()
        for needle in FORBIDDEN_SUBSTRINGS:
            assert needle not in blob


# ---------- RECURRING ----------
class TestRecurring:
    def test_recurring_min_seen(self, auth_session, scan_result):
        # Run one more scan to boost recurrence counts
        auth_session.post(f"{BASE_URL}/api/arbicore/engine/scan-once",
                          json={"limit": 6}, timeout=180)
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/recurring?min_seen=2",
                             timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        routes = d.get("routes") or d.get("recurring") or d.get("items") or []
        # If any routes returned, each must have times_seen >= 2.
        for row in routes:
            ts = row.get("times_seen") or row.get("seen_count") or row.get("count")
            assert ts is not None and ts >= 2, f"row violates min_seen: {row}"


# ---------- READINESS MATRIX iteration-6 assertions ----------
class TestReadinessMatrix6:
    @pytest.fixture(scope="class")
    def matrix(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=30)
        assert r.status_code == 200, r.text[:300]
        return r.json()

    def _rows(self, matrix):
        caps = matrix.get("capabilities") or matrix.get("matrix") or []
        if isinstance(caps, dict):
            return [{**v, "capability": k} if isinstance(v, dict) else {"capability": k, "status": v}
                    for k, v in caps.items()]
        return caps

    def test_liquidity_depth_green(self, matrix):
        rows = self._rows(matrix)
        row = next((r for r in rows if (r.get("capability") or r.get("name")) == "LIQUIDITY_DEPTH"), None)
        assert row is not None, f"LIQUIDITY_DEPTH row not found; rows={[r.get('capability') for r in rows]}"
        assert row.get("status") == "GREEN", f"LIQUIDITY_DEPTH not GREEN: {row}"

    def test_scanner_green_when_running(self, auth_session, matrix):
        # ensure scanner is running
        st = auth_session.get(f"{BASE_URL}/api/arbicore/engine/scanner/status", timeout=30).json()
        if not st.get("running"):
            auth_session.post(f"{BASE_URL}/api/arbicore/engine/scanner/start", timeout=30)
            time.sleep(1)
            matrix = auth_session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix",
                                      timeout=30).json()
        rows = self._rows(matrix)
        row = next((r for r in rows if (r.get("capability") or r.get("name")) == "SCANNER"), None)
        assert row is not None, "SCANNER row not found"
        assert row.get("status") == "GREEN", f"SCANNER not GREEN when running: {row}"

    def test_modes(self, matrix):
        modes = matrix.get("modes") or {}
        assert modes["LIMITED_LIVE"]["can_activate"] is False
        assert modes["FULL_AUTOMATION"]["can_activate"] is False
        assert modes["SHADOW"]["can_activate"] is True
        assert modes["PAPER"]["can_activate"] is True
        assert modes["PROFIT_ENGINE"]["can_activate"] is True

    def test_overall_red(self, matrix):
        assert matrix.get("overall_status") == "RED", \
            f"expected overall RED (LIMITED_LIVE prereqs missing), got {matrix.get('overall_status')}"


# ---------- REGRESSION on prior /control endpoints ----------
class TestRegression:
    def test_control_readiness(self, auth_session):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/control/readiness", timeout=30)
        assert r.status_code == 200

    def test_control_live_quote(self, auth_session):
        payload = {
            "token_in": "0x4200000000000000000000000000000000000006",
            "token_out": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "amount_in_usd": 1000,
        }
        r = auth_session.post(f"{BASE_URL}/api/arbicore/control/live-quote",
                              json=payload, timeout=60)
        assert r.status_code < 500

    def test_control_decide_opportunity(self, auth_session):
        payload = {"opportunity": {"route_id": "test", "gross_spread_bps": 5}}
        r = auth_session.post(f"{BASE_URL}/api/arbicore/control/decide-opportunity",
                              json=payload, timeout=60)
        assert r.status_code < 500


# ---------- FINAL STATE: leave scanner running, mode SHADOW, kill switch DISENGAGED ----------
class TestFinalState:
    def test_scanner_running(self, auth_session):
        auth_session.post(f"{BASE_URL}/api/arbicore/engine/scanner/start", timeout=30)
        st = auth_session.get(f"{BASE_URL}/api/arbicore/engine/scanner/status",
                              timeout=30).json()
        assert st.get("running") is True

    def test_mode_shadow_and_kill_switch(self, auth_session):
        # Try common status endpoints — accept whichever exists.
        candidates = [
            "/api/arbicore/control/readiness",
            "/api/arbicore/control/status",
            "/api/arbicore/engine/checkpoint",
        ]
        blob_lower = ""
        for path in candidates:
            r = auth_session.get(f"{BASE_URL}{path}", timeout=30)
            if r.status_code == 200:
                blob_lower += json.dumps(r.json()).lower() + "\n"
        assert "shadow" in blob_lower, "SHADOW mode not reflected anywhere"
        # kill switch disengaged: no 'engaged": true' or 'kill_switch": "engaged"'
        assert '"kill_switch_engaged": true' not in blob_lower
        assert '"kill_switch": "engaged"' not in blob_lower
