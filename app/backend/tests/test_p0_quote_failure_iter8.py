"""Iteration 8 — quote-failure categorization + RPC throttle/retry regression."""
import os, re, requests, pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://defi-exec-audit.preview.emergentagent.com").rstrip("/")
FORBIDDEN = ["private_key", "signed_tx", "raw_tx", "eth_sendTransaction",
             "eth_sendRawTransaction", "personal_sign"]
CATS_ALLOWED = {"rate_limited", "revert_no_pool", "no_adapter", "rpc_error", "other", None}


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "operator", "password": "ShadowOperator!2026"},
               timeout=15)
    assert r.status_code == 200, r.text
    return s


def _no_forbidden(body: str):
    low = body.lower()
    for tok in FORBIDDEN:
        assert tok.lower() not in low, f"forbidden token {tok} in response"


# ---------- Auth gating ----------
def test_scan_once_requires_auth():
    r = requests.post(f"{BASE}/api/arbicore/engine/scan-once",
                      json={"limit": 4}, timeout=30)
    assert r.status_code == 401


def test_scanner_status_requires_auth():
    r = requests.get(f"{BASE}/api/arbicore/engine/scanner/status", timeout=15)
    assert r.status_code == 401


# ---------- scan-once (main) ----------
@pytest.fixture(scope="module")
def scan_result(sess):
    r = sess.post(f"{BASE}/api/arbicore/engine/scan-once",
                  json={"limit": 8}, timeout=120)
    assert r.status_code == 200, r.text
    _no_forbidden(r.text)
    return r.json()


def test_scan_once_execution_flag_false(scan_result):
    assert scan_result.get("execution_performed") is False


def test_scan_once_funnel_has_quote_failure_reasons(scan_result):
    funnel = scan_result.get("funnel") or {}
    assert "quote_failure_reasons" in funnel, f"funnel keys: {list(funnel.keys())}"
    qfr = funnel["quote_failure_reasons"]
    assert isinstance(qfr, dict), "quote_failure_reasons must be an object/dict"
    # keys must be allowed categories
    for k in qfr.keys():
        assert k in {"rate_limited", "revert_no_pool", "no_adapter",
                     "rpc_error", "other"}, f"unexpected category: {k}"
    # values must be non-negative ints
    for k, v in qfr.items():
        assert isinstance(v, int) and v >= 0
    print("quote_failure_reasons:", qfr)


def test_scan_once_real_quotes_at_least_one(scan_result):
    funnel = scan_result.get("funnel") or {}
    real = funnel.get("real_quotes")
    assert isinstance(real, int)
    assert real >= 1, f"expected real_quotes>=1, funnel={funnel}"


def test_scan_once_opportunities_have_quote_failure_category(scan_result):
    opps = scan_result.get("opportunities") or []
    if not opps:
        pytest.skip("no opportunities in scan-once payload")
    for o in opps:
        assert "quote_failure_category" in o, f"missing key on opp: {list(o.keys())[:15]}"
        assert o["quote_failure_category"] in CATS_ALLOWED


# ---------- scanner/status ----------
def test_scanner_status_has_cumulative_quote_failure_reasons(sess):
    r = sess.get(f"{BASE}/api/arbicore/engine/scanner/status", timeout=15)
    assert r.status_code == 200, r.text
    _no_forbidden(r.text)
    body = r.json()
    fc = body.get("funnel_cumulative") or {}
    assert "quote_failure_reasons" in fc, f"funnel_cumulative keys: {list(fc.keys())}"
    assert isinstance(fc["quote_failure_reasons"], dict)
    # numeric funnel fields still present
    for k in ("candidate_universe", "routes_quoted", "real_quotes"):
        assert k in fc, f"missing numeric funnel key {k}"


# ---------- checkpoint regression ----------
def test_checkpoint_still_shape(sess):
    r = sess.get(f"{BASE}/api/arbicore/engine/checkpoint", timeout=20)
    assert r.status_code == 200, r.text
    _no_forbidden(r.text)
    body = r.json()
    assert "market_coverage_funnel" in body
    rm = body.get("readiness_matrix") or {}
    overall = str(rm.get("overall_status") or rm.get("overall") or "").upper()
    assert overall == "RED", f"overall readiness not RED: {overall!r}"
    # LIMITED_LIVE / FULL_AUTOMATION gating verified via capabilities containing YELLOW/RED blockers
    caps = rm.get("capabilities") or []
    non_green = [c for c in caps if str(c.get("status","")).upper() != "GREEN"]
    assert non_green, "expected at least one non-GREEN capability blocking LIMITED_LIVE"


# ---------- control endpoints unchanged ----------
def test_control_decide_opportunity_ok(sess):
    r = sess.post(f"{BASE}/api/arbicore/control/decide-opportunity",
                  json={}, timeout=45)
    assert r.status_code in (200, 400, 422), r.text
    _no_forbidden(r.text)


def test_control_live_quote_ok(sess):
    r = sess.post(f"{BASE}/api/arbicore/control/live-quote",
                  json={}, timeout=45)
    assert r.status_code in (200, 400, 422), r.text
    _no_forbidden(r.text)


# ---------- SAFETY ----------
def test_safety_mode_and_kill_switch(sess):
    r = sess.get(f"{BASE}/api/arbicore/engine/checkpoint", timeout=20)
    assert r.status_code == 200
    body = r.json()
    txt = str(body).lower()
    # mode SHADOW
    assert "shadow" in txt
    # kill switch disengaged (accept either literal)
    ks = body.get("kill_switch") or body.get("killSwitch") or {}
    state = str(ks.get("state") or ks.get("status") or "").upper() if isinstance(ks, dict) else ""
    # If nested elsewhere, just ensure not engaged/armed:
    assert "ENGAGED" not in state or state == "DISENGAGED"
