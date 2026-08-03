"""ArbiCore X — authentication module (v2.0.3).

JWT session issuance + password hashing + user seeding + role-based
authorization decorator.  Backed by Mongo collection ``auth_users``.

Default users seeded at startup if the collection is empty:
  * admin    (role=admin)     — password from env ARBICORE_ADMIN_PASSWORD
                                 or fallback ``admin-shadow-2026``
  * operator (role=operator)  — password from env ARBICORE_OPERATOR_PASSWORD
                                 or fallback ``operator-shadow-2026``

JWT signing key from env ARBICORE_JWT_SECRET (must be >= 32 chars) or a
deterministic install-scoped fallback (dev only).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import bcrypt
import jwt

logger = logging.getLogger(__name__)

USERS_COLL = "auth_users"
SESSIONS_COLL = "auth_sessions"
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 24


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _now().isoformat().replace("+00:00", "Z")


def _jwt_secret() -> str:
    secret = os.environ.get("ARBICORE_JWT_SECRET", "").strip()
    if secret and len(secret) >= 32:
        return secret
    # dev / install fallback — deterministic per install so restarts do not
    # invalidate every session.  The real secret is written into .env by
    # the operator during deployment (see docs/V2_MIGRATION_GUIDE.md).
    mongo_url = os.environ.get("MONGO_URL", "")
    seed = f"arbicore-x-dev-{mongo_url}"
    return hashlib.sha256(seed.encode()).hexdigest()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


async def ensure_seed_users(db: Any) -> Dict[str, Any]:
    """Seed default admin + operator accounts idempotently.

    Contract:
      * The function ALWAYS reports the truth about what happened.
      * "Seeded N users" is logged only if N documents were actually inserted.
      * If users already exist they are reported as present, not re-seeded.
      * A final verification step confirms both `admin` and `operator` exist
        by username in the `auth_users` collection before returning.

    Returns a summary dict:
        {
          "collection": "auth_users",
          "database": "<db_name>",
          "existed_before": [...usernames...],
          "inserted": [...usernames...],
          "skipped_existing": [...usernames...],
          "verified": {"admin": bool, "operator": bool},
          "ok": bool,
        }
    """
    coll = db[USERS_COLL]

    # ensure the username uniqueness index exists BEFORE any insert
    try:
        await coll.create_index([("username", 1)], unique=True, name="username_uniq")
    except Exception:
        pass  # already exists

    desired = [
        {
            "username": "admin",
            "role": "admin",
            "password_env": "ARBICORE_ADMIN_PASSWORD",
            "password_default": "admin-shadow-2026",
        },
        {
            "username": "operator",
            "role": "operator",
            "password_env": "ARBICORE_OPERATOR_PASSWORD",
            "password_default": "operator-shadow-2026",
        },
    ]

    existed_before: list = []
    inserted: list = []
    skipped_existing: list = []

    for spec in desired:
        found = await coll.find_one({"username": spec["username"]})
        if found:
            existed_before.append(spec["username"])
            skipped_existing.append(spec["username"])
            continue
        password = os.environ.get(spec["password_env"], spec["password_default"])
        doc = {
            "user_id": str(uuid.uuid4()),
            "username": spec["username"],
            "role": spec["role"],
            "password_hash": _hash_password(password),
            "created_at": _iso(),
            "active": True,
        }
        try:
            await coll.insert_one(doc)
            inserted.append(spec["username"])
        except Exception as exc:  # noqa: BLE001
            logger.error("auth: FAILED to insert seed user %r: %s", spec["username"], exc)

    # verification — never trust the earlier steps blindly.
    # NOTE: matches the tolerant filter used by ``find_user`` — a
    # missing ``active`` field is treated as active-by-default (v2.0.7
    # fix for VPS legacy documents).
    verified = {}
    for u in ("admin", "operator"):
        doc = await coll.find_one({"username": u, "active": {"$ne": False}})
        verified[u] = bool(doc)

    ok = verified["admin"] and verified["operator"]

    db_name = getattr(db, "name", "?")
    summary = {
        "collection": USERS_COLL,
        "database": db_name,
        "existed_before": existed_before,
        "inserted": inserted,
        "skipped_existing": skipped_existing,
        "verified": verified,
        "ok": ok,
    }

    # truthful logging
    if inserted and skipped_existing:
        logger.info(
            "auth: seeded %d new user(s) [%s] in %s.%s; %d already existed [%s]",
            len(inserted), ", ".join(inserted), db_name, USERS_COLL,
            len(skipped_existing), ", ".join(skipped_existing),
        )
    elif inserted:
        logger.info(
            "auth: seeded %d new user(s) [%s] in %s.%s",
            len(inserted), ", ".join(inserted), db_name, USERS_COLL,
        )
    elif skipped_existing:
        logger.info(
            "auth: all %d default user(s) already exist in %s.%s [%s] — no seed needed",
            len(skipped_existing), db_name, USERS_COLL, ", ".join(skipped_existing),
        )
    else:
        logger.warning("auth: seed routine wrote nothing and found nothing — check DB connection")

    if not ok:
        missing = [u for u, v in verified.items() if not v]
        logger.error(
            "auth: POST-SEED VERIFICATION FAILED — missing users in %s.%s: %s",
            db_name, USERS_COLL, ", ".join(missing),
        )
    else:
        logger.info(
            "auth: post-seed verification OK — admin=%s, operator=%s present in %s.%s",
            verified["admin"], verified["operator"], db_name, USERS_COLL,
        )

    return summary


async def find_user(db: Any, username: str) -> Optional[Dict[str, Any]]:
    """Lookup a user by username, tolerating legacy documents.

    Historical bug (v2.0.6 → v2.0.7): the filter was
    ``{"username": u, "active": True}`` which silently rejected any
    account whose ``active`` field was missing (e.g. a document created
    or repaired by an out-of-band password-reset script that only wrote
    ``password_hash``). The symptom on the VPS was ``invalid_credentials``
    on login after a password reset even though the hash matched.

    The current lookup only rejects accounts that are EXPLICITLY
    deactivated (``active: false``). Missing-or-null ``active`` is
    treated as active-by-default, matching how the seed routine has
    always stamped new documents.
    """
    return await db[USERS_COLL].find_one({
        "username": username,
        "active": {"$ne": False},
    })


def issue_token(user: Dict[str, Any]) -> Dict[str, Any]:
    now = _now()
    exp = now + timedelta(hours=JWT_TTL_HOURS)
    payload = {
        "sub": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    token = jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)
    return {
        "token": token,
        "expires_at": exp.isoformat().replace("+00:00", "Z"),
        "issued_at": now.isoformat().replace("+00:00", "Z"),
        "jti": payload["jti"],
    }


async def record_session(db: Any, user: Dict[str, Any], token_info: Dict[str, Any]) -> None:
    await db[SESSIONS_COLL].insert_one({
        "jti": token_info["jti"],
        "user_id": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "issued_at": token_info["issued_at"],
        "expires_at": token_info["expires_at"],
        "revoked": False,
    })
    try:
        # TTL cleanup 7 days after nominal expiry (retention for audit)
        await db[SESSIONS_COLL].create_index(
            [("expires_at", 1)], expireAfterSeconds=7 * 24 * 3600, name="ttl_sessions"
        )
    except Exception:
        pass


async def revoke_session(db: Any, jti: str) -> bool:
    res = await db[SESSIONS_COLL].update_one({"jti": jti}, {"$set": {"revoked": True}})
    return res.modified_count > 0


async def is_session_revoked(db: Any, jti: str) -> bool:
    doc = await db[SESSIONS_COLL].find_one({"jti": jti}, {"revoked": 1})
    return bool(doc and doc.get("revoked"))


def decode_token(token: str) -> Dict[str, Any]:
    return jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])


async def authenticate(db: Any, username: str, password: str) -> Optional[Dict[str, Any]]:
    if not username or not password:
        return None
    user = await find_user(db, username.strip())
    if not user:
        return None
    if not _verify_password(password, user.get("password_hash", "")):
        return None
    return user


# Constant-time username comparison helper (unused today but useful in
# rate-limit style extensions).
def safe_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
