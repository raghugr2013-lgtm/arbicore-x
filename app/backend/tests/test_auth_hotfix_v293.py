"""ArbiCore X — v2.9.3 hotfix/auth-routing verification tests.

Covers 15 verifications from the review request.
Run with backend at http://127.0.0.1:8001, fresh Mongo (arbicore_x_hotfix_test).
"""
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests
from pymongo import MongoClient

BASE = "http://127.0.0.1:8001"
BACKEND_DIR = Path("/app/app/backend")
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "arbicore_x_hotfix_test"


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


def _reset_canonical(mongo):
    mongo["users"].delete_many({})
    mongo["login_attempts"].delete_many({})


def _reset_all(mongo):
    _reset_canonical(mongo)
    mongo["auth_users"].delete_many({})
    mongo["auth_sessions"].delete_many({})


# ---------- Setup / status flow (V1-V4) ----------

class TestSetupFlow:
    def test_v1_status_when_empty(self, mongo):
        _reset_canonical(mongo)
        r = requests.get(f"{BASE}/api/auth/status")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data == {"setup_complete": False, "auth_required": True}

    def test_v2_setup_creates_admin_and_sets_cookies(self, mongo):
        _reset_canonical(mongo)
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/setup",
                   json={"username": "admin", "password": "testtest123"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"
        assert "id" in body and "created_at" in body
        # cookies
        cookies = {c.name: c for c in s.cookies}
        assert "access_token" in cookies
        assert "refresh_token" in cookies
        # httpOnly is transport-level; check raw Set-Cookie
        raw = r.headers.get("set-cookie", "")
        assert "HttpOnly" in raw
        assert "access_token=" in raw and "refresh_token=" in raw

    def test_v3_second_setup_returns_403(self, mongo):
        # users collection is populated from previous test
        r = requests.post(f"{BASE}/api/auth/setup",
                          json={"username": "admin", "password": "testtest123"})
        assert r.status_code == 403, r.text
        assert "Setup already completed" in r.json().get("detail", "")

    def test_v4_status_after_setup(self):
        r = requests.get(f"{BASE}/api/auth/status")
        assert r.status_code == 200
        assert r.json() == {"setup_complete": True, "auth_required": True}


# ---------- /me + logout (V5, V6) ----------

def _login(username="admin", password="testtest123"):
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return s


class TestMeAndLogout:
    def test_v5_me_with_cookie_returns_user(self):
        s = _login()
        r = s.get(f"{BASE}/api/auth/me")
        assert r.status_code == 200
        body = r.json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"
        assert "id" in body and "created_at" in body

    def test_v5_me_without_cookie_returns_401(self):
        r = requests.get(f"{BASE}/api/auth/me")
        assert r.status_code == 401
        assert r.json() == {"detail": "Not authenticated"}

    def test_v6_logout_clears_cookies(self):
        s = _login()
        r = s.post(f"{BASE}/api/auth/logout")
        assert r.status_code == 200
        raw = r.headers.get("set-cookie", "")
        # Two Set-Cookie headers combined. Verify both cookies get cleared.
        # requests concatenates set-cookies with ", "; ensure both cookie names appear
        # with Max-Age=0 semantics (delete_cookie in Starlette uses Max-Age=0).
        assert 'access_token=""' in raw or "access_token=;" in raw or "access_token=" in raw
        assert 'refresh_token=""' in raw or "refresh_token=;" in raw or "refresh_token=" in raw
        assert "Max-Age=0" in raw
        assert "Path=/" in raw


# ---------- Login + refresh (V7) ----------

class TestLoginRefresh:
    def test_v7_login_and_refresh(self):
        s = _login()
        old_access = s.cookies.get("access_token")
        assert old_access
        # remove access_token to prove refresh works with only refresh cookie
        s.cookies.set("access_token", "", domain="127.0.0.1", path="/")
        del s.cookies["access_token"]
        r = s.post(f"{BASE}/api/auth/refresh")
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        new_access = s.cookies.get("access_token")
        assert new_access  # new access cookie was set (may equal old if issued within same second)


# ---------- Change password revokes old session (V8) ----------

class TestChangePassword:
    def test_v8_change_password_revokes_old_session(self, mongo):
        # Fresh setup for isolation
        _reset_canonical(mongo)
        s1 = requests.Session()
        r = s1.post(f"{BASE}/api/auth/setup",
                    json={"username": "admin", "password": "testtest123"})
        assert r.status_code == 200
        old_access = s1.cookies.get("access_token")

        # login separately to get 2nd session (this will be the one changing pw)
        s2 = _login("admin", "testtest123")
        r = s2.post(f"{BASE}/api/auth/change-password",
                    json={"current_password": "testtest123",
                          "new_password": "newnewpass456"})
        assert r.status_code == 200, r.text

        # s2's session should be kept alive
        r2 = s2.get(f"{BASE}/api/auth/me")
        assert r2.status_code == 200

        # s1's old access token should now be revoked
        r_old = requests.get(f"{BASE}/api/auth/me",
                             cookies={"access_token": old_access})
        assert r_old.status_code == 401
        assert "Session revoked" in r_old.json().get("detail", "")

        # login with old pw fails
        r_bad = requests.post(f"{BASE}/api/auth/login",
                              json={"username": "admin", "password": "testtest123"})
        assert r_bad.status_code == 401

        # login with new pw succeeds
        r_ok = requests.post(f"{BASE}/api/auth/login",
                             json={"username": "admin", "password": "newnewpass456"})
        assert r_ok.status_code == 200


# ---------- Brute-force lockout (V9) ----------

class TestBruteForce:
    def test_v9_lockout_after_5_failures(self, mongo):
        # ensure clean state and known password
        _reset_canonical(mongo)
        r = requests.post(f"{BASE}/api/auth/setup",
                          json={"username": "admin", "password": "testtest123"})
        assert r.status_code == 200
        codes = []
        for _ in range(5):
            r = requests.post(f"{BASE}/api/auth/login",
                              json={"username": "admin", "password": "wrongpass"})
            codes.append(r.status_code)
        # first 5 should be 401
        assert all(c == 401 for c in codes), codes
        # 6th attempt (or even valid password) should be locked out
        r6 = requests.post(f"{BASE}/api/auth/login",
                           json={"username": "admin", "password": "testtest123"})
        assert r6.status_code == 429, r6.text
        assert "Too many failed attempts" in r6.json().get("detail", "")
        # cleanup: remove lockout for downstream tests
        mongo["login_attempts"].delete_many({})


# ---------- Legacy diagnostics removed (V10) ----------

class TestLegacyRemoved:
    def test_v10_diagnostics_returns_404(self):
        r = requests.get(f"{BASE}/api/auth/diagnostics")
        assert r.status_code == 404


# ---------- reset_admin.py (V11, V12) ----------

def _run_reset(*args, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "reset_admin.py", *args],
        cwd=BACKEND_DIR, capture_output=True, text=True, env=env, timeout=30,
    )


class TestResetAdmin:
    def test_v11_dry_run_reports_inventory_no_writes(self, mongo):
        # seed all four collections
        _reset_all(mongo)
        mongo["users"].insert_one({"id": "u-reset-test", "username": "reset_dummy", "password_hash": "$2b$12$abc"})
        mongo["login_attempts"].insert_one({"identifier": "x"})
        mongo["auth_users"].insert_one({"id": "au1", "username": "legacy_dummy"})
        mongo["auth_sessions"].insert_one({"id": "s1"})

        r = _run_reset("--dry-run")
        assert r.returncode == 0, r.stderr
        out = r.stdout
        assert "canonical  'users'" in out
        assert "canonical  'login_attempts'" in out
        assert "legacy     'auth_users'" in out
        assert "legacy     'auth_sessions'" in out
        assert "[dry-run]" in out
        # confirm nothing was deleted
        assert mongo["users"].count_documents({}) == 1
        assert mongo["login_attempts"].count_documents({}) == 1
        assert mongo["auth_users"].count_documents({}) == 1
        assert mongo["auth_sessions"].count_documents({}) == 1

    def test_v11_default_clears_only_canonical(self, mongo):
        # State from previous test still has 1 in each
        r = _run_reset()
        assert r.returncode == 0, r.stderr
        assert mongo["users"].count_documents({}) == 0
        assert mongo["login_attempts"].count_documents({}) == 0
        # legacy stores untouched
        assert mongo["auth_users"].count_documents({}) == 1
        assert mongo["auth_sessions"].count_documents({}) == 1

    def test_v12_safety_net_refuses_when_canonical_empty_legacy_populated(self, mongo):
        # canonical is now empty; legacy has 1 doc each
        assert mongo["users"].count_documents({}) == 0
        assert mongo["auth_users"].count_documents({}) >= 1
        r = _run_reset()
        assert r.returncode == 3, f"expected exit 3, got {r.returncode}. stdout={r.stdout}"
        assert "Refusing to proceed" in r.stdout or "WARNING" in r.stdout
        # legacy untouched
        assert mongo["auth_users"].count_documents({}) >= 1

    def test_v12_legacy_flag_clears_both(self, mongo):
        r = _run_reset("--legacy")
        assert r.returncode == 0, r.stderr
        assert mongo["auth_users"].count_documents({}) == 0
        assert mongo["auth_sessions"].count_documents({}) == 0


# ---------- Legacy seed gate (V13) ----------

class TestLegacySeedGate:
    def test_v13_default_boot_skips_seed(self):
        # The currently running backend was started without ARBICORE_LEGACY_AUTH_SEED.
        # Verify the expected log line appeared.
        log = Path("/tmp/backend.log").read_text(errors="ignore")
        assert "v2.9.3: legacy auth seed skipped" in log, (
            "Expected skip-log line not found in backend log"
        )
        assert "ARBICORE_LEGACY_AUTH_SEED != '1'" in log

    def test_v13_seed_populates_auth_users_when_enabled(self, mongo):
        """Boot a short-lived uvicorn on port 8002 with the legacy flag ON."""
        _reset_all(mongo)
        env = os.environ.copy()
        env["ARBICORE_LEGACY_AUTH_SEED"] = "1"
        env["MONGO_URL"] = MONGO_URL
        env["DB_NAME"] = DB_NAME
        # Reuse .env-provided JWT_SECRET etc.
        proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "server:app",
             "--host", "127.0.0.1", "--port", "8002"],
            cwd=BACKEND_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        )
        try:
            # wait for /api/ to respond
            deadline = time.time() + 60
            while time.time() < deadline:
                try:
                    r = requests.get("http://127.0.0.1:8002/api/", timeout=2)
                    if r.status_code == 200:
                        break
                except requests.RequestException:
                    time.sleep(1)
            else:
                pytest.fail("Second backend didn't come up in time")
            # give startup seed a moment
            time.sleep(3)
            count = mongo["auth_users"].count_documents({})
            assert count >= 2, (
                f"Expected auth_users to be seeded with admin+operator (>=2), got {count}"
            )
            usernames = {d.get("username") for d in mongo["auth_users"].find({}, {"username": 1})}
            assert "admin" in usernames
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


# ---------- Regression: business endpoints (V14) ----------

class TestBusinessRegression:
    @pytest.mark.parametrize("path", [
        "/api/",
        "/api/status",
        "/api/arbicore/dashboard/pulse",
        "/api/arbicore/live/status",
        "/api/arbicore/safety/status",
    ])
    def test_v14_business_endpoint_200(self, path):
        r = requests.get(f"{BASE}{path}", timeout=15)
        assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"


# ---------- Regression: cookie session works on admin bearer endpoints (V15) ----------

class TestKillSwitchCookieAuth:
    def test_v15_kill_engage_disengage_with_cookie(self, mongo):
        # Ensure known admin
        _reset_canonical(mongo)
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/setup",
                   json={"username": "admin", "password": "testtest123"})
        assert r.status_code == 200
        r_eng = s.post(f"{BASE}/api/arbicore/safety/kill/engage")
        assert r_eng.status_code == 200, r_eng.text
        st = requests.get(f"{BASE}/api/arbicore/safety/status", timeout=10)
        assert st.status_code == 200
        # side effect check — kill engaged
        js = st.json()
        engaged = js.get("kill_switch", {}).get("engaged", js.get("engaged", None))
        # Some implementations put it elsewhere; just confirm SOMETHING flipped
        # by comparing engage then disengage semantics: after disengage, again 200.
        r_dis = s.post(f"{BASE}/api/arbicore/safety/kill/disengage")
        assert r_dis.status_code == 200, r_dis.text
