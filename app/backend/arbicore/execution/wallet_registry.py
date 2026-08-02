"""Wave 6A · Wallet Registry.

Distinct from the canonical *wallet-profile* concept (which is a
scoring / profiling substrate).  This registry expresses the
**execution role** of each wallet the platform can observe or (post
Wave-6D) sign for.

Roles:
    * ``watch_only``  — read-only monitor; no execution capability
    * ``gas``         — dedicated gas wallet for Mode-3 execution
    * ``funding``     — treasury source (never a signer in MVP)
    * ``receiving``   — settlement destination

Chains:
    * Approved MVP chain: ``base``.  Ethereum mainnet added later.

Security invariants:
    * Registry stores **no** private key material.  A wallet with
      ``execution_role='gas'`` carries a ``secret_handle`` reference
      that the Secret Registry resolves at broadcast time (Wave 6D+).
    * Registry writes are audit-logged with ``actor``, ``reason``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


EXECUTION_ROLES: tuple = ("watch_only", "gas", "funding", "receiving")
SUPPORTED_CHAINS: tuple = ("base", "ethereum", "arbitrum", "optimism", "polygon")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class WalletRegistryRepo:
    def __init__(self, db, collection: str = "wallet_registry",
                 audit_collection: str = "wallet_registry_audit"):
        self._db = db
        self._coll = db[collection]
        self._audit = db[audit_collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._coll.create_index("wallet_id", unique=True)
        await self._coll.create_index([("chain", 1), ("execution_role", 1)])
        await self._coll.create_index("address")
        await self._audit.create_index([("wallet_id", 1), ("at", -1)])
        self._indexes_ready = True

    # --- validation ---

    @staticmethod
    def _validate(payload: Dict[str, Any]) -> None:
        addr = payload.get("address")
        if not addr or not isinstance(addr, str):
            raise ValueError("address is required (string)")
        # Very-light address hygiene — full checksum belongs to signer package.
        if not (addr.startswith("0x") and len(addr) == 42):
            raise ValueError("address must be a 0x-prefixed 20-byte hex string")
        chain = payload.get("chain", "base")
        if chain not in SUPPORTED_CHAINS:
            raise ValueError(f"unsupported chain '{chain}'; supported: {SUPPORTED_CHAINS}")
        role = payload.get("execution_role", "watch_only")
        if role not in EXECUTION_ROLES:
            raise ValueError(f"unknown execution_role '{role}'; must be one of {EXECUTION_ROLES}")

    # --- reads ---

    async def get(self, wallet_id: str) -> Optional[Dict[str, Any]]:
        return await self._coll.find_one({"wallet_id": wallet_id}, {"_id": 0})

    async def list_all(self, chain: Optional[str] = None,
                       execution_role: Optional[str] = None) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if chain:
            q["chain"] = chain
        if execution_role:
            q["execution_role"] = execution_role
        cur = self._coll.find(q, {"_id": 0}).sort("created_at", -1)
        return await cur.to_list(200)

    async def audit_history(self, wallet_id: Optional[str] = None,
                            limit: int = 50) -> List[Dict[str, Any]]:
        q = {"wallet_id": wallet_id} if wallet_id else {}
        cur = self._audit.find(q, {"_id": 0}).sort("at", -1).limit(limit)
        return await cur.to_list(limit)

    # --- writes ---

    async def register(self, wallet_id: str, address: str, chain: str = "base",
                       execution_role: str = "watch_only",
                       label: Optional[str] = None,
                       whitelisted_venues: Optional[List[str]] = None,
                       secret_handle_id: Optional[str] = None,
                       actor: str = "operator",
                       reason: str = "") -> Dict[str, Any]:
        payload = {"address": address, "chain": chain, "execution_role": execution_role}
        self._validate(payload)
        # Invariant: only 'gas' role may carry a secret_handle_id.  All
        # other roles are watch-only from the platform's perspective.
        if secret_handle_id and execution_role != "gas":
            raise ValueError("only 'gas' wallets may reference a secret_handle_id")
        now = _now_iso()
        doc = {
            "wallet_id": wallet_id,
            "address": address,
            "chain": chain,
            "execution_role": execution_role,
            "label": label or wallet_id,
            "whitelisted_venues": list(whitelisted_venues or []),
            "secret_handle_id": secret_handle_id,
            "created_at": now,
            "updated_at": now,
        }
        await self._coll.insert_one(doc)
        await self._audit.insert_one({
            "wallet_id": wallet_id, "action": "register", "at": now,
            "actor": actor, "reason": reason,
            "role": execution_role, "chain": chain,
        })
        doc.pop("_id", None)
        return doc

    async def update_role(self, wallet_id: str, execution_role: str,
                          actor: str = "operator",
                          reason: str = "") -> Optional[Dict[str, Any]]:
        if execution_role not in EXECUTION_ROLES:
            raise ValueError(f"unknown execution_role '{execution_role}'")
        current = await self.get(wallet_id)
        if not current:
            return None
        # Downgrading a wallet away from 'gas' must scrub the secret_handle_id.
        updates = {"execution_role": execution_role, "updated_at": _now_iso()}
        unset: Dict[str, str] = {}
        if execution_role != "gas" and current.get("secret_handle_id"):
            unset["secret_handle_id"] = ""
        update_op: Dict[str, Any] = {"$set": updates}
        if unset:
            update_op["$unset"] = unset
        await self._coll.update_one({"wallet_id": wallet_id}, update_op)
        await self._audit.insert_one({
            "wallet_id": wallet_id, "action": "update_role", "at": _now_iso(),
            "actor": actor, "reason": reason,
            "from_role": current.get("execution_role"),
            "to_role": execution_role,
        })
        return await self.get(wallet_id)

    async def unregister(self, wallet_id: str, actor: str = "operator",
                         reason: str = "") -> bool:
        r = await self._coll.delete_one({"wallet_id": wallet_id})
        if r.deleted_count:
            await self._audit.insert_one({
                "wallet_id": wallet_id, "action": "unregister",
                "at": _now_iso(), "actor": actor, "reason": reason,
            })
            return True
        return False
