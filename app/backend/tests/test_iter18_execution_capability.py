"""Iter18 endpoint suite: execution capability, executor ABI, atomic sim, fork validation, readiness.

Verifies the ArbiCore X final execution-alignment invariants against the live public backend.
"""
import os
import re
import json
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://exec-readiness-x.preview.emergentagent.com").rstrip("/")
USER = "operator"
PASS = "ShadowOperator!2026"

SECRET_RE = re.compile(r"(private_key|signed_tx|raw_tx|eth_sendTransaction|eth_sendRawTransaction|personal_sign)", re.I)
HEX64_RE = re.compile(r"\b(0x)?[0-9a-fA-F]{64}\b")

ALLOWED_HEX64_KEYS = {"tx_hash", "block_hash", "hash", "parent_hash", "state_root", "receipts_root", "transactions_root", "mix_hash", "sha3_uncles", "logs_bloom_hash", "code_hash", "storage_hash", "keccak", "selector_256"}


def _no_secret_leak(payload) -> tuple:
    s = json.dumps(payload)
    m = SECRET_RE.search(s)
    if m:
        return False, f"secret keyword leak: {m.group(0)}"
    # Look for possible 64-hex secrets (skip known hashes/roots which appear as tx_hash etc)
    # We only flag 64-hex tokens if they appear alongside 'key' in the surrounding key name.
    def walk(o, keypath=""):
        if isinstance(o, dict):
            for k, v in o.items():
                kp = f"{keypath}.{k}" if keypath else k
                if isinstance(v, str) and HEX64_RE.fullmatch(v.replace("0x","")):
                    low = k.lower()
                    if "key" in low or "secret" in low or "private" in low:
                        return False, f"64-hex under sensitive key {kp}"
                r = walk(v, kp)
                if r is not None:
                    return r
        elif isinstance(o, list):
            for i, v in enumerate(o):
                r = walk(v, f"{keypath}[{i}]")
                if r is not None:
                    return r
        return None
    r = walk(payload)
    if r:
        return False, r[1]
    return True, "ok"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": USER, "password": PASS}, timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# ---------- Executor ABI ----------

def test_executor_abi(client):
    r = client.get(f"{BASE_URL}/api/arbicore/engine/executor-abi", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    abi = d.get("executor_abi") or d
    print("executor-abi keys:", list(abi.keys()))
    assert abi.get("entrypoint_signature") == "execute(address[],uint256[],bytes)", abi.get("entrypoint_signature")
    assert abi.get("entrypoint_selector") == "0x64ba4bc1", abi.get("entrypoint_selector")
    assert abi.get("userdata_schema"), "userdata_schema missing"
    # Owner may be null on first calls due to public Base RPC rate limits; retry with backoff.
    owner = abi.get("owner")
    for _ in range(6):
        if owner:
            break
        time.sleep(5)
        r2 = client.get(f"{BASE_URL}/api/arbicore/engine/executor-abi", timeout=60)
        abi = (r2.json().get("executor_abi") or r2.json())
        owner = abi.get("owner")
    assert owner and owner.lower() == "0x998d6eff2b28b72c44f7a334c42678eb4ccaad25", owner
    assert abi.get("swap_venue") == "uniswap_v3", abi.get("swap_venue")
    assert abi.get("flash_provider") == "balancer_v2", abi.get("flash_provider")
    ok, why = _no_secret_leak(d)
    assert ok, why


# ---------- Atomic sim ----------

def test_run_atomic_sim(client):
    r = client.post(f"{BASE_URL}/api/arbicore/engine/run-atomic-sim", json={}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    atomic = d.get("atomic_sim") or d
    print("atomic_sim keys:", list(atomic.keys()))
    assert atomic.get("entrypoint") == "execute(address[],uint256[],bytes)", atomic.get("entrypoint")
    venue = (atomic.get("venue") or "").lower()
    assert "uniswap_v3" in venue, atomic.get("venue")
    assert atomic.get("available") is True, atomic
    assert atomic.get("signed") is False, atomic
    assert atomic.get("broadcast") is False, atomic
    assert atomic.get("passed") is False, atomic
    root_cause = (atomic.get("root_cause") or "").lower()
    assert root_cause, "root_cause required"
    ok, why = _no_secret_leak(d)
    assert ok, why


# ---------- Fork validation ----------

def test_run_fork_validation(client):
    r = client.post(f"{BASE_URL}/api/arbicore/engine/run-fork-validation", json={}, timeout=180)
    assert r.status_code == 200, r.text[:400]
    d = r.json()
    fv = d.get("fork_validation") or d
    print("fork_validation keys:", list(fv.keys()))
    assert fv.get("ran") is True, fv
    assert fv.get("passed") is True, fv
    checks = (fv.get("evidence") or {}).get("checks") or fv.get("checks") or {}
    assert checks.get("chain_id_ok") is True, checks
    assert checks.get("executor_has_code") is True, checks
    assert checks.get("state_override_ok") is True, checks


# ---------- Readiness matrix ----------

def test_readiness_matrix(client):
    r = client.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=60)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    print("matrix top-level:", list(d.keys()))
    assert (d.get("overall_status") or d.get("overall") or "").upper() == "YELLOW", d.get("overall_status")
    assert (d.get("current_mode") or "").upper() == "SHADOW", d.get("current_mode")
    caps = d.get("capabilities") or []
    counts = {"GREEN": 0, "YELLOW": 0, "RED": 0}
    by_name = {}
    for c in caps:
        st = (c.get("status") or "").upper()
        nm = c.get("capability") or c.get("name")
        by_name[nm] = st
        counts[st] = counts.get(st, 0) + 1
    print("counts:", counts)
    print("SIMULATION_ONCHAIN:", by_name.get("SIMULATION_ONCHAIN"))
    print("FORK_VALIDATION:", by_name.get("FORK_VALIDATION"))
    print("SIGNER:", by_name.get("SIGNER"), "WALLET_GAS:", by_name.get("WALLET_GAS"), "ATOMIC:", by_name.get("ATOMIC_EXECUTOR_SIM"))
    assert counts.get("GREEN", 0) == 24, counts
    assert counts.get("YELLOW", 0) == 1, counts
    assert counts.get("RED", 0) == 0, counts
    assert by_name.get("SIMULATION_ONCHAIN") == "YELLOW"
    for g in ("FORK_VALIDATION", "SIGNER", "WALLET_GAS", "ATOMIC_EXECUTOR_SIM"):
        assert by_name.get(g) == "GREEN", (g, by_name.get(g))
    modes = d.get("modes") or {}
    assert modes.get("LIMITED_LIVE", {}).get("can_activate") is False, modes.get("LIMITED_LIVE")
    assert modes.get("FULL_AUTOMATION", {}).get("can_activate") is False, modes.get("FULL_AUTOMATION")


def test_control_readiness(client):
    r = client.get(f"{BASE_URL}/api/arbicore/control/readiness", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    print("control readiness keys:", list(d.keys()))
    assert (d.get("overall_status") or d.get("overall") or "").upper() == "YELLOW", d.get("overall_status")
    modes = d.get("modes") or {}
    assert modes.get("LIMITED_LIVE", {}).get("can_activate") is False, modes



# ---------- Execution capability on scan-once ----------

def test_scan_once_execution_capability(client):
    r = client.post(f"{BASE_URL}/api/arbicore/engine/scan-once", json={"limit": 12}, timeout=90)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    opps = d.get("opportunities") or d.get("results") or []
    print(f"received {len(opps)} opps")
    assert isinstance(opps, list)
    # If none returned, the invariants are trivially satisfied, but we should still assert would_execute=False overall
    n_exec_univ3 = 0
    n_non = 0
    any_would_execute_true = False
    for i, o in enumerate(opps):
        cap = o.get("execution_capability")
        venue = o.get("executor_venue")
        assert cap in ("EXECUTABLE_UNIV3", "NON_EXECUTABLE_BY_CURRENT_EXECUTOR"), (i, cap, o.get("dex_path"))
        assert venue, (i, "executor_venue missing")
        dex_path = o.get("dex_path") or o.get("dexes") or []
        # detect non-univ3 dex
        non_univ3 = any(("aerodrome" in (str(x).lower())) or ("slipstream" in str(x).lower()) for x in dex_path)
        mixed_or_aero = non_univ3
        if cap == "EXECUTABLE_UNIV3":
            assert not mixed_or_aero, (i, "non-UniV3 dex but labelled EXECUTABLE_UNIV3", dex_path)
            n_exec_univ3 += 1
        else:
            assert o.get("would_execute") in (False, None), (i, "NON_EXECUTABLE with would_execute true")
            n_non += 1
        if o.get("would_execute") is True:
            any_would_execute_true = True
            # gates must hold
            assert cap == "EXECUTABLE_UNIV3"
            sim = o.get("atomic_simulation") or {}
            assert sim.get("passed") is True, (i, "would_execute true but atomic_simulation not passed")
    print(f"EXECUTABLE_UNIV3={n_exec_univ3} NON_EXECUTABLE={n_non} would_execute_true={any_would_execute_true}")
    # Current honest state: no profitable route
    assert not any_would_execute_true, "market-honest state expects no would_execute=true"
    ok, why = _no_secret_leak(d)
    assert ok, why


# ---------- Anonymous auth check ----------

def test_endpoints_require_auth():
    anon = requests.Session()
    for path, method in [
        ("/api/arbicore/engine/executor-abi", "GET"),
        ("/api/arbicore/engine/run-atomic-sim", "POST"),
        ("/api/arbicore/engine/run-fork-validation", "POST"),
        ("/api/arbicore/engine/scan-once", "POST"),
    ]:
        r = anon.request(method, f"{BASE_URL}{path}", json={} if method == "POST" else None, timeout=15)
        assert r.status_code in (401, 403), (path, r.status_code)
