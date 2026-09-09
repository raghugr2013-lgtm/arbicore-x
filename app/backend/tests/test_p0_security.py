"""P0 security remediation tests: authz locks & server-derived actor."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # Fallback: read frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

UNAUTH_ENDPOINTS = [
    ("POST", "/arbicore/execution/mode/flash_loan_arbitrage", {"to_mode": "PAPER"}),
    ("POST", "/arbicore/settings/network/apply", {}),
    ("POST", "/arbicore/settings/network/rollback", {}),
    ("POST", "/arbicore/pipeline/evaluate", {}),
    ("POST", "/arbicore/auto-executor/start", {}),
    ("POST", "/arbicore/auto-executor/stop", {}),
    ("POST", "/arbicore/settings/scanner/pause", {}),
    ("POST", "/arbicore/settings/scanner/resume", {}),
    ("POST", "/arbicore/settings/scanner/global/apply", {}),
    ("PATCH", "/arbicore/settings/operational", {}),
    ("POST", "/arbicore/execution/wallets", {}),
    ("POST", "/arbicore/execution/secrets", {}),
    ("POST", "/arbicore/settings/telegram/test", {}),
]


@pytest.fixture(scope="module")
def clean_session():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def operator_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login",
               json={"username": "operator", "password": "ShadowOperator!2026"},
               timeout=15)
    assert r.status_code == 200, f"Operator login failed: {r.status_code} {r.text}"
    return s


@pytest.mark.parametrize("method,path,body", UNAUTH_ENDPOINTS)
def test_unauth_returns_401(clean_session, method, path, body):
    r = clean_session.request(method, f"{API}{path}", json=body, timeout=15)
    assert r.status_code == 401, f"{method} {path} expected 401, got {r.status_code}: {r.text[:200]}"


def test_admin_login():
    r = requests.post(f"{API}/auth/login",
                      json={"username": "admin", "password": "ArbiCore2026!"},
                      timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    data = r.json()
    assert "user" in data or "username" in str(data).lower()


def test_operator_login_sets_cookie(operator_session):
    cookies = operator_session.cookies.get_dict()
    assert "access_token" in cookies, f"access_token cookie missing: {cookies}"


def test_operator_pipeline_evaluate(operator_session):
    r = operator_session.post(f"{API}/arbicore/pipeline/evaluate", json={}, timeout=30)
    assert r.status_code == 200, f"pipeline/evaluate: {r.status_code} {r.text[:300]}"


def test_operator_scanner_pause(operator_session):
    r = operator_session.post(f"{API}/arbicore/settings/scanner/pause", json={}, timeout=15)
    assert r.status_code == 200, f"scanner/pause: {r.status_code} {r.text[:300]}"


def test_operator_scanner_resume(operator_session):
    r = operator_session.post(f"{API}/arbicore/settings/scanner/resume", json={}, timeout=15)
    assert r.status_code == 200, f"scanner/resume: {r.status_code} {r.text[:300]}"


def test_server_derived_actor_ignores_spoof(operator_session):
    """Attempt to spoof actor field - server must ignore it and use authenticated user."""
    r = operator_session.post(
        f"{API}/arbicore/execution/mode/flash_loan_arbitrage",
        json={"to_mode": "SHADOW", "reason": "agent-test", "actor": "attacker-spoof"},
        timeout=20,
    )
    assert r.status_code == 200, f"mode transition: {r.status_code} {r.text[:300]}"
    body_text = r.text
    assert "attacker-spoof" not in body_text, f"Response echoed spoofed actor: {body_text[:300]}"

    # Try to fetch history to confirm operator is recorded
    for hist_path in [
        "/arbicore/execution/mode/audit/history",
        "/arbicore/execution/mode/audit/history?strategy=flash_loan_arbitrage",
    ]:
        hr = operator_session.get(f"{API}{hist_path}", timeout=10)
        if hr.status_code == 200:
            txt = hr.text
            assert "attacker-spoof" not in txt, f"History echoed spoof at {hist_path}: {txt[:300]}"
            assert "operator" in txt.lower(), f"Operator not recorded at {hist_path}: {txt[:300]}"
            print(f"History verified at {hist_path}")
            return
    print("No history endpoint found; server-derived actor validated via response only.")


def test_invalid_bearer_rejected():
    r = requests.post(
        f"{API}/arbicore/pipeline/evaluate",
        headers={"Authorization": "Bearer not-a-real-token-xxxxx"},
        json={},
        timeout=15,
    )
    assert r.status_code == 401, f"Invalid bearer expected 401, got {r.status_code}: {r.text[:200]}"
