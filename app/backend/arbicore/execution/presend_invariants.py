"""WP-C · Pre-send enforcement primitives (offline-testable).

Authoritative kill-switch reads, kill-vs-send critical section, transaction
byte binding, chain allowlists/ceilings, durable budgets, nonce coordination,
and technical-validation failure cleanup helpers.

No live RPC / sign / broadcast occurs in this module.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, FrozenSet, Optional, Tuple

logger = logging.getLogger("arbicore.execution.presend_invariants")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# C4 · Chain allowlist + per-chain ceilings (this-build freeze)
# ---------------------------------------------------------------------------

# Broadcast allowlist for this build: Base mainnet only.
# Multichain discovery must not imply multichain broadcast.
ALLOWED_BROADCAST_CHAIN_IDS: Dict[str, int] = {
    "base": 8453,
}

# Per-chain notional ceiling (USD) — fail-closed if exceeded at send gate.
PER_CHAIN_CEILING_USD: Dict[str, float] = {
    "base": 2_500.0,
}


class ChainPolicyError(PermissionError):
    """Raised when chain_id / ceiling checks fail."""


def assert_chain_allowed(chain: str, chain_id: Optional[int] = None) -> int:
    key = (chain or "").strip().lower()
    if key not in ALLOWED_BROADCAST_CHAIN_IDS:
        raise ChainPolicyError(
            f"chain '{chain}' not in broadcast allowlist "
            f"{sorted(ALLOWED_BROADCAST_CHAIN_IDS)}"
        )
    expected = ALLOWED_BROADCAST_CHAIN_IDS[key]
    if chain_id is not None and int(chain_id) != expected:
        raise ChainPolicyError(
            f"chain_id mismatch for '{key}': got {chain_id}, expected {expected}"
        )
    return expected


def assert_chain_ceiling(chain: str, notional_usd: float) -> None:
    key = (chain or "").strip().lower()
    ceiling = PER_CHAIN_CEILING_USD.get(key)
    if ceiling is None:
        raise ChainPolicyError(f"no ceiling configured for chain '{chain}'")
    if float(notional_usd) > float(ceiling):
        raise ChainPolicyError(
            f"notional {notional_usd} exceeds per-chain ceiling {ceiling} on {key}"
        )


# ---------------------------------------------------------------------------
# C3 · Transaction-byte immutability binding
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TxByteBinding:
    """Cryptographic bind of validated tx fields to the sign/send boundary."""

    digest: str
    to: str
    data: str
    value_wei: int
    chain_id: int
    nonce: int
    gas: int
    gas_price_wei: int

    @staticmethod
    def from_tx(tx: Dict[str, Any]) -> "TxByteBinding":
        canonical = {
            "to": str(tx.get("to") or "").lower(),
            "data": str(tx.get("data") or "").lower(),
            "value": int(tx.get("value") or 0),
            "chainId": int(tx.get("chainId") or 0),
            "nonce": int(tx.get("nonce") or 0),
            "gas": int(tx.get("gas") or 0),
            "gasPrice": int(tx.get("gasPrice") or 0),
        }
        raw = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(raw).hexdigest()
        return TxByteBinding(
            digest=digest,
            to=canonical["to"],
            data=canonical["data"],
            value_wei=canonical["value"],
            chain_id=canonical["chainId"],
            nonce=canonical["nonce"],
            gas=canonical["gas"],
            gas_price_wei=canonical["gasPrice"],
        )

    def assert_matches(self, tx: Dict[str, Any]) -> None:
        other = TxByteBinding.from_tx(tx)
        if other.digest != self.digest:
            raise PermissionError(
                "tx_byte_immutability: validated transaction bytes mutated "
                f"before send (expected={self.digest[:16]}… got={other.digest[:16]}…)"
            )


# ---------------------------------------------------------------------------
# C2 · Kill-vs-send critical section (not check-then-send)
# ---------------------------------------------------------------------------

class SendCriticalSection:
    """DEPRECATED for LIVE broadcast — process-local only (Handoff-4 / C2).

    Retained for unit-level illustrations. Production send path uses
    ``BroadcastCoordinator`` in ``durable_broadcast_coordination.py``.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def run_send(self, *, kill_switch, send_coro_factory):
        """Re-read KS under lock, then invoke ``send_coro_factory()`` still holding the lock."""
        async with self._lock:
            await kill_switch.guard()
            return await send_coro_factory()


# ---------------------------------------------------------------------------
# C6 · Nonce coordination / single-writer
# ---------------------------------------------------------------------------

SINGLE_WRITER_ENV = "ARBICORE_BROADCAST_INSTANCE_ID"


class NonceCoordinator:
    """DEPRECATED for LIVE broadcast — process-local only (Handoff-4 / C6).

    Retained for unit-level illustrations. Production path uses
    ``BroadcastCoordinator`` durable writer/nonce leases.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._leases: Dict[str, int] = {}
        self._writer_id: Optional[str] = None

    def claim_writer(self, instance_id: Optional[str] = None) -> None:
        iid = instance_id or os.environ.get(SINGLE_WRITER_ENV) or "default"
        if self._writer_id is None:
            self._writer_id = iid
            return
        if self._writer_id != iid:
            raise PermissionError(
                f"nonce_coordination: single-writer violated "
                f"(held by {self._writer_id!r}, claimed by {iid!r})"
            )

    async def allocate(self, signer: str, observed_nonce: int) -> int:
        async with self._lock:
            key = (signer or "").lower()
            current = self._leases.get(key)
            if current is None:
                self._leases[key] = observed_nonce
                return observed_nonce
            if observed_nonce > current:
                self._leases[key] = observed_nonce
                return observed_nonce
            # Serialize: next nonce after in-flight lease
            nxt = current + 1
            self._leases[key] = nxt
            return nxt

    async def release(self, signer: str, nonce: int) -> None:
        """No-op placeholder for lease release after send settles."""
        return None


# ---------------------------------------------------------------------------
# C5 · Durable budgets (Mongo-backed counters)
# ---------------------------------------------------------------------------

class DurableBudgetStore:
    """Concurrency-safe cumulative budgets persisted in Mongo.

    Uses find_one_and_update with $inc for atomic increments.
    """

    def __init__(self, db, collection: str = "arbicore_durable_budgets"):
        self._coll = db[collection]

    async def ensure_indexes(self) -> None:
        await self._coll.create_index("key", unique=True)

    async def get(self, key: str) -> float:
        doc = await self._coll.find_one({"key": key}, {"_id": 0})
        return float((doc or {}).get("value") or 0.0)

    async def add_and_check(
        self, key: str, delta: float, *, ceiling: float
    ) -> Tuple[bool, float]:
        """Atomically add ``delta``; return (allowed, new_total).

        If the post-increment total would exceed ``ceiling``, the increment
        is reverted (second $inc negative) and allowed=False.
        """
        from pymongo import ReturnDocument

        doc = await self._coll.find_one_and_update(
            {"key": key},
            {"$inc": {"value": float(delta)},
             "$set": {"updated_at": _now_iso()},
             "$setOnInsert": {"key": key}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        total = float((doc or {}).get("value") or 0.0)
        if total > float(ceiling):
            await self._coll.update_one(
                {"key": key},
                {"$inc": {"value": -float(delta)},
                 "$set": {"updated_at": _now_iso()}},
            )
            return False, total - float(delta)
        return True, total


# ---------------------------------------------------------------------------
# C7 · Technical-validation failure cleanup
# ---------------------------------------------------------------------------

async def cleanup_failed_technical_validation(
    db, *, opportunity_id: Optional[str] = None, run_id: Optional[str] = None
) -> Dict[str, Any]:
    """Expire sticky allowances / eligibility flags after failed TV.

    Clears ``arbicore_tv_allowances`` matching the run/opportunity and marks
    the validation record as ``cleanup=expired`` so a retry requires full
    re-validation. Fail-closed: if cleanup cannot run, returns ok=False.
    """
    now = _now_iso()
    q: Dict[str, Any] = {}
    if opportunity_id:
        q["opportunity_id"] = opportunity_id
    if run_id:
        q["run_id"] = run_id
    if not q:
        q = {"status": {"$in": ["FAILED", "failed", "ERROR", "error"]}}
    try:
        allow = await db["arbicore_tv_allowances"].delete_many(q)
        await db["arbicore_technical_validations"].update_many(
            {**q, "engine_ready": {"$ne": True}},
            {"$set": {
                "live_eligible": False,
                "allowance_cleared": True,
                "cleanup_at": now,
                "cleanup": "expired",
            }},
        )
        return {
            "ok": True,
            "allowances_deleted": int(getattr(allow, "deleted_count", 0) or 0),
            "cleaned_at": now,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("tv cleanup failed")
        return {"ok": False, "error": type(exc).__name__, "cleaned_at": now}


# ---------------------------------------------------------------------------
# C1 helpers · authoritative engage flag
# ---------------------------------------------------------------------------

@dataclass
class AuthoritativeKillView:
    engaged: bool
    reason: Optional[str]
    source: str  # "persistent" | "fail_closed_unavailable"


async def read_authoritative_kill(repo) -> AuthoritativeKillView:
    """Persistent KillSwitchRepo is the sole source of truth.

    Unavailable state → engaged=True (fail-closed).
    """
    try:
        st = await repo.state()
        return AuthoritativeKillView(
            engaged=bool(st.engaged),
            reason=getattr(st, "reason", None),
            source="persistent",
        )
    except Exception as exc:  # noqa: BLE001
        return AuthoritativeKillView(
            engaged=True,
            reason=f"state_unavailable: {type(exc).__name__}",
            source="fail_closed_unavailable",
        )
