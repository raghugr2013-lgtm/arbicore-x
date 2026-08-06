"""ArbiCore X — Mongo OpportunityRepository (Phase B).

Motor-backed concrete impl. No raw _id leaks (we exclude _id via
projection and key everything off ``opportunity_id``).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...models.canonical import CanonicalOpportunity
from ...models.enums import OpportunityStatus, OpportunityType
from ..opportunity_repo import OpportunityRepository, validate_for_upsert

# Phase 8 REFINE: canonical `arbicore_collections.get_collection` depends on a
# ``services.db`` module that is not part of the running tree.  We keep the
# canonical collection-name registry inline (single source of truth) and
# accept the Motor ``db`` at construction time.  This is the minimum-touch
# activation of `MongoOpportunityRepository`.
_CANONICAL_COLLECTION_NAMES = {
    "opportunities":      "arbicore_opportunities",
    "outcomes":           "arbicore_outcomes",
    "state_snapshots":    "arbicore_state_snapshots",
    "audit_log":          "arbicore_audit_log",
    "route_stats":        "arbicore_route_stats",
    "provenance_audit":   "arbicore_provenance_audit",
}


def _serialise(opp: CanonicalOpportunity) -> Dict[str, Any]:
    d = opp.model_dump(mode="json")
    return d


def _deserialise(doc: Dict[str, Any]) -> CanonicalOpportunity:
    if doc is None:
        return None  # type: ignore
    doc = {k: v for k, v in doc.items() if k != "_id"}
    return CanonicalOpportunity.model_validate(doc)


def _apply_provenance_filter(filt: Dict[str, Any],
                             provenance_filter: Optional[frozenset]) -> Dict[str, Any]:
    if provenance_filter:
        values = [p.value for p in provenance_filter]
        filt["source_data_quality"] = {"$in": values}
    return filt


class MongoOpportunityRepository(OpportunityRepository):
    def __init__(self, db):
        self._db = db

    @property
    def _col(self):
        return self._db[_CANONICAL_COLLECTION_NAMES["opportunities"]]

    async def ensure_indexes(self) -> None:
        """Idempotent index bootstrap.

        The canonical boot indexer (:mod:`arbicore.data.mongo.arbicore_collections`)
        already creates the following named indexes on ``arbicore_opportunities``:

            * ``opportunity_id_unique``  (unique on ``opportunity_id``)
            * ``subject_id_idx``         (on ``subject_id``)
            * ``type_status_idx``        (on ``opportunity_type`` + ``status``)
            * ``created_at_desc``        (on ``created_at`` descending)

        Calling ``create_index`` again with the SAME key spec but *different*
        options (in particular an auto-generated ``name``) triggers
        ``IndexOptionsConflict`` on the Mongo server — Mongo treats ``name``
        as a semantically-significant option and refuses to promote a
        second index for the same key even when every other option matches.

        This method therefore:
          1. Inspects the live index list.
          2. Skips creation when a compatible index (same key spec + same
             ``unique`` posture) already exists — irrespective of name.
          3. Only creates when no compatible index is present.

        No drop is ever attempted here — the canonical boot indexer is
        the sole authority for schema migrations on this collection.
        """
        c = self._col
        # Snapshot the live index list once. Each entry looks like:
        #   {"v":2,"key":{"opportunity_id":1},"name":"opportunity_id_unique",
        #    "unique":true}
        existing: list = []
        try:
            async for idx in c.list_indexes():
                existing.append(dict(idx))
        except Exception:
            # Fresh collection with no indexes yet — fall through to create.
            existing = []

        def _has_key(key_spec: list, *, unique: bool = False) -> bool:
            """Return True iff an existing index already covers ``key_spec``
            with a matching ``unique`` posture.  ``key_spec`` is a list of
            (field, direction) tuples in the canonical Mongo shape."""
            want = list(key_spec)
            for idx in existing:
                idx_key = idx.get("key") or {}
                if list(idx_key.items()) != want:
                    continue
                if bool(idx.get("unique")) != bool(unique):
                    continue
                return True
            return False

        # 1. unique(opportunity_id)
        if not _has_key([("opportunity_id", 1)], unique=True):
            await c.create_index(
                "opportunity_id", unique=True, name="opportunity_id_unique",
            )
        # 2. subject_id
        if not _has_key([("subject_id", 1)]):
            await c.create_index("subject_id", name="subject_id_idx")
        # 3. compound (opportunity_type, status)
        if not _has_key([("opportunity_type", 1), ("status", 1)]):
            await c.create_index(
                [("opportunity_type", 1), ("status", 1)],
                name="type_status_idx",
            )
        # 4. created_at descending
        if not _has_key([("created_at", -1)]):
            await c.create_index(
                [("created_at", -1)], name="created_at_desc",
            )

    async def upsert(self, opp: CanonicalOpportunity) -> bool:
        validate_for_upsert(opp)
        if not opp.opportunity_id:
            opp.opportunity_id = uuid.uuid4().hex
        opp.updated_at = datetime.now(timezone.utc).isoformat()
        doc = _serialise(opp)
        await self._col.update_one(
            {"opportunity_id": opp.opportunity_id},
            {"$set": doc},
            upsert=True,
        )
        return True

    async def get(self, opportunity_id: str) -> Optional[CanonicalOpportunity]:
        doc = await self._col.find_one({"opportunity_id": opportunity_id}, {"_id": 0})
        return _deserialise(doc) if doc else None

    async def list_for_subject(self,
                               subject_id: str,
                               limit: int = 50,
                               provenance_filter: Optional[frozenset] = None,
                               ) -> List[CanonicalOpportunity]:
        filt: Dict[str, Any] = {"subject_id": subject_id}
        filt = _apply_provenance_filter(filt, provenance_filter)
        cursor = self._col.find(filt, {"_id": 0}).sort("created_at", -1).limit(limit)
        return [_deserialise(d) async for d in cursor]

    async def find(self,
                   filter: dict,
                   limit: int = 100,
                   provenance_filter: Optional[frozenset] = None,
                   ) -> List[CanonicalOpportunity]:
        f: Dict[str, Any] = {}
        if "opportunity_type" in filter:
            v = filter["opportunity_type"]
            f["opportunity_type"] = v.value if isinstance(v, OpportunityType) else str(v)
        if "status" in filter:
            v = filter["status"]
            f["status"] = v.value if isinstance(v, OpportunityStatus) else str(v)
        if "subject_id" in filter:
            f["subject_id"] = filter["subject_id"]
        if "since" in filter:
            since = filter["since"]
            try:
                if isinstance(since, (int, float)):
                    iso = datetime.fromtimestamp(float(since), tz=timezone.utc).isoformat()
                else:
                    iso = str(since)
                f["created_at"] = {"$gte": iso}
            except Exception:
                pass
        f = _apply_provenance_filter(f, provenance_filter)
        cursor = self._col.find(f, {"_id": 0}).sort("created_at", -1).limit(limit)
        return [_deserialise(d) async for d in cursor]

    async def count_by_type_status(self) -> dict:
        pipeline = [
            {"$group": {
                "_id": {"t": "$opportunity_type", "s": "$status"},
                "n": {"$sum": 1},
            }},
        ]
        out: Dict[str, Dict[str, int]] = {}
        async for row in self._col.aggregate(pipeline):
            t = row["_id"]["t"]
            s = row["_id"]["s"]
            out.setdefault(t, {})
            out[t][s] = int(row["n"])
        return out
