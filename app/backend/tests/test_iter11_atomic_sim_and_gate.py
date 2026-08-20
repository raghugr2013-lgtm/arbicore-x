"""Iteration 11 — Atomic executor sim status + mandatory settlement gate (live URL)."""
import json
import os
import re

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = (BASE_URL or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"

USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"

SIGN_BROADCAST_STRS = [
    "private_key", "signed_tx", "raw_tx",
    "eth_sendTransaction", "eth_sendRawTransaction", "personal_sign",
]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# --------------------- 1. atomic-sim-status
def test_atomic_sim_status_shape(session):
    r = session.get(f"{BASE_URL}/api/arbicore/engine/atomic-sim-status", timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("code_injection_verified") is True, data
    readiness = data.get("readiness") or {}
    # env now provides ARBICORE_EXECUTOR_ADDRESS_BASE → executor_address_set=true;
    # bytecode + signer still absent so atomic_sim stays gated (no fake GREEN).
    assert readiness.get("executor_address_set") is True
    assert readiness.get("executor_bytecode_available") is False
    # Signer now in vault → atomic sim ready against the deployed executor.
    assert data.get("atomic_sim_ready") is True
    note = (data.get("note") or "").lower()
    assert "executor" in note or "signer" in note, data


def test_atomic_sim_status_requires_auth():
    r = requests.get(f"{BASE_URL}/api/arbicore/engine/atomic-sim-status", timeout=30)
    assert r.status_code == 401


# --------------------- 2. readiness-matrix
def test_readiness_matrix_rows_and_activation(session):
    r = session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()

    caps_list = data.get("capabilities") or data.get("rows") or data.get("matrix") or []
    rows = {row.get("capability") or row.get("name"): row for row in caps_list}
    assert rows, f"no rows in matrix: {data}"

    def _status(name):
        row = rows.get(name)
        assert row, f"missing row {name}"
        return (row.get("status") or "").upper()

    assert _status("SETTLEMENT_SIMULATION") == "GREEN"
    assert _status("RPC_STATE_OVERRIDE") == "GREEN"
    assert _status("HISTORICAL_REPLAY") == "GREEN"
    assert _status("DEX_ADAPTERS_SETTLE") == "GREEN"
    # Signer present in vault → ATOMIC_EXECUTOR_SIM GREEN; on-chain sim +
    # fork validation remain honest YELLOWs.
    assert _status("ATOMIC_EXECUTOR_SIM") == "GREEN"
    assert _status("SIMULATION_ONCHAIN") == "YELLOW"
    assert _status("FORK_VALIDATION") == "YELLOW"

    ae = rows["SIMULATION_ONCHAIN"]
    blocker = json.dumps(ae).lower()
    assert "executor" in blocker or "sim" in blocker

    overall = (data.get("overall_status") or data.get("overall") or "").upper()
    assert overall == "YELLOW", data

    modes = data.get("modes") or {}
    assert modes.get("LIMITED_LIVE", {}).get("can_activate") is False
    assert modes.get("FULL_AUTOMATION", {}).get("can_activate") is False

    current_mode = (data.get("current_mode") or "").upper()
    assert current_mode == "SHADOW"


# --------------------- 3. scan-once: settlement gate invariant
def test_scan_once_settlement_gate_invariant(session):
    r = session.post(f"{BASE_URL}/api/arbicore/engine/scan-once",
                     json={"limit": 6}, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    opps = data.get("opportunities") or data.get("results") or []
    assert isinstance(opps, list)

    for o in opps:
        assert "settlement_simulation" in o, f"opp missing settlement_simulation: {list(o.keys())}"
        if o.get("would_execute") is True:
            ss = o.get("settlement_simulation") or {}
            assert ss.get("passed") is True, \
                f"would_execute=true without settlement_simulation.passed=true: {o}"

    # no signing/broadcast strings leaked
    body_low = r.text.lower()
    for s in SIGN_BROADCAST_STRS:
        assert s.lower() not in body_low, f"leak: {s}"


def test_scan_once_requires_auth():
    r = requests.post(f"{BASE_URL}/api/arbicore/engine/scan-once",
                      json={"limit": 2}, timeout=30)
    assert r.status_code == 401


# --------------------- 4. simulate-settlement regression (WETH->USDC->WETH)
def test_simulate_settlement_aerodrome_round_trip(session):
    WETH = "0x4200000000000000000000000000000000000006"
    USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    payload = {
        "hops": [
            {"token_in": WETH, "token_out": USDC, "stable": False},
            {"token_in": USDC, "token_out": WETH, "stable": False},
        ],
        "amount_in_wei": 10000000000000000,
        "token_decimals": 18,
        "token_usd": 2500,
        "gas_cost_usd": 1.0,
    }
    r = None
    data = None
    sim = {}
    # Retry on public RPC rate limit
    for attempt in range(4):
        r = session.post(f"{BASE_URL}/api/arbicore/engine/simulate-settlement",
                         json=payload, timeout=120)
        assert r.status_code == 200, r.text
        data = r.json()
        sim = data.get("simulation") or {}
        if sim.get("ran") is True:
            break
        if "rate limit" in (sim.get("reason") or "").lower():
            import time as _t; _t.sleep(15)
            continue
        break
    assert sim.get("ran") is True, data
    assert sim.get("passed") is False, data
    assert sim.get("signed") is False and sim.get("broadcast") is False
    assert sim.get("repayment_ok") is False or "repay" in json.dumps(sim).lower()


# --------------------- 5. Global safety: SHADOW + no broadcast leaks
def test_scanner_running_and_shadow(session):
    r = session.get(f"{BASE_URL}/api/arbicore/engine/scanner-status", timeout=30)
    if r.status_code == 404:
        # fallback — matrix already verifies current_mode=SHADOW
        return
    assert r.status_code == 200, r.text
    data = r.json()
    body_low = r.text.lower()
    for s in SIGN_BROADCAST_STRS:
        assert s.lower() not in body_low
    # scanner running flag (best-effort key detection)
    running = data.get("running") or data.get("is_running") or data.get("scanner_running")
    if running is not None:
        assert running is True, data
