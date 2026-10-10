"""WP-C2/C6 · Durable cross-process broadcast coordination.

Mongo-backed (or any find_one_and_update store) coordination that closes:

* **C2** — kill-switch engage vs send race across process boundaries
* **C6** — durable writer/nonce leases with fencing and recovery

Linearization (C2)
------------------
* Kill engage linearizes at the successful persistent write that sets
  ``kill_engaged=true`` and increments ``kill_fence``.
* A *new* send linearizes at ``mark_entering_rpc`` (the last durable check
  before ``eth_sendRawTransaction``). That update requires ``kill_engaged=false``.
* Therefore: once engage is acknowledged, no new transaction may enter the
  RPC broadcast boundary.
* An in-flight send that already reached ``status=rpc_submitted`` is NOT
  recalled — the chain/RPC owns that attempt. Engage still blocks *new* sends.

C6 architecture
---------------
Durable single-broadcaster writer lease + per-signer nonce lease documents.
Ownership uses monotonic ``fence`` tokens; stale owners cannot act after
lease expiry or fence change. Definite pre-RPC failures release the nonce
for reuse; ambiguous RPC results block further sends until reconcile.
"""
from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("arbicore.execution.durable_broadcast_coordination")

COORD_KEY = "global"
DEFAULT_SEND_LEASE_TTL_S = 120.0
DEFAULT_WRITER_LEASE_TTL_S = 60.0
INSTANCE_ENV = "ARBICORE_BROADCAST_INSTANCE_ID"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_ts() -> float:
    return time.time()


class CoordinationError(PermissionError):
    """Fail-closed coordination / fencing failure."""


class AmbiguousBroadcastError(CoordinationError):
    """Send result unknown — further sends blocked until reconcile."""


def _instance_id(explicit: Optional[str] = None) -> str:
    return (explicit or os.environ.get(INSTANCE_ENV) or "").strip() or f"inst-{uuid.uuid4().hex[:12]}"


@dataclass(frozen=True)
class SendAuthorization:
    owner_id: str
    send_id: str
    kill_fence: int


@dataclass(frozen=True)
class NonceLease:
    signer: str
    nonce: int
    owner_id: str
    fence: int


class BroadcastCoordinator:
    """Durable C2 send/kill coordinator + C6 writer/nonce coordinator."""

    def __init__(
        self,
        db,
        *,
        coord_collection: str = "arbicore_send_coordination",
        nonce_collection: str = "arbicore_nonce_leases",
        send_lease_ttl_s: float = DEFAULT_SEND_LEASE_TTL_S,
        writer_lease_ttl_s: float = DEFAULT_WRITER_LEASE_TTL_S,
        instance_id: Optional[str] = None,
    ):
        self._db = db
        self._coord_name = coord_collection
        self._nonce_name = nonce_collection
        self._send_ttl = float(send_lease_ttl_s)
        self._writer_ttl = float(writer_lease_ttl_s)
        self.instance_id = _instance_id(instance_id)

    @property
    def _coord(self):
        return self._db[self._coord_name]

    @property
    def _nonces(self):
        return self._db[self._nonce_name]

    async def ensure_indexes(self) -> None:
        await self._coord.create_index("key", unique=True)
        await self._nonces.create_index("key", unique=True)

    # ------------------------------------------------------------------
    # C2 · kill / send coordination
    # ------------------------------------------------------------------

    async def _ensure_coord_doc(self) -> Dict[str, Any]:
        existing = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0})
        if existing:
            return existing
        doc = {
            "key": COORD_KEY,
            "kill_engaged": False,
            "kill_fence": 0,
            "writer_lease": None,
            "writer_fence": 0,
            "active_send": None,
            "updated_at": _now_iso(),
        }
        try:
            await self._coord.insert_one(dict(doc))
        except Exception:  # noqa: BLE001 — race on create
            existing = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0})
            if existing:
                return existing
            raise CoordinationError("coord_doc_unavailable")
        return doc

    async def on_kill_engaged(self, *, reason: str, actor: str) -> Dict[str, Any]:
        """Acknowledge kill engagement in the shared coordination store.

        Bumps ``kill_fence`` and sets ``kill_engaged=True``. Does not clear
        ``active_send`` if ``status=rpc_submitted`` (cannot recall).
        """
        await self._ensure_coord_doc()
        from pymongo import ReturnDocument

        doc = await self._coord.find_one_and_update(
            {"key": COORD_KEY},
            {
                "$set": {
                    "kill_engaged": True,
                    "kill_reason": reason,
                    "kill_actor": actor,
                    "updated_at": _now_iso(),
                },
                "$inc": {"kill_fence": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            raise CoordinationError("kill_engage_coord_failed")
        return {
            "kill_engaged": True,
            "kill_fence": int(doc.get("kill_fence") or 0),
            "active_send": doc.get("active_send"),
            "linearization": (
                "engage_acked; new mark_entering_rpc denied; "
                "rpc_submitted in-flight not recalled"
            ),
        }

    async def on_kill_disengaged(self, *, reason: str, actor: str) -> Dict[str, Any]:
        await self._ensure_coord_doc()
        from pymongo import ReturnDocument

        doc = await self._coord.find_one_and_update(
            {"key": COORD_KEY},
            {
                "$set": {
                    "kill_engaged": False,
                    "kill_reason": None,
                    "kill_actor": actor,
                    "disengage_reason": reason,
                    "updated_at": _now_iso(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            raise CoordinationError("kill_disengage_coord_failed")
        return {"kill_engaged": False, "kill_fence": int(doc.get("kill_fence") or 0)}

    async def authorize_send(self, *, owner_id: Optional[str] = None) -> SendAuthorization:
        """Claim a durable send slot. Requires kill disengaged.

        Does not alone authorize RPC — caller must ``mark_entering_rpc``.
        """
        owner = owner_id or self.instance_id
        send_id = f"send-{uuid.uuid4().hex}"
        await self._ensure_coord_doc()
        now = _now_ts()
        expires = now + self._send_ttl
        from pymongo import ReturnDocument

        # Conditional claim: kill clear + no blocking in-flight send.
        doc = await self._coord.find_one_and_update(
            {
                "key": COORD_KEY,
                "kill_engaged": {"$ne": True},
                "$or": [
                    {"active_send": None},
                    {"active_send": {"$exists": False}},
                    {"active_send.status": {"$in": ["completed", "failed_pre_rpc"]}},
                    {
                        "active_send.status": "authorized",
                        "active_send.expires_ts": {"$lt": now},
                    },
                ],
            },
            {
                "$set": {
                    "active_send": {
                        "owner_id": owner,
                        "send_id": send_id,
                        "status": "authorized",
                        "started_at": _now_iso(),
                        "expires_ts": expires,
                    },
                    "updated_at": _now_iso(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            # Distinguish kill vs busy for diagnostics (fail closed either way).
            cur = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0}) or {}
            if cur.get("kill_engaged"):
                raise CoordinationError(
                    "send_denied: kill_switch engaged (durable coord)"
                )
            raise CoordinationError(
                "send_denied: another send in flight or coord unavailable"
            )
        # Stamp fence observed at claim (separate read-safe set).
        fence = int(doc.get("kill_fence") or 0)
        await self._coord.update_one(
            {"key": COORD_KEY, "active_send.send_id": send_id},
            {"$set": {"active_send.kill_fence_at_claim": fence}},
        )
        return SendAuthorization(owner_id=owner, send_id=send_id, kill_fence=fence)

    async def mark_entering_rpc(self, auth: SendAuthorization) -> None:
        """Final durable gate before eth_sendRawTransaction (C2 linearization)."""
        from pymongo import ReturnDocument

        doc = await self._coord.find_one_and_update(
            {
                "key": COORD_KEY,
                "kill_engaged": {"$ne": True},
                "active_send.owner_id": auth.owner_id,
                "active_send.send_id": auth.send_id,
                "active_send.status": "authorized",
            },
            {
                "$set": {
                    "active_send.status": "rpc_submitted",
                    "active_send.rpc_entered_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            cur = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0}) or {}
            if cur.get("kill_engaged"):
                raise CoordinationError(
                    "broadcast_boundary_denied: kill engaged before RPC "
                    "(engage linearized ahead of mark_entering_rpc)"
                )
            raise CoordinationError(
                "broadcast_boundary_denied: lost send lease or fence mismatch"
            )

    async def complete_send(
        self, auth: SendAuthorization, *, outcome: str
    ) -> None:
        """outcome: completed | failed_pre_rpc"""
        status = "completed" if outcome == "completed" else "failed_pre_rpc"
        await self._coord.update_one(
            {
                "key": COORD_KEY,
                "active_send.send_id": auth.send_id,
                "active_send.owner_id": auth.owner_id,
            },
            {
                "$set": {
                    "active_send.status": status,
                    "active_send.finished_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            },
        )

    async def run_authorized_send(self, *, send_coro_factory, owner_id: Optional[str] = None):
        """Authorize → mark_entering_rpc → send_coro → complete.

        ``send_coro_factory`` is invoked only after durable RPC entry is marked.
        On exception before/during factory: if not yet rpc_submitted, mark
        failed_pre_rpc; if rpc already marked, leave status for reconcile
        (caller should pass AmbiguousBroadcastError for timeouts).
        """
        auth = await self.authorize_send(owner_id=owner_id)
        entered_rpc = False
        try:
            await self.mark_entering_rpc(auth)
            entered_rpc = True
            result = await send_coro_factory()
            await self.complete_send(auth, outcome="completed")
            return result
        except AmbiguousBroadcastError:
            # Leave active_send as rpc_submitted for operator reconcile.
            raise
        except Exception:
            if not entered_rpc:
                await self.complete_send(auth, outcome="failed_pre_rpc")
            raise

    # ------------------------------------------------------------------
    # C6 · durable writer + nonce leases
    # ------------------------------------------------------------------

    async def _nonce_doc(self, signer: str) -> Dict[str, Any]:
        key = (signer or "").lower()
        doc = await self._nonces.find_one({"key": key}, {"_id": 0})
        if doc:
            return doc
        fresh = {
            "key": key,
            "fence": 0,
            "writer_lease": None,
            "inflight": None,
            "next_nonce": None,
            "blocked_reason": None,
            "updated_at": _now_iso(),
        }
        try:
            await self._nonces.insert_one(dict(fresh))
        except Exception:  # noqa: BLE001
            doc = await self._nonces.find_one({"key": key}, {"_id": 0})
            if doc:
                return doc
            raise CoordinationError("nonce_doc_unavailable")
        return fresh

    async def claim_writer(self, owner_id: Optional[str] = None) -> Dict[str, Any]:
        """Durable single-broadcaster lease with fencing."""
        owner = owner_id or self.instance_id
        # Writer lease is global (one broadcaster process family).
        await self._ensure_coord_doc()
        now = _now_ts()
        expires = now + self._writer_ttl
        from pymongo import ReturnDocument

        doc = await self._coord.find_one_and_update(
            {
                "key": COORD_KEY,
                "$or": [
                    {"writer_lease": None},
                    {"writer_lease": {"$exists": False}},
                    {"writer_lease.expires_ts": {"$lt": now}},
                    {"writer_lease.owner_id": owner},
                ],
            },
            {
                "$set": {
                    "writer_lease": {
                        "owner_id": owner,
                        "expires_ts": expires,
                        "claimed_at": _now_iso(),
                    },
                    "updated_at": _now_iso(),
                },
                "$inc": {"writer_fence": 1},
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            cur = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0}) or {}
            held = (cur.get("writer_lease") or {}).get("owner_id")
            raise CoordinationError(
                f"writer_lease_denied: held by {held!r}, claimed by {owner!r}"
            )
        return {
            "owner_id": owner,
            "writer_fence": int(doc.get("writer_fence") or 0),
            "expires_ts": expires,
        }

    async def _require_writer(self, owner: str) -> int:
        cur = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0}) or {}
        lease = cur.get("writer_lease") or {}
        if lease.get("owner_id") != owner:
            raise CoordinationError("stale_or_missing_writer_lease")
        if float(lease.get("expires_ts") or 0) < _now_ts():
            raise CoordinationError("writer_lease_expired")
        return int(cur.get("writer_fence") or 0)

    async def allocate_nonce(
        self, signer: str, observed_nonce: int, *, owner_id: Optional[str] = None
    ) -> NonceLease:
        owner = owner_id or self.instance_id
        await self._require_writer(owner)
        key = (signer or "").lower()
        await self._nonce_doc(key)
        from pymongo import ReturnDocument

        # Blocked ambiguous state → fail closed.
        cur = await self._nonces.find_one({"key": key}, {"_id": 0}) or {}
        if cur.get("blocked_reason"):
            raise AmbiguousBroadcastError(
                f"nonce_blocked: {cur.get('blocked_reason')}"
            )
        inflight = cur.get("inflight")
        if inflight and inflight.get("status") in ("leased", "submitted", "ambiguous"):
            if inflight.get("owner_id") == owner and inflight.get("status") == "leased":
                return NonceLease(
                    signer=key,
                    nonce=int(inflight["nonce"]),
                    owner_id=owner,
                    fence=int(inflight.get("fence") or 0),
                )
            raise CoordinationError(
                f"nonce_in_use: status={inflight.get('status')} "
                f"owner={inflight.get('owner_id')}"
            )

        next_n = cur.get("next_nonce")
        nonce = int(observed_nonce) if next_n is None else max(int(observed_nonce), int(next_n))
        fence = int(cur.get("fence") or 0) + 1
        doc = await self._nonces.find_one_and_update(
            {
                "key": key,
                "blocked_reason": None,
                "$or": [
                    {"inflight": None},
                    {"inflight": {"$exists": False}},
                    {"inflight.status": {"$in": ["released_pre_rpc", "completed"]}},
                ],
            },
            {
                "$set": {
                    "fence": fence,
                    "inflight": {
                        "nonce": nonce,
                        "owner_id": owner,
                        "fence": fence,
                        "status": "leased",
                        "leased_at": _now_iso(),
                    },
                    "next_nonce": nonce,
                    "updated_at": _now_iso(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            raise CoordinationError("nonce_allocate_failed")
        return NonceLease(signer=key, nonce=nonce, owner_id=owner, fence=fence)

    async def mark_nonce_pre_broadcast_failure(self, lease: NonceLease) -> None:
        """Definite failure before RPC — release nonce for reuse (no skip)."""
        await self._nonces.update_one(
            {
                "key": lease.signer,
                "inflight.nonce": lease.nonce,
                "inflight.owner_id": lease.owner_id,
                "inflight.fence": lease.fence,
                "inflight.status": "leased",
            },
            {
                "$set": {
                    "inflight": {
                        "nonce": lease.nonce,
                        "owner_id": lease.owner_id,
                        "fence": lease.fence,
                        "status": "released_pre_rpc",
                        "finished_at": _now_iso(),
                    },
                    # Keep next_nonce at this nonce so retry can reuse it.
                    "next_nonce": lease.nonce,
                    "updated_at": _now_iso(),
                }
            },
        )

    async def mark_nonce_submitted(
        self, lease: NonceLease, *, tx_hash: Optional[str] = None
    ) -> None:
        await self._nonces.update_one(
            {
                "key": lease.signer,
                "inflight.nonce": lease.nonce,
                "inflight.owner_id": lease.owner_id,
                "inflight.fence": lease.fence,
            },
            {
                "$set": {
                    "inflight.status": "submitted",
                    "inflight.tx_hash": tx_hash,
                    "inflight.submitted_at": _now_iso(),
                    "updated_at": _now_iso(),
                }
            },
        )

    async def mark_nonce_ambiguous(
        self, lease: NonceLease, *, reason: str
    ) -> None:
        await self._nonces.update_one(
            {
                "key": lease.signer,
                "inflight.nonce": lease.nonce,
                "inflight.fence": lease.fence,
            },
            {
                "$set": {
                    "inflight.status": "ambiguous",
                    "blocked_reason": reason,
                    "updated_at": _now_iso(),
                }
            },
        )

    async def mark_nonce_completed(self, lease: NonceLease) -> None:
        await self._nonces.update_one(
            {
                "key": lease.signer,
                "inflight.nonce": lease.nonce,
                "inflight.fence": lease.fence,
            },
            {
                "$set": {
                    "inflight.status": "completed",
                    "next_nonce": int(lease.nonce) + 1,
                    "blocked_reason": None,
                    "updated_at": _now_iso(),
                }
            },
        )

    async def reconcile_nonce(
        self,
        signer: str,
        *,
        chain_pending_nonce: int,
        tx_hash: Optional[str] = None,
        tx_found_on_chain: Optional[bool] = None,
        owner_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Safe recovery for ambiguous / restart cases.

        Rules:
        * tx_found_on_chain True → complete, advance next_nonce
        * tx_found_on_chain False and chain_pending_nonce <= leased nonce
          → definite unused; release for retry
        * Otherwise keep blocked (fail closed)
        """
        owner = owner_id or self.instance_id
        key = (signer or "").lower()
        doc = await self._nonces.find_one({"key": key}, {"_id": 0}) or {}
        inflight = doc.get("inflight") or {}
        if not inflight:
            return {"ok": True, "action": "noop"}
        nonce = int(inflight.get("nonce") or 0)
        if tx_found_on_chain is True:
            lease = NonceLease(
                signer=key,
                nonce=nonce,
                owner_id=str(inflight.get("owner_id") or owner),
                fence=int(inflight.get("fence") or 0),
            )
            await self.mark_nonce_completed(lease)
            return {"ok": True, "action": "completed_on_chain", "next_nonce": nonce + 1}
        if tx_found_on_chain is False and int(chain_pending_nonce) <= nonce:
            # Unused on chain — safe to retry same nonce.
            await self._nonces.update_one(
                {"key": key, "inflight.nonce": nonce},
                {
                    "$set": {
                        "inflight": {
                            "nonce": nonce,
                            "status": "released_pre_rpc",
                            "reconciled_at": _now_iso(),
                            "tx_hash": tx_hash,
                        },
                        "next_nonce": nonce,
                        "blocked_reason": None,
                        "updated_at": _now_iso(),
                    }
                },
            )
            return {"ok": True, "action": "released_for_retry", "nonce": nonce}
        # Ambiguous still
        await self._nonces.update_one(
            {"key": key},
            {
                "$set": {
                    "blocked_reason": (
                        "reconcile_inconclusive: require operator/chain evidence"
                    ),
                    "updated_at": _now_iso(),
                }
            },
        )
        return {"ok": False, "action": "still_blocked", "nonce": nonce}
