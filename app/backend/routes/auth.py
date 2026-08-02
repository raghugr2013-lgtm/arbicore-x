"""Auth endpoints — single-admin system with first-run setup flow.
Registration locks automatically after the first (and only) account is created."""
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.models import new_id, now_iso
from services import auth, db

router = APIRouter(prefix="/api/auth", tags=["auth"])


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
    return {"setup_complete": count > 0, "auth_required": True}


@router.post("/setup")
async def setup(body: SetupBody, response: Response):
    if await db.users_col.count_documents({}) > 0:
        raise HTTPException(403, "Setup already completed — registration is locked (single-admin system)")
    username = body.username.strip().lower()
    user = {"id": new_id(), "username": username,
            "password_hash": auth.hash_password(body.password),
            "role": "admin", "session_version": 1,
            "created_at": now_iso(), "updated_at": now_iso()}
    await db.users_col.insert_one(dict(user))
    auth.set_auth_cookies(response, user)
    return auth.public_user(user)


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    username = body.username.strip().lower()
    ip = request.client.host if request.client else "unknown"
    identifier = f"{ip}:{username}"
    await auth.check_lockout(identifier)
    user = await db.users_col.find_one({"username": username}, {"_id": 0})
    if not user or not auth.verify_password(body.password, user["password_hash"]):
        await auth.register_failure(identifier)
        raise HTTPException(401, "Invalid username or password")
    await auth.clear_failures(identifier)
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
    response.set_cookie("access_token", auth.create_access_token(user), httponly=True,
                        secure=False, samesite="lax", max_age=auth.ACCESS_TTL_MIN * 60, path="/")
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
