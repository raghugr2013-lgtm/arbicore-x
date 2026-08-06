"""Paper Validation evidence persistence (v2.11.8).

Insert-only Mongo repository writing to ``arbicore_paper_evidence``.

The repo intentionally exposes NO ``update``, ``replace``, ``upsert``,
or ``delete`` methods on individual bundles — bundles are immutable
by design.  The only mutation surface is ``clear_all()`` and it is
strictly guarded (test-only, disabled in production).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .evidence import EvidenceBundle

logger = logging.getLogger(__name__)


class InMemoryPaperEvidenceRepository:
    """Test-only, in-memory backing store.  Mirrors the Mongo repo's
    read/write surface but keeps data on the instance."""

    def __init__(self) -> None:
        self._store: Dict[str, Dict[str, Any]] = {}

    async def insert(self, bundle: EvidenceBundle) -> str:
        vid = bundle.validation_id
        if vid in self._store:
            # Immutability guarantee: same validation_id can never be
            # re-inserted.
            raise ValueError(
                f"EvidenceBundle {vid!r} already exists — bundles are "
                f"immutable and cannot be re-inserted."
            )
        self._store[vid] = bundle.to_mongo()
        return vid

    async def get_by_validation_id(self, vid: str) -> Optional[EvidenceBundle]:
        doc = self._store.get(vid)
        return EvidenceBundle.from_mongo(doc) if doc else None

    async def get_by_opportunity_id(self, opp_id: str
                                     ) -> Optional[EvidenceBundle]:
        for doc in self._store.values():
            if doc.get("opportunity_id") == opp_id:
                return EvidenceBundle.from_mongo(doc)
        return None

    async def list_recent(self, *,
                           limit: int = 100,
                           outcome: Optional[str] = None,
                           strategy: Optional[str] = None,
                           ) -> List[EvidenceBundle]:
        rows = list(self._store.values())
        rows.sort(key=lambda d: d.get("created_at") or "", reverse=True)
        out: List[EvidenceBundle] = []
        for d in rows:
            if outcome and d.get("outcome") != outcome:
                continue
            if strategy and d.get("strategy") != strategy:
                continue
            out.append(EvidenceBundle.from_mongo(d))
            if len(out) >= limit:
                break
        return out

    async def count(self, *, outcome: Optional[str] = None) -> int:
        if not outcome:
            return len(self._store)
        return sum(1 for d in self._store.values()
                    if d.get("outcome") == outcome)

    async def outcome_histogram(self) -> Dict[str, int]:
        hist: Dict[str, int] = {}
        for d in self._store.values():
            k = d.get("outcome") or "UNKNOWN"
            hist[k] = hist.get(k, 0) + 1
        return hist

    async def clear_all(self) -> None:
        """Test-only. Never call in production."""
        self._store.clear()


class PaperEvidenceRepository:
    """Mongo-backed, insert-only Paper Validation repo.

    Collection: ``arbicore_paper_evidence``.  Recommended indexes:

        db.arbicore_paper_evidence.createIndex(
            {validation_id: 1}, {unique: true}
        )
        db.arbicore_paper_evidence.createIndex(
            {opportunity_id: 1, created_at: -1}
        )
        db.arbicore_paper_evidence.createIndex(
            {outcome: 1, created_at: -1}
        )

    The index creation is *not* forced from within the repo — the boot
    sequence does that (see :mod:`arbicore.runtime.composition`).
    """

    COLLECTION = "arbicore_paper_evidence"

    def __init__(self, db) -> None:
        if db is None:
            raise ValueError("PaperEvidenceRepository requires a Mongo db handle")
        self._db = db
        self._col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        try:
            await self._col.create_index(
                "validation_id", unique=True, name="uniq_validation_id"
            )
            await self._col.create_index(
                [("opportunity_id", 1), ("created_at", -1)],
                name="opp_recent",
            )
            await self._col.create_index(
                [("outcome", 1), ("created_at", -1)],
                name="outcome_recent",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("PaperEvidenceRepository index ensure failed: %s", exc)

    # ------------------------------------------------------------------
    # Insert-only write surface
    # ------------------------------------------------------------------
    async def insert(self, bundle: EvidenceBundle) -> str:
        """Insert a bundle.  Raises if ``validation_id`` collides."""
        doc = bundle.to_mongo()
        await self._col.insert_one(doc)
        return bundle.validation_id

    # ------------------------------------------------------------------
    # Read surface
    # ------------------------------------------------------------------
    async def get_by_validation_id(self, vid: str) -> Optional[EvidenceBundle]:
        doc = await self._col.find_one({"validation_id": vid})
        if not doc:
            return None
        doc.pop("_id", None)
        return EvidenceBundle.from_mongo(doc)

    async def get_by_opportunity_id(self, opp_id: str
                                     ) -> Optional[EvidenceBundle]:
        doc = await self._col.find_one(
            {"opportunity_id": opp_id},
            sort=[("created_at", -1)],
        )
        if not doc:
            return None
        doc.pop("_id", None)
        return EvidenceBundle.from_mongo(doc)

    async def list_recent(self, *,
                           limit: int = 100,
                           outcome: Optional[str] = None,
                           strategy: Optional[str] = None,
                           ) -> List[EvidenceBundle]:
        q: Dict[str, Any] = {}
        if outcome:
            q["outcome"] = outcome
        if strategy:
            q["strategy"] = strategy
        cur = self._col.find(q, sort=[("created_at", -1)]).limit(int(limit))
        out: List[EvidenceBundle] = []
        async for doc in cur:
            doc.pop("_id", None)
            out.append(EvidenceBundle.from_mongo(doc))
        return out

    async def count(self, *, outcome: Optional[str] = None) -> int:
        q: Dict[str, Any] = {}
        if outcome:
            q["outcome"] = outcome
        return await self._col.count_documents(q)

    async def outcome_histogram(self) -> Dict[str, int]:
        pipeline = [{"$group": {"_id": "$outcome", "n": {"$sum": 1}}}]
        hist: Dict[str, int] = {}
        async for row in self._col.aggregate(pipeline):
            hist[str(row.get("_id") or "UNKNOWN")] = int(row.get("n") or 0)
        return hist
