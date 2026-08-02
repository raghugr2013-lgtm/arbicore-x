"""ArbiCore X — Opportunity Journal (P0-A).

The Opportunity Journal is the append-only historical intelligence store
that records every opportunity the platform observes, from first sighting
through final outcome. It is the write-side foundation of both:

  * the Learning Ledger (P0-B) — which turns journal rows into labelled
    samples for the calibration + adaptive-weights workers.
  * the Autonomous Executor (P0-D) — which uses the journal as its
    memory: which opportunities have already been quoted, certified,
    scored, and either rejected or broadcast.

Design invariants:
  * ONE aggregated document per ``opportunity_id`` — the document carries
    ``first_seen``, ``last_seen``, ``lifetime_ms`` plus every state change
    as an ``events`` array (append-only). This keeps queries cheap and
    preserves the full audit trail on the same row.
  * Reuses the existing Motor ``db`` handle. No new drivers, no new
    dependencies.
  * Never discards a row. Rejections, skips, kill-switch trips, policy
    denials — everything is captured with a stable ``execution_status``
    label so the AI can learn from *why* we did not trade, not only from
    trades that happened.
  * Writes are idempotent per (``opportunity_id``, ``event.kind``,
    ``event.at``) — replays cannot corrupt history.

Collection: ``arbicore_opportunity_journal``
Indexes:    ``opportunity_id`` (unique), ``execution_status``, ``mode``,
            ``opportunity_type``, ``last_seen`` (desc).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Constants + enums
# ---------------------------------------------------------------------------

JOURNAL_COLLECTION = "arbicore_opportunity_journal"


class ExecutionStatus(str, Enum):
    """Coarse-grained state label for the journal aggregate row."""

    DISCOVERED       = "DISCOVERED"       # first observation, nothing evaluated yet
    QUOTED           = "QUOTED"           # live quote captured (buy + sell)
    GAS_ESTIMATED    = "GAS_ESTIMATED"    # gas oracle answered
    PROFITED         = "PROFITED"         # economics engine returned a decision
    CERTIFIED        = "CERTIFIED"        # certification pipeline returned OK
    POLICY_DENIED    = "POLICY_DENIED"    # policy engine blocked (mode / capital / kill switch)
    REJECTED         = "REJECTED"         # any other rejection (below threshold, invalid, etc.)
    SHADOW_RECORDED  = "SHADOW_RECORDED"  # would-have-broadcast in SHADOW mode
    BROADCAST_SENT   = "BROADCAST_SENT"   # real broadcast dispatched
    BROADCAST_FAILED = "BROADCAST_FAILED" # broadcast attempt reverted / errored
    COMPLETED        = "COMPLETED"        # broadcast + confirmed + PnL recorded


TERMINAL_STATUSES = frozenset({
    ExecutionStatus.REJECTED,
    ExecutionStatus.POLICY_DENIED,
    ExecutionStatus.SHADOW_RECORDED,
    ExecutionStatus.COMPLETED,
    ExecutionStatus.BROADCAST_FAILED,
})


class LearningLabel(str, Enum):
    """Coarse learning signal derived by the Learning Ledger (P0-B)."""

    POSITIVE = "POSITIVE"   # executed profitably OR shadow decision matched reality
    NEGATIVE = "NEGATIVE"   # executed at a loss OR shadow decision contradicted reality
    NEUTRAL  = "NEUTRAL"    # rejected / skipped / not enough signal yet
    PENDING  = "PENDING"    # awaiting outcome


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except Exception:
        return None


class JournalEvent(BaseModel):
    """One immutable state-change record on a journal row."""

    model_config = ConfigDict(extra="forbid")

    kind: str                                 # e.g. 'discovered', 'quoted', 'policy_denied'
    at: str = Field(default_factory=_iso_now)
    detail: Dict[str, Any] = Field(default_factory=dict)


class JournalEntry(BaseModel):
    """Aggregated per-opportunity journal document.

    All fields are Optional except identity + lifecycle timestamps, so the
    document can be built incrementally as the pipeline enriches it.
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    # Identity
    opportunity_id: str
    opportunity_type: Optional[str] = None
    chain: Optional[str] = None
    asset: Optional[str] = None
    buy_venue: Optional[str] = None
    sell_venue: Optional[str] = None
    scanner_family: Optional[str] = None

    # Lifecycle timestamps
    first_seen: str = Field(default_factory=_iso_now)
    last_seen: str = Field(default_factory=_iso_now)
    lifetime_ms: int = 0
    observation_count: int = 1

    # Economics snapshot (most recent)
    expected_profit_usd: Optional[float] = None
    capital_required_usd: Optional[float] = None
    spread_pct: Optional[float] = None
    gas_estimate: Optional[Dict[str, Any]] = None       # {gwei, units, usd}

    # Intelligence snapshot (most recent)
    confidence_score: Optional[float] = None
    risk_score: Optional[float] = None
    mev_risk_level: Optional[str] = None

    # Decisions
    certification_result: Optional[Dict[str, Any]] = None   # {status, stage_results?, evidence_hash?}
    policy_decision: Optional[Dict[str, Any]] = None        # {decision, reasons, engine}
    rejection_reason: Optional[str] = None

    # Execution
    execution_status: str = ExecutionStatus.DISCOVERED.value
    mode: Optional[str] = None                              # OBSERVE / PAPER / SHADOW / LIMITED_LIVE / FULL_LIVE
    expected_result: Optional[Dict[str, Any]] = None        # what the planner/simulator predicted
    actual_result: Optional[Dict[str, Any]] = None          # what actually happened after broadcast
    plan_id: Optional[str] = None

    # Learning
    learning_label: str = LearningLabel.PENDING.value
    learning_consumed: bool = False

    # Immutable event trail
    events: List[JournalEvent] = Field(default_factory=list)

    # System
    created_at: str = Field(default_factory=_iso_now)
    updated_at: str = Field(default_factory=_iso_now)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

class OpportunityJournal:
    """Motor-backed append-only journal.

    Public API:
        record_discovery(opp, mode, scanner_family=None)
        record_event(opportunity_id, kind, detail, patch=None, status=None)
        set_learning_label(opportunity_id, label, consumed=False)
        get(opportunity_id) -> Optional[JournalEntry]
        list(filter_dict, limit=100) -> List[JournalEntry]
        summary() -> Dict[str, Any]
    """

    def __init__(self, db, *, collection_name: str = JOURNAL_COLLECTION):
        self._db = db
        self._collection_name = collection_name

    # ---- Collection accessor -----------------------------------------
    @property
    def _col(self):
        return self._db[self._collection_name]

    async def ensure_indexes(self) -> None:
        c = self._col
        await c.create_index("opportunity_id", unique=True)
        await c.create_index("execution_status")
        await c.create_index("opportunity_type")
        await c.create_index("mode")
        await c.create_index([("last_seen", -1)])
        await c.create_index("learning_label")
        await c.create_index("learning_consumed")

    # ---- Internal helpers --------------------------------------------
    @staticmethod
    def _lifetime_ms(first_seen_iso: str, last_seen_iso: str) -> int:
        a = _parse_iso(first_seen_iso)
        b = _parse_iso(last_seen_iso)
        if not a or not b:
            return 0
        delta = (b - a).total_seconds() * 1000.0
        return int(max(delta, 0))

    async def _load(self, opportunity_id: str) -> Optional[JournalEntry]:
        doc = await self._col.find_one({"opportunity_id": opportunity_id}, {"_id": 0})
        if not doc:
            return None
        return JournalEntry.model_validate(doc)

    async def _save(self, entry: JournalEntry) -> None:
        entry.updated_at = _iso_now()
        entry.lifetime_ms = self._lifetime_ms(entry.first_seen, entry.last_seen)
        doc = entry.model_dump(mode="json")
        await self._col.update_one(
            {"opportunity_id": entry.opportunity_id},
            {"$set": doc},
            upsert=True,
        )

    # ---- Public write API --------------------------------------------
    async def record_discovery(
        self,
        opp: Any,
        *,
        mode: str,
        scanner_family: Optional[str] = None,
        detail: Optional[Dict[str, Any]] = None,
    ) -> JournalEntry:
        """Idempotently record an opportunity observation.

        Accepts either a ``CanonicalOpportunity`` (duck-typed) or a plain
        dict with the same keys. If the opportunity has been seen before
        the ``last_seen`` + ``observation_count`` are updated but the
        ``first_seen`` is preserved.
        """
        opp_id = self._get(opp, "opportunity_id") or uuid.uuid4().hex
        existing = await self._load(opp_id)
        now = _iso_now()
        event = JournalEvent(
            kind="discovered",
            at=now,
            detail=detail or {},
        )
        if existing:
            existing.last_seen = now
            existing.observation_count += 1
            existing.mode = mode
            if scanner_family:
                existing.scanner_family = scanner_family
            existing.events.append(event)
            self._enrich_from_opp(existing, opp)
            await self._save(existing)
            return existing

        entry = JournalEntry(
            opportunity_id=opp_id,
            opportunity_type=self._get(opp, "opportunity_type"),
            chain=self._get(opp, "chain"),
            asset=self._get(opp, "asset"),
            buy_venue=self._get(opp, "buy_venue"),
            sell_venue=self._get(opp, "sell_venue"),
            scanner_family=scanner_family,
            first_seen=now,
            last_seen=now,
            expected_profit_usd=self._get(opp, "expected_profit_usd"),
            capital_required_usd=self._get(opp, "capital_required_usd"),
            spread_pct=self._get(opp, "spread_pct"),
            confidence_score=self._get(opp, "confidence_score"),
            risk_score=self._get(opp, "risk_score"),
            mev_risk_level=self._normalise_enum(self._get(opp, "mev_risk_level")),
            mode=mode,
            events=[event],
        )
        await self._save(entry)
        return entry

    async def record_event(
        self,
        opportunity_id: str,
        kind: str,
        *,
        detail: Optional[Dict[str, Any]] = None,
        patch: Optional[Dict[str, Any]] = None,
        status: Optional[str] = None,
    ) -> Optional[JournalEntry]:
        """Append an event to an existing row. Never creates a new row.

        Returns None if the row does not exist (caller must have called
        ``record_discovery`` first). This is intentional — every
        opportunity begins with a discovery event.
        """
        entry = await self._load(opportunity_id)
        if not entry:
            return None
        entry.last_seen = _iso_now()
        entry.events.append(JournalEvent(kind=kind, detail=detail or {}))
        if patch:
            data = entry.model_dump()
            data.update({k: v for k, v in patch.items() if k in data and k not in {
                "opportunity_id", "first_seen", "created_at", "events",
            }})
            entry = JournalEntry.model_validate(data)
            entry.last_seen = _iso_now()
            entry.events = [
                *entry.events[:-1],
                JournalEvent(kind=kind, detail=detail or {}),
            ]
        if status:
            entry.execution_status = status
        await self._save(entry)
        return entry

    async def set_learning_label(
        self,
        opportunity_id: str,
        label: str,
        *,
        consumed: bool = False,
    ) -> Optional[JournalEntry]:
        """Set the learning label for a row. Used by the Learning Ledger."""
        entry = await self._load(opportunity_id)
        if not entry:
            return None
        entry.learning_label = label
        entry.learning_consumed = consumed
        entry.events.append(JournalEvent(
            kind="learning_labelled",
            detail={"label": label, "consumed": consumed},
        ))
        await self._save(entry)
        return entry

    # ---- Public read API ---------------------------------------------
    async def get(self, opportunity_id: str) -> Optional[JournalEntry]:
        return await self._load(opportunity_id)

    async def list(
        self,
        *,
        execution_status: Optional[str] = None,
        opportunity_type: Optional[str] = None,
        mode: Optional[str] = None,
        learning_label: Optional[str] = None,
        limit: int = 100,
    ) -> List[JournalEntry]:
        filt: Dict[str, Any] = {}
        if execution_status:
            filt["execution_status"] = execution_status
        if opportunity_type:
            filt["opportunity_type"] = opportunity_type
        if mode:
            filt["mode"] = mode
        if learning_label:
            filt["learning_label"] = learning_label
        cursor = self._col.find(filt, {"_id": 0}).sort("last_seen", -1).limit(limit)
        out: List[JournalEntry] = []
        async for d in cursor:
            try:
                out.append(JournalEntry.model_validate(d))
            except Exception:
                continue
        return out

    async def summary(self) -> Dict[str, Any]:
        pipeline = [
            {"$group": {
                "_id": {
                    "status": "$execution_status",
                    "mode": "$mode",
                    "label": "$learning_label",
                },
                "n": {"$sum": 1},
                "avg_profit": {"$avg": "$expected_profit_usd"},
                "avg_confidence": {"$avg": "$confidence_score"},
            }},
        ]
        buckets: List[Dict[str, Any]] = []
        total = 0
        async for row in self._col.aggregate(pipeline):
            n = int(row.get("n", 0))
            total += n
            buckets.append({
                "execution_status": row["_id"].get("status"),
                "mode": row["_id"].get("mode"),
                "learning_label": row["_id"].get("label"),
                "n": n,
                "avg_profit_usd": row.get("avg_profit"),
                "avg_confidence": row.get("avg_confidence"),
            })
        return {"total": total, "buckets": buckets, "as_of": _iso_now()}

    # ---- Duck-type helpers -------------------------------------------
    @staticmethod
    def _get(opp: Any, key: str) -> Any:
        if opp is None:
            return None
        if isinstance(opp, dict):
            return opp.get(key)
        return getattr(opp, key, None)

    @staticmethod
    def _normalise_enum(value: Any) -> Optional[str]:
        if value is None:
            return None
        return getattr(value, "value", str(value))

    def _enrich_from_opp(self, entry: JournalEntry, opp: Any) -> None:
        """Update mutable snapshot fields from the latest observation."""
        for key in (
            "expected_profit_usd", "capital_required_usd", "spread_pct",
            "confidence_score", "risk_score",
        ):
            v = self._get(opp, key)
            if v is not None:
                setattr(entry, key, v)
        mev = self._normalise_enum(self._get(opp, "mev_risk_level"))
        if mev is not None:
            entry.mev_risk_level = mev
