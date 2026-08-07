"""Iteration 3: Technical Validation endpoint (dry) + history + regressions.

DO NOT set execute=true — broadcasting is out of scope.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
EXECUTED_TX = "0x7b61cdb6a5bcceb41875398a6b9ba512ff8cc2c15b823cbb9bca65d269185f20"
EXECUTOR = "0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052"


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- NEW: technical-validation dry ---
def test_technical_validation_dry(s):
    r = s.post(
        f"{BASE_URL}/api/arbicore/wizard/technical-validation",
        json={"execute": False},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    result = body.get("result") or body
    assert result.get("mode") == "preflight_only", result
    assert result.get("engine_ready") is True, result
    steps = result.get("steps") or []
    assert len(steps) >= 1, result
    assert steps[0].get("stage") == "preflight_funded_sim"
    assert steps[0].get("ok") is True, steps[0]
    swap = result.get("swap") or steps[0].get("swap")
    assert swap is not None, f"swap block missing: {result}"
    # WETH -> USDC hop, 5 bps
    assert int(swap.get("fee_tier_bps", -1)) == 5, swap
    token_in = (swap.get("token_in") or swap.get("from") or "").lower()
    token_out = (swap.get("token_out") or swap.get("to") or "").lower()
    assert "weth" in token_in or token_in.endswith("4200000000000000000000000000000000000006"), swap
    assert "usdc" in token_out or "036cbd53842c5426634e7929541ec2318f3dcf7e" in token_out, swap
    prefund = int(result.get("prefund_buffer_wei") or steps[0].get("prefund_buffer_wei") or 0)
    assert prefund > 0, result


# --- NEW: history contains the executed run ---
def test_technical_validation_history(s):
    r = s.get(
        f"{BASE_URL}/api/arbicore/wizard/technical-validation/history",
        params={"limit": 5},
        timeout=30,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    count = body.get("count", len(body.get("items") or body.get("runs") or []))
    assert count >= 1, body
    runs = body.get("items") or body.get("runs") or body.get("history") or []
    assert runs, body
    executed = [x for x in runs if (x.get("mode") == "executed" or x.get("tx_hash"))]
    assert executed, f"no executed run found in {runs}"
    match = None
    for x in executed:
        if (x.get("tx_hash") or "").lower() == EXECUTED_TX:
            match = x
            break
    assert match is not None, f"executed tx not found. runs={runs}"
    assert match.get("engine_ready") is True, match
    ev = match.get("evidence_bundle") or match.get("evidence") or {}
    for k in ("aave_borrow_ok", "swap_executed_ok", "repayment_ok", "no_contract_revert"):
        assert ev.get(k) is True, f"{k} not true in {ev}"


# --- Governance invariant ---
def test_governance_mode_still_shadow(s):
    r = s.get(f"{BASE_URL}/api/arbicore/execution/mode", timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body.get("items") or []
    fla = next((i for i in items if i.get("strategy") == "flash_loan_arbitrage"), None)
    assert fla is not None, body
    assert fla.get("mode") == "SHADOW", fla


# --- Regression: executor verify READY ---
def test_executor_verify_ready(s):
    r = s.get(f"{BASE_URL}/api/arbicore/executor/verify", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("overall_status") == "READY", body
    assert (body.get("address") or "").lower() == EXECUTOR.lower()


# --- Regression: opportunity-probe ---
def test_opportunity_probe(s):
    r = s.post(f"{BASE_URL}/api/arbicore/wizard/opportunity-probe", json={}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True, r.json()


# --- Regression: rpc/check ---
def test_rpc_check(s):
    r = s.get(f"{BASE_URL}/api/arbicore/rpc/check", timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") == "READY" or body.get("overall_status") == "READY", body
    assert int(body.get("chain_id")) == 84532, body
