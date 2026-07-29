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


def set_auth_cookies(response, user: dict):
    response.set_cookie("access_token", create_access_token(user), httponly=True,
                        secure=False, samesite="lax", max_age=ACCESS_TTL_MIN * 60, path="/")
    response.set_cookie("refresh_token", create_refresh_token(user), httponly=True,
                        secure=False, samesite="lax", max_age=REFRESH_TTL_DAYS * 86400, path="/")


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
