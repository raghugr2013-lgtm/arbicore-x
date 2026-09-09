"""M07 truthfulness + P0 authz regression tests"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fall back to frontend .env
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip().rstrip("/")

API = f"{BASE_URL}/api"

OPERATOR = {"username": "operator", "password": "ShadowOperator!2026"}


@pytest.fixture(scope="module")
def op_session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=OPERATOR, timeout=15)
    assert r.status_code == 200, f"Operator login failed: {r.status_code} {r.text}"
    return s


# ---------- M07 truthfulness ----------

def test_vaults_truthful(op_session):
    r = op_session.get(f"{API}/arbicore/settings/vaults", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("mocked") is True, body
    assert body.get("contributes_to_readiness") is False, body
    items = body.get("items") or body.get("vaults") or []
    assert items, f"No vault items: {body}"
    for it in items:
        assert it.get("state") == "NOT_CONFIGURED", it
        assert it.get("evidence_tier") == "MOCKED", it
        assert it.get("address") is None, it
        assert "reconciled_at" not in it or it.get("reconciled_at") is None, it


def test_vault_reconcile_truthful(op_session):
    r = op_session.post(f"{API}/arbicore/settings/vaults/cold_wallet/reconcile", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is False, body
    assert body.get("state") == "NOT_CONFIGURED", body
    assert body.get("mocked") is True, body


def test_exchanges_truthful(op_session):
    r = op_session.get(f"{API}/arbicore/settings/exchanges", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("mocked") is True, body
    assert body.get("contributes_to_readiness") is False, body
    items = body.get("items") or body.get("exchanges") or []
    assert items, f"No exchange items: {body}"
    for it in items:
        assert it.get("state") == "NOT_CONFIGURED", it
        assert it.get("evidence_tier") == "MOCKED", it
        assert it.get("api_key_masked") is None, it
        assert "last_tested_at" not in it or it.get("last_tested_at") is None, it


def test_exchange_test_truthful(op_session):
    r = op_session.post(f"{API}/arbicore/settings/exchanges/binance/test", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is False, body
    assert body.get("state") == "NOT_CONFIGURED", body
    assert body.get("mocked") is True, body
    assert "latency_ms" not in body or body.get("latency_ms") is None, body


# ---------- P0 authz regression (no auth) ----------

def test_unauth_vaults_get():
    # M07 contract: the vaults GET is a PUBLIC read (consistent with the app's
    # existing public-GET settings posture). What matters for M07 is that the
    # body is TRUTHFUL and carries no secrets — verify that, not read-authz
    # (read-side authz across all settings GETs is a separate, out-of-scope
    # app-wide decision).
    r = requests.get(f"{API}/arbicore/settings/vaults", timeout=15)
    assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("mocked") is True
    assert body.get("contributes_to_readiness") is False
    for it in body.get("items", []):
        assert it["state"] == "NOT_CONFIGURED"
        assert it["evidence_tier"] == "MOCKED"
        assert it["address"] is None


def test_unauth_exchanges_get():
    r = requests.get(f"{API}/arbicore/settings/exchanges", timeout=15)
    assert r.status_code == 200, f"expected 200 got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("mocked") is True
    assert body.get("contributes_to_readiness") is False
    for it in body.get("items", []):
        assert it["state"] == "NOT_CONFIGURED"
        assert it["evidence_tier"] == "MOCKED"
        assert it["api_key_masked"] is None


def test_unauth_vault_reconcile_post():
    r = requests.post(f"{API}/arbicore/settings/vaults/cold_wallet/reconcile", timeout=15)
    assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text}"


def test_unauth_exchange_test_post():
    r = requests.post(f"{API}/arbicore/settings/exchanges/binance/test", timeout=15)
    assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text}"


def test_unauth_execution_mode_post():
    r = requests.post(f"{API}/arbicore/execution/mode/flash_loan_arbitrage",
                      json={"to_mode": "PAPER"}, timeout=15)
    assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text}"


def test_unauth_pipeline_evaluate_post():
    r = requests.post(f"{API}/arbicore/pipeline/evaluate", timeout=15)
    assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text}"


# ---------- P0 authz — authorized 200 ----------

def test_auth_execution_mode_post(op_session):
    r = op_session.post(f"{API}/arbicore/execution/mode/flash_loan_arbitrage",
                        json={"to_mode": "PAPER"}, timeout=15)
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"


def test_auth_pipeline_evaluate_post(op_session):
    r = op_session.post(f"{API}/arbicore/pipeline/evaluate", timeout=15)
    assert r.status_code == 200, f"got {r.status_code}: {r.text}"
