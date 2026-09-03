"""Single-admin JWT auth — bcrypt hashing, access/refresh httpOnly cookies,
session versioning (logout-all), and brute-force lockout."""
import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import HTTPException, Request

from services import db

JWT_ALGORITHM = "HS256"
ACCESS_TTL_MIN = 30
REFRESH_TTL_DAYS = 7
MAX_ATTEMPTS = 5
LOCKOUT_MIN = 15


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def _now():
    return datetime.now(timezone.utc)


def client_ip(request) -> str:
    """Resolve the real client IP behind a reverse proxy / k8s ingress.

    Uses the left-most hop of X-Forwarded-For (the original client) and falls
    back to the direct socket peer. Without this, request.client.host is the
    proxy pod address, which fragments brute-force counters across pods and
    silently defeats the lockout."""
    xff = request.headers.get("x-forwarded-for") or ""
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    real = request.headers.get("x-real-ip")
    if real:
        return real.strip()
    return request.client.host if request.client else "unknown"


# ---------- passwords ----------

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------- tokens ----------

def create_access_token(user: dict) -> str:
    payload = {"sub": user["id"], "username": user["username"],
               "sv": user.get("session_version", 1), "type": "access",
               "exp": _now() + timedelta(minutes=ACCESS_TTL_MIN)}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user: dict) -> str:
    payload = {"sub": user["id"], "sv": user.get("session_version", 1), "type": "refresh",
               "exp": _now() + timedelta(days=REFRESH_TTL_DAYS)}
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str, expected_type: str) -> dict:
    try:
        payload = jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def _cookie_flags() -> dict:
    """Cookie security flags. Defaults are safe for the http preview ingress
    (which itself upgrades to Secure); a direct HTTPS deployment should set
    ARBICORE_COOKIE_SECURE=true so the Secure flag is emitted at the origin."""
    secure = (os.environ.get("ARBICORE_COOKIE_SECURE") or "").strip().lower() in ("1", "true", "yes")
    samesite = (os.environ.get("ARBICORE_COOKIE_SAMESITE") or "lax").strip().lower()
    return {"secure": secure, "samesite": samesite}


def set_auth_cookies(response, user: dict):
    flags = _cookie_flags()
    response.set_cookie("access_token", create_access_token(user), httponly=True,
                        secure=flags["secure"], samesite=flags["samesite"],
                        max_age=ACCESS_TTL_MIN * 60, path="/")
    response.set_cookie("refresh_token", create_refresh_token(user), httponly=True,
                        secure=flags["secure"], samesite=flags["samesite"],
                        max_age=REFRESH_TTL_DAYS * 86400, path="/")


def set_access_cookie(response, user: dict):
    """Issue only the access cookie (used by /refresh). Single source of truth
    for cookie flags — avoids drift with set_auth_cookies."""
    flags = _cookie_flags()
    response.set_cookie("access_token", create_access_token(user), httponly=True,
                        secure=flags["secure"], samesite=flags["samesite"],
                        max_age=ACCESS_TTL_MIN * 60, path="/")


def clear_auth_cookies(response):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")


# ---------- user resolution ----------

def public_user(user: dict) -> dict:
    return {"id": user["id"], "username": user["username"],
            "role": user.get("role", "admin"), "created_at": user.get("created_at")}


async def get_user_by_payload(payload: dict) -> dict:
    user = await db.users_col.find_one({"id": payload.get("sub")}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if payload.get("sv") != user.get("session_version", 1):
        raise HTTPException(status_code=401, detail="Session revoked")
    return user


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        header = request.headers.get("Authorization", "")
        if header.startswith("Bearer "):
            token = header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(token, "access")
    return public_user(await get_user_by_payload(payload))


require_auth = get_current_user


# ---------- brute force protection ----------

async def check_lockout(identifier: str):
    doc = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    if doc and doc.get("locked_until") and doc["locked_until"] > _now().isoformat():
        raise HTTPException(status_code=429,
                            detail=f"Too many failed attempts — locked until {doc['locked_until'][:16]} UTC")


async def register_failure(identifier: str):
    doc = await db.login_attempts.find_one({"identifier": identifier}, {"_id": 0})
    count = (doc or {}).get("count", 0) + 1
    update = {"identifier": identifier, "count": count, "last_at": _now().isoformat()}
    if count >= MAX_ATTEMPTS:
        update["locked_until"] = (_now() + timedelta(minutes=LOCKOUT_MIN)).isoformat()
        update["count"] = 0
    await db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)


async def clear_failures(identifier: str):
    await db.login_attempts.delete_one({"identifier": identifier})


# ---------- canonical startup provisioning ----------
# v2.9.4 — deterministic, idempotent seeding of admin/operator into the SAME
# `users` collection that login reads. Resolves the auth source-of-truth drift
# (legacy `auth_users` seed was gated off, leaving a fresh DB with zero users →
# /api/auth/login 401). Insert-ONLY: an existing user is never overwritten, so
# operator-changed passwords are preserved. Skips gracefully (no crash, no weak
# default) when a credential env is absent. Never logs secret values.

import logging as _logging

_seed_logger = _logging.getLogger("arbicore.auth.provision")

# role → (username env, password env candidates)
_PROVISION_SPECS = (
    ("admin",    "ARBICORE_ADMIN_USER",    ("ARBICORE_ADMIN_PASS", "ARBICORE_ADMIN_PASSWORD")),
    ("operator", "ARBICORE_OPERATOR_USER", ("ARBICORE_OPERATOR_PASS", "ARBICORE_OPERATOR_PASSWORD")),
)


def _first_env(*keys: str) -> str:
    for k in keys:
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    return ""


async def ensure_provisioned_users() -> dict:
    """Idempotently provision admin (+ operator) from environment credentials
    into the canonical ``users`` collection. Safe to run on every boot and
    under concurrent workers (unique index on username + DuplicateKeyError
    guard). Returns a non-secret summary for the boot log."""
    from core.models import new_id, now_iso
    from pymongo.errors import DuplicateKeyError

    summary: dict = {"collection": db.users_col.name, "created": [], "existed": [],
                     "skipped": [], "jwt_secret_present": bool(os.environ.get("JWT_SECRET"))}

    # Ensure the uniqueness guard exists before we insert (idempotent).
    try:
        await db.users_col.create_index("username", unique=True)
    except Exception:  # noqa: BLE001
        pass

    for role, user_env, pass_envs in _PROVISION_SPECS:
        username = (_first_env(user_env) or role).strip().lower()
        password = _first_env(*pass_envs)
        if not password:
            summary["skipped"].append({"role": role, "username": username,
                                        "reason": f"no password env set ({' / '.join(pass_envs)})"})
            continue
        existing = await db.users_col.find_one({"username": username}, {"_id": 0, "password_hash": 0})
        if existing:
            # Preserve existing record — never blindly overwrite the password.
            summary["existed"].append({"username": username, "role": existing.get("role")})
            continue
        doc = {"id": new_id(), "username": username,
               "password_hash": hash_password(password),
               "role": role, "session_version": 1,
               "created_at": now_iso(), "updated_at": now_iso()}
        try:
            await db.users_col.insert_one(dict(doc))
            summary["created"].append({"username": username, "role": role})
        except DuplicateKeyError:
            summary["existed"].append({"username": username, "role": role})

    if not summary["jwt_secret_present"]:
        _seed_logger.warning("auth provision: JWT_SECRET is not set — login cannot "
                             "issue tokens until it is configured in the environment")
    _seed_logger.info("auth provision (canonical `users`): created=%s existed=%s skipped=%s",
                      [c["username"] for c in summary["created"]],
                      [e["username"] for e in summary["existed"]],
                      [s["role"] for s in summary["skipped"]])
    return summary
