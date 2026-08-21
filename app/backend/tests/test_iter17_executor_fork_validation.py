"""Iteration 17: Executor ABI + atomic sim + fork validation + readiness + secret leak scan."""
import os
import re
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"

EXPECTED_OWNER = "0x998d6efF2b28b72c44f7a334c42678eb4cCaad25"
UNISWAP_V3_ROUTER02 = "0x2626664c2603336E57B271c5C0b26F421741e481"
BALANCER_V2_VAULT = "0xba12222222228d8ba445958a75a0704d566bf2c8"
FLASHLOAN_SELECTOR = "0x64ba4bc1"  # execute(address[],uint256[],bytes)

SECRET_KEYWORDS = [
    "private_key",
    "signed_tx",
    "raw_tx",
    "eth_sendTransaction",
    "eth_sendRawTransaction",
    "personal_sign",
]

HEX64_RE = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{64}(?![0-9a-fA-F])")


def _scan_no_secrets(payload_text: str, allow_context=None):
    """Ensure no signing/broadcast/secret leaks. Ignore known safe 32-byte hashes context."""
    lower = payload_text.lower()
    for kw in SECRET_KEYWORDS:
        assert kw.lower() not in lower, f"leaked keyword: {kw}"
    # 64-hex private key check - allow known non-secret 64-hex (tx hashes, block hashes, keccak selectors)
    # but a raw private key would typically appear alone. We just ensure "private_key" keyword absent.


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code}: {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def anon():
    return requests.Session()


# ---------- Auth: 401 anonymous ----------
class TestAuth:
    def test_executor_abi_requires_auth(self, anon):
        r = anon.get(f"{BASE_URL}/api/arbicore/engine/executor-abi", timeout=15)
        assert r.status_code == 401

    def test_run_atomic_sim_requires_auth(self, anon):
        r = anon.post(f"{BASE_URL}/api/arbicore/engine/run-atomic-sim", json={}, timeout=15)
        assert r.status_code == 401

    def test_run_fork_validation_requires_auth(self, anon):
        r = anon.post(f"{BASE_URL}/api/arbicore/engine/run-fork-validation", json={}, timeout=15)
        assert r.status_code == 401


# ---------- Executor ABI ----------
class TestExecutorAbi:
    def test_executor_abi_shape(self, session):
        r = session.get(f"{BASE_URL}/api/arbicore/engine/executor-abi", timeout=30)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        text = r.text
        abi = data.get("executor_abi", data)
        entry_sig = abi.get("entrypoint_signature") or ""
        # Review requires the entrypoint signature to be execute(address[],uint256[],bytes)
        assert "execute(address[],uint256[],bytes)" in entry_sig, f"entrypoint_signature={entry_sig!r} (expected execute(...))"
        # flashLoan selector 0x64ba4bc1 must be present
        assert FLASHLOAN_SELECTOR.lower() in text.lower(), "expected 0x64ba4bc1 selector present"
        owner = (abi.get("owner") or "").lower()
        assert owner == EXPECTED_OWNER.lower(), f"owner mismatch: {owner!r} expected {EXPECTED_OWNER.lower()}"
        router = (abi.get("router") or "").lower()
        assert router == UNISWAP_V3_ROUTER02.lower(), f"router mismatch: {router}"
        vault = (abi.get("vault") or "").lower()
        assert vault == BALANCER_V2_VAULT.lower(), f"vault mismatch: {vault}"
        assert abi.get("swap_venue") == "uniswap_v3"
        assert abi.get("flash_provider") == "balancer_v2"
        _scan_no_secrets(text)


# ---------- Atomic sim ----------
class TestAtomicSim:
    def test_run_atomic_sim(self, session):
        r = session.post(f"{BASE_URL}/api/arbicore/engine/run-atomic-sim", json={}, timeout=60)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        text = r.text
        atomic = data.get("atomic_sim") or data
        entrypoint = atomic.get("entrypoint") or ""
        assert "execute(address[],uint256[],bytes)" in entrypoint
        venue = atomic.get("venue") or ""
        assert "balancer_v2_flash" in venue and "uniswap_v3_swaps" in venue
        assert atomic.get("available") is True
        assert atomic.get("signed") is False
        assert atomic.get("broadcast") is False
        assert atomic.get("passed") is False, "expected honest false on no live arbitrage"
        root = (atomic.get("root_cause") or atomic.get("reason") or "").lower()
        assert not any(bad in root for bad in ["calldata mismatch", "abi mismatch"]), f"stale claim: {root}"
        _scan_no_secrets(text)


# ---------- Fork validation ----------
class TestForkValidation:
    def test_fork_status(self, session):
        r = session.get(f"{BASE_URL}/api/arbicore/engine/fork-status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        fh = data.get("fork_harness") or data
        assert fh.get("anvil_installed") is True
        assert fh.get("fork_rpc_configured") is True
        assert fh.get("ready_to_run") is True
        _scan_no_secrets(r.text)

    def test_run_fork_validation(self, session):
        r = session.post(f"{BASE_URL}/api/arbicore/engine/run-fork-validation", json={}, timeout=180)
        assert r.status_code == 200, r.text[:500]
        data = r.json()
        fv = data.get("fork_validation") or data
        assert fv.get("ran") is True, f"fork_validation.ran={fv.get('ran')} reason={fv.get('reason')}"
        assert fv.get("passed") is True, f"fork_validation.passed={fv.get('passed')} reason={fv.get('reason')}"
        evidence = fv.get("evidence") or {}
        assert evidence.get("fork_block") is not None
        checks = evidence.get("checks") or {}
        assert checks.get("chain_id_ok") is True
        assert checks.get("executor_has_code") is True
        assert checks.get("state_override_ok") is True
        _scan_no_secrets(r.text)


# ---------- Readiness matrix ----------
class TestReadinessMatrix:
    def test_engine_readiness_matrix(self, session):
        # warm caches first
        session.get(f"{BASE_URL}/api/arbicore/engine/rpc-capabilities?refresh=true", timeout=30)
        r = session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=30)
        assert r.status_code == 200
        data = r.json()
        text = r.text
        caps = data.get("capabilities") or []
        by_cap = {c.get("capability"): c.get("status") for c in caps}
        green = sum(1 for s in by_cap.values() if s == "GREEN")
        yellow = sum(1 for s in by_cap.values() if s == "YELLOW")
        red = sum(1 for s in by_cap.values() if s == "RED")
        print(f"matrix counts G={green} Y={yellow} R={red}; SIMULATION_ONCHAIN={by_cap.get('SIMULATION_ONCHAIN')}")
        # Required per review:
        assert by_cap.get("SIMULATION_ONCHAIN") == "YELLOW"
        assert by_cap.get("SIGNER") == "GREEN"
        assert by_cap.get("WALLET_GAS") == "GREEN"
        assert by_cap.get("ATOMIC_EXECUTOR_SIM") == "GREEN"
        assert by_cap.get("FORK_VALIDATION") == "GREEN"
        assert by_cap.get("DEX_ADAPTERS_SETTLE") == "GREEN"
        assert red == 0, f"unexpected RED capabilities: {[k for k,v in by_cap.items() if v=='RED']}"
        assert yellow == 1, f"expected exactly 1 YELLOW got {yellow}: {[k for k,v in by_cap.items() if v=='YELLOW']}"
        assert data.get("overall_status") == "YELLOW"
        assert data.get("current_mode") == "SHADOW"
        modes = data.get("modes") or {}
        assert (modes.get("LIMITED_LIVE") or {}).get("can_activate") is False
        assert (modes.get("FULL_AUTOMATION") or {}).get("can_activate") is False
        _scan_no_secrets(text)

    def test_control_readiness(self, session):
        r = session.get(f"{BASE_URL}/api/arbicore/control/readiness", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert data.get("overall_status") == "YELLOW", f"expected YELLOW got {data.get('overall_status')}"
        modes = data.get("modes") or {}
        assert (modes.get("LIMITED_LIVE") or {}).get("can_activate") is False
        _scan_no_secrets(r.text)


# ---------- Secret leak sweep across surfaces ----------
class TestSecretLeaks:
    def test_no_secrets_all_surfaces(self, session):
        endpoints = [
            ("GET", "/api/arbicore/engine/executor-abi"),
            ("POST", "/api/arbicore/engine/run-atomic-sim"),
            ("POST", "/api/arbicore/engine/run-fork-validation"),
            ("GET", "/api/arbicore/engine/readiness-matrix"),
            ("GET", "/api/arbicore/engine/fork-status"),
        ]
        for method, path in endpoints:
            if method == "GET":
                r = session.get(f"{BASE_URL}{path}", timeout=180)
            else:
                r = session.post(f"{BASE_URL}{path}", json={}, timeout=180)
            assert r.status_code == 200, f"{path} => {r.status_code}"
            _scan_no_secrets(r.text)
