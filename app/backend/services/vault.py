"""Encrypted API-key vault — Fernet (AES-128-CBC + HMAC-SHA256) at rest.
Secrets are write-only via the API: they are encrypted on insert and never
returned to the client. Only the backend health tester ever decrypts them."""
import os

from cryptography.fernet import Fernet

from core.models import new_id, now_iso
from services import db

SUPPORTED_EXCHANGES = ("xt", "mexc", "gate", "bitmart", "coinstore")


def _fernet() -> Fernet:
    return Fernet(os.environ["VAULT_KEY"].encode())


def encrypt(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def mask(s: str) -> str:
    if not s:
        return ""
    if len(s) <= 8:
        return s[:2] + "…"
    return f"{s[:4]}…{s[-4:]}"


def _public(doc: dict) -> dict:
    return {k: doc.get(k) for k in ("id", "exchange", "label", "key_mask", "status",
                                    "last_tested_at", "last_test_message", "created_at")}


async def list_keys():
    docs = await db.api_keys_col.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    return [_public(d) for d in docs]


async def add_key(exchange: str, label: str, api_key: str, api_secret: str, passphrase: str = None):
    doc = {"id": new_id(), "exchange": exchange, "label": label or f"{exchange} read-only",
           "key_enc": encrypt(api_key), "secret_enc": encrypt(api_secret),
           "passphrase_enc": encrypt(passphrase) if passphrase else None,
           "key_mask": mask(api_key), "status": "untested",
           "last_tested_at": None, "last_test_message": None,
           "created_at": now_iso(), "updated_at": now_iso()}
    await db.api_keys_col.insert_one(dict(doc))
    return _public(doc)


async def get_credentials(key_id: str):
    doc = await db.api_keys_col.find_one({"id": key_id}, {"_id": 0})
    if not doc:
        return None
    return {"exchange": doc["exchange"],
            "api_key": decrypt(doc["key_enc"]), "api_secret": decrypt(doc["secret_enc"]),
            "passphrase": decrypt(doc["passphrase_enc"]) if doc.get("passphrase_enc") else None}


async def delete_key(key_id: str) -> bool:
    res = await db.api_keys_col.delete_one({"id": key_id})
    return res.deleted_count > 0


async def set_test_result(key_id: str, ok: bool, message: str):
    await db.api_keys_col.update_one({"id": key_id}, {"$set": {
        "status": "healthy" if ok else "error",
        "last_tested_at": now_iso(), "last_test_message": message, "updated_at": now_iso()}})


async def get_key_public(key_id: str):
    doc = await db.api_keys_col.find_one({"id": key_id}, {"_id": 0})
    return _public(doc) if doc else None
