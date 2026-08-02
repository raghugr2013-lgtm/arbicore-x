"""Repository over ``db.evidence_bundles`` (Wave 5).

Append-only audit trail — bundles are inserted once and never mutated.
The ``verification_status`` field snapshotted on a bundle at creation
time is a hint; the authoritative check is always ``EvidenceVerifier``.
Rollback is expressed as "insert a superseding bundle" rather than
mutating history.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EvidenceBundlesRepo:
    def __init__(self, db, collection_name: str = "evidence_bundles"):
        self._db = db
        self._collection = db[collection_name]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._collection.create_index("bundle_id", unique=True)
        await self._collection.create_index([("source_component", 1), ("created_at", -1)])
        await self._collection.create_index("source_model_id")
        self._indexes_ready = True

    async def insert(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        doc = dict(bundle)
        doc.setdefault("persisted_at", _now_iso())
        await self._collection.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get_latest(self, source_component: str) -> Optional[Dict[str, Any]]:
        cur = self._collection.find(
            {"source_component": source_component}, {"_id": 0}
        ).sort("created_at", -1).limit(1)
        rows = await cur.to_list(1)
        return rows[0] if rows else None

    async def list_recent(self, source_component: Optional[str] = None,
                          limit: int = 20) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if source_component:
            q["source_component"] = source_component
        cur = self._collection.find(q, {"_id": 0}).sort("created_at", -1).limit(limit)
        return await cur.to_list(limit)

    async def find_by_source_model(self, source_model_id: str) -> Optional[Dict[str, Any]]:
        return await self._collection.find_one(
            {"source_model_id": source_model_id}, {"_id": 0}
        )

    async def find_by_bundle_id(self, bundle_id: str) -> Optional[Dict[str, Any]]:
        return await self._collection.find_one({"bundle_id": bundle_id}, {"_id": 0})
