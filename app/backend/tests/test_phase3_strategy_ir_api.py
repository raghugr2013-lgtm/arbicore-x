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
    "provenance": {"source": "strategy_factory",
                   "source_ref": "https://example.org/research/dex-dex-note",
                   "trust": 0.7, "confidence": 0.6},
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


# --- ITERATION 6: FIX VERIFICATION ---------------------------------------
# Module: arbicore/strategy_ir/registry.py (duplicate identity + dedup upsert)
#         arbicore/strategy_ir/schema.py   (extra='forbid', size caps, cap values)
def _mongo_candidates():
    """Direct DB access to assert dedup (one candidate row per fingerprint)."""
    from pymongo import MongoClient
    benv = dotenv_values("/app/app/backend/.env")
    url = os.environ.get("MONGO_URL") or benv.get("MONGO_URL")
    name = os.environ.get("DB_NAME") or benv.get("DB_NAME")
    assert url and name, "MONGO_URL/DB_NAME missing"
    return MongoClient(url)[name]["strategy_candidates"]


def _mongo_registry():
    from pymongo import MongoClient
    benv = dotenv_values("/app/app/backend/.env")
    url = os.environ.get("MONGO_URL") or benv.get("MONGO_URL")
    name = os.environ.get("DB_NAME") or benv.get("DB_NAME")
    assert url and name, "MONGO_URL/DB_NAME missing"
    return MongoClient(url)[name]["strategy_registry"]


class TestDuplicateIdentityFixed:
    def test_duplicate_strategy_id_equals_first_and_resolves(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": f"TEST_IDFIX_{uuid.uuid4().hex[:8]}/USDC"}
        r1 = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r1.status_code == 200, r1.text[:300]
        a = r1.json()
        CREATED_STRATEGY_IDS.append(a["strategy_id"])
        assert a["duplicate"] is False and a["registered"] is True

        r2 = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r2.status_code == 200, r2.text[:300]
        b = r2.json()
        assert b["duplicate"] is True, b
        assert b["registered"] is False, b
        assert b["strategy_id"] == a["strategy_id"], (
            f"duplicate returned {b['strategy_id']} != canonical {a['strategy_id']}")
        assert b["strategy_fingerprint"] == a["strategy_fingerprint"]

        reg = admin_client.get(f"{BASE_URL}/api/strategy/registry/{a['strategy_id']}", timeout=30)
        assert reg.status_code == 200, f"registry {reg.status_code}: {reg.text[:300]}"
        assert reg.json()["strategy_fingerprint"] == a["strategy_fingerprint"]

        prev = admin_client.post(
            f"{BASE_URL}/api/strategy/candidates/{a['strategy_id']}/preview-hypothesis",
            timeout=30)
        assert prev.status_code == 200, f"preview {prev.status_code}: {prev.text[:300]}"
        assert prev.json()["hypothesis"]["executable"] is False

    def test_dedup_single_candidate_row_with_ingest_count(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": f"TEST_DEDUP_{uuid.uuid4().hex[:8]}/USDC"}
        fps = set()
        for _ in range(4):
            r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
            assert r.status_code == 200, r.text[:300]
            d = r.json()
            fps.add(d["strategy_fingerprint"])
            CREATED_STRATEGY_IDS.append(d["strategy_id"])
        assert len(fps) == 1
        fp = fps.pop()
        col = _mongo_candidates()
        docs = list(col.find({"strategy_fingerprint": fp, "strategy_version": 1}))
        assert len(docs) == 1, f"expected 1 candidate doc, got {len(docs)}"
        assert docs[0].get("ingest_count") == 4, docs[0].get("ingest_count")
        assert docs[0].get("executable") is False
        assert docs[0].get("lifecycle_state") == "INGESTED"

        # one more ingest increments the counter, still one row
        admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        docs = list(col.find({"strategy_fingerprint": fp, "strategy_version": 1}))
        assert len(docs) == 1
        assert docs[0].get("ingest_count") == 5, docs[0].get("ingest_count")


EXTRA_FORBID_CASES = [
    ("executable", True),
    ("lifecycle_state", "APPROVED"),
    ("calldata", "0xdeadbeef"),
    ("signer", "0x1111111111111111111111111111111111111111"),
    ("execution_mode", "live"),
    ("kill_switch", False),
    ("ingest_count", 999),
    ("unknown_random_field", "x"),
]


class TestExtraForbidHardening:
    @pytest.mark.parametrize("key,value", EXTRA_FORBID_CASES)
    def test_root_level_extra_field_rejected(self, admin_client, key, value):
        body = copy.deepcopy(VALID_IR)
        body[key] = value
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 422, f"root {key} -> {r.status_code}: {r.text[:300]}"

    def test_provenance_extra_field_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["provenance"] = {"source": "x", "signer": "0xabc"}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:300]}"


class TestForbiddenTokenAsValue:
    @pytest.mark.parametrize("cap", ["signer", "calldata", "private_key",
                                     "Kill-Switch", "EXECUTION MODE"])
    def test_forbidden_capability_value_rejected(self, admin_client, cap):
        body = copy.deepcopy(VALID_IR)
        body["required_capabilities"] = ["flash_loan", cap]
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 422, f"cap={cap} -> {r.status_code}: {r.text[:300]}"

    def test_benign_capability_accepted(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["required_capabilities"] = ["flash_loan", "dex_quote"]
        body["parameters"] = {"pair": f"TEST_CAPOK_{uuid.uuid4().hex[:8]}/USDC"}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        CREATED_STRATEGY_IDS.append(r.json()["strategy_id"])


class TestSizeCaps:
    def test_oversized_parameter_value_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"blob": "A" * 300_000}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:200]}"

    def test_too_many_parameter_keys_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {f"k{i}": i for i in range(250)}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:200]}"

    def test_too_many_route_hints_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["route_hints"] = [{"dex": f"d{i}"} for i in range(150)]
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:200]}"

    def test_too_many_constraint_keys_rejected(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["constraints"] = {f"c{i}": i for i in range(250)}
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 422, f"{r.status_code}: {r.text[:200]}"

    def test_within_caps_accepted(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": f"TEST_CAPS_{uuid.uuid4().hex[:8]}/USDC",
                              **{f"k{i}": i for i in range(50)}}
        body["route_hints"] = [{"dex": f"d{i}"} for i in range(20)]
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates", json=body, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        CREATED_STRATEGY_IDS.append(r.json()["strategy_id"])


class TestStrategyIdIntegrity:
    """iteration_7 FIX VERIFICATION: strategy_id is SERVER-DERIVED from
    (fingerprint, version) as 'sid_<sha256[:32]>' and a client-supplied
    strategy_id is IGNORED, so identity can never be hijacked/spoofed."""

    def test_client_cannot_hijack_existing_strategy_id(self, admin_client):
        victim = copy.deepcopy(VALID_IR)
        victim["parameters"] = {"pair": f"TEST_VICTIM_{uuid.uuid4().hex[:8]}/USDC"}
        v = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=victim, timeout=30).json()
        CREATED_STRATEGY_IDS.append(v["strategy_id"])

        attacker = copy.deepcopy(VALID_IR)
        attacker["parameters"] = {"pair": f"TEST_ATTACK_{uuid.uuid4().hex[:8]}/USDC"}
        attacker["strategy_id"] = v["strategy_id"]
        r = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=attacker, timeout=30)
        assert r.status_code == 200, r.text[:300]
        a = r.json()
        CREATED_STRATEGY_IDS.append(a["strategy_id"])
        assert a["strategy_fingerprint"] != v["strategy_fingerprint"]
        assert a["strategy_id"] != v["strategy_id"], (
            "client-supplied strategy_id was honoured: two different strategies "
            f"now share id {v['strategy_id']} — identity is ambiguous")
        assert a["strategy_id"].startswith("sid_"), a["strategy_id"]

    def test_spoofed_id_ignored_for_two_different_irs(self, admin_client):
        """Both IRs carry the SAME client strategy_id 'spoof-123' but differ
        semantically -> two DISTINCT server-derived sid_ ids; 'spoof-123' is
        never persisted."""
        spoof = f"spoof-123-{uuid.uuid4().hex[:6]}"
        a_body = copy.deepcopy(VALID_IR)
        a_body["strategy_type"] = "dex_dex"
        a_body["parameters"] = {"pair": f"TEST_SPOOFA_{uuid.uuid4().hex[:8]}/USDC"}
        a_body["strategy_id"] = spoof

        b_body = copy.deepcopy(VALID_IR)
        b_body["strategy_type"] = "triangular"
        b_body["parameters"] = {"legs": 3,
                                "pair": f"TEST_SPOOFB_{uuid.uuid4().hex[:8]}/USDC"}
        b_body["strategy_id"] = spoof

        ra = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                               json=a_body, timeout=30)
        rb = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                               json=b_body, timeout=30)
        assert ra.status_code == 200, ra.text[:300]
        assert rb.status_code == 200, rb.text[:300]
        a, b = ra.json(), rb.json()
        CREATED_STRATEGY_IDS.extend([a["strategy_id"], b["strategy_id"]])

        assert a["strategy_fingerprint"] != b["strategy_fingerprint"]
        assert a["strategy_id"] != b["strategy_id"], "spoofed id collapsed identity"
        for d in (a, b):
            assert d["strategy_id"].startswith("sid_"), d["strategy_id"]
            assert d["strategy_id"] != spoof
            assert len(d["strategy_id"]) == 36, d["strategy_id"]

        reg = _mongo_registry()
        assert reg.count_documents({"strategy_id": spoof}) == 0
        assert _mongo_candidates().count_documents({"strategy_id": spoof}) == 0
        # both derived ids resolve, independently
        for d in (a, b):
            g = admin_client.get(f"{BASE_URL}/api/strategy/registry/{d['strategy_id']}",
                                 timeout=30)
            assert g.status_code == 200, g.text[:200]
            assert g.json()["strategy_fingerprint"] == d["strategy_fingerprint"]

    def test_derived_id_is_deterministic_function_of_fingerprint(self, admin_client):
        """sid == 'sid_' + sha256('<fp>:<ver>')[:32] — server-authoritative."""
        import hashlib
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": f"TEST_DERIV_{uuid.uuid4().hex[:8]}/USDC"}
        body["strategy_id"] = "client-junk-id"
        d = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                              json=body, timeout=30).json()
        CREATED_STRATEGY_IDS.append(d["strategy_id"])
        expected = "sid_" + hashlib.sha256(
            f"{d['strategy_fingerprint']}:{d['strategy_version']}".encode()
        ).hexdigest()[:32]
        assert d["strategy_id"] == expected, (d["strategy_id"], expected)


class TestCanonicalIdempotency:
    """Same semantic IR twice -> same derived id, duplicate on 2nd, exactly one
    registry doc and one candidate row with incrementing ingest_count."""

    def test_same_ir_twice_same_derived_id_and_single_docs(self, admin_client):
        body = copy.deepcopy(VALID_IR)
        body["parameters"] = {"pair": f"TEST_CANON_{uuid.uuid4().hex[:8]}/USDC"}
        body["strategy_id"] = "ignored-1"
        first = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                                  json=body, timeout=30).json()
        CREATED_STRATEGY_IDS.append(first["strategy_id"])
        assert first["duplicate"] is False and first["registered"] is True

        body2 = copy.deepcopy(body)
        body2["strategy_id"] = "ignored-2-different"
        second = admin_client.post(f"{BASE_URL}/api/strategy/candidates",
                                   json=body2, timeout=30).json()
        assert second["duplicate"] is True, second
        assert second["registered"] is False, second
        assert second["strategy_id"] == first["strategy_id"]

        sid, fp = first["strategy_id"], first["strategy_fingerprint"]
        reg, cand = _mongo_registry(), _mongo_candidates()
        assert reg.count_documents({"strategy_fingerprint": fp,
                                    "strategy_version": 1}) == 1
        assert reg.count_documents({"strategy_id": sid}) == 1
        cdocs = list(cand.find({"strategy_fingerprint": fp, "strategy_version": 1}))
        assert len(cdocs) == 1, len(cdocs)
        assert cdocs[0]["ingest_count"] == 2, cdocs[0]["ingest_count"]
        assert cdocs[0]["strategy_id"] == sid

        assert admin_client.get(f"{BASE_URL}/api/strategy/registry/{sid}",
                                timeout=30).status_code == 200
        prev = admin_client.post(
            f"{BASE_URL}/api/strategy/candidates/{sid}/preview-hypothesis", timeout=30)
        assert prev.status_code == 200, prev.text[:300]
        assert prev.json()["hypothesis"]["executable"] is False
