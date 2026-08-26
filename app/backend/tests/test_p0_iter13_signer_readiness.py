"""Iter13 — Backend integration tests for:
- Secure signer ingest/status/delete endpoints (+ auth, + no leaks, + validation)
- Readiness reconciliation between /control/readiness and /engine/readiness-matrix
- Gas wallet auto-registration
- Modes still locked (LIMITED_LIVE / FULL_AUTOMATION)
- Atomic-sim mandatory gate + scan-once invariants
- Anvil fork validation body (no fake GREEN)
- No signing/broadcast leaks

Runs against live REACT_APP_BACKEND_URL. Leaves vault empty on completion.
"""
import json
import os
import re
import time

import pytest
import requests
from eth_account import Account
from eth_utils import to_checksum_address

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://arbitrum-launch-1.preview.emergentagent.com",
).rstrip("/")
OPERATOR = ("operator", "ShadowOperator!2026")

# Deterministic non-zero test private key (address must NOT equal the gas wallet).
TEST_PK = "0x" + ("11" * 32)
TEST_PK_ADDR = to_checksum_address(Account.from_key(TEST_PK).address)

GAS_WALLET_ADDR = "0x998d6efF2b28b72c44f7a334c42678eb4cCaad25"

LEAK_PATTERNS = [
    r"signed_tx", r"raw_tx", r"eth_sendTransaction",
    r"eth_sendRawTransaction", r"personal_sign",
]


def _no_leaks(payload):
    txt = json.dumps(payload).lower()
    for p in LEAK_PATTERNS:
        assert not re.search(p.lower(), txt), f"leak of {p} in response"
    # Raw private key must NEVER appear in any response body
    pk_bare = TEST_PK[2:].lower()
    assert pk_bare not in txt, "raw private key leaked in response"
    assert TEST_PK.lower() not in txt, "raw 0x-prefixed private key leaked in response"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": OPERATOR[0], "password": OPERATOR[1]}, timeout=30)
    assert r.status_code == 200, f"auth failed: {r.status_code} {r.text[:200]}"
    return s


@pytest.fixture(scope="module", autouse=True)
def _cleanup_vault(auth_session):
    """Ensure vault is empty at start AND at end (post-condition per review)."""
    auth_session.delete(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=30)
    yield
    auth_session.delete(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=30)
    # Final assertion — vault must be empty
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=30)
    assert r.status_code == 200
    assert r.json().get("present") is False, "vault not empty after cleanup"


# ---------------- SIGNER: auth ----------------
def test_signer_endpoints_require_auth():
    for method, payload in [
        ("GET", None),
        ("POST", {"private_key": TEST_PK, "label": "qa"}),
        ("DELETE", None),
    ]:
        r = requests.request(
            method, f"{BASE_URL}/api/arbicore/engine/settings/signer",
            json=payload, timeout=20,
        )
        assert r.status_code == 401, f"{method} anon expected 401, got {r.status_code}"


# ---------------- SIGNER: validation ----------------
@pytest.mark.parametrize("bad", [
    "0xdeadbeef",                 # too short
    "notahexstring" * 5,          # not hex, wrong length
    "0x" + "00" * 32,             # all zero
    "0x" + "gg" * 32,             # non-hex chars
])
def test_signer_malformed_key_returns_422(auth_session, bad):
    r = auth_session.post(
        f"{BASE_URL}/api/arbicore/engine/settings/signer",
        json={"private_key": bad, "label": "qa"}, timeout=30,
    )
    assert r.status_code == 422, f"expected 422 for {bad[:10]}..., got {r.status_code}"


# ---------------- SIGNER: ingest / status / delete ----------------
def test_signer_ingest_status_delete_flow(auth_session):
    # POST ingest
    r = auth_session.post(
        f"{BASE_URL}/api/arbicore/engine/settings/signer",
        json={"private_key": TEST_PK, "label": "qa"}, timeout=30,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert body.get("ok") is True
    assert body.get("derived_address", "").lower() == TEST_PK_ADDR.lower()
    # checksummed?
    assert body["derived_address"] == TEST_PK_ADDR
    assert "matches_expected" in body  # bool or None
    assert isinstance(body["matches_expected"], (bool, type(None)))
    assert body.get("signed") is False
    assert body.get("broadcast") is False
    assert body.get("address_mask")
    _no_leaks(body)

    # GET status
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=30)
    assert r.status_code == 200
    body = r.json()
    assert body.get("present") is True
    assert body.get("derived_address", "").lower() == TEST_PK_ADDR.lower()
    assert "matches_expected" in body
    _no_leaks(body)

    # Ingest a second (different) key → replaces
    alt_pk = "0x" + ("22" * 32)
    alt_addr = to_checksum_address(Account.from_key(alt_pk).address)
    r = auth_session.post(
        f"{BASE_URL}/api/arbicore/engine/settings/signer",
        json={"private_key": alt_pk, "label": "qa2"}, timeout=30,
    )
    assert r.status_code == 200
    assert r.json()["derived_address"].lower() == alt_addr.lower()
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=30)
    assert r.json()["derived_address"].lower() == alt_addr.lower()

    # DELETE
    r = auth_session.delete(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=30)
    assert r.status_code in (200, 204)
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/settings/signer", timeout=30)
    assert r.status_code == 200
    assert r.json().get("present") is False


# ---------------- Gas wallet auto-registration ----------------
def test_gas_wallet_registered(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/execution/wallets", timeout=30)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    wallets = body if isinstance(body, list) else body.get("wallets", body.get("items", []))
    assert isinstance(wallets, list) and wallets, f"no wallets returned: {body}"
    match = [
        w for w in wallets
        if (w.get("address", "").lower() == GAS_WALLET_ADDR.lower())
        or (w.get("wallet_id") == "base-gas-primary")
    ]
    assert match, f"gas wallet not registered: {wallets}"
    w = match[0]
    assert w.get("execution_role", "").lower() == "gas"
    assert w.get("chain", "").lower() == "base"
    assert w.get("wallet_id") == "base-gas-primary"
    assert w.get("address", "").lower() == GAS_WALLET_ADDR.lower()


# ---------------- Readiness reconciliation (vault empty) ----------------
def test_readiness_reconciliation(auth_session):
    ctrl = auth_session.get(f"{BASE_URL}/api/arbicore/control/readiness", timeout=30)
    matrix = auth_session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=30)
    assert ctrl.status_code == 200 and matrix.status_code == 200
    c = ctrl.json()
    m = matrix.json()

    # Overall
    assert c["overall_status"] == "YELLOW", c["overall_status"]
    assert m["overall_status"] == "YELLOW", m["overall_status"]

    # Modes
    assert c["modes"]["LIMITED_LIVE"]["can_activate"] is False
    assert c["modes"]["LIMITED_LIVE"]["status"] == "RED"
    assert c["modes"]["FULL_AUTOMATION"]["can_activate"] is False
    assert m["modes"]["LIMITED_LIVE"]["can_activate"] is False
    assert m["modes"]["FULL_AUTOMATION"]["can_activate"] is False
    assert c.get("current_mode", "SHADOW") == "SHADOW"
    assert m.get("current_mode") == "SHADOW"

    # Control components
    comps = {c_["name"]: c_ for c_ in c["components"]}

    contracts = comps["CONTRACTS"]
    assert contracts["status"] == "GREEN", contracts
    passed_txt = " ".join(contracts.get("passed", [])).lower()
    assert "aerodrome" in passed_txt and (
        "settlement" in passed_txt or "encoder" in passed_txt or "validated" in passed_txt
    ), contracts.get("passed")
    # No "not yet implemented" warning
    warns = " ".join(contracts.get("warnings", [])).lower()
    assert "not yet implemented" not in warns, warns

    wsig = comps["WALLET_SIGNER"]
    assert wsig["status"] == "YELLOW", wsig
    passed_wsig = " ".join(wsig.get("passed", [])).lower()
    assert "gas" in passed_wsig, wsig.get("passed")
    req_wsig = " ".join(wsig.get("requirements", [])).lower()
    assert "signer" in req_wsig, wsig.get("requirements")

    shadow = comps["SHADOW_VALIDATION"]
    assert shadow["status"] in ("GREEN", "YELLOW"), shadow
    passed_sh = " ".join(shadow.get("passed", [])).lower()
    if shadow["status"] == "GREEN":
        assert "20/20" in passed_sh or "pass" in passed_sh, shadow
    else:
        # RUNNING acceptable
        assert "running" in " ".join(shadow.get("warnings", []) + shadow.get("passed", [])).lower()

    # Matrix capabilities
    caps = {x["capability"].upper(): x for x in m["capabilities"]}
    for key in ("WALLET_GAS", "SIGNER", "DEX_ADAPTERS_SETTLE", "EXECUTOR_CONTRACT"):
        assert key in caps, f"missing capability {key}"
    assert caps["WALLET_GAS"]["status"].upper() == "GREEN", caps["WALLET_GAS"]
    assert caps["SIGNER"]["status"].upper() == "YELLOW", caps["SIGNER"]
    assert caps["DEX_ADAPTERS_SETTLE"]["status"].upper() == "GREEN", caps["DEX_ADAPTERS_SETTLE"]
    assert caps["EXECUTOR_CONTRACT"]["status"].upper() == "GREEN", caps["EXECUTOR_CONTRACT"]

    _no_leaks(c)
    _no_leaks(m)


# ---------------- Atomic sim mandatory gate + scan-once ----------------
def test_atomic_sim_status(auth_session):
    body = None
    for i in range(3):
        r = auth_session.get(
            f"{BASE_URL}/api/arbicore/engine/atomic-sim-status",
            params={"refresh": "true" if i == 0 else "false"}, timeout=45,
        )
        assert r.status_code == 200
        body = r.json()
        if body.get("code_injection_verified") is True:
            break
        time.sleep(6)
    assert body["code_injection_verified"] is True, body
    rd = body["readiness"]
    assert rd["executor_address_set"] is True
    assert rd["executor_bytecode_available"] is False
    assert body["atomic_sim_ready"] is False
    _no_leaks(body)


def test_scan_once_atomic_and_settlement_fields(auth_session):
    r = auth_session.post(
        f"{BASE_URL}/api/arbicore/engine/scan-once",
        json={"limit": 6}, timeout=120,
    )
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    opps = body.get("opportunities") or body.get("results") or body.get("items") or []
    # Empty is acceptable ("no arb"), but if returned each must carry both fields
    for o in opps:
        assert "settlement_simulation" in o, list(o.keys())
        assert "atomic_simulation" in o, list(o.keys())
        assert o.get("would_execute") is False
        if o.get("would_execute") is True:
            assert o["settlement_simulation"].get("passed") is True
            assert o["atomic_simulation"].get("passed") is True
    _no_leaks(body)


# ---------------- Anvil fork body ----------------
def test_fork_status_body(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/fork-status", timeout=30)
    assert r.status_code == 200
    body = r.json()
    fh = body["fork_harness"]
    assert fh["ready_to_run"] is False
    reason = (fh.get("reason") or "").lower()
    assert "anvil" in reason, fh
    _no_leaks(body)


def test_run_fork_validation_no_fake_green(auth_session):
    r = auth_session.post(
        f"{BASE_URL}/api/arbicore/engine/run-fork-validation", json={}, timeout=60,
    )
    assert r.status_code in (200, 202), r.text[:300]
    body = r.json()
    fv = body.get("fork_validation") or body
    assert fv.get("ran") is False, fv
    assert fv.get("passed") is False, fv
    reason = (fv.get("reason") or "").lower()
    assert "anvil" in reason, fv
    _no_leaks(body)


# ---------------- Readiness responses: no private-key leaks ----------------
def test_readiness_responses_no_leaks(auth_session):
    for path in (
        "/api/arbicore/engine/scanner-status",
        "/api/arbicore/control/readiness",
        "/api/arbicore/engine/readiness-matrix",
    ):
        r = auth_session.get(f"{BASE_URL}{path}", timeout=30)
        if r.status_code == 200:
            _no_leaks(r.json())
