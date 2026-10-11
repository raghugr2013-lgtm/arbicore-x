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
        rpc_verifier: Any = None,
    ):
        self._db = db
        self._coord_name = coord_collection
        self._nonce_name = nonce_collection
        self._send_ttl = float(send_lease_ttl_s)
        self._writer_ttl = float(writer_lease_ttl_s)
        self.instance_id = _instance_id(instance_id)
        # Trusted server-side RPC observer (injectable for tests).
        self._rpc_verifier = rpc_verifier

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

    def _verifier(self):
        if self._rpc_verifier is not None:
            return self._rpc_verifier
        from .recovery_rpc_evidence import RecoveryRpcVerifier

        self._rpc_verifier = RecoveryRpcVerifier()
        return self._rpc_verifier

    async def recover_stuck_send(
        self,
        *,
        operator: str,
        reason: str,
        decision: str,
        evidence: Optional[Dict[str, Any]] = None,
        send_id: Optional[str] = None,
        signer: Optional[str] = None,
        audit_coll_name: str = "arbicore_send_recovery_audit",
    ) -> Dict[str, Any]:
        """Admin recovery for ``active_send.status=rpc_submitted``.

        Authoritative evidence is obtained via trusted server-side RPC
        (``RecoveryRpcVerifier``), bound to the durable stuck-send record
        (send_id, tx_binding_digest, chain_id, signer, nonce). Operator JSON
        is NOT proof of an RPC observation — only ``candidate_tx_hash`` is
        accepted as a lookup hint for ``tx_found``.

        Crash-safe commit: audit ``commit_intent`` is persisted before the
        durable status mutation; restarts resume idempotently.
        """
        from .recovery_rpc_evidence import (
            assert_tx_bound_to_stuck,
            evidence_audit_summary,
            parse_rpc_entered_age_s,
        )

        reason = (reason or "").strip()
        operator = (operator or "").strip()
        decision = (decision or "").strip().lower()
        evidence = evidence if isinstance(evidence, dict) else {}
        if not reason or not operator:
            raise CoordinationError("recovery_rejected: operator and reason required")
        if decision not in ("tx_found", "tx_absent", "investigate"):
            raise CoordinationError(
                "recovery_rejected: decision must be tx_found|tx_absent|investigate"
            )

        # Forbidden fields — never accept secrets / signed material / RPC URLs.
        forbidden = (
            "private_key", "privkey", "signed_tx", "raw_transaction",
            "raw_tx", "rpc_url", "api_key", "authorization",
        )
        for k in evidence:
            if str(k).lower() in forbidden:
                raise CoordinationError(
                    f"recovery_rejected: evidence field '{k}' not allowed"
                )

        # Operator-supplied "proof" fields are ignored (Handoff-6 defect).
        # Only candidate_tx_hash is a hint for server-side lookup.
        candidate = (
            evidence.get("candidate_tx_hash")
            or evidence.get("tx_hash")  # legacy key name — treated as hint only
        )
        if candidate is not None:
            candidate = str(candidate).strip().lower()
            if candidate and not candidate.startswith("0x"):
                raise CoordinationError(
                    "recovery_rejected: candidate_tx_hash must be 0x-prefixed"
                )
            if candidate and len(candidate) > 66:
                raise CoordinationError(
                    "recovery_rejected: candidate_tx_hash malformed"
                )
            if not candidate:
                candidate = None

        audit = self._db[audit_coll_name]
        claim_id = f"recv-{uuid.uuid4().hex}"
        audit_doc = {
            "claim_id": claim_id,
            "operator": operator,
            "reason": reason,
            "decision": decision,
            "send_id": send_id,
            "evidence_summary": {
                "evidence_authority": "server_trusted_rpc",
                "operator_proof_fields_ignored": True,
                "candidate_tx_hash_prefix": (
                    (candidate[:10] + "…") if candidate and len(candidate) > 12
                    else candidate
                ),
            },
            "status": "started",
            "at": _now_iso(),
        }
        try:
            await audit.insert_one(dict(audit_doc))
        except Exception as exc:  # noqa: BLE001
            raise CoordinationError(
                f"recovery_audit_failed: {type(exc).__name__}"
            ) from exc

        try:
            cur = await self._coord.find_one({"key": COORD_KEY}, {"_id": 0})
        except Exception as exc:  # noqa: BLE001
            await self._audit_finish(
                audit, claim_id, ok=False, action="coord_unavailable",
                detail=type(exc).__name__,
            )
            raise CoordinationError(
                f"recovery_coord_unavailable: {type(exc).__name__}"
            ) from exc

        if not cur:
            await self._audit_finish(audit, claim_id, ok=False, action="no_coord_doc")
            raise CoordinationError("recovery_rejected: coordination document missing")

        active = cur.get("active_send") or {}
        if not active:
            await self._audit_finish(
                audit, claim_id, ok=True, action="noop_no_active_send"
            )
            return {
                "ok": True, "action": "noop_no_active_send",
                "claim_id": claim_id, "resend_forbidden": False,
            }

        sid = send_id or active.get("send_id")
        if send_id and active.get("send_id") != send_id:
            await self._audit_finish(audit, claim_id, ok=False, action="send_id_mismatch")
            raise CoordinationError("recovery_rejected: send_id mismatch")

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

        active = claimed.get("active_send") or {}
        # Signer override is advisory only when stuck record lacks signer;
        # when stuck has a signer it is authoritative.
        stuck_signer = (active.get("signer") or "").lower()
        if stuck_signer:
            signer_key = stuck_signer
            if signer and str(signer).lower() != stuck_signer:
                await self._release_recovery_claim(claim_id, note="signer_override_rejected")
                await self._audit_finish(
                    audit, claim_id, ok=False, action="signer_mismatch"
                )
                raise CoordinationError(
                    "recovery_rejected: request signer disagrees with stuck send"
                )
        else:
            signer_key = (signer or "").lower()

        nonce_i = active.get("nonce")
        if nonce_i is not None:
            nonce_i = int(nonce_i)

        if decision == "investigate":
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

        # ---- Trusted RPC verification (authoritative) ----
        try:
            chain_id = int(active["chain_id"])
        except (KeyError, TypeError, ValueError):
            await self._release_recovery_claim(claim_id, note="missing_chain_id")
            await self._audit_finish(
                audit, claim_id, ok=False, action="stuck_metadata_incomplete"
            )
            raise CoordinationError(
                "recovery_rejected: stuck send missing chain_id — remain blocked"
            )

        if not active.get("tx_binding_digest"):
            await self._release_recovery_claim(claim_id, note="missing_digest")
            await self._audit_finish(
                audit, claim_id, ok=False, action="stuck_metadata_incomplete"
            )
            raise CoordinationError(
                "recovery_rejected: stuck send missing tx_binding_digest"
            )
        if nonce_i is None or not signer_key:
            await self._release_recovery_claim(claim_id, note="missing_signer_nonce")
            await self._audit_finish(
                audit, claim_id, ok=False, action="stuck_metadata_incomplete"
            )
            raise CoordinationError(
                "recovery_rejected: stuck send missing signer/nonce"
            )

        verifier = self._verifier()
        try:
            chain_obs = await verifier.observe_chain_id(chain_id)
        except Exception as exc:  # noqa: BLE001
            await self._release_recovery_claim(claim_id, note="rpc_unavailable")
            await self._audit_finish(
                audit, claim_id, ok=False, action="rpc_unavailable",
                detail=type(exc).__name__,
            )
            raise CoordinationError(
                f"recovery_rejected: trusted RPC unavailable ({type(exc).__name__})"
            ) from exc

        if int(chain_obs.observed_chain_id) != int(chain_id):
            await self._release_recovery_claim(claim_id, note="chain_id_mismatch")
            await self._audit_finish(
                audit, claim_id, ok=False, action="chain_id_mismatch",
                detail=f"observed={chain_obs.observed_chain_id} expected={chain_id}",
                evidence_summary=evidence_audit_summary(chain_obs=chain_obs),
            )
            raise CoordinationError(
                "recovery_rejected: trusted RPC chain_id disagrees with stuck send"
            )

        if decision == "tx_found":
            return await self._recover_tx_found(
                audit=audit,
                claim_id=claim_id,
                operator=operator,
                sid=sid,
                active=active,
                signer_key=signer_key,
                nonce_i=nonce_i,
                chain_id=chain_id,
                candidate=candidate,
                chain_obs=chain_obs,
                verifier=verifier,
            )

        # decision == tx_absent
        return await self._recover_tx_absent(
            audit=audit,
            claim_id=claim_id,
            operator=operator,
            sid=sid,
            active=active,
            signer_key=signer_key,
            nonce_i=nonce_i,
            chain_id=chain_id,
            candidate=candidate,
            chain_obs=chain_obs,
            verifier=verifier,
        )

    async def _recover_tx_found(
        self,
        *,
        audit,
        claim_id: str,
        operator: str,
        sid: str,
        active: Dict[str, Any],
        signer_key: str,
        nonce_i: int,
        chain_id: int,
        candidate: Optional[str],
        chain_obs,
        verifier,
    ) -> Dict[str, Any]:
        from .recovery_rpc_evidence import (
            assert_tx_bound_to_stuck,
            evidence_audit_summary,
        )

        # Prefer durable hint from nonce lease if operator omitted candidate.
        hint = candidate
        if not hint:
            try:
                ndoc = await self._nonces.find_one(
                    {"key": signer_key}, {"_id": 0}
                ) or {}
                inflight = ndoc.get("inflight") or {}
                if inflight.get("tx_hash"):
                    hint = str(inflight["tx_hash"]).strip().lower()
            except Exception:  # noqa: BLE001
                hint = None
        if not hint:
            await self._release_recovery_claim(claim_id, note="candidate_tx_hash_required")
            await self._audit_finish(
                audit, claim_id, ok=False, action="evidence_incomplete",
                evidence_summary=evidence_audit_summary(chain_obs=chain_obs),
            )
            raise CoordinationError(
                "recovery_rejected: tx_found requires candidate_tx_hash "
                "(server will verify via trusted RPC)"
            )

        tx_obs = await verifier.observe_transaction(chain_id, hint)
        if tx_obs.status != "found" or not tx_obs.tx:
            await self._release_recovery_claim(
                claim_id, note=f"tx_lookup_{tx_obs.status}"
            )
            await self._audit_finish(
                audit, claim_id, ok=False,
                action="tx_not_authoritatively_found",
                detail=tx_obs.status,
                evidence_summary=evidence_audit_summary(
                    chain_obs=chain_obs, tx_obs=tx_obs, candidate_tx_hash=hint,
                ),
            )
            raise CoordinationError(
                f"recovery_rejected: trusted RPC did not find transaction "
                f"(status={tx_obs.status!r}); remain blocked"
            )

        try:
            assert_tx_bound_to_stuck(tx_obs.tx, stuck=active)
        except (PermissionError, ValueError) as exc:
            await self._release_recovery_claim(claim_id, note="binding_failed")
            await self._audit_finish(
                audit, claim_id, ok=False, action="tx_binding_failed",
                detail=str(exc)[:200],
                evidence_summary=evidence_audit_summary(
                    chain_obs=chain_obs, tx_obs=tx_obs,
                    candidate_tx_hash=hint, binding_ok=False,
                ),
            )
            raise CoordinationError(
                f"recovery_rejected: {exc}"
            ) from exc

        try:
            nonce_obs = await verifier.observe_nonces(chain_id, signer_key)
        except Exception as exc:  # noqa: BLE001
            await self._release_recovery_claim(claim_id, note="nonce_rpc_failed")
            await self._audit_finish(
                audit, claim_id, ok=False, action="rpc_unavailable",
                detail=type(exc).__name__,
            )
            raise CoordinationError(
                f"recovery_rejected: trusted nonce RPC failed ({type(exc).__name__})"
            ) from exc

        summary = evidence_audit_summary(
            chain_obs=chain_obs, tx_obs=tx_obs, nonce_obs=nonce_obs,
            candidate_tx_hash=hint, binding_ok=True,
        )
        outcome = {
            "terminal_status": "completed",
            "action": "completed_on_chain_no_resend",
            "resolved_tx_hash": hint,
            "resend_forbidden": True,
            "nonce_reconcile": {
                "tx_found_on_chain": True,
                "chain_pending_nonce": max(nonce_obs.pending_nonce, nonce_i + 1),
            },
        }
        return await self._commit_recovery(
            audit=audit,
            claim_id=claim_id,
            operator=operator,
            sid=sid,
            active=active,
            signer_key=signer_key,
            nonce_i=nonce_i,
            outcome=outcome,
            evidence_summary=summary,
        )

    async def _recover_tx_absent(
        self,
        *,
        audit,
        claim_id: str,
        operator: str,
        sid: str,
        active: Dict[str, Any],
        signer_key: str,
        nonce_i: int,
        chain_id: int,
        candidate: Optional[str],
        chain_obs,
        verifier,
    ) -> Dict[str, Any]:
        from .recovery_rpc_evidence import (
            evidence_audit_summary,
            parse_rpc_entered_age_s,
        )

        age = parse_rpc_entered_age_s(active)
        min_age = float(getattr(verifier, "absent_min_age_s", 0) or 0)
        if age < min_age:
            await self._release_recovery_claim(claim_id, note="absent_too_fresh")
            await self._audit_finish(
                audit, claim_id, ok=False, action="evidence_stale_window",
                detail=f"age_s={age:.3f} min={min_age}",
                evidence_summary=evidence_audit_summary(chain_obs=chain_obs),
            )
            raise CoordinationError(
                "recovery_rejected: rpc_submitted too recent for tx_absent; "
                "remain blocked (possible delayed/pending acceptance)"
            )

        # If a concrete hash is known, absence of THAT hash is required —
        # but never sufficient alone.
        tx_obs = None
        if candidate:
            tx_obs = await verifier.observe_transaction(chain_id, candidate)
            if tx_obs.status == "error":
                await self._release_recovery_claim(claim_id, note="tx_lookup_error")
                await self._audit_finish(
                    audit, claim_id, ok=False, action="rpc_unavailable",
                    evidence_summary=evidence_audit_summary(
                        chain_obs=chain_obs, tx_obs=tx_obs,
                        candidate_tx_hash=candidate,
                    ),
                )
                raise CoordinationError(
                    "recovery_rejected: trusted tx lookup errored; remain blocked"
                )
            if tx_obs.status == "found":
                await self._release_recovery_claim(claim_id, note="candidate_still_present")
                await self._audit_finish(
                    audit, claim_id, ok=False, action="evidence_contradictory",
                    detail="candidate_tx_hash still present on trusted RPC",
                    evidence_summary=evidence_audit_summary(
                        chain_obs=chain_obs, tx_obs=tx_obs,
                        candidate_tx_hash=candidate,
                    ),
                )
                raise CoordinationError(
                    "recovery_rejected: candidate_tx_hash still present — "
                    "use decision=tx_found if it binds to the stuck send"
                )

        try:
            nonce_obs = await verifier.observe_nonces_consistent(
                chain_id, signer_key
            )
        except Exception as exc:  # noqa: BLE001
            await self._release_recovery_claim(claim_id, note="nonce_rpc_failed")
            await self._audit_finish(
                audit, claim_id, ok=False, action="rpc_unavailable",
                detail=str(exc)[:200],
                evidence_summary=evidence_audit_summary(
                    chain_obs=chain_obs, tx_obs=tx_obs,
                    candidate_tx_hash=candidate,
                ),
            )
            raise CoordinationError(
                f"recovery_rejected: authoritative nonce evidence unavailable "
                f"({exc}); remain blocked"
            ) from exc

        pending = int(nonce_obs.pending_nonce)
        latest = int(nonce_obs.latest_nonce)
        summary = evidence_audit_summary(
            chain_obs=chain_obs, tx_obs=tx_obs, nonce_obs=nonce_obs,
            candidate_tx_hash=candidate,
        )

        # Conservative absence policy:
        # * pending == latest == stuck nonce → no acceptance of this nonce
        # * pending > stuck → nonce consumed by something → stay blocked
        # * pending < stuck → chain behind our allocation → still unused OK
        # * pending != latest → mempool activity → ambiguous → stay blocked
        if pending != latest:
            await self._release_recovery_claim(claim_id, note="pending_ne_latest")
            await self._audit_finish(
                audit, claim_id, ok=False, action="evidence_inconclusive",
                detail="pending_nonce != latest_nonce",
                evidence_summary=summary,
            )
            raise CoordinationError(
                "recovery_rejected: pending/latest nonce diverge — "
                "delayed or pending transaction possible; remain blocked"
            )
        if pending > nonce_i:
            await self._release_recovery_claim(claim_id, note="pending_ahead")
            await self._audit_finish(
                audit, claim_id, ok=False, action="evidence_contradictory",
                detail="pending advanced without bound tx_found",
                evidence_summary=summary,
            )
            raise CoordinationError(
                "recovery_rejected: chain pending nonce advanced past stuck "
                "nonce without a digest-bound tx_found — remain blocked"
            )
        if pending < nonce_i:
            # Chain has not reached our nonce — unused is consistent.
            pass
        # pending == nonce_i and pending == latest → unused

        outcome = {
            "terminal_status": "recovered_unused",
            "action": "released_unused",
            "resolved_tx_hash": None,
            "resend_forbidden": False,
            "nonce_reconcile": {
                "tx_found_on_chain": False,
                "chain_pending_nonce": pending,
            },
            "note": "nonce reusable; prior send_id must not be resent",
        }
        return await self._commit_recovery(
            audit=audit,
            claim_id=claim_id,
            operator=operator,
            sid=sid,
            active=active,
            signer_key=signer_key,
            nonce_i=nonce_i,
            outcome=outcome,
            evidence_summary=summary,
        )

    async def _commit_recovery(
        self,
        *,
        audit,
        claim_id: str,
        operator: str,
        sid: str,
        active: Dict[str, Any],
        signer_key: str,
        nonce_i: int,
        outcome: Dict[str, Any],
        evidence_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Crash-safe: audit commit_intent → durable terminal status → audit finish."""
        action = str(outcome["action"])
        terminal = str(outcome["terminal_status"])
        tx_hash = outcome.get("resolved_tx_hash")
        resend_forbidden = bool(outcome.get("resend_forbidden"))

        # Persist intent BEFORE mutating coordination (Handoff-6 crash finding).
        try:
            await audit.update_one(
                {"claim_id": claim_id},
                {
                    "$set": {
                        "status": "commit_intent",
                        "action": action,
                        "commit_intent": {
                            "terminal_status": terminal,
                            "resolved_tx_hash": tx_hash,
                            "resend_forbidden": resend_forbidden,
                            "send_id": sid,
                        },
                        "evidence_summary": evidence_summary,
                        "commit_intent_at": _now_iso(),
                    }
                },
            )
        except Exception as exc:  # noqa: BLE001
            await self._release_recovery_claim(claim_id, note="commit_intent_audit_failed")
            raise CoordinationError(
                f"recovery_audit_failed: commit_intent {type(exc).__name__}"
            ) from exc

        from pymongo import ReturnDocument

        committed = await self._coord.find_one_and_update(
            {
                "key": COORD_KEY,
                "active_send.send_id": sid,
                "active_send.status": "rpc_submitted",
                "active_send.recovery_claim_id": claim_id,
            },
            {
                "$set": {
                    "active_send.status": terminal,
                    "active_send.resolved_tx_hash": tx_hash,
                    "active_send.resend_forbidden": resend_forbidden,
                    "active_send.finished_at": _now_iso(),
                    "active_send.recovery_claim_id": None,
                    "active_send.recovery_expires_ts": None,
                    "active_send.recovered_by": operator,
                    "active_send.last_recovery_note": action,
                    "active_send.recovery_evidence": {
                        "authority": "server_trusted_rpc",
                        "binding_ok": evidence_summary.get("binding_ok"),
                        "observed_chain_id": evidence_summary.get("observed_chain_id"),
                        "pending_nonce": evidence_summary.get("pending_nonce"),
                        "latest_nonce": evidence_summary.get("latest_nonce"),
                        "tx_lookup": evidence_summary.get("tx_lookup"),
                    },
                    "updated_at": _now_iso(),
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not committed:
            # Another actor won, or state changed — fail closed (do not invent success).
            await self._audit_finish(
                audit, claim_id, ok=False, action="commit_cas_failed",
                evidence_summary=evidence_summary,
            )
            raise CoordinationError(
                "recovery_rejected: durable commit lost race or state changed"
            )

        nr = outcome.get("nonce_reconcile") or {}
        try:
            await self.reconcile_nonce(
                signer_key,
                chain_pending_nonce=int(
                    nr.get("chain_pending_nonce")
                    if nr.get("chain_pending_nonce") is not None
                    else nonce_i
                ),
                tx_hash=tx_hash,
                tx_found_on_chain=bool(nr.get("tx_found_on_chain")),
                owner_id=str(active.get("owner_id") or self.instance_id),
            )
        except Exception as exc:  # noqa: BLE001
            # Terminal send state already committed — record but surface.
            await self._audit_finish(
                audit, claim_id, ok=True, action=action,
                detail=f"nonce_reconcile_error:{type(exc).__name__}",
                evidence_summary=evidence_summary,
            )
            return {
                "ok": True,
                "action": action,
                "claim_id": claim_id,
                "send_id": sid,
                "resolved_tx_hash": tx_hash,
                "resend_forbidden": resend_forbidden,
                "status": terminal,
                "note": outcome.get("note"),
                "nonce_reconcile_warning": type(exc).__name__,
            }

        await self._audit_finish(
            audit, claim_id, ok=True, action=action,
            evidence_summary=evidence_summary,
        )
        return {
            "ok": True,
            "action": action,
            "claim_id": claim_id,
            "send_id": sid,
            "resolved_tx_hash": tx_hash,
            "resend_forbidden": resend_forbidden,
            "status": terminal,
            "note": outcome.get("note"),
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
        self,
        audit,
        claim_id: str,
        *,
        ok: bool,
        action: str,
        detail: Optional[str] = None,
        evidence_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            patch: Dict[str, Any] = {
                "status": "ok" if ok else "rejected",
                "action": action,
                "detail": detail,
                "finished_at": _now_iso(),
            }
            if evidence_summary is not None:
                patch["evidence_summary"] = evidence_summary
            await audit.update_one({"claim_id": claim_id}, {"$set": patch})
        except Exception:  # noqa: BLE001
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
