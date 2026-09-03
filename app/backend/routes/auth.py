"""Auth endpoints — single-admin system with first-run setup flow.
Registration locks automatically after the first (and only) account is created.

First-admin bootstrap is FAIL-CLOSED (P0 security):
  UNINITIALIZED → AUTHORIZED_BOOTSTRAP → ADMIN_CREATED → BOOTSTRAP_LOCKED

Creating the sole administrator requires an independent, server-side
authorization token (``ARBICORE_BOOTSTRAP_TOKEN``) presented by the operator
in the ``X-Bootstrap-Token`` header. The mere absence of an administrator does
NOT authorize an anonymous visitor to create one. If no token is provisioned
server-side, bootstrap is DISABLED (503) — never open."""
import hmac
import logging
import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.models import new_id, now_iso
from services import auth, db

router = APIRouter(prefix="/api/auth", tags=["auth"])

_logger = logging.getLogger("arbicore.auth.bootstrap")

# Fixed-id sentinel that makes first-admin creation atomic across concurrent
# requests / workers. settings_col has a unique index on "key", so at most one
# request can ever insert it — the rest get DuplicateKeyError → 403.
_BOOTSTRAP_LOCK_KEY = "auth_bootstrap_lock"


def _bootstrap_token() -> str:
    return (os.environ.get("ARBICORE_BOOTSTRAP_TOKEN") or "").strip()


def _authorize_bootstrap(request: Request) -> None:
    """Fail-closed, server-side authorization for first-admin creation."""
    expected = _bootstrap_token()
    if not expected:
        _logger.warning("bootstrap attempt rejected: no ARBICORE_BOOTSTRAP_TOKEN provisioned")
        raise HTTPException(
            503,
            "First-admin bootstrap is disabled: no server-side bootstrap token is "
            "provisioned. Set ARBICORE_BOOTSTRAP_TOKEN in the deployment environment.",
        )
    provided = (request.headers.get("X-Bootstrap-Token") or "").strip()
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(403, "Invalid or missing bootstrap authorization token")


class SetupBody(BaseModel):
    username: str = Field(min_length=3, max_length=40)
    password: str = Field(min_length=8, max_length=128)


class LoginBody(BaseModel):
    username: str
    password: str


class ChangePasswordBody(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


@router.get("/status")
async def auth_status():
    count = await db.users_col.count_documents({})
    # Intentionally does NOT disclose whether a bootstrap token is provisioned.
    return {"setup_complete": count > 0, "auth_required": True,
            "bootstrap_requires_token": True}


@router.post("/setup")
async def setup(body: SetupBody, request: Request, response: Response):
    # ── P0: independent server-side authorization (fail-closed) ──
    _authorize_bootstrap(request)

    # ── atomic single-admin guard ──
    # Ensure the uniqueness constraint exists BEFORE relying on it (idempotent;
    # a fresh DB may not have run ensure_indexes yet). create_index only returns
    # once the unique index is in place, so the insert below is truly atomic
    # across concurrent authorized requests / workers.
    await db.settings_col.create_index("key", unique=True)
    await db.users_col.create_index("username", unique=True)
    # Acquire the one-shot bootstrap lock BEFORE any user check/insert so two
    # concurrent authorized requests cannot each create an admin.
    try:
        await db.settings_col.insert_one(
            {"key": _BOOTSTRAP_LOCK_KEY, "locked_at": now_iso()})
    except DuplicateKeyError:
        raise HTTPException(403, "Setup already completed — registration is locked (single-admin system)")

    # Defense in depth: if a user somehow exists without the lock (e.g. env
    # provisioning seeded one), keep the lock and refuse.
    if await db.users_col.count_documents({}) > 0:
        raise HTTPException(403, "Setup already completed — registration is locked (single-admin system)")

    username = body.username.strip().lower()
    user = {"id": new_id(), "username": username,
            "password_hash": auth.hash_password(body.password),
            "role": "admin", "session_version": 1,
            "created_at": now_iso(), "updated_at": now_iso()}
    try:
        await db.users_col.insert_one(dict(user))
    except DuplicateKeyError:
        raise HTTPException(403, "Setup already completed — registration is locked (single-admin system)")
    _logger.info("first administrator created (bootstrap locked): username=%s", username)
    auth.set_auth_cookies(response, user)
    return auth.public_user(user)


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    username = body.username.strip().lower()
    # Proxy-aware, defence-in-depth brute-force keys:
    #  * username-scoped  → cannot be bypassed by rotating source IPs (the
    #    primary control for a small/single-admin system behind an ingress).
    #  * ip:username       → real client IP resolved from X-Forwarded-For so a
    #    shared proxy pod IP does not fragment or over-broaden the counter.
    identifiers = [f"user:{username}", f"ip:{auth.client_ip(request)}:{username}"]
    for ident in identifiers:
        await auth.check_lockout(ident)
    user = await db.users_col.find_one({"username": username}, {"_id": 0})
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        for ident in identifiers:
            await auth.register_failure(ident)
        raise HTTPException(401, "Invalid username or password")
    for ident in identifiers:
        await auth.clear_failures(ident)
    auth.set_auth_cookies(response, user)
    return auth.public_user(user)


@router.get("/me")
async def me(request: Request):
    return await auth.get_current_user(request)


@router.post("/refresh")
async def refresh(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "No refresh token")
    payload = auth.decode_token(token, "refresh")
    user = await auth.get_user_by_payload(payload)
    auth.set_access_cookie(response, user)
    return {"ok": True}


@router.post("/logout")
async def logout(response: Response):
    auth.clear_auth_cookies(response)
    return {"ok": True, "message": "Logged out"}


@router.post("/logout-all")
async def logout_all(request: Request, response: Response):
    user = await auth.get_current_user(request)
    await db.users_col.update_one({"id": user["id"]}, {"$inc": {"session_version": 1},
                                                       "$set": {"updated_at": now_iso()}})
    auth.clear_auth_cookies(response)
    return {"ok": True, "message": "All sessions revoked"}


@router.post("/change-password")
async def change_password(body: ChangePasswordBody, request: Request, response: Response):
    current = await auth.get_current_user(request)
    user = await db.users_col.find_one({"id": current["id"]}, {"_id": 0})
    if not auth.verify_password(body.current_password, user["password_hash"]):
        raise HTTPException(401, "Current password is incorrect")
    sv = user.get("session_version", 1) + 1
    await db.users_col.update_one({"id": user["id"]}, {"$set": {
        "password_hash": auth.hash_password(body.new_password),
        "session_version": sv, "updated_at": now_iso()}})
    user["session_version"] = sv
    auth.set_auth_cookies(response, user)  # keep THIS session alive; all others die
    return {"ok": True, "message": "Password changed — all other sessions revoked"}
