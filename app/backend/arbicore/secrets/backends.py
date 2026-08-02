"""Wave 6A · Secret backends.

Design commitments:
    * ``SecretBackend`` is a Protocol — HSM/KMS/Fireblocks/Turnkey
      backends drop in without touching business logic.
    * Backends never leak plaintext material through public APIs.
    * ``FernetSecretBackend`` (MVP) uses the operator-supplied
      ``VAULT_KEY`` env from the existing canonical vault
      (``services/vault.py``) so we don't fork the encryption
      substrate.

Every secret carries a **handle** — an opaque `SecretHandle` value
object that identifies the secret without embedding its bytes.  The
handle is what other subsystems (wallet registry, signer) store; the
backend is the only party that ever sees plaintext.
"""
from __future__ import annotations

import base64
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Protocol

from cryptography.fernet import Fernet, InvalidToken


CAPABILITY_SCOPES: tuple = (
    "cex_read",
    "cex_trade",
    "cex_withdraw",
    "evm_sign",
    "custom",
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SecretHandle:
    """Opaque identifier for a stored secret.

    Serialised into ``wallet_registry`` (and, later, the signer
    registry) so operational callers can *reference* a secret without
    ever holding its bytes.
    """
    handle_id: str
    scope: str
    provider: str
    algorithm: str
    created_at: str
    label: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "handle_id": self.handle_id,
            "scope": self.scope,
            "provider": self.provider,
            "algorithm": self.algorithm,
            "created_at": self.created_at,
            "label": self.label,
        }


class SecretBackend(Protocol):
    """Backend contract.  Drop-in surface for future HSM / KMS providers."""

    provider: str

    def is_available(self) -> bool: ...

    async def put(self, plaintext: bytes, *, scope: str, algorithm: str,
                  label: str = "") -> SecretHandle: ...

    async def get(self, handle_id: str) -> Optional[bytes]:
        """Return plaintext material for a handle.  ONLY the signer path
        may call this — it MUST never surface through public REST."""

    async def list_handles(self) -> list:
        """Return handle metadata (no plaintext)."""

    async def delete(self, handle_id: str) -> bool: ...


# ---------------------------------------------------------------------------
# FernetSecretBackend — MVP
# ---------------------------------------------------------------------------


class FernetSecretBackend:
    """MVP backend that encrypts secret material with Fernet.

    Storage is a Mongo collection so the substrate is durable and
    audit-friendly; the encryption key comes from ``VAULT_KEY`` (same
    key the canonical vault already uses — we do NOT introduce a new
    key material lifecycle).
    """

    provider = "fernet_local"

    def __init__(self, db, collection: str = "arbicore_secrets"):
        self._db = db
        self._coll = db[collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._coll.create_index("handle_id", unique=True)
        await self._coll.create_index([("scope", 1), ("created_at", -1)])
        self._indexes_ready = True

    def _fernet(self) -> Fernet:
        key = os.environ.get("VAULT_KEY")
        if not key:
            raise RuntimeError(
                "VAULT_KEY env var missing — FernetSecretBackend requires "
                "an operator-supplied Fernet key.  Backend disabled."
            )
        return Fernet(key.encode())

    def is_available(self) -> bool:
        return bool(os.environ.get("VAULT_KEY"))

    async def put(self, plaintext: bytes, *, scope: str, algorithm: str,
                  label: str = "") -> SecretHandle:
        if scope not in CAPABILITY_SCOPES:
            raise ValueError(f"unknown scope '{scope}'; supported: {CAPABILITY_SCOPES}")
        await self.ensure_indexes()
        cipher = self._fernet().encrypt(plaintext).decode()
        handle_id = f"sec-{uuid.uuid4().hex}"
        now = _now_iso()
        await self._coll.insert_one({
            "handle_id": handle_id,
            "scope": scope,
            "provider": self.provider,
            "algorithm": algorithm,
            "label": label,
            "cipher": cipher,
            "created_at": now,
        })
        return SecretHandle(
            handle_id=handle_id, scope=scope, provider=self.provider,
            algorithm=algorithm, created_at=now, label=label,
        )

    async def get(self, handle_id: str) -> Optional[bytes]:
        doc = await self._coll.find_one({"handle_id": handle_id}, {"_id": 0})
        if not doc or not doc.get("cipher"):
            return None
        try:
            return self._fernet().decrypt(doc["cipher"].encode())
        except InvalidToken:
            return None

    async def list_handles(self) -> list:
        cur = self._coll.find({}, {"_id": 0, "cipher": 0}).sort("created_at", -1)
        return await cur.to_list(500)

    async def delete(self, handle_id: str) -> bool:
        r = await self._coll.delete_one({"handle_id": handle_id})
        return bool(r.deleted_count)


# ---------------------------------------------------------------------------
# InMemorySecretBackend — test-only.  Never registered in production.
# ---------------------------------------------------------------------------


class InMemorySecretBackend:
    provider = "memory"

    def __init__(self):
        self._store: Dict[str, Dict[str, Any]] = {}

    def is_available(self) -> bool:
        return True

    async def put(self, plaintext: bytes, *, scope: str, algorithm: str,
                  label: str = "") -> SecretHandle:
        if scope not in CAPABILITY_SCOPES:
            raise ValueError(f"unknown scope '{scope}'")
        handle_id = f"sec-mem-{uuid.uuid4().hex}"
        now = _now_iso()
        self._store[handle_id] = {
            "handle_id": handle_id, "scope": scope, "provider": self.provider,
            "algorithm": algorithm, "label": label,
            "plaintext": bytes(plaintext), "created_at": now,
        }
        return SecretHandle(handle_id, scope, self.provider, algorithm, now, label)

    async def get(self, handle_id: str) -> Optional[bytes]:
        d = self._store.get(handle_id)
        return None if d is None else d["plaintext"]

    async def list_handles(self) -> list:
        return [
            {k: v for k, v in d.items() if k != "plaintext"}
            for d in self._store.values()
        ]

    async def delete(self, handle_id: str) -> bool:
        return self._store.pop(handle_id, None) is not None
