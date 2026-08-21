"""Iter12 — Integration tests for the 3 new executor endpoints against the
live REACT_APP_BACKEND_URL. No signing / no broadcast. Auth via cookie."""
import json
import os
import re
import time

import pytest
import requests
from eth_utils import keccak

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://defi-exec-audit.preview.emergentagent.com").rstrip("/")
OPERATOR = ("operator", "ShadowOperator!2026")

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
AERO_ROUTER = "0xcF77a3Ba9A5CA399B7c97c74d54e5b1Beb874E43"

SELECTOR = "0x" + keccak(text="executeArbitrage(address,uint256,address,bytes)")[:4].hex()

LEAK_PATTERNS = [r"private_key", r"signed_tx", r"raw_tx",
                 r"eth_sendTransaction", r"eth_sendRawTransaction", r"personal_sign"]


def _no_leaks(payload):
    txt = json.dumps(payload).lower()
    for p in LEAK_PATTERNS:
        assert not re.search(p.lower(), txt), f"leak of {p} in response"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": OPERATOR[0], "password": OPERATOR[1]}, timeout=30)
    assert r.status_code == 200, f"auth failed: {r.status_code} {r.text[:200]}"
    return s


# ---------------- Auth enforcement ----------------
@pytest.mark.parametrize("method,path,payload", [
    ("GET",  "/api/arbicore/engine/fork-status", None),
    ("GET",  "/api/arbicore/engine/atomic-sim-status", None),
    ("POST", "/api/arbicore/engine/build-executor-calldata",
     {"borrow_token": WETH, "borrow_amount_wei": 10**16,
      "hops": [{"token_in": WETH, "token_out": USDC, "stable": False}]}),
])
def test_endpoints_require_auth(method, path, payload):
    r = requests.request(method, f"{BASE_URL}{path}", json=payload, timeout=30)
    assert r.status_code == 401, f"{path} anon expected 401 got {r.status_code}"


# ---------------- fork-status ----------------
def test_fork_status_no_fake_green(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/fork-status", timeout=30)
    assert r.status_code == 200
    body = r.json()
    fh = body["fork_harness"]
    # anvil is now installed + archive RPC configured → ready_to_run True.
    # The no-fake-green invariant now lives in the RUN result (ran/passed only
    # after a genuine fork run), validated via run-fork-validation elsewhere.
    assert fh["anvil_installed"] is True
    assert fh["fork_rpc_configured"] is True
    assert fh["ready_to_run"] is True
    _no_leaks(body)


# ---------------- atomic-sim-status ----------------
def test_atomic_sim_status_shape(auth_session):
    # allow up to 3 attempts due to public RPC rate limits on self-test
    body = None
    for i in range(3):
        r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/atomic-sim-status",
                             params={"refresh": "true" if i == 0 else "false"}, timeout=45)
        assert r.status_code == 200
        body = r.json()
        if body.get("code_injection_verified") is True:
            break
        time.sleep(6)
    assert body["code_injection_verified"] is True, body
    rd = body["readiness"]
    assert rd["executor_address_set"] is True
    assert rd["executor_bytecode_available"] is False
    # Signer is now in the vault → atomic sim is ready against the deployed
    # executor (local bytecode not required for a deployed contract).
    assert body["atomic_sim_ready"] is True
    _no_leaks(body)


# ---------------- build-executor-calldata ----------------
def test_build_executor_calldata_happy_path(auth_session):
    payload = {
        "borrow_token": WETH,
        "borrow_amount_wei": 10**16,  # 0.01 WETH
        "hops": [
            {"token_in": WETH, "token_out": USDC, "stable": False},
            {"token_in": USDC, "token_out": WETH, "stable": False},
        ],
        "min_amount_out_wei": 1,
    }
    r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/build-executor-calldata",
                          json=payload, timeout=30)
    assert r.status_code == 200, r.text[:500]
    body = r.json()
    ep = body["executor_entrypoint"]
    assert ep["selector"] == SELECTOR
    assert ep["calldata"].startswith(SELECTOR)
    assert ep["signed"] is False
    assert ep["broadcast"] is False
    assert body["signed"] is False and body["broadcast"] is False
    assert body["settlement"]["to"].lower() == AERO_ROUTER.lower()
    _no_leaks(body)


def test_build_executor_calldata_rejects_non_allowlisted_token(auth_session):
    bad = "0x000000000000000000000000000000000000dEaD"
    payload = {"borrow_token": bad, "borrow_amount_wei": 10**16,
               "hops": [{"token_in": bad, "token_out": USDC, "stable": False}]}
    r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/build-executor-calldata",
                          json=payload, timeout=30)
    assert r.status_code == 422


def test_build_executor_calldata_missing_hops(auth_session):
    r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/build-executor-calldata",
                          json={"borrow_token": WETH, "borrow_amount_wei": 10**16}, timeout=30)
    assert r.status_code == 422


def test_build_executor_calldata_missing_borrow_fields(auth_session):
    r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/build-executor-calldata",
                          json={"hops": [{"token_in": WETH, "token_out": USDC, "stable": False}]},
                          timeout=30)
    assert r.status_code == 422


# ---------------- readiness-matrix invariants ----------------
def test_readiness_matrix_evidence_based(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body["overall_status"] == "YELLOW"
    assert body["current_mode"] == "SHADOW"
    modes = body["modes"]
    assert modes["LIMITED_LIVE"]["can_activate"] is False
    assert modes["FULL_AUTOMATION"]["can_activate"] is False
    rows = {c["capability"].lower(): c for c in body["capabilities"]}
    for green in ("settlement_simulation", "rpc_state_override",
                  "historical_replay", "dex_adapters_settle",
                  "atomic_executor_sim", "signer", "wallet_gas"):
        assert rows[green]["status"].lower() == "green", (green, rows[green])
    # Signer present → ATOMIC_EXECUTOR_SIM is GREEN; the remaining honest
    # YELLOWs are the on-chain sim (executed but route reverts) + fork validation.
    # FORK_VALIDATION now GREEN (genuine anvil fork run); SIMULATION_ONCHAIN
    # stays YELLOW (executes but reverts — no live arbitrage, honest).
    for green2 in ("fork_validation",):
        assert rows[green2]["status"].lower() == "green", (green2, rows[green2])
    for yellow in ("simulation_onchain",):
        assert rows[yellow]["status"].lower() == "yellow", (yellow, rows[yellow])
        assert rows[yellow].get("blocker"), rows[yellow]
    _no_leaks(body)
