"""P0 independent verification via the EXTERNAL ingress URL.

Scope: fail-closed first-admin bootstrap (POST /api/auth/setup), login/session
cookies, /api/auth/me, and the fail-closed safety posture.

NON-DESTRUCTIVE: never deletes the canonical admin. Brute-force lockout test is
marked and runs last (it locks ip:admin for 15 min) — it clears login_attempts
afterwards so the admin stays usable.
"""
import os

import pytest
import requests
from dotenv import dotenv_values

_be = dotenv_values("/app/app/backend/.env")
_fe = dotenv_values("/app/app/frontend/.env")

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or _fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

BOOTSTRAP_TOKEN = (os.environ.get("ARBICORE_BOOTSTRAP_TOKEN") or _be.get("ARBICORE_BOOTSTRAP_TOKEN") or "").strip()

ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCoreAdmin2026"
TIMEOUT = 30


def _setup(headers=None, username="TEST_intruder", password="IntruderPass123"):
    return requests.post(f"{BASE}/api/auth/setup",
                         json={"username": username, "password": password},
                         headers=headers or {}, timeout=TIMEOUT)


# ---------- /api/auth/status ----------

class TestAuthStatus:
    def test_status_contract(self):
        r = requests.get(f"{BASE}/api/auth/status", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["setup_complete"] is True
        assert d["auth_required"] is True
        assert d["bootstrap_requires_token"] is True
        assert isinstance(d.get("bootstrap_available"), bool)

    def test_status_never_leaks_token(self):
        r = requests.get(f"{BASE}/api/auth/status", timeout=TIMEOUT)
        assert BOOTSTRAP_TOKEN
        assert BOOTSTRAP_TOKEN not in r.text
        assert "token" not in {k.lower() for k in r.json()} - {"bootstrap_requires_token"}


# ---------- SECURITY: /api/auth/setup fail-closed ----------

class TestBootstrapFailClosed:
    def test_setup_no_token_is_403(self):
        r = _setup()
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"

    def test_setup_wrong_token_is_403(self):
        r = _setup(headers={"X-Bootstrap-Token": "definitely-wrong-token"})
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"

    def test_setup_empty_token_is_403(self):
        r = _setup(headers={"X-Bootstrap-Token": ""})
        assert r.status_code == 403, r.text

    def test_setup_correct_token_still_403_locked(self):
        r = _setup(headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN})
        assert r.status_code == 403, f"expected 403 (locked), got {r.status_code}: {r.text[:300]}"
        assert "lock" in r.json().get("detail", "").lower()

    def test_setup_does_not_set_cookies_on_rejection(self):
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/setup", json={"username": "TEST_x", "password": "Passw0rd123"},
                   timeout=TIMEOUT)
        assert r.status_code == 403
        assert "access_token" not in {c.name for c in s.cookies}

    def test_no_extra_admin_created(self):
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login",
                   json={"username": "TEST_intruder", "password": "IntruderPass123"},
                   timeout=TIMEOUT)
        assert r.status_code == 401, "intruder account must not exist"


# ---------- Login / session ----------

class TestLoginSession:
    def test_login_success_sets_httponly_cookies(self):
        s = requests.Session()
        r = s.post(f"{BASE}/api/auth/login",
                   json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["username"] == ADMIN_USER
        assert body["role"] == "admin"
        assert "password_hash" not in body
        names = {c.name for c in s.cookies}
        assert "access_token" in names and "refresh_token" in names
        raw = r.headers.get("set-cookie", "")
        assert "HttpOnly" in raw

    def test_me_with_cookie(self):
        s = requests.Session()
        assert s.post(f"{BASE}/api/auth/login",
                      json={"username": ADMIN_USER, "password": ADMIN_PASS},
                      timeout=TIMEOUT).status_code == 200
        r = s.get(f"{BASE}/api/auth/me", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        assert r.json()["username"] == ADMIN_USER
        assert r.json()["role"] == "admin"

    def test_me_without_cookie_401(self):
        r = requests.get(f"{BASE}/api/auth/me", timeout=TIMEOUT)
        assert r.status_code == 401, r.text

    def test_login_wrong_password_401(self):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"username": ADMIN_USER, "password": "totally-wrong-pw"},
                          timeout=TIMEOUT)
        assert r.status_code == 401, r.text

    def test_admin_still_exists_at_end(self):
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=TIMEOUT)
        assert r.status_code == 200, r.text


# ---------- Fail-closed safety posture ----------

class TestSafetyPosture:
    def test_safety_status_fail_closed(self):
        r = requests.get(f"{BASE}/api/arbicore/safety/status", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        flat = str(d)
        assert d.get("live_execution_enabled") is False, flat[:400]
        ks = d.get("kill") or d.get("kill_switch") or {}
        engaged = ks.get("engaged", d.get("engaged"))
        assert engaged is True, f"kill switch not engaged: {flat[:400]}"

    def test_live_status_not_live(self):
        r = requests.get(f"{BASE}/api/arbicore/live/status", timeout=TIMEOUT)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("live_execution_enabled") in (False, None), str(d)[:400]
        assert d.get("broadcast_enabled") in (False, None), str(d)[:400]


# ---------- Brute force (destructive to lockout state; run explicitly) ----------

@pytest.mark.bruteforce
class TestBruteForceLast:
    """KNOWN DEFECT (verified 2026-07): via the external ingress this FAILS.
    services/auth.py keys lockout on request.client.host, which is the ingress
    proxy pod IP. Requests round-robin across >=2 pod IPs, so 5 failures split
    into 4+3 and the correct password still returns 200. Lockout only triggers
    after ~5*N attempts. Run with: pytest -m bruteforce (locks admin 15 min;
    clear with db.login_attempts.delete_many({}))."""

    def test_lockout_after_5_failures(self):
        codes = [requests.post(f"{BASE}/api/auth/login",
                               json={"username": ADMIN_USER, "password": f"wrong-{i}"},
                               timeout=TIMEOUT).status_code for i in range(5)]
        assert all(c == 401 for c in codes), codes
        r = requests.post(f"{BASE}/api/auth/login",
                          json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=TIMEOUT)
        assert r.status_code == 429, f"expected 429, got {r.status_code}: {r.text[:300]}"
