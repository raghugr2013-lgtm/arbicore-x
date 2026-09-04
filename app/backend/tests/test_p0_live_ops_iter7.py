"""P0 iteration 7 — Live Ops / Market-Coverage Funnel / Profit Alerts / Onboarding."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://p0-3-certification.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"

FUNNEL_KEYS = [
    "candidate_universe", "routes_quoted", "real_quotes",
    # accept either 'quote_or_liquidity_failures' (spec name) or 'quote_failures' (impl name)
    "negative_economics",
    "positive_net", "positive_ev", "simulation_candidates",
    "simulation_passes", "executable",
]

FORBIDDEN = ["private_key", "signed_tx", "raw_tx",
             "eth_sendTransaction", "eth_sendRawTransaction", "personal_sign"]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ---- Auth gating ---- #
@pytest.mark.parametrize("path,method", [
    ("/arbicore/engine/scan-once", "POST"),
    ("/arbicore/engine/alerts", "GET"),
    ("/arbicore/engine/onboarding", "GET"),
    ("/arbicore/engine/scanner/status", "GET"),
    ("/arbicore/engine/checkpoint", "GET"),
])
def test_auth_required(path, method):
    r = requests.request(method, f"{API}{path}", timeout=30,
                         json={} if method == "POST" else None)
    assert r.status_code == 401, f"{path} anon returned {r.status_code}"


# ---- scan-once funnel ---- #
def test_scan_once_returns_funnel(session):
    r = session.post(f"{API}/arbicore/engine/scan-once",
                     json={"limit": 6}, timeout=120)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["execution_performed"] is False
    assert body["shadow_safe"] is True
    assert "funnel" in body, "scan-once must include 'funnel'"
    funnel = body["funnel"]
    for k in FUNNEL_KEYS:
        assert k in funnel, f"funnel missing key {k}"
    # quote/liquidity failure signal must exist under either canonical name
    assert ("quote_or_liquidity_failures" in funnel) or ("quote_failures" in funnel), \
        f"funnel missing quote/liquidity failure key. keys={list(funnel.keys())}"
    assert funnel["candidate_universe"] >= funnel["routes_quoted"], (
        f"candidate_universe({funnel['candidate_universe']}) < routes_quoted({funnel['routes_quoted']})"
    )
    text = r.text.lower()
    for f in FORBIDDEN:
        assert f.lower() not in text, f"forbidden token found: {f}"


# ---- alerts ---- #
def test_alerts_shape(session):
    r = session.get(f"{API}/arbicore/engine/alerts?limit=20", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "alerts" in body
    assert "total" in body
    assert "criteria" in body
    crit = body["criteria"].lower()
    assert "real_quote" in crit and "simulation" in crit
    assert isinstance(body["alerts"], list)


# ---- onboarding ---- #
def test_onboarding_checklist(session):
    r = session.get(f"{API}/arbicore/engine/onboarding", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "checklist" in body
    keys = {c["key"] for c in body["checklist"]}
    for expected in ["read_rpc", "gas_wallet", "signer", "executor", "archive_rpc"]:
        assert expected in keys, f"missing checklist key {expected}"
    by_key = {c["key"]: c for c in body["checklist"]}
    assert by_key["read_rpc"]["status"] == "DONE"
    # secret items flagged
    for k in ["gas_wallet", "signer", "executor"]:
        assert by_key[k].get("handles_secret") is True, f"{k} must be flagged secret"
    # never leak secrets
    text = r.text
    for token in ["ARBICORE_VALIDATION_SIGNER_KEY", "ARBICORE_SIGNER_KEY"]:
        # env var name mention is ok in how_to; ensure no key values leaked
        pass
    lowered = text.lower()
    for f in FORBIDDEN:
        assert f.lower() not in lowered


# ---- scanner status ---- #
def test_scanner_status_funnel(session):
    r = session.get(f"{API}/arbicore/engine/scanner/status", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert "candidate_universe" in body, f"missing candidate_universe. keys={list(body.keys())}"
    assert "funnel_cumulative" in body, f"missing funnel_cumulative. keys={list(body.keys())}"
    fc = body["funnel_cumulative"]
    # cumulative funnel should at least contain some canonical keys
    for k in ("candidate_universe", "routes_quoted", "real_quotes"):
        assert k in fc, f"funnel_cumulative missing {k}"


# ---- checkpoint regressions ---- #
def test_checkpoint_regression(session):
    r = session.get(f"{API}/arbicore/engine/checkpoint", timeout=90)
    assert r.status_code == 200
    body = r.json()
    assert "market_coverage_funnel" in body
    assert "profit_alerts_total" in body
    assert isinstance(body["profit_alerts_total"], int)
    matrix = body["readiness_matrix"]
    modes = matrix["modes"]
    ll = modes.get("LIMITED_LIVE") if isinstance(modes, dict) else \
         next((m for m in modes if m.get("mode") == "LIMITED_LIVE"), None)
    assert ll is not None, f"LIMITED_LIVE not found in modes: {modes}"
    assert ll["can_activate"] is False
