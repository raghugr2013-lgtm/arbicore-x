"""ArbiCore X — Execution signer vault integration (P0, secure ingestion).

Accepts an operator-supplied EVM execution-signer private key EXACTLY ONCE over
an authenticated HTTPS endpoint, derives its checksummed address with
``eth_account.Account.from_key`` (no signing / no broadcast), and stores ONLY
the Fernet-encrypted ciphertext + an opaque handle in the existing
``arbicore_secrets`` vault (scope ``evm_sign``). The raw key is never logged,
echoed, or persisted outside the vault.

Design commitments:
    * Address derivation only — this module never signs or broadcasts.
    * The plaintext key lifetime is minimised; references are dropped promptly.
      (Python cannot guarantee cryptographic zeroization — process isolation +
      strict logging controls + the encrypted vault are the real boundary.)
    * ``resolve_signer_account`` is INTERNAL (atomic-sim / signing flow only) and
      MUST NEVER be surfaced through public REST.
    * A single active signer is enforced: ingesting a new key replaces the old
      evm_sign handle.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from eth_account import Account
from eth_utils import to_checksum_address

EVM_SIGN_SCOPE = "evm_sign"
EVM_SIGN_ALGO = "eth_privkey"
_SECRETS_COLLECTION = "arbicore_secrets"


def _normalize_privkey(raw: str) -> str:
    """Return a canonical 64-hex private key (no 0x) or raise ValueError.

    Never include the key material in the raised message."""
    if not isinstance(raw, str):
        raise ValueError("private key must be a string")
    h = raw.strip()
    if h.startswith(("0x", "0X")):
        h = h[2:]
    h = h.strip()
    if len(h) != 64 or not all(c in "0123456789abcdefABCDEF" for c in h):
        raise ValueError("private key must be 64 hex characters")
    if int(h, 16) == 0:
        raise ValueError("private key must be non-zero")
    return h.lower()


def _mask_address(address: str) -> str:
    if not address or len(address) < 10:
        return address or ""
    return address[:6] + "…" + address[-4:]


async def _list_signer_handles(db) -> List[Dict[str, Any]]:
    cur = db[_SECRETS_COLLECTION].find(
        {"scope": EVM_SIGN_SCOPE}, {"_id": 0, "cipher": 0}
    ).sort("created_at", -1)
    return await cur.to_list(50)


async def ingest_signer(registry, db, *, private_key: str,
                        expected_address: Optional[str] = None,
                        label: str = "execution-signer") -> Dict[str, Any]:
    """Derive → verify → encrypt → store. Returns handle + derived address only.

    Never returns or logs the raw key. Enforces a single active signer."""
    norm = _normalize_privkey(private_key)
    try:
        account = Account.from_key("0x" + norm)
        address = account.address  # checksummed
    finally:
        # Drop the LocalAccount reference immediately — it retains key material.
        account = None  # noqa: F841

    matches_expected: Optional[bool] = None
    if expected_address:
        try:
            matches_expected = (to_checksum_address(expected_address) == address)
        except (ValueError, TypeError):
            matches_expected = None

    old_handles = await _list_signer_handles(db)

    handle = await registry.put(
        norm.encode("utf-8"), scope=EVM_SIGN_SCOPE,
        algorithm=EVM_SIGN_ALGO, label=label or "execution-signer")
    norm = ""  # drop plaintext reference

    # Annotate the vault doc with the PUBLIC derived address so readiness can
    # match it against the gas wallet WITHOUT decrypting the key each time.
    await db[_SECRETS_COLLECTION].update_one(
        {"handle_id": handle.handle_id},
        {"$set": {"derived_address": address, "execution_role": "signer"}})

    # Single active signer: remove any previously-stored signer handles.
    for h in old_handles:
        try:
            await registry.delete(h["handle_id"])
        except Exception:  # noqa: BLE001
            pass

    return {
        "handle_id": handle.handle_id,
        "scope": handle.scope,
        "algorithm": handle.algorithm,
        "label": handle.label,
        "provider": handle.provider,
        "derived_address": address,
        "address_mask": _mask_address(address),
        "matches_expected": matches_expected,
        "replaced_handles": [h["handle_id"] for h in old_handles],
    }


async def signer_status(db, *, expected_address: Optional[str] = None) -> Dict[str, Any]:
    """Presence + derived-address match. No plaintext ever touched."""
    docs = await _list_signer_handles(db)
    present = len(docs) > 0
    derived = docs[0].get("derived_address") if present else None
    matches = None
    if present and derived and expected_address:
        try:
            matches = (to_checksum_address(derived) == to_checksum_address(expected_address))
        except (ValueError, TypeError):
            matches = None
    return {
        "present": present,
        "handle_count": len(docs),
        "handle_id": docs[0]["handle_id"] if present else None,
        "derived_address": derived,
        "address_mask": _mask_address(derived) if derived else None,
        "matches_expected": matches,
    }


async def delete_signer(registry, db) -> Dict[str, Any]:
    docs = await _list_signer_handles(db)
    deleted = []
    for h in docs:
        try:
            if await registry.delete(h["handle_id"]):
                deleted.append(h["handle_id"])
        except Exception:  # noqa: BLE001
            pass
    return {"deleted": deleted, "count": len(deleted)}


async def resolve_signer_account(registry, db):
    """INTERNAL — resolve the stored signer to an eth_account LocalAccount for
    the atomic-simulation / signing flow. MUST NEVER be exposed via REST.

    Returns the LocalAccount or None. Callers must not log ``account.key``."""
    docs = await _list_signer_handles(db)
    if not docs:
        return None
    material = await registry.resolve(docs[0]["handle_id"])
    if material is None:
        return None
    try:
        pk = material.decode("utf-8").strip()
    except Exception:  # noqa: BLE001
        return None
    if not pk.startswith("0x"):
        pk = "0x" + pk
    try:
        return Account.from_key(pk)
    except Exception:  # noqa: BLE001
        return None


async def ensure_signer_address(registry, db, *,
                                expected_address: Optional[str] = None) -> Dict[str, Any]:
    """Self-heal: if an evm_sign handle exists but lacks the public
    ``derived_address`` annotation (e.g. stored via the generic secrets path),
    resolve the key INTERNALLY once, derive the address, and backfill the doc.

    The raw key is never logged or returned — only the public address."""
    docs = await _list_signer_handles(db)
    if not docs:
        return {"present": False, "backfilled": False}
    doc = docs[0]
    if doc.get("derived_address"):
        return {"present": True, "backfilled": False,
                "derived_address": doc.get("derived_address")}
    account = await resolve_signer_account(registry, db)
    if account is None:
        return {"present": True, "backfilled": False,
                "reason": "unable to resolve signer key from vault"}
    address = account.address  # checksummed public address
    account = None  # drop key-bearing ref
    await db[_SECRETS_COLLECTION].update_one(
        {"handle_id": doc["handle_id"]},
        {"$set": {"derived_address": address, "execution_role": "signer"}})
    matches = None
    if expected_address:
        try:
            matches = (to_checksum_address(address) == to_checksum_address(expected_address))
        except (ValueError, TypeError):
            matches = None
    return {"present": True, "backfilled": True,
            "derived_address": address, "matches_expected": matches}


__all__ = ["ingest_signer", "signer_status", "delete_signer",
           "resolve_signer_account", "ensure_signer_address",
           "EVM_SIGN_SCOPE", "EVM_SIGN_ALGO"]
