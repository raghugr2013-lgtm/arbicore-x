"""Live HTTP tests for v2.11.9 Shadow Certification endpoints.

Uses the public REACT_APP_BACKEND_URL and admin session cookie.
Also verifies Mongo persistence (arbicore_shadow_certifications collection).
"""
from __future__ import annotations

import os
import time
from typing import Optional

import pytest
import requests
from pymongo import MongoClient

# Load frontend/.env to pick up REACT_APP_BACKEND_URL when pytest is run standalone
if not os.environ.get("REACT_APP_BACKEND_URL"):
    try:
        with open("/app/frontend/.env") as _f:
            for _line in _f:
                if _line.startswith("REACT_APP_BACKEND_URL="):
                    os.environ["REACT_APP_BACKEND_URL"] = _line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_USER = "admin"
ADMIN_PASS = "testtest123"

CERT_COLL = "arbicore_shadow_certifications"


def _unwrap(body):
    """API envelope: {'run': {...}, 'generated_at': ...} → return the run dict."""
    if isinstance(body, dict) and "run" in body and isinstance(body["run"], dict):
        return body["run"]
    return body


# --------------------------------------------------------------------------- fixtures
@pytest.fixture(scope="module")
def anon_client() -> requests.Session:
    return requests.Session()


@pytest.fixture(scope="module")
def admin_client() -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    # cookie stored in session
    return s


@pytest.fixture(scope="module")
def mongo_coll():
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "arbicore_x_hotfix_test")
    client = MongoClient(mongo_url, serverSelectionTimeoutMS=3000)
    return client[db_name][CERT_COLL]


@pytest.fixture(scope="module", autouse=True)
def ensure_no_active_run(admin_client):
    """Clean any leftover RUNNING run before starting."""
    try:
        r = admin_client.get(f"{API}/arbicore/certification/shadow/current", timeout=10)
        if r.status_code == 200 and (r.json() or {}).get("current"):
            admin_client.post(
                f"{API}/arbicore/certification/shadow/stop",
                json={"reason": "pretest-cleanup"},
                timeout=10,
            )
    except Exception:
        pass
    yield


# --------------------------------------------------------------------------- auth gating
SHADOW_ENDPOINTS_GET = [
    "/arbicore/certification/shadow/thresholds",
    "/arbicore/certification/shadow/current",
    "/arbicore/certification/shadow/runs",
]
SHADOW_ENDPOINTS_POST = [
    ("/arbicore/certification/shadow/start", {"target_cycles": 3}),
    ("/arbicore/certification/shadow/stop", {"reason": "x"}),
    ("/arbicore/certification/shadow/tick", {}),
]


@pytest.mark.parametrize("path", SHADOW_ENDPOINTS_GET)
def test_auth_gating_get_unauth(anon_client, path):
    r = anon_client.get(f"{API}{path}", timeout=10)
    assert r.status_code == 401, f"{path} expected 401 got {r.status_code} body={r.text[:200]}"


@pytest.mark.parametrize("path,body", SHADOW_ENDPOINTS_POST)
def test_auth_gating_post_unauth(anon_client, path, body):
    r = anon_client.post(f"{API}{path}", json=body, timeout=10)
    assert r.status_code == 401


def test_auth_gating_runs_by_id_unauth(anon_client):
    r = anon_client.get(f"{API}/arbicore/certification/shadow/runs/nonexistent", timeout=10)
    assert r.status_code == 401


# --------------------------------------------------------------------------- thresholds
def test_thresholds_shape(admin_client):
    r = admin_client.get(f"{API}/arbicore/certification/shadow/thresholds", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "thresholds" in data
    assert "generated_at" in data and isinstance(data["generated_at"], str)
    th = data["thresholds"]
    required = {
        "target_cycles", "min_executable_rate_pass", "min_executable_rate_warn",
        "max_stage_p95_ms", "max_infra_exception_rate", "max_fail_cycles",
        "max_warn_cycles", "min_opps_per_cycle",
    }
    missing = required - set(th.keys())
    assert not missing, f"missing threshold keys: {missing}"


# --------------------------------------------------------------------------- current when idle
def test_current_null_when_no_run(admin_client):
    # first make sure no active run
    cur = admin_client.get(f"{API}/arbicore/certification/shadow/current", timeout=10).json()
    if cur.get("current"):
        admin_client.post(
            f"{API}/arbicore/certification/shadow/stop",
            json={"reason": "idle-precheck"},
            timeout=10,
        )
    r = admin_client.get(f"{API}/arbicore/certification/shadow/current", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("current") is None
    assert "generated_at" in data


# --------------------------------------------------------------------------- start / duplicate / tick / finalise
def test_full_lifecycle_start_tick_finalise(admin_client, mongo_coll):
    # Start with target_cycles=3
    r = admin_client.post(
        f"{API}/arbicore/certification/shadow/start",
        json={"target_cycles": 3},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    run = _unwrap(r.json())
    assert run["status"] == "RUNNING"
    assert run["target_cycles"] == 3
    assert run["cycles_completed"] == 0
    assert run["schema_version"] == "shadow_cert_v1"
    assert isinstance(run["cycles"], list) and run["cycles"] == []
    assert run["pass_reasons"] == []
    assert run["warning_reasons"] == []
    assert run["fail_reasons"] == []
    assert "thresholds" in run and "target_cycles" in run["thresholds"]
    run_id = run["run_id"]

    # Duplicate start -> 409
    r2 = admin_client.post(
        f"{API}/arbicore/certification/shadow/start",
        json={"target_cycles": 3},
        timeout=10,
    )
    assert r2.status_code == 409
    detail = (r2.json() or {}).get("detail", "")
    assert "already active" in str(detail).lower()

    # 3 ticks
    last = None
    for i in range(1, 4):
        rt = admin_client.post(
            f"{API}/arbicore/certification/shadow/tick", json={}, timeout=30,
        )
        assert rt.status_code == 200, rt.text
        last = _unwrap(rt.json())
        # tick returns updated run
        assert last["run_id"] == run_id
        # cycles_completed should equal i (unless already finalised at i==3)
        assert last["cycles_completed"] == i, (
            f"tick {i}: expected cycles_completed={i} got {last['cycles_completed']}"
        )
        # inspect newest cycle
        cyc = last["cycles"][-1]
        for k in ("cycle_id", "cycle_index", "started_at", "completed_at", "duration_ms", "cycle_status"):
            assert k in cyc, f"cycle missing key {k}"
        assert cyc["cycle_status"] in {"PASS", "WARNING", "FAIL"}
        infra = cyc.get("infra_health") or {}
        assert "mongo_ok" in infra and "runner_ok" in infra
        assert isinstance(infra["mongo_ok"], bool)
        assert isinstance(infra["runner_ok"], bool)

    # After 3rd tick, auto-finalised
    assert last is not None
    assert last["status"] in {"PASS", "WARNING", "FAIL"}, f"expected terminal, got {last['status']}"
    assert last["completed_at"] and isinstance(last["completed_at"], str)
    summary = last.get("summary") or {}
    expected_summary_keys = {
        "opportunities_seen", "opportunities_processed", "executable_count",
        "executable_rate", "outcome_counts", "worst_stage_p95_ms",
        "total_runner_exceptions", "exception_rate",
        "cycles_pass", "cycles_warn", "cycles_fail", "infra_healthy",
    }
    missing = expected_summary_keys - set(summary.keys())
    assert not missing, f"summary missing keys: {missing}"

    # Mongo persistence
    doc = mongo_coll.find_one({"run_id": run_id})
    assert doc is not None
    assert doc.get("schema_version") == "shadow_cert_v1"


# --------------------------------------------------------------------------- runs list / filter / limit / by id
def test_runs_list_and_by_id(admin_client):
    r = admin_client.get(f"{API}/arbicore/certification/shadow/runs", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data and "count" in data
    assert data["count"] == len(data["items"])
    if data["items"]:
        # newest first — started_at descending
        starts = [it.get("started_at") for it in data["items"]]
        assert starts == sorted(starts, reverse=True)

        first = data["items"][0]
        for k in ("run_id", "status", "target_cycles", "cycles_completed", "thresholds", "cycles"):
            assert k in first, f"report missing {k}"
        run_id = first["run_id"]

        # by id
        r2 = admin_client.get(f"{API}/arbicore/certification/shadow/runs/{run_id}", timeout=10)
        assert r2.status_code == 200
        assert _unwrap(r2.json())["run_id"] == run_id

    # limit=1
    r3 = admin_client.get(f"{API}/arbicore/certification/shadow/runs?limit=1", timeout=10)
    assert r3.status_code == 200
    assert len(r3.json()["items"]) <= 1

    # status=PASS filter — accept 0+ but no non-PASS items
    r4 = admin_client.get(f"{API}/arbicore/certification/shadow/runs?status=PASS", timeout=10)
    assert r4.status_code == 200
    for it in r4.json()["items"]:
        assert it["status"] == "PASS"

    # 404 for unknown id
    r5 = admin_client.get(f"{API}/arbicore/certification/shadow/runs/does-not-exist-xyz", timeout=10)
    assert r5.status_code == 404


# --------------------------------------------------------------------------- stop / abort / idempotent
def test_stop_aborts_running_and_is_idempotent(admin_client, mongo_coll):
    # ensure fresh start
    admin_client.post(
        f"{API}/arbicore/certification/shadow/stop", json={"reason": "cleanup"}, timeout=10,
    )
    r = admin_client.post(
        f"{API}/arbicore/certification/shadow/start", json={"target_cycles": 10}, timeout=15,
    )
    assert r.status_code == 200
    run_id = _unwrap(r.json())["run_id"]

    r2 = admin_client.post(
        f"{API}/arbicore/certification/shadow/stop", json={"reason": "test"}, timeout=10,
    )
    assert r2.status_code == 200
    aborted = _unwrap(r2.json())
    assert aborted.get("status") == "ABORTED"
    assert any("aborted" in fr.lower() and "test" in fr.lower() for fr in aborted.get("fail_reasons", []))
    assert aborted.get("run_id") == run_id

    # Second stop → idempotent (null current or already-terminal)
    r3 = admin_client.post(
        f"{API}/arbicore/certification/shadow/stop", json={"reason": "again"}, timeout=10,
    )
    assert r3.status_code in (200, 409)
    body = r3.json()
    if body:
        # may be {run: null} or already-terminal doc
        run = body.get("run") if isinstance(body, dict) and "run" in body else body
        if run:
            assert run.get("status") in ("ABORTED", None)


# --------------------------------------------------------------------------- dashboard pulse hook
def test_dashboard_pulse_shadow_block(admin_client):
    # ensure no active run
    admin_client.post(
        f"{API}/arbicore/certification/shadow/stop", json={"reason": "pulse-precheck"}, timeout=10,
    )
    r = admin_client.get(f"{API}/arbicore/dashboard/pulse", timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "shadow_certification" in data, f"pulse missing shadow_certification: {list(data.keys())}"
    sc = data["shadow_certification"]
    for k in ("active", "run_id", "status", "cycles_completed", "target_cycles", "executable_rate"):
        assert k in sc, f"pulse.shadow_certification missing key: {k}"
    assert sc["active"] is False


def test_dashboard_pulse_shadow_active(admin_client):
    r = admin_client.post(
        f"{API}/arbicore/certification/shadow/start", json={"target_cycles": 5}, timeout=15,
    )
    assert r.status_code == 200
    run_id = _unwrap(r.json())["run_id"]
    try:
        p = admin_client.get(f"{API}/arbicore/dashboard/pulse", timeout=15)
        assert p.status_code == 200
        sc = p.json()["shadow_certification"]
        assert sc["active"] is True
        assert sc["run_id"] == run_id
        assert sc["status"] == "RUNNING"
        assert sc["target_cycles"] == 5
    finally:
        admin_client.post(
            f"{API}/arbicore/certification/shadow/stop", json={"reason": "pulse-active-teardown"}, timeout=10,
        )


# --------------------------------------------------------------------------- Mongo indexes
def test_mongo_indexes(mongo_coll):
    idx = mongo_coll.index_information()
    names = set(idx.keys())
    # 3 idempotent indexes + default _id_
    expected = {"uniq_run_id", "status_recent", "recent"}
    missing = expected - names
    assert not missing, f"missing indexes: {missing} in {names}"
    assert idx["uniq_run_id"].get("unique") is True


# --------------------------------------------------------------------------- regression: paper validation still works
def test_regression_paper_validation_endpoints(admin_client):
    for path in (
        "/arbicore/validation/report",
        "/arbicore/validation/evidence",
        "/arbicore/validation/metrics",
    ):
        r = admin_client.get(f"{API}{path}", timeout=15)
        assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:200]}"


def test_regression_pulse_paper_validation_block(admin_client):
    r = admin_client.get(f"{API}/arbicore/dashboard/pulse", timeout=15)
    assert r.status_code == 200
    assert "paper_validation" in r.json()
