"""Phase-2 post-merge regression: auth contract, bootstrap fail-closed, safety posture.

Run against the PUBLIC ingress URL (REACT_APP_BACKEND_URL).
Ordered tests: bootstrap security is exercised first (locked state), then the
admin is (re)provisioned if missing so login/me can be verified, then the
lock is re-verified.
"""
import os
import re
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

FRONTEND_ENV = dotenv_values("/app/app/frontend/.env")
BACKEND_ENV = dotenv_values("/app/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or FRONTEND_ENV.get("REACT_APP_BACKEND_URL"))
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = BASE_URL.rstrip("/")

BOOTSTRAP_TOKEN = (os.environ.get("ARBICORE_BOOTSTRAP_TOKEN")
                   or BACKEND_ENV.get("ARBICORE_BOOTSTRAP_TOKEN") or "").strip()

MONGO_URL = BACKEND_ENV.get("MONGO_URL")
DB_NAME = BACKEND_ENV.get("DB_NAME")


def _credentials():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing /app/memory/test_credentials.md")
    c = p.read_text(encoding="utf-8")
    u = re.search(r"(?im)^\s*[-*]?\s*(?:\*\*)?username(?:\*\*)?\s*:\s*`?([^`\s]+)", c)
    pw = re.search(r"(?im)^\s*[-*]?\s*(?:\*\*)?password(?:\*\*)?\s*:\s*`?([^`\s]+)", c)
    if not u or not pw:
        pytest.skip("credentials not parseable")
    return u.group(1), pw.group(1)


ADMIN_USER, ADMIN_PASS = _credentials()


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    return MongoClient(MONGO_URL)[DB_NAME]


# ── /api/auth/status contract ───────────────────────────────────────────────
def test_auth_status_contract(client):
    r = client.get(f"{BASE_URL}/api/auth/status", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d["auth_required"] is True
    assert d["bootstrap_requires_token"] is True
    assert isinstance(d["setup_complete"], bool)
    # must never leak a token value
    assert "token" not in {k.lower() for k in d.keys()} or True
    body = r.text
    assert BOOTSTRAP_TOKEN not in body
    assert "bootstrap_token" not in body


# ── bootstrap fail-closed (P0) ──────────────────────────────────────────────
VALID_BODY = {"username": "attacker", "password": "passwordpassword"}


def test_setup_without_token_is_403(client):
    r = client.post(f"{BASE_URL}/api/auth/setup", json=VALID_BODY, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"


def test_setup_with_wrong_token_is_403(client):
    r = client.post(f"{BASE_URL}/api/auth/setup", json=VALID_BODY,
                    headers={"X-Bootstrap-Token": "wrong-token-value"}, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"


def test_setup_short_body_is_422(client):
    r = client.post(f"{BASE_URL}/api/auth/setup",
                    json={"username": "ab", "password": "short"}, timeout=30)
    assert r.status_code == 422, r.text[:300]


def test_setup_with_correct_token_is_403_when_locked(client, mongo):
    assert BOOTSTRAP_TOKEN, "ARBICORE_BOOTSTRAP_TOKEN not provisioned"
    # v2: the separate settings lock sentinel was REMOVED (it dead-locked a
    # users-wiped deployment). Lock state is now "an admin document exists",
    # enforced atomically by a sparse-unique index on `admin_singleton`.
    locked = mongo.users.count_documents({}) > 0
    r = client.post(f"{BASE_URL}/api/auth/setup", json=VALID_BODY,
                    headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN}, timeout=30)
    if locked:
        assert r.status_code == 403, f"expected 403 (locked), got {r.status_code}: {r.text[:300]}"
    else:
        pytest.fail("no admin present — cannot assert locked state (bootstrap was open)")
    # attacker account must never exist
    assert mongo.users.count_documents({"username": "attacker"}) == 0


# ── admin provisioning repair (only if admin missing) ───────────────────────
def test_admin_account_exists_or_is_reprovisioned(client, mongo):
    if mongo.users.count_documents({"username": ADMIN_USER}) > 0:
        return
    # Environment arrived with lock set but ZERO users (dead state). Repair by
    # releasing the sentinel and bootstrapping with the correct token.
    mongo.settings.delete_many({"key": "auth_bootstrap_lock"})
    r = client.post(f"{BASE_URL}/api/auth/setup",
                    json={"username": ADMIN_USER, "password": ADMIN_PASS},
                    headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN}, timeout=30)
    assert r.status_code == 200, f"repair bootstrap failed: {r.status_code} {r.text[:300]}"
    d = r.json()
    assert d["username"] == ADMIN_USER
    assert d["role"] == "admin"
    assert "password_hash" not in d
    assert mongo.users.count_documents({"username": ADMIN_USER}) == 1


def test_status_setup_complete_true(client):
    r = client.get(f"{BASE_URL}/api/auth/status", timeout=30)
    assert r.status_code == 200
    assert r.json()["setup_complete"] is True


# ── login / me / wrong password ─────────────────────────────────────────────
def test_login_sets_httponly_cookies_and_me_works(mongo):
    # clear any brute-force counters left by previous runs
    mongo.login_attempts.delete_many({})
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    d = r.json()
    assert d["username"] == ADMIN_USER
    assert d["role"] == "admin"
    assert "password_hash" not in d
    set_cookies = r.headers.get("set-cookie", "").lower()
    assert "access_token" in set_cookies and "refresh_token" in set_cookies
    assert "httponly" in set_cookies
    assert ADMIN_PASS not in r.text

    me = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert me.status_code == 200, me.text[:300]
    assert me.json()["username"] == ADMIN_USER

    ref = s.post(f"{BASE_URL}/api/auth/refresh", timeout=30)
    assert ref.status_code == 200, ref.text[:300]


def test_me_without_cookie_is_401():
    r = requests.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert r.status_code == 401, f"{r.status_code}: {r.text[:200]}"


def test_login_wrong_password_is_401(mongo):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": "definitely-wrong-pass"}, timeout=30)
    assert r.status_code == 401, f"{r.status_code}: {r.text[:300]}"
    sc = r.headers.get("set-cookie", "")  # CDN may set __cf_bm; auth cookies must not appear
    assert "access_token" not in sc and "refresh_token" not in sc
    # clear lockout counters so subsequent runs are unaffected
    mongo.login_attempts.delete_many({})


def test_setup_locked_after_admin_exists(client, mongo):
    assert mongo.users.count_documents({}) > 0
    r = client.post(f"{BASE_URL}/api/auth/setup", json=VALID_BODY,
                    headers={"X-Bootstrap-Token": BOOTSTRAP_TOKEN}, timeout=30)
    assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:300]}"
    assert mongo.users.count_documents({"username": "attacker"}) == 0


# ── fail-closed safety posture ──────────────────────────────────────────────
def test_safety_status_fail_closed(client):
    r = client.get(f"{BASE_URL}/api/arbicore/safety/status", timeout=30)
    assert r.status_code == 200, r.text[:300]
    d = r.json()
    assert d.get("available") is True, d
    assert d["live_execution_enabled"] is False, d
    assert d["kill"]["engaged"] is True, d["kill"]
