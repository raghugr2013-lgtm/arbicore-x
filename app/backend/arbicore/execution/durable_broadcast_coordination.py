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
                    {"active_send.status": {
                        "$in": ["completed", "failed_pre_rpc", "recovered_unused"],
                    }},
                    # TTL may reclaim only pre-RPC "authorized" leases — NEVER
                    # rpc_submitted (crash after boundary requires operator recovery).
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

    async def mark_entering_rpc(
        self,
        auth: SendAuthorization,
        *,
        signer: Optional[str] = None,
        nonce: Optional[int] = None,
        chain_id: Optional[int] = None,
        tx_binding_digest: Optional[str] = None,
    ) -> None:
        """Final durable gate before eth_sendRawTransaction (C2 linearization).

        Stamps recovery metadata (signer/nonce/digest) — never raw signed bytes
        or private keys.
        """
        from pymongo import ReturnDocument

        meta: Dict[str, Any] = {
            "active_send.status": "rpc_submitted",
            "active_send.rpc_entered_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        if signer:
            meta["active_send.signer"] = str(signer).lower()
        if nonce is not None:
            meta["active_send.nonce"] = int(nonce)
        if chain_id is not None:
            meta["active_send.chain_id"] = int(chain_id)
        if tx_binding_digest:
            # Hash only — not calldata / signed payload.
            meta["active_send.tx_binding_digest"] = str(tx_binding_digest)[:80]

        doc = await self._coord.find_one_and_update(
            {
                "key": COORD_KEY,
                "kill_engaged": {"$ne": True},
                "active_send.owner_id": auth.owner_id,
                "active_send.send_id": auth.send_id,
                "active_send.status": "authorized",
            },
            {"$set": meta},
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

    # ------------------------------------------------------------------
    # Operator recovery for stuck active_send=rpc_submitted (crash after boundary)
    # ------------------------------------------------------------------

    async def get_coordination_status(self) -> Dict[str, Any]:
        """Safe status snapshot — no secrets / signed bytes / RPC URLs."""
        try:
            doc = await self._ensure_coord_doc()
        except Exception as exc:  # noqa: BLE001
            raise CoordinationError(
                f"coord_status_unavailable: {type(exc).__name__}"
            ) from exc
        active = doc.get("active_send") or None
        safe_active = None
        if isinstance(active, dict):
            safe_active = {
                "send_id": active.get("send_id"),
                "owner_id": active.get("owner_id"),
                "status": active.get("status"),
                "signer": active.get("signer"),
                "nonce": active.get("nonce"),
                "chain_id": active.get("chain_id"),
                "tx_binding_digest": active.get("tx_binding_digest"),
                "resolved_tx_hash": active.get("resolved_tx_hash"),
                "resend_forbidden": bool(active.get("resend_forbidden")),
                "rpc_entered_at": active.get("rpc_entered_at"),
                "recovery_claim_id": active.get("recovery_claim_id"),
                "last_recovery_note": active.get("last_recovery_note"),
            }
        return {
            "kill_engaged": bool(doc.get("kill_engaged")),
            "kill_fence": int(doc.get("kill_fence") or 0),
            "active_send": safe_active,
            "writer_lease_owner": (doc.get("writer_lease") or {}).get("owner_id"),
        }

    async def recover_stuck_send(
        self,
        *,
        operator: str,
        reason: str,
        decision: str,
        evidence: Dict[str, Any],
        send_id: Optional[str] = None,
        signer: Optional[str] = None,
        audit_coll_name: str = "arbicore_send_recovery_audit",
    ) -> Dict[str, Any]:
        """Evidence-based operator recovery for ``active_send.status=rpc_submitted``.

        Never clears a stuck send because a TTL expired. Requires chain/RPC
        evidence. Fail-closed if coordination or audit persistence fails.

        ``decision``:
          * ``tx_found`` — tx present on chain/RPC; complete without resend
          * ``tx_absent`` — authoritative absence + pending nonce proves unused
          * ``investigate`` — record audit only; remain blocked
        """
        reason = (reason or "").strip()
        operator = (operator or "").strip()
        decision = (decision or "").strip().lower()
        if not reason or not operator:
            raise CoordinationError("recovery_rejected: operator and reason required")
        if decision not in ("tx_found", "tx_absent", "investigate"):
            raise CoordinationError(
                "recovery_rejected: decision must be tx_found|tx_absent|investigate"
            )
        if not isinstance(evidence, dict):
            raise CoordinationError("recovery_rejected: evidence object required")

        # Forbidden fields — never accept or echo secrets / signed material.
        forbidden = (
            "private_key", "privkey", "signed_tx", "raw_transaction",
            "raw_tx", "rpc_url", "api_key", "authorization",
        )
        for k in evidence:
            if str(k).lower() in forbidden:
                raise CoordinationError(
                    f"recovery_rejected: evidence field '{k}' not allowed"
                )

        tx_found = evidence.get("tx_found_on_chain")
        tx_hash = evidence.get("tx_hash")
        if tx_hash is not None:
            tx_hash = str(tx_hash).strip().lower()
            if tx_hash and not tx_hash.startswith("0x"):
                raise CoordinationError("recovery_rejected: tx_hash must be 0x-prefixed")
            if len(tx_hash) > 66:
                raise CoordinationError("recovery_rejected: tx_hash malformed")
        rpc_result = str(evidence.get("rpc_get_transaction_result") or "").lower()
        try:
            chain_pending = evidence.get("chain_pending_nonce")
            chain_pending_i = int(chain_pending) if chain_pending is not None else None
        except (TypeError, ValueError) as exc:
            raise CoordinationError(
                "recovery_rejected: chain_pending_nonce invalid"
            ) from exc

        audit = self._db[audit_coll_name]
        claim_id = f"recv-{uuid.uuid4().hex}"
        audit_doc = {
            "claim_id": claim_id,
            "operator": operator,
            "reason": reason,
            "decision": decision,
            "send_id": send_id,
            "evidence_summary": {
                "tx_found_on_chain": tx_found,
                "tx_hash_present": bool(tx_hash),
                "tx_hash_prefix": (tx_hash[:10] + "…") if tx_hash and len(tx_hash) > 12 else tx_hash,
                "rpc_get_transaction_result": rpc_result or None,
                "chain_pending_nonce": chain_pending_i,
                "evidence_source": evidence.get("evidence_source"),
                "observed_at": evidence.get("observed_at"),
            },
            "status": "started",
            "at": _now_iso(),
        }
        # Audit-first — fail closed before mutating coordination state.
        try:
            await audit.insert_one(dict(audit_doc))
        except Exception as exc:  # noqa: BLE001
            raise CoordinationError(
                f"recovery_audit_failed: {type(exc).__name__}"
            ) from exc

        try:
            cur = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0})
        except Exception as exc:  # noqa: BLE001
            await self._audit_finish(audit, claim_id, ok=False, action="coord_unavailable",
                                     detail=type(exc).__name__)
            raise CoordinationError(
                f"recovery_coord_unavailable: {type(exc).__name__}"
            ) from exc

        if not cur:
            await self._audit_finish(audit, claim_id, ok=False, action="no_coord_doc")
            raise CoordinationError("recovery_rejected: coordination document missing")

        active = cur.get("active_send") or {}
        if not active:
            # Idempotent: nothing stuck
            await self._audit_finish(audit, claim_id, ok=True, action="noop_no_active_send")
            return {"ok": True, "action": "noop_no_active_send", "claim_id": claim_id,
                    "resend_forbidden": False}

        sid = send_id or active.get("send_id")
        if send_id and active.get("send_id") != send_id:
            await self._audit_finish(audit, claim_id, ok=False, action="send_id_mismatch")
            raise CoordinationError("recovery_rejected: send_id mismatch")

        # Already recovered — idempotent success
        if active.get("status") in ("completed", "recovered_unused") and (
            not send_id or active.get("send_id") == send_id
        ):
            await self._audit_finish(
                audit, claim_id, ok=True, action="idempotent_already_resolved",
                detail=active.get("status"),
            )
            return {
                "ok": True,
                "action": "idempotent_already_resolved",
                "claim_id": claim_id,
                "status": active.get("status"),
                "resolved_tx_hash": active.get("resolved_tx_hash"),
                "resend_forbidden": bool(active.get("resend_forbidden")),
            }

        if active.get("status") != "rpc_submitted":
            await self._audit_finish(
                audit, claim_id, ok=False, action="not_rpc_submitted",
                detail=str(active.get("status")),
            )
            raise CoordinationError(
                f"recovery_rejected: active_send.status is "
                f"{active.get('status')!r}, need rpc_submitted"
            )

        # Concurrent recovery: CAS claim
        from pymongo import ReturnDocument
        claimed = await self._coord.find_one_and_update(
            {
                "key": COORD_KEY,
                "active_send.send_id": sid,
                "active_send.status": "rpc_submitted",
                "$or": [
                    {"active_send.recovery_claim_id": None},
                    {"active_send.recovery_claim_id": {"$exists": False}},
                    {"active_send.recovery_expires_ts": {"$lt": _now_ts()}},
                ],
            },
            {
                "$set": {
                    "active_send.recovery_claim_id": claim_id,
                    "active_send.recovery_operator": operator,
                    "active_send.recovery_expires_ts": _now_ts() + 120.0,
                    "active_send.last_recovery_note": f"claimed:{decision}",
                    "updated_at": _now_iso(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not claimed:
            await self._audit_finish(audit, claim_id, ok=False, action="recovery_busy")
            raise CoordinationError(
                "recovery_rejected: concurrent recovery in progress or state changed"
            )

        active = (claimed.get("active_send") or {})
        signer_key = (signer or active.get("signer") or "").lower()
        nonce_i = active.get("nonce")
        if nonce_i is not None:
            nonce_i = int(nonce_i)

        if decision == "investigate":
            # Release claim; remain rpc_submitted — TTL must not clear.
            await self._coord.update_one(
                {"key": COORD_KEY, "active_send.recovery_claim_id": claim_id},
                {
                    "$set": {
                        "active_send.recovery_claim_id": None,
                        "active_send.recovery_expires_ts": None,
                        "active_send.last_recovery_note": "investigate_only",
                        "updated_at": _now_iso(),
                    }
                },
            )
            await self._audit_finish(audit, claim_id, ok=True, action="investigate_only")
            return {
                "ok": True,
                "action": "investigate_only",
                "claim_id": claim_id,
                "status": "rpc_submitted",
                "blocked": True,
                "resend_forbidden": False,
                "note": "stuck send retained; TTL does not clear rpc_submitted",
            }

        # Evidence evaluation — fail closed on inconsistency
        if decision == "tx_found":
            if tx_found is not True:
                await self._release_recovery_claim(claim_id, note="tx_found_requires_true")
                await self._audit_finish(audit, claim_id, ok=False,
                                        action="evidence_inconsistent")
                raise CoordinationError(
                    "recovery_rejected: decision=tx_found requires "
                    "evidence.tx_found_on_chain=true"
                )
            if rpc_result in ("not_found", "error", "unavailable", ""):
                await self._release_recovery_claim(claim_id, note="rpc_result_conflict")
                await self._audit_finish(audit, claim_id, ok=False,
                                        action="evidence_inconsistent")
                raise CoordinationError(
                    "recovery_rejected: contradictory rpc_get_transaction_result "
                    f"for tx_found ({rpc_result!r})"
                )
            if not tx_hash:
                await self._release_recovery_claim(claim_id, note="tx_hash_required")
                await self._audit_finish(audit, claim_id, ok=False,
                                        action="evidence_incomplete")
                raise CoordinationError(
                    "recovery_rejected: tx_found requires evidence.tx_hash"
                )
            # Complete send + nonce without resend
            await self._coord.update_one(
                {"key": COORD_KEY, "active_send.recovery_claim_id": claim_id},
                {
                    "$set": {
                        "active_send.status": "completed",
                        "active_send.resolved_tx_hash": tx_hash,
                        "active_send.resend_forbidden": True,
                        "active_send.finished_at": _now_iso(),
                        "active_send.recovery_claim_id": None,
                        "active_send.recovered_by": operator,
                        "active_send.last_recovery_note": "completed_on_chain_no_resend",
                        "updated_at": _now_iso(),
                    }
                },
            )
            if signer_key and nonce_i is not None:
                await self.reconcile_nonce(
                    signer_key,
                    chain_pending_nonce=chain_pending_i if chain_pending_i is not None else nonce_i + 1,
                    tx_hash=tx_hash,
                    tx_found_on_chain=True,
                    owner_id=str(active.get("owner_id") or self.instance_id),
                )
            await self._audit_finish(
                audit, claim_id, ok=True, action="completed_on_chain_no_resend",
            )
            return {
                "ok": True,
                "action": "completed_on_chain_no_resend",
                "claim_id": claim_id,
                "send_id": sid,
                "resolved_tx_hash": tx_hash,
                "resend_forbidden": True,
                "status": "completed",
            }

        # decision == tx_absent
        if tx_found is not False:
            await self._release_recovery_claim(claim_id, note="tx_absent_requires_false")
            await self._audit_finish(audit, claim_id, ok=False, action="evidence_inconsistent")
            raise CoordinationError(
                "recovery_rejected: decision=tx_absent requires "
                "evidence.tx_found_on_chain=false"
            )
        if rpc_result not in ("not_found",):
            await self._release_recovery_claim(claim_id, note="rpc_not_found_required")
            await self._audit_finish(audit, claim_id, ok=False, action="evidence_inconclusive")
            raise CoordinationError(
                "recovery_rejected: tx_absent requires "
                "rpc_get_transaction_result='not_found' "
                f"(got {rpc_result!r}); unavailable/error remains blocked"
            )
        if chain_pending_i is None or nonce_i is None:
            await self._release_recovery_claim(claim_id, note="pending_nonce_required")
            await self._audit_finish(audit, claim_id, ok=False, action="evidence_incomplete")
            raise CoordinationError(
                "recovery_rejected: tx_absent requires chain_pending_nonce and "
                "known active_send.nonce"
            )
        if chain_pending_i > nonce_i:
            # Pending advanced past our nonce without our tx hash — contradictory
            await self._release_recovery_claim(claim_id, note="pending_ahead_conflict")
            await self._audit_finish(audit, claim_id, ok=False, action="evidence_contradictory")
            raise CoordinationError(
                "recovery_rejected: chain_pending_nonce > stuck nonce without "
                "tx_found — inconclusive (possible foreign/other submission)"
            )
        if chain_pending_i < nonce_i:
            # Chain still behind — safe unused
            pass
        # chain_pending_i == nonce_i and not found → unused, safe to release

        await self._coord.update_one(
            {"key": COORD_KEY, "active_send.recovery_claim_id": claim_id},
            {
                "$set": {
                    "active_send.status": "recovered_unused",
                    "active_send.resend_forbidden": False,
                    "active_send.finished_at": _now_iso(),
                    "active_send.recovery_claim_id": None,
                    "active_send.recovered_by": operator,
                    "active_send.last_recovery_note": "released_unused_no_resend_of_prior",
                    "updated_at": _now_iso(),
                }
            },
        )
        if signer_key:
            await self.reconcile_nonce(
                signer_key,
                chain_pending_nonce=chain_pending_i,
                tx_hash=tx_hash,
                tx_found_on_chain=False,
                owner_id=str(active.get("owner_id") or self.instance_id),
            )
        await self._audit_finish(audit, claim_id, ok=True, action="released_unused")
        return {
            "ok": True,
            "action": "released_unused",
            "claim_id": claim_id,
            "send_id": sid,
            "status": "recovered_unused",
            "resend_forbidden": False,
            "note": "nonce reusable; prior send_id must not be resent",
        }

    async def _release_recovery_claim(self, claim_id: str, *, note: str) -> None:
        try:
            await self._coord.update_one(
                {"key": COORD_KEY, "active_send.recovery_claim_id": claim_id},
                {
                    "$set": {
                        "active_send.recovery_claim_id": None,
                        "active_send.recovery_expires_ts": None,
                        "active_send.last_recovery_note": note,
                        "updated_at": _now_iso(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            logger.exception("recovery claim release failed")

    async def _audit_finish(
        self, audit, claim_id: str, *, ok: bool, action: str, detail: Optional[str] = None
    ) -> None:
        try:
            await audit.update_one(
                {"claim_id": claim_id},
                {
                    "$set": {
                        "status": "ok" if ok else "rejected",
                        "action": action,
                        "detail": detail,
                        "finished_at": _now_iso(),
                    }
                },
            )
        except Exception:  # noqa: BLE001
            # Surface as failure if we cannot persist outcome after start
            if ok:
                raise CoordinationError("recovery_audit_finish_failed")
            logger.exception("recovery audit finish failed claim=%s", claim_id)

    def was_send_resolved_no_resend(self, active_send: Optional[Dict[str, Any]]) -> bool:
        """True when a recovered/completed send must never be rebroadcast."""
        if not active_send:
            return False
        return bool(active_send.get("resend_forbidden")) and (
            active_send.get("status") == "completed"
        )
