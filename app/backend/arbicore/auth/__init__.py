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


async def ensure_seed_users(db: Any) -> None:
    coll = db[USERS_COLL]
    count = await coll.estimated_document_count()
    if count > 0:
        return
    seed = [
        {
            "user_id": str(uuid.uuid4()),
            "username": "admin",
            "role": "admin",
            "password_hash": _hash_password(
                os.environ.get("ARBICORE_ADMIN_PASSWORD", "admin-shadow-2026")
            ),
            "created_at": _iso(),
            "active": True,
        },
        {
            "user_id": str(uuid.uuid4()),
            "username": "operator",
            "role": "operator",
            "password_hash": _hash_password(
                os.environ.get("ARBICORE_OPERATOR_PASSWORD", "operator-shadow-2026")
            ),
            "created_at": _iso(),
            "active": True,
        },
    ]
    await coll.insert_many(seed)
    try:
        await coll.create_index([("username", 1)], unique=True, name="username_uniq")
    except Exception:
        pass
    logger.info("auth: seeded 2 default users (admin, operator)")


async def find_user(db: Any, username: str) -> Optional[Dict[str, Any]]:
    return await db[USERS_COLL].find_one({"username": username, "active": True})


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
