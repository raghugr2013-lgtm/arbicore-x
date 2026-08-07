"""Tests for ArbiCore opportunity probe + RPC UA fix (Base Sepolia)."""
import os
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass

API = f"{BASE_URL}/api/arbicore"
TIMEOUT = 45

BASE_SEPOLIA_QUOTER = "0xC5290058841028F1614F3A6F0F5816cAd0df5E27"
BASE_MAINNET_QUOTER = "0x3d4e44Eb1374240CE5F1B871ab261CD16335B76a"


def test_rpc_check_ready_base_sepolia():
    r = requests.get(f"{API}/rpc/check", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "READY", data
    assert data.get("chain_id") == 84532, data
    assert isinstance(data.get("block_number"), int) and data["block_number"] > 0, data


def test_opportunity_probe_default_body():
    r = requests.post(f"{API}/wizard/opportunity-probe", json={}, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("chain") == "base-sepolia"
    tiers = data.get("tiers")
    assert isinstance(tiers, list) and len(tiers) >= 3
    fee_set = {t.get("fee_ppm") for t in tiers}
    assert {500, 3000, 10000}.issubset(fee_set), fee_set
    assert isinstance(data.get("any_live_pool"), bool)
    # all tiers must use base-sepolia quoter
    for t in tiers:
        if t.get("quoter_contract"):
            assert t["quoter_contract"].lower() == BASE_SEPOLIA_QUOTER.lower(), t
    if data["any_live_pool"]:
        lt = data.get("live_tier")
        assert lt is not None
        assert lt.get("quoter_contract", "").lower() == BASE_SEPOLIA_QUOTER.lower()
        assert isinstance(lt.get("block_number"), int) and lt["block_number"] > 0


def test_opportunity_probe_custom_body_reflected():
    body = {
        "chain": "base-sepolia",
        "token_in": "0x4200000000000000000000000000000000000006",
        "token_out": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
        "amount_in_wei": "1000000000000000",
        "fees": [500, 3000],
    }
    r = requests.post(f"{API}/wizard/opportunity-probe", json=body, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("chain") == "base-sepolia"
    tiers = data.get("tiers")
    assert isinstance(tiers, list)
    fees = {t.get("fee_ppm") for t in tiers}
    assert fees == {500, 3000}, fees
    assert data["token_in"].lower() == body["token_in"].lower()
    assert data["token_out"].lower() == body["token_out"].lower()
    assert int(data["amount_in_wei"]) == int(body["amount_in_wei"])


def test_opportunity_probe_base_mainnet_routes_correct_quoter():
    body = {"chain": "base"}
    r = requests.post(f"{API}/wizard/opportunity-probe", json=body, timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    assert data.get("chain") == "base"
    tiers = data.get("tiers", [])
    quoters = {t.get("quoter_contract", "").lower() for t in tiers if t.get("quoter_contract")}
    if data.get("live_tier") and data["live_tier"].get("quoter_contract"):
        quoters.add(data["live_tier"]["quoter_contract"].lower())
    assert BASE_SEPOLIA_QUOTER.lower() not in quoters, quoters
    if quoters:
        assert BASE_MAINNET_QUOTER.lower() in quoters, quoters


def _steps_by_key(steps):
    return {s.get("key"): s for s in steps if isinstance(s, dict)}


def test_wizard_state_blocked_overall():
    r = requests.get(f"{API}/wizard/state", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("overall_status") == "BLOCKED", data
    steps = _steps_by_key(data.get("steps", []))
    assert steps.get("kill_switch", {}).get("status") == "READY", steps.get("kill_switch")
    assert steps.get("wallet", {}).get("status") == "BLOCKED", steps.get("wallet")
    assert steps.get("executor", {}).get("status") == "BLOCKED", steps.get("executor")
    assert set(data.get("blockers", [])) >= {"wallet", "executor"}


def test_execution_mode_flash_loan_shadow():
    r = requests.get(f"{API}/execution/mode", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    items = data.get("items") or []
    flarb = next((i for i in items if i.get("strategy") == "flash_loan_arbitrage"), None)
    assert flarb is not None, data
    assert flarb.get("mode") == "SHADOW", flarb
    # Governance sanity: default also SHADOW
    assert (data.get("defaults") or {}).get("flash_loan_arbitrage") == "SHADOW"


def test_executor_verify_clean_blocked():
    r = requests.get(f"{API}/executor/verify", timeout=TIMEOUT)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("overall_status") == "BLOCKED", data
    assert data.get("ready") is False
    assert data.get("address") in (None, "", "0x0000000000000000000000000000000000000000")
    checks = data.get("checks") or {}
    assert checks.get("address_configured", {}).get("status") == "BLOCKED"
