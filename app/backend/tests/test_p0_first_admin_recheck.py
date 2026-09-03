"""P0 re-verification: unauthenticated internet visitor MUST NOT be able to
create the first administrator, even when the users collection is EMPTY.

Run in two phases so a browser check can run against the empty-DB state:
  phase A:  pytest -k EmptyDbFailClosed   (leaves DB empty)
  phase B:  pytest -k AuthorizedBootstrapAndRestore   (creates + restores admin)
"""
import os

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BACKEND_ENV = dotenv_values("/app/app/backend/.env")
FRONTEND_ENV = dotenv_values("/app/app/frontend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or FRONTEND_ENV.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
BOOTSTRAP_TOKEN = (os.environ.get("ARBICORE_BOOTSTRAP_TOKEN")
                   or BACKEND_ENV.get("ARBICORE_BOOTSTRAP_TOKEN") or "").strip()
MONGO_URL = os.environ.get("MONGO_URL") or BACKEND_ENV.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or BACKEND_ENV.get("DB_NAME")

if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
if not BOOTSTRAP_TOKEN:
    raise RuntimeError("ARBICORE_BOOTSTRAP_TOKEN missing")

ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCoreAdmin2026"


def _db():
    return MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)[DB_NAME]


def _wipe_users():
    db = _db()
    db.users.delete_many({})
    db.settings.delete_many({"key": "auth_bootstrap_lock"})
    db.login_attempts.delete_many({})
    return db.users.count_documents({})


def _users_count():
    return _db().users.count_documents({})


def _fresh():
    """Brand-new session: no cookies, no auth state (simulates internet visitor)."""
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


ATTACK_BODY = {"username": "attacker", "password": "passwordpassword"}


# ── Module: routes/auth.py — first-admin bootstrap fail-closed (empty DB) ──
class TestEmptyDbFailClosed:
    def test_users_collection_is_empty_precondition(self):
        assert _wipe_users() == 0

    def test_status_endpoint_is_safe_and_leaks_nothing(self):
        r = _fresh().get(f"{BASE_URL}/api/auth/status", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["setup_complete"] is False
        assert data["auth_required"] is True
        assert data["bootstrap_requires_token"] is True
        assert "bootstrap_available" not in data
        body = r.text
        assert BOOTSTRAP_TOKEN not in body
        assert set(data.keys()) == {"setup_complete", "auth_required",
                                    "bootstrap_requires_token"}

    def test_setup_without_token_is_403_and_no_admin_created(self):
        assert _users_count() == 0
        r = _fresh().post(f"{BASE_URL}/api/auth/setup", json=ATTACK_BODY, timeout=30)
        assert r.status_code == 403, f"expected 403 fail-closed, got {r.status_code}: {r.text[:300]}"
        assert _users_count() == 0, "SECURITY: admin was created without bootstrap token"

    def test_setup_with_wrong_token_is_403(self):
        r = _fresh().post(f"{BASE_URL}/api/auth/setup", json=ATTACK_BODY,
                          headers={"X-Bootstrap-Token": "wrong-token-value-000"}, timeout=30)
        assert r.status_code == 403, r.text[:300]
        assert _users_count() == 0

    def test_setup_with_empty_string_token_is_403(self):
        r = _fresh().post(f"{BASE_URL}/api/auth/setup", json=ATTACK_BODY,
                          headers={"X-Bootstrap-Token": ""}, timeout=30)
        assert r.status_code == 403, r.text[:300]
        assert _users_count() == 0

    def test_setup_with_case_mutated_token_is_403(self):
        # requests refuses whitespace-only header values, so exercise a
        # near-miss mutation instead (constant-time compare must reject it).
        mutated = BOOTSTRAP_TOKEN.swapcase()
        assert mutated != BOOTSTRAP_TOKEN
        r = _fresh().post(f"{BASE_URL}/api/auth/setup", json=ATTACK_BODY,
                          headers={"X-Bootstrap-Token": mutated}, timeout=30)
        assert r.status_code == 403, r.text[:300]
        assert _users_count() == 0

    def test_setup_with_token_prefix_is_403(self):
        r = _fresh().post(f"{BASE_URL}/api/auth/setup", json=ATTACK_BODY,
                          headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN[:-1]}, timeout=30)
        assert r.status_code == 403, r.text[:300]
        assert _users_count() == 0

    def test_no_auth_cookies_issued_on_rejected_bootstrap(self):
        s = _fresh()
        s.post(f"{BASE_URL}/api/auth/setup", json=ATTACK_BODY, timeout=30)
        assert "access_token" not in s.cookies
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert me.status_code == 401, me.text[:200]

    # fail-closed trading posture must be unaffected
    def test_safety_status_fail_closed(self):
        r = _fresh().get(f"{BASE_URL}/api/arbicore/safety/status", timeout=30)
        assert r.status_code in (200, 401), r.text[:300]
        if r.status_code == 200:
            d = r.json()
            assert d.get("live_execution_enabled") is False, d
            eff = d.get("effective_kill_engaged", d.get("kill_switch_engaged"))
            assert eff is True, d


# ── Module: routes/auth.py — the ONLY authorized path + state restore ──
class TestAuthorizedBootstrapAndRestore:
    def test_correct_token_creates_admin(self):
        _wipe_users()
        s = _fresh()
        r = s.post(f"{BASE_URL}/api/auth/setup",
                   json={"username": ADMIN_USER, "password": ADMIN_PASS},
                   headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN}, timeout=30)
        assert r.status_code == 200, r.text[:400]
        data = r.json()
        assert data["username"] == ADMIN_USER
        assert data["role"] == "admin"
        assert "password_hash" not in data and "_id" not in data
        assert _users_count() == 1

    def test_repeat_with_correct_token_is_locked_403(self):
        r = _fresh().post(f"{BASE_URL}/api/auth/setup",
                          json={"username": "second", "password": "passwordpassword"},
                          headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN}, timeout=30)
        assert r.status_code == 403, r.text[:300]
        assert _users_count() == 1

    def test_status_reports_setup_complete(self):
        d = _fresh().get(f"{BASE_URL}/api/auth/status", timeout=30).json()
        assert d["setup_complete"] is True

    def test_admin_login_works_and_state_restored(self):
        db = _db()
        db.login_attempts.delete_many({})
        s = _fresh()
        r = s.post(f"{BASE_URL}/api/auth/login",
                   json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["username"] == ADMIN_USER
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert me.status_code == 200
        assert me.json()["username"] == ADMIN_USER
        db.login_attempts.delete_many({})
        assert db.login_attempts.count_documents({}) == 0
        assert db.users.count_documents({}) == 1


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
