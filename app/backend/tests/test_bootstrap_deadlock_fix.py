"""Iteration 3 — re-test of the iteration_2 HIGH dead-lock defect in first-admin bootstrap.

Covers:
  * DEAD-LOCK FIX: wiped users (+ stale settings lock) can be re-bootstrapped with the token.
  * Self-heal is still token-gated (no token / wrong token -> 403).
  * Atomicity under concurrency (sparse-unique admin_singleton index).
  * LOCKED when an admin already exists.
  * No regression on /api/auth/status, /login, /me, wrong password.
  * Fail-closed safety posture.
Teardown restores exactly one admin (admin / ArbiCoreAdmin2026) and clears login_attempts.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_fe = dotenv_values("/app/app/frontend/.env")
_be = dotenv_values("/app/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
TOKEN = (os.environ.get("ARBICORE_BOOTSTRAP_TOKEN") or _be.get("ARBICORE_BOOTSTRAP_TOKEN") or "").strip()
MONGO_URL = os.environ.get("MONGO_URL") or _be.get("MONGO_URL") or "mongodb://localhost:27017"
DB_NAME = _be.get("DB_NAME") or "arbicore_x"

ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCoreAdmin2026"

if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
if not TOKEN:
    raise RuntimeError("ARBICORE_BOOTSTRAP_TOKEN missing")


@pytest.fixture(scope="module")
def mdb():
    return MongoClient(MONGO_URL)[DB_NAME]


def _wipe(mdb):
    mdb.users.delete_many({})
    mdb.settings.delete_many({"key": "auth_bootstrap_lock"})
    mdb.login_attempts.delete_many({})


def _setup(session, username, password="ArbiCorePass2026", token=TOKEN):
    headers = {} if token is None else {"X-Bootstrap-Token": token}
    return session.post(f"{BASE_URL}/api/auth/setup",
                        json={"username": username, "password": password},
                        headers=headers, timeout=30)


def _restore_admin(mdb):
    """Leave the DB with exactly one admin: admin / ArbiCoreAdmin2026."""
    _wipe(mdb)
    s = requests.Session()
    r = _setup(s, ADMIN_USER, ADMIN_PASS)
    assert r.status_code == 200, f"restore failed: {r.status_code} {r.text[:300]}"
    mdb.login_attempts.delete_many({})
    assert mdb.users.count_documents({}) == 1
    login = requests.Session().post(f"{BASE_URL}/api/auth/login",
                                    json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
    assert login.status_code == 200, f"restored admin cannot log in: {login.status_code} {login.text[:300]}"


@pytest.fixture(scope="module", autouse=True)
def final_restore(mdb):
    yield
    _restore_admin(mdb)


# ── settings/auth_bootstrap_lock sentinel must no longer exist in code ──
def test_no_lock_sentinel_in_source():
    src = open("/app/app/backend/routes/auth.py").read()
    assert "auth_bootstrap_lock" not in src, "stale lock sentinel still referenced in auth.py"
    assert "admin_singleton" in src and "partialFilterExpression" in src


# ── 1. DEAD-LOCK FIX ──
def test_deadlock_fix_rebootstrap_after_wipe(mdb):
    _wipe(mdb)
    # simulate the iteration_2 state: stale lock sentinel present
    mdb.settings.insert_one({"key": "auth_bootstrap_lock", "value": True})
    mdb.settings.delete_many({"key": "auth_bootstrap_lock"})

    status = requests.get(f"{BASE_URL}/api/auth/status", timeout=30).json()
    assert status["setup_complete"] is False, status

    s = requests.Session()
    r = _setup(s, "TEST_recover_admin")
    assert r.status_code == 200, f"DEAD-LOCK: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data["username"] == "test_recover_admin"
    assert data["role"] == "admin"
    assert "password_hash" not in data and "_id" not in data
    assert mdb.users.count_documents({}) == 1
    assert mdb.users.find_one({})["admin_singleton"] == "admin"
    # cookies issued on setup
    assert "access_token" in s.cookies.get_dict()
    # status now reflects reality
    assert requests.get(f"{BASE_URL}/api/auth/status", timeout=30).json()["setup_complete"] is True


# ── 2. LOCKED when admin exists ──
def test_locked_when_admin_exists(mdb):
    assert mdb.users.count_documents({}) == 1
    r = _setup(requests.Session(), "TEST_second_admin")
    assert r.status_code == 403, f"{r.status_code} {r.text[:300]}"
    assert mdb.users.count_documents({}) == 1


# ── 3. Self-heal still token-gated ──
def test_selfheal_requires_token(mdb):
    _wipe(mdb)
    r_none = _setup(requests.Session(), "TEST_no_token", token=None)
    assert r_none.status_code == 403, f"{r_none.status_code} {r_none.text[:300]}"
    r_wrong = _setup(requests.Session(), "TEST_wrong_token", token="not-the-real-token-value")
    assert r_wrong.status_code == 403, f"{r_wrong.status_code} {r_wrong.text[:300]}"
    r_empty = _setup(requests.Session(), "TEST_empty_token", token="")
    assert r_empty.status_code == 403, f"{r_empty.status_code} {r_empty.text[:300]}"
    assert mdb.users.count_documents({}) == 0


# ── 4. Atomic under concurrency ──
def test_concurrent_bootstrap_exactly_one_winner(mdb):
    _wipe(mdb)
    n = 12

    def attempt(i):
        return _setup(requests.Session(), f"TEST_race_admin_{i}").status_code

    with ThreadPoolExecutor(max_workers=n) as ex:
        codes = list(ex.map(attempt, range(n)))

    assert codes.count(200) == 1, f"expected exactly 1 winner, got {codes}"
    assert all(c == 403 for c in codes if c != 200), f"unexpected codes: {codes}"
    assert mdb.users.count_documents({}) == 1, list(mdb.users.find({}, {"_id": 0, "password_hash": 0}))


# ── 5. No regression: login / me / wrong password ──
def test_login_me_and_wrong_password(mdb):
    _restore_admin(mdb)
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:300]
    assert r.json()["username"] == ADMIN_USER
    cookies = s.cookies.get_dict()
    assert "access_token" in cookies and "refresh_token" in cookies
    raw = "\n".join(str(c) for c in r.raw.headers.getlist("Set-Cookie")) if hasattr(r.raw, "headers") else ""
    if raw:
        assert "HttpOnly" in raw, raw

    me = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert me.status_code == 200, me.text[:300]
    assert me.json()["username"] == ADMIN_USER
    assert "password_hash" not in me.json()

    bad = requests.Session().post(f"{BASE_URL}/api/auth/login",
                                  json={"username": ADMIN_USER, "password": "wrong-password-123"}, timeout=30)
    assert bad.status_code == 401, f"{bad.status_code} {bad.text[:300]}"

    unauth = requests.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert unauth.status_code == 401, unauth.status_code

    mdb.login_attempts.delete_many({})


# ── 6. Fail-closed posture ──
def test_safety_status_fail_closed():
    r = requests.get(f"{BASE_URL}/api/arbicore/safety/status", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d.get("live_execution_enabled") is False, d
    kill = d.get("kill") or {}
    assert kill.get("engaged") is True, d
