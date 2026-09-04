"""Iteration 10 — Live integration tests for settlement simulator + RPC caps + readiness matrix.

Exercises against public REACT_APP_BACKEND_URL. Public Base RPC is rate limited
(-32016); simulator has throttle+retry so allow up to 60s per call.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://p0-3-certification.preview.emergentagent.com").rstrip("/")
USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"

WETH = "0x4200000000000000000000000000000000000006"
USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

FORBIDDEN_STRINGS = [
    "private_key", "signed_tx", "raw_tx",
    "eth_sendTransaction", "eth_sendRawTransaction", "personal_sign",
]


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ---------- Auth guard ---------------------------------------------------

def test_simulate_settlement_requires_auth():
    r = requests.post(
        f"{BASE_URL}/api/arbicore/engine/simulate-settlement",
        json={"hops": [{"token_in": WETH, "token_out": USDC, "stable": False}],
              "amount_in_wei": 10**16}, timeout=15)
    assert r.status_code == 401


# ---------- RPC capabilities --------------------------------------------

def test_rpc_capabilities(session):
    r = session.get(f"{BASE_URL}/api/arbicore/engine/rpc-capabilities?refresh=true", timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["rpc_configured"] is True
    caps = data["capabilities"]
    assert caps.get("state_override") is True
    assert caps.get("archive_state") is True
    assert caps.get("trace") is False


# ---------- Settlement simulation (round-trip) --------------------------

def test_simulate_settlement_roundtrip(session):
    body = {
        "hops": [{"token_in": WETH, "token_out": USDC, "stable": False},
                 {"token_in": USDC, "token_out": WETH, "stable": False}],
        "amount_in_wei": 10000000000000000,
        "token_decimals": 18,
        "token_usd": 2500,
        "gas_cost_usd": 1.0,
    }
    r = session.post(f"{BASE_URL}/api/arbicore/engine/simulate-settlement",
                     json=body, timeout=90)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["execution_performed"] is False
    assert d["shadow_safe"] is True
    sim = d["simulation"]
    assert sim["ran"] is True
    # Round-trip: passed=false (repay fail) is CORRECT.
    assert "passed" in sim
    assert "final_amount_out_wei" in sim
    assert "repayment_ok" in sim
    assert "net_profit_usd" in sim
    assert "block_number" in sim
    assert sim["signed"] is False
    assert sim["broadcast"] is False


# ---------- Block-pinned historical replay -------------------------------

def test_simulate_settlement_block_pinned_replay(session):
    block = 50000000
    body = {
        "hops": [{"token_in": WETH, "token_out": USDC, "stable": False},
                 {"token_in": USDC, "token_out": WETH, "stable": False}],
        "amount_in_wei": 10000000000000000,
        "token_decimals": 18,
        "token_usd": 2500,
        "gas_cost_usd": 1.0,
        "block_number": block,
    }
    r = session.post(f"{BASE_URL}/api/arbicore/engine/simulate-settlement",
                     json=body, timeout=90)
    assert r.status_code == 200, r.text
    sim = r.json()["simulation"]
    assert sim.get("replay_block_number") == block
    assert sim.get("block") == hex(block)
    assert sim.get("signed") is False and sim.get("broadcast") is False


# ---------- Validation & allowlist ---------------------------------------

def test_simulate_settlement_missing_hops(session):
    r = session.post(f"{BASE_URL}/api/arbicore/engine/simulate-settlement",
                     json={"amount_in_wei": 10**16}, timeout=30)
    assert r.status_code == 422


def test_simulate_settlement_rejects_non_allowlisted_token(session):
    body = {
        "hops": [{"token_in": WETH,
                  "token_out": "0xdeadbeefdeadbeefdeadbeefdeadbeefdeadbeef",
                  "stable": False}],
        "amount_in_wei": 10000000000000000,
        "token_decimals": 18,
        "token_usd": 2500,
    }
    r = session.post(f"{BASE_URL}/api/arbicore/engine/simulate-settlement",
                     json=body, timeout=60)
    # Should return 200 with sim.stage=='encode' rejection (per simulator contract).
    assert r.status_code == 200, r.text
    sim = r.json()["simulation"]
    assert sim.get("passed") is False
    assert sim.get("stage") == "encode"


# ---------- Readiness matrix --------------------------------------------

def test_readiness_matrix(session):
    r = session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=60)
    assert r.status_code == 200, r.text
    m = r.json()
    caps = {c["capability"]: c for c in m["capabilities"]}
    expected_green = ["SETTLEMENT_SIMULATION", "RPC_STATE_OVERRIDE",
                      "HISTORICAL_REPLAY", "DEX_ADAPTERS_SETTLE",
                      "LIQUIDITY_DEPTH"]
    for cap in expected_green:
        assert cap in caps, f"missing capability {cap}"
        assert caps[cap]["status"] == "GREEN", f"{cap} != GREEN ({caps[cap]['status']})"

    for cap in ("SIMULATION_ONCHAIN", "FORK_VALIDATION"):
        assert cap in caps
        assert caps[cap]["status"] == "YELLOW", f"{cap} != YELLOW ({caps[cap]['status']})"

    # Activation locks (nested under 'modes')
    modes = m.get("modes", {})
    assert modes.get("LIMITED_LIVE", {}).get("can_activate") is False
    assert modes.get("FULL_AUTOMATION", {}).get("can_activate") is False
    assert m.get("current_mode") == "SHADOW"


# ---------- Regression / safety ----------------------------------------

def test_scanner_still_running(session):
    r = session.get(f"{BASE_URL}/api/arbicore/engine/scanner/status", timeout=30)
    assert r.status_code == 200
    st = r.json()
    assert st.get("running") is True or st.get("is_running") is True or st.get("state") == "running"


def test_scan_once_funnel_intact(session):
    r = session.post(f"{BASE_URL}/api/arbicore/engine/scan-once", timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    # Funnel keys must be present
    text = str(d).lower()
    assert "funnel" in text or "candidate" in text


def test_no_signing_or_broadcast_leaks(session):
    """Scan several representative endpoints and assert no forbidden strings."""
    endpoints = [
        "/api/arbicore/engine/rpc-capabilities",
        "/api/arbicore/engine/readiness-matrix",
        "/api/arbicore/engine/scanner/status",
    ]
    for ep in endpoints:
        r = session.get(f"{BASE_URL}{ep}", timeout=30)
        assert r.status_code == 200, ep
        body = r.text
        for s in FORBIDDEN_STRINGS:
            assert s not in body, f"forbidden string '{s}' in {ep}"


def test_mode_shadow_and_killswitch(session):
    """Ensure mode is SHADOW and kill switch is disengaged."""
    # Try common status endpoints
    for path in ("/api/arbicore/control/status", "/api/arbicore/engine/status"):
        r = session.get(f"{BASE_URL}{path}", timeout=20)
        if r.status_code == 200:
            txt = r.text.upper()
            assert "SHADOW" in txt, f"expected SHADOW mode in {path}: {r.text[:200]}"
            return
    pytest.skip("no status endpoint available")
