"""OpportunityLifetimeTracker — Phase 2 canonical aggregate updater.

Every scanner emission and every intelligence engine write that touches
an ``opp_id`` calls into this tracker. The tracker is responsible for
maintaining a single ``mid_opportunity_lifetime`` document per
``opp_id`` that answers every Phase 2 question the operator can ask.

The tracker:
  * Race-safely UPSERTs the doc using the same pattern that
    :func:`MidWriter.write_route_observation` uses for ``mid_routes``.
  * Never writes anywhere else — MID remains canonical.
  * Preserves ``first_seen`` / ``mid_id`` on updates.
  * Tracks observation_count monotonically.
  * Distinguishes rediscovery (gap > REDISCOVERY_GAP_SECONDS) from
    recurrence (gap > RECURRENCE_GAP_SECONDS) and increments the two
    counters independently, matching the semantics the user approved.
  * Maintains bounded ring buffers for ``confidence_trend``,
    ``profitability_trend`` and ``evidence_history``.
  * Derives ``opportunity_status`` (ACTIVE / STALE / EXPIRED) from the
    time since last observation on each write.

The tracker is thread-safe at the Mongo level (all writes are single
atomic ``update_one`` or ``find_one_and_update`` operations). No
in-process state is held.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...data.mid.schemas import (
    MID_COLLECTION_MAP, MidMetadata, OpportunityLifetimeRecord,
    ReplayContext,
)
from ...data.mid.writers import MidWriter, make_meta, new_mid_id
from .config import LifetimeConfig, load_config_from_env

logger = logging.getLogger(__name__)


_ISO_TRAILER = "+00:00"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace(_ISO_TRAILER, "Z")


def _parse_iso(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


def _seconds_between(iso_a: str, iso_b: str) -> float:
    return (_parse_iso(iso_b) - _parse_iso(iso_a)).total_seconds()


@dataclass
class TrackerStats:
    total_upserts: int = 0
    inserts: int = 0
    updates: int = 0
    rediscoveries: int = 0
    recurrences: int = 0
    by_status: Dict[str, int] = field(default_factory=dict)
    last_upsert_at: Optional[str] = None
    last_opp_id: Optional[str] = None
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_upserts": self.total_upserts,
            "inserts": self.inserts,
            "updates": self.updates,
            "rediscoveries": self.rediscoveries,
            "recurrences": self.recurrences,
            "by_status": dict(self.by_status),
            "last_upsert_at": self.last_upsert_at,
            "last_opp_id": self.last_opp_id,
            "last_error": self.last_error,
        }


class OpportunityLifetimeTracker:
    """Public entry point used by the scanner bridge + intelligence
    engines + the sweeper."""

    COLLECTION = MID_COLLECTION_MAP["opportunity_lifetime"]

    def __init__(
        self,
        db: Any,
        writer: MidWriter,
        config: Optional[LifetimeConfig] = None,
    ) -> None:
        self._db = db
        self._writer = writer
        self._cfg = config or load_config_from_env()
        self.stats = TrackerStats()

    @property
    def config(self) -> LifetimeConfig:
        return self._cfg

    async def ensure_indexes(self) -> None:
        coll = self._db[self.COLLECTION]
        try:
            await coll.create_index("opp_id", unique=True)
            await coll.create_index([("opportunity_status", 1),
                                     ("last_seen", -1)])
            await coll.create_index([("last_seen", -1)])
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "lifetime: failed to create indexes on %s: %s",
                self.COLLECTION, exc)

    # ------------------------------------------------------------------
    # write path
    # ------------------------------------------------------------------

    async def observe(
        self,
        *,
        opp_id: str,
        opportunity_type: str,
        chain: str,
        payload: Optional[Dict[str, Any]] = None,
        meta: Optional[MidMetadata] = None,
        event_type: Optional[str] = None,
        confidence: Optional[float] = None,
        profitability: Optional[float] = None,
        evidence_pointer: Optional[Dict[str, Any]] = None,
        ts: Optional[str] = None,
    ) -> Dict[str, Any]:
        """One-observation UPSERT.

        Returns a small summary dict (``inserted``/``updated``, new
        derived status, current counters) — never raises. Callers can
        keep going even if a single upsert fails.
        """
        try:
            return await self._observe_impl(
                opp_id=opp_id, opportunity_type=opportunity_type,
                chain=chain, payload=payload, meta=meta,
                event_type=event_type, confidence=confidence,
                profitability=profitability,
                evidence_pointer=evidence_pointer, ts=ts,
            )
        except Exception as exc:  # noqa: BLE001
            self.stats.last_error = f"observe[{opp_id}]: {exc!r}"
            logger.exception("lifetime.observe failed: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def _observe_impl(
        self,
        *,
        opp_id: str,
        opportunity_type: str,
        chain: str,
        payload: Optional[Dict[str, Any]],
        meta: Optional[MidMetadata],
        event_type: Optional[str],
        confidence: Optional[float],
        profitability: Optional[float],
        evidence_pointer: Optional[Dict[str, Any]],
        ts: Optional[str],
    ) -> Dict[str, Any]:
        ts = ts or _now_iso()
        meta = meta or make_meta(
            opportunity_type=opportunity_type, chain=chain,
            execution_mode="shadow",
        )
        # validate through the writer's enum audit path
        await self._writer._validate_meta(meta)  # noqa: SLF001

        coll = self._db[self.COLLECTION]
        existing = await coll.find_one({"opp_id": opp_id})

        if existing is None:
            # first sighting — insert
            rec = OpportunityLifetimeRecord(
                mid_id=new_mid_id(), ts=ts, meta=meta,
                replay_context=ReplayContext(),
                opp_id=opp_id,
                opportunity_type=opportunity_type, chain=chain,
                first_seen=ts, last_seen=ts,
                lifetime_seconds=0.0, opportunity_age_seconds=0.0,
                observation_count=1,
                rediscovery_count=0, recurrence_count=0,
                opportunity_status="ACTIVE",
                last_confidence=confidence,
                last_profitability=profitability,
                confidence_trend=self._trend_entry(ts, confidence),
                profitability_trend=self._trend_entry(ts, profitability),
                evidence_history=self._evidence_entry(
                    ts, event_type, evidence_pointer),
            )
            try:
                await coll.insert_one(rec.to_doc())
                self._record_stats("insert", "ACTIVE", opp_id, ts)
                return {"ok": True, "inserted": True,
                        "opportunity_status": "ACTIVE",
                        "observation_count": 1}
            except Exception:
                # race: another writer inserted between our find and
                # insert.  Fall through to the update path.
                existing = await coll.find_one({"opp_id": opp_id})
                if existing is None:
                    raise

        # update path — recompute counters and trends
        gap = _seconds_between(existing["last_seen"], ts)
        rediscovered = gap > self._cfg.rediscovery_gap_seconds
        recurred = gap > self._cfg.recurrence_gap_seconds

        lifetime_seconds = _seconds_between(existing["first_seen"], ts)
        opportunity_age_seconds = lifetime_seconds
        status = self._cfg.status_for_age(0.0)   # fresh observation → ACTIVE

        new_confidence_trend = self._append_trend(
            existing.get("confidence_trend"), ts, confidence)
        new_profitability_trend = self._append_trend(
            existing.get("profitability_trend"), ts, profitability)
        new_evidence_history = self._append_evidence(
            existing.get("evidence_history"), ts, event_type,
            evidence_pointer)

        inc = {"observation_count": 1}
        if rediscovered:
            inc["rediscovery_count"] = 1
        if recurred:
            inc["recurrence_count"] = 1

        update = {
            "$set": {
                "last_seen": ts,
                "lifetime_seconds": lifetime_seconds,
                "opportunity_age_seconds": opportunity_age_seconds,
                "opportunity_status": status,
                "last_confidence":
                    confidence if confidence is not None
                    else existing.get("last_confidence"),
                "last_profitability":
                    profitability if profitability is not None
                    else existing.get("last_profitability"),
                "confidence_trend": new_confidence_trend,
                "profitability_trend": new_profitability_trend,
                "evidence_history": new_evidence_history,
                "meta": meta.to_doc(),
            },
            "$inc": inc,
        }
        await coll.update_one({"opp_id": opp_id}, update)

        self._record_stats("update", status, opp_id, ts,
                            rediscovered=rediscovered, recurred=recurred)
        return {
            "ok": True, "inserted": False,
            "opportunity_status": status,
            "observation_count": existing.get("observation_count", 0) + 1,
            "rediscovered": rediscovered, "recurred": recurred,
            "lifetime_seconds": lifetime_seconds,
        }

    # ------------------------------------------------------------------
    # read helpers (used by API endpoints)
    # ------------------------------------------------------------------

    async def get(self, opp_id: str) -> Optional[Dict[str, Any]]:
        return await self._db[self.COLLECTION].find_one(
            {"opp_id": opp_id}, {"_id": 0})

    async def list_recent(
        self,
        *,
        limit: int = 50,
        status: Optional[str] = None,
        opportunity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if status:
            q["opportunity_status"] = status
        if opportunity_type:
            q["opportunity_type"] = opportunity_type
        cursor = self._db[self.COLLECTION].find(q, {"_id": 0}).sort(
            "last_seen", -1).limit(limit)
        return [d async for d in cursor]

    async def status_summary(self) -> Dict[str, Any]:
        cursor = self._db[self.COLLECTION].aggregate([
            {"$group": {"_id": "$opportunity_status",
                        "count": {"$sum": 1}}},
        ])
        by_status = {r["_id"]: r["count"] async for r in cursor}
        total = await self._db[self.COLLECTION].count_documents({})
        return {
            "total": total,
            "by_status": by_status,
            "config": {
                "active_seconds": self._cfg.active_seconds,
                "stale_seconds": self._cfg.stale_seconds,
                "expired_seconds": self._cfg.expired_seconds,
                "trend_ring_buffer": self._cfg.trend_ring_buffer,
                "rediscovery_gap_seconds":
                    self._cfg.rediscovery_gap_seconds,
                "recurrence_gap_seconds":
                    self._cfg.recurrence_gap_seconds,
                "sweeper_interval_seconds":
                    self._cfg.sweeper_interval_seconds,
            },
        }

    # ------------------------------------------------------------------
    # sweeper hooks
    # ------------------------------------------------------------------

    async def sweep_status_transitions(self, *, now: Optional[str] = None
                                       ) -> Dict[str, int]:
        """Update ``opportunity_status`` for every doc whose derived
        status differs from what is currently stored.

        Never modifies the counters, only the status label.  Returns a
        dict of {'active_to_stale', 'stale_to_expired', ...} counts.
        """
        now_iso = now or _now_iso()
        now_dt  = _parse_iso(now_iso)
        moved = {"active_to_stale": 0, "stale_to_expired": 0,
                 "reactivated": 0}
        cursor = self._db[self.COLLECTION].find(
            {}, {"opp_id": 1, "opportunity_status": 1, "last_seen": 1})
        async for doc in cursor:
            try:
                age = (now_dt - _parse_iso(doc["last_seen"])).total_seconds()
            except Exception:
                continue
            derived = self._cfg.status_for_age(age)
            stored = doc.get("opportunity_status")
            if derived == stored:
                continue
            await self._db[self.COLLECTION].update_one(
                {"opp_id": doc["opp_id"]},
                {"$set": {"opportunity_status": derived}},
            )
            if stored == "ACTIVE" and derived == "STALE":
                moved["active_to_stale"] += 1
            elif stored == "STALE" and derived == "EXPIRED":
                moved["stale_to_expired"] += 1
            elif derived == "ACTIVE":
                moved["reactivated"] += 1
        return moved

    # ------------------------------------------------------------------
    # internals
    # ------------------------------------------------------------------

    def _record_stats(self, kind: str, status: str, opp_id: str, ts: str,
                       *, rediscovered: bool = False,
                       recurred: bool = False) -> None:
        s = self.stats
        s.total_upserts += 1
        if kind == "insert":
            s.inserts += 1
        else:
            s.updates += 1
        s.by_status[status] = s.by_status.get(status, 0) + 1
        if rediscovered:
            s.rediscoveries += 1
        if recurred:
            s.recurrences += 1
        s.last_upsert_at = ts
        s.last_opp_id = opp_id

    def _trend_entry(self, ts: str,
                     value: Optional[float]) -> List[Dict[str, Any]]:
        if value is None:
            return []
        return [{"ts": ts, "value": float(value)}]

    def _evidence_entry(self, ts: str,
                         event_type: Optional[str],
                         evidence_pointer: Optional[Dict[str, Any]]
                         ) -> List[Dict[str, Any]]:
        if not event_type and not evidence_pointer:
            return []
        return [{"ts": ts, "event_type": event_type,
                 "pointer": evidence_pointer or {}}]

    def _append_trend(self, existing: Optional[List[Dict[str, Any]]],
                       ts: str, value: Optional[float]
                       ) -> List[Dict[str, Any]]:
        if value is None:
            return list(existing or [])[-self._cfg.trend_ring_buffer:]
        rows = list(existing or [])
        rows.append({"ts": ts, "value": float(value)})
        return rows[-self._cfg.trend_ring_buffer:]

    def _append_evidence(self, existing: Optional[List[Dict[str, Any]]],
                          ts: str, event_type: Optional[str],
                          evidence_pointer: Optional[Dict[str, Any]]
                          ) -> List[Dict[str, Any]]:
        rows = list(existing or [])
        rows.append({"ts": ts, "event_type": event_type,
                     "pointer": evidence_pointer or {}})
        return rows[-self._cfg.trend_ring_buffer:]
