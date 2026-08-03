"""v2.1.1 — Env-var name mismatch fix.

Validates:
  * Seed reads ``ARBICORE_ADMIN_PASS`` first, then falls back to
    ``ARBICORE_ADMIN_PASSWORD``, then to the hardcoded default.
  * When an existing seed doc still holds the hardcoded default's hash
    AND a real env secret is now present, the seed routine self-heals
    by rehashing that ONE field. All other fields preserved.
  * A doc whose hash matches the real env value is NEVER overwritten.
  * With no env secret set at all, behaviour matches v2.1.0 exactly.
"""
from __future__ import annotations

import os
import uuid

import bcrypt
import pytest
from motor.motor_asyncio import AsyncIOMotorClient

pytestmark = pytest.mark.asyncio


@pytest.fixture()
async def scratch_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    name = f"auth_v211_test_{uuid.uuid4().hex[:8]}"
    db = client[name]
    try:
        yield db
    finally:
        await client.drop_database(name)
        client.close()


async def test_seed_prefers_new_env_var_name(scratch_db, monkeypatch):
    from arbicore.auth import _hash_password, authenticate, ensure_seed_users
    monkeypatch.setenv("ARBICORE_ADMIN_PASS", "new-pass-xyz")
    monkeypatch.delenv("ARBICORE_ADMIN_PASSWORD", raising=False)
    monkeypatch.setenv("ARBICORE_OPERATOR_PASS", "op-pass-xyz")
    monkeypatch.delenv("ARBICORE_OPERATOR_PASSWORD", raising=False)

    summary = await ensure_seed_users(scratch_db)
    assert summary["ok"] is True
    assert "admin" in summary["inserted"]
    assert "operator" in summary["inserted"]

    # bcrypt-verify the stored hashes match the env values
    admin = await scratch_db.auth_users.find_one({"username": "admin"})
    assert bcrypt.checkpw(b"new-pass-xyz", admin["password_hash"].encode())
    # and authenticate() succeeds end-to-end
    assert (await authenticate(scratch_db, "admin", "new-pass-xyz")) is not None


async def test_seed_falls_back_to_old_env_var(scratch_db, monkeypatch):
    from arbicore.auth import ensure_seed_users, authenticate
    monkeypatch.delenv("ARBICORE_ADMIN_PASS", raising=False)
    monkeypatch.setenv("ARBICORE_ADMIN_PASSWORD", "legacy-plain")
    monkeypatch.delenv("ARBICORE_OPERATOR_PASS", raising=False)
    monkeypatch.setenv("ARBICORE_OPERATOR_PASSWORD", "op-legacy")

    await ensure_seed_users(scratch_db)
    assert (await authenticate(
        scratch_db, "admin", "legacy-plain")) is not None


async def test_seed_falls_back_to_default_when_no_env(scratch_db,
                                                       monkeypatch):
    from arbicore.auth import ensure_seed_users, authenticate
    for v in ("ARBICORE_ADMIN_PASS", "ARBICORE_ADMIN_PASSWORD",
              "ARBICORE_OPERATOR_PASS", "ARBICORE_OPERATOR_PASSWORD"):
        monkeypatch.delenv(v, raising=False)

    await ensure_seed_users(scratch_db)
    assert (await authenticate(
        scratch_db, "admin", "admin-shadow-2026")) is not None


async def test_self_heal_rehashes_stale_default(scratch_db, monkeypatch):
    """The VPS regression: a doc seeded from the hardcoded default,
    later paired with a real env secret. v2.1.1 must repair the hash."""
    from arbicore.auth import (
        _hash_password, authenticate, ensure_seed_users, _iso,
    )
    # 1. simulate the pre-v2.1.1 stale state: hash was made from the
    #    hardcoded default, no env secret was set at seed time
    await scratch_db.auth_users.insert_many([
        {"user_id": "stale-admin", "username": "admin", "role": "admin",
         "active": True, "created_at": _iso(),
         "password_hash": _hash_password("admin-shadow-2026")},
        {"user_id": "stale-op",    "username": "operator",
         "role": "operator", "active": True, "created_at": _iso(),
         "password_hash": _hash_password("operator-shadow-2026")},
    ])

    # 2. operator now sets real secrets (matching how the VPS is configured)
    monkeypatch.setenv("ARBICORE_ADMIN_PASS", "Arbicorex@2026")
    monkeypatch.setenv("ARBICORE_OPERATOR_PASS", "Op@2026")
    monkeypatch.delenv("ARBICORE_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ARBICORE_OPERATOR_PASSWORD", raising=False)

    # 3. seed routine runs on next boot
    summary = await ensure_seed_users(scratch_db)

    # 4. self-heal must have happened for BOTH users
    assert set(summary["rehashed_from_default"]) == {"admin", "operator"}
    assert summary["inserted"] == []
    assert set(summary["existed_before"]) == {"admin", "operator"}

    # 5. login now succeeds with the real env secret
    admin_ok = await authenticate(scratch_db, "admin", "Arbicorex@2026")
    op_ok    = await authenticate(scratch_db, "operator", "Op@2026")
    assert admin_ok is not None
    assert op_ok is not None

    # 6. only password_hash changed — other fields preserved
    admin = await scratch_db.auth_users.find_one({"username": "admin"})
    assert admin["user_id"] == "stale-admin"
    assert admin["role"] == "admin"
    assert admin["active"] is True


async def test_self_heal_never_overwrites_matching_hash(scratch_db,
                                                        monkeypatch):
    """Idempotency guard: on the boot AFTER a self-heal, the hash
    already matches the real env value; the seed MUST NOT touch it."""
    from arbicore.auth import (
        _hash_password, ensure_seed_users, _iso,
    )
    # doc's hash already matches the real env value
    real_pw = "Arbicorex@2026"
    good_hash = _hash_password(real_pw)
    await scratch_db.auth_users.insert_one({
        "user_id": "healthy-admin", "username": "admin", "role": "admin",
        "active": True, "created_at": _iso(),
        "password_hash": good_hash,
    })
    monkeypatch.setenv("ARBICORE_ADMIN_PASS", real_pw)
    monkeypatch.setenv("ARBICORE_OPERATOR_PASS", "op-pass")
    monkeypatch.delenv("ARBICORE_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("ARBICORE_OPERATOR_PASSWORD", raising=False)

    summary = await ensure_seed_users(scratch_db)

    assert "admin" not in summary["rehashed_from_default"]
    admin = await scratch_db.auth_users.find_one({"username": "admin"})
    assert admin["password_hash"] == good_hash    # byte-identical
