"""API Key Vault endpoints — encrypted storage + health testing for read-only keys."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from services import key_health, vault
from services.auth import require_auth

router = APIRouter(prefix="/api/vault", tags=["vault"], dependencies=[Depends(require_auth)])


class KeyCreate(BaseModel):
    exchange: str
    label: Optional[str] = None
    api_key: str = Field(min_length=8)
    api_secret: str = Field(min_length=8)
    passphrase: Optional[str] = None  # BitMart "memo" etc.


@router.get("/keys")
async def list_keys():
    return await vault.list_keys()


@router.post("/keys")
async def add_key(body: KeyCreate):
    exchange = body.exchange.strip().lower()
    if exchange not in vault.SUPPORTED_EXCHANGES:
        raise HTTPException(400, f"Unsupported exchange; allowed: {list(vault.SUPPORTED_EXCHANGES)}")
    return await vault.add_key(exchange, body.label, body.api_key.strip(),
                               body.api_secret.strip(),
                               body.passphrase.strip() if body.passphrase else None)


@router.delete("/keys/{key_id}")
async def delete_key(key_id: str):
    if not await vault.delete_key(key_id):
        raise HTTPException(404, "Key not found")
    return {"ok": True}


@router.post("/keys/{key_id}/test")
async def test_key(key_id: str):
    creds = await vault.get_credentials(key_id)
    if not creds:
        raise HTTPException(404, "Key not found")
    result = await key_health.run_test(creds["exchange"], creds["api_key"],
                                       creds["api_secret"], creds["passphrase"])
    await vault.set_test_result(key_id, result["ok"], result["message"])
    return {**result, "key": await vault.get_key_public(key_id)}
