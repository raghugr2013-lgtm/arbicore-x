"""Iteration 16 — SIGNER end-to-end + ATOMIC_EXECUTOR_SIM + Anvil fork validation + readiness.

Backend-only. Uses operator cookie auth. Assumes signer vault is populated
(derived address = ARBICORE_GAS_WALLET_ADDRESS = 0x998d6efF2b28b72c44f7a334c42678eb4cCaad25).
"""
import os
import re
import json
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://base-v3-live.preview.emergentagent.com").rstrip("/")
EXPECTED_ADDR = "0x998d6efF2b28b72c44f7a334c42678eb4cCaad25"
HEX64_RE = re.compile(r"(?<![0-9a-fA-Fx])[0-9a-fA-F]{64}(?![0-9a-fA-F])")
LEAK_TOKENS = ["private_key", "signed_tx", "raw_tx", "eth_sendTransaction",
               "eth_sendRawTransaction", "personal_sign"]


def _scan_leaks(payload, allow_addr=True):
    text = json.dumps(payload)
    lower = text.lower()
    for tok in LEAK_TOKENS:
        assert tok.lower() not in lower, f"Leak token {tok!r} present in payload"
    # 64-hex scan (private key length). Note: tx hashes are also 64-hex.
    # For signer endpoints we should have NONE. For sim endpoints we
    # tolerate transaction hashes but still ensure no 'private_key' etc.
    return HEX64_RE.findall(text)


@pytest.fixture(scope="module")
def op_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": "operator", "password": "ShadowOperator!2026"},
               timeout=20)
    assert r.status_code == 200, f"operator login failed: {r.status_code} {r.text[:200]}"
    return s


# --- SIGNER ---------------------------------------------------------------
class TestSigner:
    def test_settings_signer_derived_and_no_leak(self, op_session):
        r = op_session.get(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data.get("present") is True, data
        assert data.get("derived_address", "").lower() == EXPECTED_ADDR.lower(), data
        assert data.get("matches_expected") is True, data
        assert "address_mask" in data or "address_masked" in data or data.get("derived_address"), data
        # No 64-hex private key anywhere
        hex64 = _scan_leaks(data)
        assert hex64 == [], f"Unexpected 64-hex material in signer response: {hex64}"

    def test_settings_signer_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=15)
        assert r.status_code in (401, 403), r.status_code


# --- READINESS ------------------------------------------------------------
class TestReadiness:
    def test_engine_readiness_matrix(self, op_session):
        r = op_session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        caps = {c.get("capability"): c for c in data.get("capabilities", [])}
        assert caps.get("SIGNER", {}).get("status") == "GREEN", caps.get("SIGNER")
        assert caps.get("WALLET_GAS", {}).get("status") == "GREEN", caps.get("WALLET_GAS")
        assert caps.get("ATOMIC_EXECUTOR_SIM", {}).get("status") == "GREEN", caps.get("ATOMIC_EXECUTOR_SIM")
        # SIMULATION_ONCHAIN must stay YELLOW (ran but reverted)
        sim_onchain = caps.get("SIMULATION_ONCHAIN", {})
        assert sim_onchain.get("status") in ("YELLOW", "GREEN"), sim_onchain
        # Per request expectation: YELLOW (not GREEN)
        assert sim_onchain.get("status") == "YELLOW", f"SIMULATION_ONCHAIN should be YELLOW (ran-but-reverted), got {sim_onchain}"
        modes = data.get("modes", {})
        assert modes.get("LIMITED_LIVE", {}).get("can_activate") is False, modes.get("LIMITED_LIVE")
        assert modes.get("FULL_AUTOMATION", {}).get("can_activate") is False, modes.get("FULL_AUTOMATION")

    def test_control_readiness(self, op_session):
        r = op_session.get(f"{BASE_URL}/api/arbicore/control/readiness", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        comps = {c.get("name"): c for c in data.get("components", [])}
        wsig = comps.get("WALLET_SIGNER") or comps.get("SIGNER")
        assert wsig is not None, list(comps.keys())
        assert wsig.get("status") == "GREEN", wsig
        passed_join = " ".join(wsig.get("passed", []) or []).lower()
        # passed[] should mention signer address matches gas wallet
        assert ("match" in passed_join and ("gas" in passed_join or "wallet" in passed_join)) or EXPECTED_ADDR.lower() in json.dumps(wsig).lower(), wsig
        modes = data.get("modes", {})
        assert modes.get("LIMITED_LIVE", {}).get("can_activate") is False, modes.get("LIMITED_LIVE")
        assert (data.get("current_mode") or "").upper() == "SHADOW", data.get("current_mode")
        assert (data.get("overall_status") or "").upper() == "YELLOW", data.get("overall_status")


# --- ATOMIC SIM -----------------------------------------------------------
class TestAtomicSim:
    def test_run_atomic_sim(self, op_session):
        r = op_session.post(f"{BASE_URL}/api/arbicore/engine/run-atomic-sim", timeout=60)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        atomic = data.get("atomic_sim") or data
        assert atomic.get("available") is True, atomic
        # signed/broadcast must be false — no live broadcast
        assert atomic.get("signed") in (False, None), f"signed={atomic.get('signed')}"
        assert atomic.get("broadcast") in (False, None), f"broadcast={atomic.get('broadcast')}"
        # Expected honest revert
        passed = atomic.get("passed")
        reason = (atomic.get("reason") or atomic.get("error") or "").lower()
        assert passed is False, f"Expected passed=False, got {passed} reason={reason}"
        assert "revert" in reason or "executor" in reason, f"reason should mention revert/executor: {reason!r}"
        # No secret leaks
        _scan_leaks(data)

    def test_run_atomic_sim_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/arbicore/engine/run-atomic-sim", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_atomic_sim_status(self, op_session):
        r = op_session.get(f"{BASE_URL}/api/arbicore/engine/atomic-sim-status?refresh=true", timeout=60)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        assert data.get("atomic_sim_ready") is True, data
        readiness = data.get("readiness") or {}
        assert readiness.get("signer_present") is True, readiness
        assert "live_run" in data and data.get("live_run") is not None, data
        _scan_leaks(data)


# --- FORK VALIDATION ------------------------------------------------------
class TestForkValidation:
    def test_run_fork_validation_honest_no_anvil(self, op_session):
        r = op_session.post(f"{BASE_URL}/api/arbicore/engine/run-fork-validation", timeout=30)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        fv = data.get("fork_validation") or data
        assert fv.get("ran") is False, fv
        assert fv.get("passed") is False, fv
        reason = (fv.get("reason") or fv.get("error") or "").lower()
        assert "anvil" in reason and ("not installed" in reason or "not found" in reason or "missing" in reason), \
            f"reason should mention 'anvil binary not installed': {reason!r}"

    def test_run_fork_validation_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/arbicore/engine/run-fork-validation", timeout=15)
        assert r.status_code in (401, 403), r.status_code

    def test_fork_status(self, op_session):
        r = op_session.get(f"{BASE_URL}/api/arbicore/engine/fork-status", timeout=20)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # ready_to_run may be top-level or nested under fork_harness
        harness = data.get("fork_harness") or {}
        ready = data.get("ready_to_run", harness.get("ready_to_run"))
        assert ready is False, data
        assert harness.get("anvil_installed") is False, harness


# --- END-TO-END LEAK SCAN --------------------------------------------------
class TestNoLeaks:
    def test_no_leaks_across_endpoints(self, op_session):
        endpoints = [
            ("GET", "/api/arbicore/engine/settings/signer"),
            ("POST", "/api/arbicore/engine/run-atomic-sim"),
            ("GET", "/api/arbicore/engine/atomic-sim-status?refresh=true"),
            ("GET", "/api/arbicore/engine/readiness-matrix"),
        ]
        for method, path in endpoints:
            r = op_session.request(method, f"{BASE_URL}{path}", timeout=60)
            assert r.status_code == 200, f"{method} {path} -> {r.status_code}"
            body = r.text
            lower = body.lower()
            for tok in LEAK_TOKENS:
                assert tok.lower() not in lower, f"Leak {tok!r} in {method} {path}"
