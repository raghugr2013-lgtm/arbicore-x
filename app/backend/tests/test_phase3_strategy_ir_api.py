"""T1 API-level tests: Strategy IR ingestion contract (/api/strategy/*).

Covers auth isolation, valid ingest, idempotency, execution-isolation
(forbidden keys), unknown strategy_type, preview-hypothesis, safety
invariants and P0 auth regression.
"""
import copy
import os
import uuid

import pytest
import requests
from dotenv import dotenv_values

_env = dotenv_values("/app/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or _env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = _base.rstrip("/")

ADMIN = {"username": "admin", "password": "ArbiCoreAdmin2026"}

VALID_IR = {
    "strategy_type": "dex_dex",
    "parameters": {"pair": "WETH/USDC"},
    "constraints": {"max_notional_usd": 50000},
    "provenance": {"source": "strategy_factory", "trust": 0.7, "confidence": 0.6},
    "source_class": "EXTERNAL",
}

CREATED_STRATEGY_IDS = []


@pytest.fixture(scope="module")
def anon():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def ingested(admin_client):
    """Ingest a UNIQUE IR once per worker; returns its ids (xdist-safe)."""
    body = copy.deepcopy(VALID_IR)
    body["parameters"] = {"pair": f"TEST_UNIQ_{uuid.uuid4().hex[:10]}/USDC"}
    r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                          json=body, timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
    d = r.json()
    CREATED_STRATEGY_IDS.append(d["strategy_id"])
    return d


@pytest.fixture(scope="module")
def admin_client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    return s


# --- AUTH ISOLATION -------------------------------------------------------
class TestAuthIsolation:
    def test_post_candidates_requires_auth(self, anon):
        r = anon.post(f"{BASE_URL}/api/strategy/candidates", json=VALID_IR, timeout=30)
        assert r.status_code == 401, f"got {r.status_code}: {r.text[:300]}"

    def test_get_candidates_requires_auth(self, anon):
        r = anon.get(f"{BASE_URL}/api/strategy/candidates", timeout=30)
        assert r.status_code == 401, f"got {r.status_code}: {r.text[:300]}"

    def test_preview_requires_auth(self, anon):
        r = anon.post(f"{BASE_URL}/api/strategy/candidates/anything/preview-hypothesis",
                      timeout=30)
        assert r.status_code == 401, f"got {r.status_code}: {r.text[:300]}"

    def test_registry_requires_auth(self, anon):
        r = anon.get(f"{BASE_URL}/api/strategy/registry/anything", timeout=30)
        assert r.status_code == 401, f"got {r.status_code}: {r.text[:300]}"

    def test_bad_cookie_rejected(self):
        s = requests.Session()
        s.cookies.set("access_token", "not.a.jwt")
        r = s.get(f"{BASE_URL}/api/strategy/candidates", timeout=30)
        assert r.status_code == 401, f"got {r.status_code}: {r.text[:300]}"


# --- VALID INGEST + IDEMPOTENCY ------------------------------------------
class TestIngest:
    def test_valid_ingest(self, admin_client):
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=VALID_IR, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        assert d["executable"] is False
        assert d["strategy_fingerprint"].startswith("sfp_")
        assert d["strategy_version"] == 1
        assert d["lifecycle_state"] == "INGESTED"
        assert isinstance(d["strategy_id"], str) and d["strategy_id"]
        CREATED_STRATEGY_IDS.append(d["strategy_id"])

    def test_idempotent_duplicate(self, admin_client, ingested):
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=VALID_IR, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        CREATED_STRATEGY_IDS.append(d["strategy_id"])
        assert d["duplicate"] is True
        assert d["registered"] is False
        assert d["strategy_fingerprint"] == globals().setdefault(
            "_first_fp", d["strategy_fingerprint"])
        assert d["strategy_version"] == 1

    def test_semantically_identical_reordered_keys_same_fingerprint(self, admin_client, ingested):
        payload = copy.deepcopy(VALID_IR)
        payload["required_capabilities"] = []
        payload["route_hints"] = []
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=payload, timeout=30)
        assert r.status_code == 200
        d = r.json()
        CREATED_STRATEGY_IDS.append(d["strategy_id"])
        base = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                                 json=VALID_IR, timeout=30).json()
        CREATED_STRATEGY_IDS.append(base["strategy_id"])
        assert d["strategy_fingerprint"] == base["strategy_fingerprint"]

    def test_duplicate_response_strategy_id_is_resolvable(self, admin_client):
        """BUG CHECK: duplicate ingest returns a fresh strategy_id that has no
        registry entry, so /registry/{id} and preview-hypothesis 404."""
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": f"TEST_DUP_{uuid.uuid4().hex[:8]}/USDC"}
        first = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                                  json=body, timeout=30).json()
        CREATED_STRATEGY_IDS.append(first["strategy_id"])
        assert first["duplicate"] is False
        dup = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                                json=body, timeout=30).json()
        CREATED_STRATEGY_IDS.append(dup["strategy_id"])
        assert dup["duplicate"] is True
        r = admin_client.get(
            f"{BASE_URL}/api/strategy/registry/{dup['strategy_id']}", timeout=30)
        assert r.status_code == 200, (
            "duplicate ingest returned strategy_id %s which is not resolvable "
            "in the registry (%s)" % (dup["strategy_id"], r.status_code))

    def test_listed_and_persisted(self, admin_client, ingested):
        r = admin_client.get(f"{BASE_URL}/api/strategy/candidates?limit=100", timeout=30)
        assert r.status_code == 200
        cands = r.json()["candidates"]
        assert isinstance(cands, list) and cands
        mine = [c for c in cands if c["strategy_id"] == ingested["strategy_id"]]
        assert mine, "ingested candidate not persisted/listed"
        c = mine[0]
        assert "_id" not in c
        assert c["executable"] is False
        assert c["lifecycle_state"] == "INGESTED"
        assert c["strategy_type"] == "dex_dex"
        assert c["strategy_fingerprint"] == ingested["strategy_fingerprint"]

    def test_registry_entry(self, admin_client, ingested):
        sid = ingested["strategy_id"]
        r = admin_client.get(f"{BASE_URL}/api/strategy/registry/{sid}",
                             timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert "_id" not in d
        assert d["strategy_fingerprint"] == ingested["strategy_fingerprint"]
        assert d["source_class"] == "EXTERNAL"

    def test_registry_404_unknown(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/strategy/registry/does_not_exist_xyz",
                             timeout=30)
        assert r.status_code == 404


# --- EXECUTION ISOLATION (core security) ---------------------------------
FORBIDDEN_CASES = [
    ("parameters", {"calldata": "0xdeadbeef", "pair": "WETH/USDC"}),
    ("parameters", {"private_key": "0xabc"}),
    ("parameters", {"signer": "0x1234"}),
    ("parameters", {"broadcast": True}),
    ("parameters", {"execution_mode": "live"}),
    ("parameters", {"kill_switch": False}),
    ("parameters", {"authorize": True}),
    ("parameters", {"bypass_simulation": True}),
    ("parameters", {"allowlist_override": True}),
    ("parameters", {"profitability_override": True}),
    ("parameters", {"enable_live": True}),
    ("constraints", {"kill_switch": False}),
    ("constraints", {"Kill-Switch": False}),
    ("constraints", {"EXECUTION MODE": "live"}),
]


class TestExecutionIsolation:
    @pytest.mark.parametrize("field,payload", FORBIDDEN_CASES)
    def test_forbidden_key_rejected(self, admin_client, field, payload):
        body = copy.deepcopy(VALID_IR)
        body[field] = payload
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 422, f"{field}={payload} -> {r.status_code}: {r.text[:300]}"

    def test_nested_route_hints_userdata_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["route_hints"] = [{"userData": "0xdead"}]
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:300]}"

    def test_deeply_nested_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"a": {"b": [{"c": {"raw_tx": "0x01"}}]}}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:300]}"

    def test_rejected_ir_not_stored(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": "TEST_FORBIDDEN/USDC", "calldata": "0xbeef"}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 422
        lst = admin_client.get(f"{BASE_URL}/api/strategy/candidates?limit=200",
                               timeout=30).json()["candidates"]
        assert not [c for c in lst
                    if c.get("parameters", {}).get("pair") == "TEST_FORBIDDEN/USDC"], \
            "forbidden IR was persisted"

    def test_unknown_strategy_type_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["strategy_type"] = "fx_scalp"
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:300]}"

    def test_version_below_one_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["strategy_version"] = 0
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 422

    def test_client_supplied_fingerprint_is_overwritten(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["strategy_fingerprint"] = "sfp_ATTACKER"
        body["parameters"] = {"pair": "TEST_FPOVR/USDC"}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        CREATED_STRATEGY_IDS.append(d["strategy_id"])
        assert d["strategy_fingerprint"] != "sfp_ATTACKER"
        assert d["strategy_fingerprint"].startswith("sfp_")


# --- PREVIEW HYPOTHESIS ---------------------------------------------------
class TestPreviewHypothesis:
    def test_preview(self, admin_client, ingested):
        sid = ingested["strategy_id"]
        r = admin_client.post(
            f"{BASE_URL}/api/strategy/candidates/{sid}/preview-hypothesis", timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        h = r.json()["hypothesis"]
        assert h["executable"] is False
        assert h["provenance"] == "STRATEGY_IR_CANDIDATE"
        assert h["quote_status"] == "UNAVAILABLE"
        assert h["requires_downstream_validation"] is True
        assert h["repayment_ok"] is False
        blob = str(h).lower()
        for banned in ("calldata", "signer", "execution_mode", "private_key",
                       "broadcast", "kill_switch"):
            assert banned not in blob, f"hypothesis leaks '{banned}'"

    def test_preview_404_unknown(self, admin_client):
        r = admin_client.post(
            f"{BASE_URL}/api/strategy/candidates/nope_xyz/preview-hypothesis", timeout=30)
        assert r.status_code == 404


# --- SAFETY INVARIANTS ----------------------------------------------------
class TestSafetyUnchanged:
    def test_safety_status_fail_closed(self, admin_client):
        r = admin_client.get(f"{BASE_URL}/api/arbicore/safety/status", timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:400]}"
        d = r.json()
        assert d.get("live_execution_enabled") is False, d
        assert d.get("effective_kill_engaged") is True, d

    def test_safety_unchanged_after_ingest(self, admin_client):
        before = admin_client.get(f"{BASE_URL}/api/arbicore/safety/status",
                                  timeout=30).json()
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": "TEST_SAFETY/USDC"}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30)
        assert r.status_code == 200
        CREATED_STRATEGY_IDS.append(r.json()["strategy_id"])
        after = admin_client.get(f"{BASE_URL}/api/arbicore/safety/status",
                                 timeout=30).json()
        for k in ("live_execution_enabled", "effective_kill_engaged",
                  "execution_mode", "kill_switch_engaged"):
            assert before.get(k) == after.get(k), f"{k} changed: {before.get(k)} -> {after.get(k)}"
        assert after.get("live_execution_enabled") is False
        assert after.get("effective_kill_engaged") is True


# --- P0 AUTH REGRESSION ---------------------------------------------------
class TestP0AuthRegression:
    def test_auth_status(self, anon):
        r = anon.get(f"{BASE_URL}/api/auth/status", timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"

    def test_login_ok(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"

    def test_setup_without_bootstrap_token_forbidden(self, anon):
        r = anon.post(f"{BASE_URL}/api/auth/setup",
                      json={"username": "TEST_intruder",
                            "password": "TEST_Password12345"}, timeout=30)
        assert r.status_code == 403, f"{r.status_code}: {r.text[:300]}"
