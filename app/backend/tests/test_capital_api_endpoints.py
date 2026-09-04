"""HTTP integration tests for /api/arbicore/capital/* endpoints."""
import json
import os
import re
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://p0-3-certification.preview.emergentagent.com").rstrip("/")
GAS_ADDR = "0x998d6efF2b28b72c44f7a334c42678eb4cCaad25"

USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"

FORBIDDEN_KEYS = ("private_key", "signed_tx", "raw_tx", "eth_sendTransaction", "privateKey", "signedTx", "rawTx")


@pytest.fixture(scope="module")
def sess():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text}"
    return s


def _no_key_leak(payload):
    body = json.dumps(payload).lower()
    for k in FORBIDDEN_KEYS:
        assert k.lower() not in body, f"forbidden key {k} found in response"


# ---------- auth ----------
def test_auth_required_anonymous():
    r = requests.get(f"{BASE_URL}/api/arbicore/capital/balances", timeout=60)
    assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"


# ---------- balances ----------
def test_balances(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/balances", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    assert "native" in d and "balance" in d["native"]
    bal = float(d["native"]["balance"])
    assert 0.003 < bal < 0.006, f"expected ~0.00418 ETH, got {bal}"
    assert "value_usd" in d["native"]
    assert isinstance(d.get("tokens"), list)
    assert "total_value_usd" in d
    assert "block_number" in d
    assert "last_sync" in d
    _no_key_leak(d)


# ---------- wallets ----------
def test_wallets(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/wallets", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    wallets = d.get("wallets", [])
    addrs = [str(w.get("address","")).lower() for w in wallets]
    assert GAS_ADDR.lower() in addrs, f"gas wallet missing: {addrs}"
    _no_key_leak(d)


# ---------- statement ----------
def test_statement_graceful_degradation(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/statement?limit=50", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "transactions" in d and isinstance(d["transactions"], list)
    assert "count" in d
    assert d.get("explorer_key_configured") is False
    assert d.get("source_ok") is False
    reason = str(d.get("source_reason","")).lower()
    assert "arbicore_etherscan_api_key" in reason or "etherscan" in reason
    _no_key_leak(d)


def test_statement_filters_accepted(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/statement?limit=25&tx_type=swap&venue=uniswap&status=success", timeout=30)
    assert r.status_code == 200, r.text


# ---------- reconciliation ----------
def test_reconciliation(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/reconciliation", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("start_balance","inflows","outflows","fees","end_balance","residual","reconciled","statement_complete"):
        assert k in d, f"missing {k}"
    residual = float(d["residual"])
    assert abs(residual) < 1e-6, f"residual not zero: {residual}"
    assert d["reconciled"] is True
    assert d["statement_complete"] is False
    # identity: start = end - inflows + outflows + fees  (i.e. residual ~ 0)
    start = float(d["start_balance"]); end = float(d["end_balance"])
    inflows = float(d["inflows"]); outflows = float(d["outflows"]); fees = float(d["fees"])
    identity = start - (end - inflows + outflows + fees)
    assert abs(identity) < 1e-6, f"identity violated: {identity}"
    _no_key_leak(d)


# ---------- money-trail ----------
def test_money_trail(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/money-trail?tx_hash=0xabc", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "ok" in d
    # legs present on success; when explorer unavailable, ok=false + reason is acceptable
    if d.get("ok") is True:
        assert "legs" in d
    else:
        assert "reason" in d
    _no_key_leak(d)


# ---------- venue stats ----------
def test_venue_stats(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/venue-stats", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "by_venue" in d and "by_tx_type" in d
    _no_key_leak(d)


# ---------- overview ----------
def test_overview(sess):
    r = sess.get(f"{BASE_URL}/api/arbicore/capital/overview", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("balances","statement","reconciliation","venue_stats","monitored_wallets"):
        assert k in d, f"missing {k}"
    _no_key_leak(d)
