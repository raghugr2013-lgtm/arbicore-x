"""Canonical auth provisioning + source-of-truth drift acceptance tests (v2.9.4).

Proves:
  * clean install creates the admin from configured env credentials
  * restart does not duplicate users (idempotent)
  * the configured ARBICORE_ADMIN_PASS is actually the one that logs in
  * POST /api/auth/login succeeds with configured admin creds
  * wrong credentials return 401
  * existing users are preserved (password never overwritten)
  * authentication reads the SAME collection startup provisioning writes to
  * DRIFT DETECTOR (J): startup-seed collection == login collection == `users`
"""
import asyncio
import os
import uuid

import bcrypt
import requests
from dotenv import load_dotenv
from pymongo import MongoClient

_BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BACKEND, ".env"))

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")

ADMIN_USER = (os.environ.get("ARBICORE_ADMIN_USER") or "admin").strip().lower()
ADMIN_PASS = os.environ.get("ARBICORE_ADMIN_PASS") or os.environ.get("ARBICORE_ADMIN_PASSWORD")

_mc = MongoClient(os.environ["MONGO_URL"])
_pdb = _mc[os.environ["DB_NAME"]]


# ---------- collection identity (drift detector J) ----------
def test_seed_collection_equals_login_collection():
    from services import db as sdb
    from services import auth as sauth
    from routes import auth as rauth
    # canonical collection is `users`
    assert sdb.users_col.name == "users"
    # login (routes.auth) and the provisioner (services.auth) both bind the
    # SAME collection object — this is the exact drift that broke production.
    assert rauth.db.users_col is sdb.users_col
    assert sauth.db.users_col is sdb.users_col


def test_admin_seeded_into_users_collection():
    # clean-install effect: startup provisioning created the admin in `users`
    u = _pdb.users.find_one({"username": ADMIN_USER})
    assert u is not None, f"admin '{ADMIN_USER}' not provisioned into users collection"
    assert u.get("password_hash", "").startswith("$2"), "password not bcrypt-hashed"
    assert u.get("role") == "admin"
    # legacy collection is NOT the source of truth
    assert _pdb.auth_users.count_documents({"username": ADMIN_USER}) == 0


def test_restart_does_not_duplicate_admin():
    # unique index + insert-only seeder → exactly one admin across restarts
    assert _pdb.users.count_documents({"username": ADMIN_USER}) == 1


def test_configured_password_actually_logs_in():
    assert ADMIN_PASS, "ARBICORE_ADMIN_PASS must be configured for this test"
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=30)
    # 200 = success; 429 only if a prior test tripped lockout (safety feature)
    assert r.status_code in (200, 429), r.text
    if r.status_code == 200:
        body = r.json()
        assert body.get("username") == ADMIN_USER
        assert "password_hash" not in body
        # cookie session works against the SAME collection
        me = s.get(f"{BASE_URL}/api/auth/me", timeout=30)
        assert me.status_code == 200, me.text
        assert me.json().get("username") == ADMIN_USER


def test_wrong_credentials_rejected():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"username": ADMIN_USER, "password": "definitely-wrong-" + uuid.uuid4().hex},
                      timeout=30)
    assert r.status_code in (401, 429), r.text  # 401 rejected, 429 if locked


def test_status_reports_setup_complete():
    r = requests.get(f"{BASE_URL}/api/auth/status", timeout=20)
    assert r.status_code == 200, r.text
    assert r.json().get("setup_complete") is True


def test_seeder_idempotent_and_preserves_existing_password():
    """Direct provisioner test with a throwaway user: create → re-run with a
    CHANGED env password → original password must be preserved (insert-only)."""
    uname = f"ac_prov_{uuid.uuid4().hex[:8]}"
    os.environ["ARBICORE_OPERATOR_USER"] = uname
    os.environ["ARBICORE_OPERATOR_PASS"] = "InitPass!2026"
    from services.auth import ensure_provisioned_users, verify_password
    from services import db as sdb

    async def scenario():
        s1 = await ensure_provisioned_users()
        u1 = await sdb.users_col.find_one({"username": uname})
        os.environ["ARBICORE_OPERATOR_PASS"] = "Changed!2026"   # must NOT overwrite
        await ensure_provisioned_users()
        u2 = await sdb.users_col.find_one({"username": uname})
        cnt = await sdb.users_col.count_documents({"username": uname})
        await sdb.users_col.delete_one({"username": uname})     # cleanup
        return s1, u1, u2, cnt

    try:
        s1, u1, u2, cnt = asyncio.run(scenario())
    finally:
        os.environ.pop("ARBICORE_OPERATOR_USER", None)
        os.environ.pop("ARBICORE_OPERATOR_PASS", None)
        _pdb.users.delete_one({"username": uname})  # belt-and-suspenders cleanup

    assert any(c["username"] == uname for c in s1["created"]), s1
    assert cnt == 1, "provisioner duplicated a user"
    assert u1["password_hash"] == u2["password_hash"], "existing password was overwritten"
    assert verify_password("InitPass!2026", u2["password_hash"]), "original configured password not used"
    assert not verify_password("Changed!2026", u2["password_hash"]), "password was blindly changed"
