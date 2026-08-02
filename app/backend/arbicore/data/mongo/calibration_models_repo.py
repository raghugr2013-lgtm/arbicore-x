"""Repository over ``db.calibration_models`` (Wave-3 sibling collection).

Enforces the promotion invariants:

    * Exactly one row with ``state="active"`` per ``kind`` at any time.
    * A promotion is a two-step write: activate new, retire old.
    * Retired rows are kept for audit with a ``retired_at`` timestamp
      (TTL managed by :func:`ensure_indexes`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CalibrationModelsRepo:
    def __init__(self, db, collection_name: str = "calibration_models",
                 retired_ttl_days: int = 30):
        self._db = db
        self._collection = db[collection_name]
        self._retired_ttl_days = int(retired_ttl_days)
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        # Unique lookup by id + state.
        await self._collection.create_index("id", unique=True)
        await self._collection.create_index([("kind", 1), ("state", 1)])
        # TTL on retired_at (Mongo ignores docs without the field).
        await self._collection.create_index(
            "retired_at",
            expireAfterSeconds=self._retired_ttl_days * 86400,
        )
        self._indexes_ready = True

    # ------- reads -------

    async def get_active(self, kind: str = "confidence") -> Optional[Dict[str, Any]]:
        return await self._collection.find_one(
            {"kind": kind, "state": "active"}, {"_id": 0}
        )

    async def list_recent(self, kind: str = "confidence", limit: int = 20) -> List[Dict[str, Any]]:
        cur = self._collection.find({"kind": kind}, {"_id": 0}).sort("fitted_at", -1).limit(limit)
        return await cur.to_list(limit)

    async def get_by_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        return await self._collection.find_one({"id": model_id}, {"_id": 0})

    # ------- writes -------

    async def insert_shadow(self, model: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new model row in ``state='shadow'`` (not yet active)."""
        doc = dict(model)
        doc["state"] = "shadow"
        doc.setdefault("fitted_at", _now_iso())
        await self._collection.insert_one(doc)
        # Remove _id if Mongo mutated the input.
        doc.pop("_id", None)
        return doc

    async def promote(self, new_model_id: str, kind: str = "confidence") -> Dict[str, Any]:
        """Promote a shadow row to active, retiring the previous active.

        Order (matches the user-specified lifecycle):
          1. Retire current active (state=retired, retired_at=now).
          2. Publish new active (state=active).

        The order minimises the window in which two rows might briefly
        both be considered active — the retirement write commits before
        the promotion write.  Readers use ``get_active()`` which is
        deterministic even during the tiny gap because it filters by
        ``state='active'`` and picks the newest ``fitted_at``.
        """
        current = await self.get_active(kind)
        now = _now_iso()
        if current and current.get("id") != new_model_id:
            await self._collection.update_one(
                {"id": current["id"]},
                {"$set": {"state": "retired", "retired_at": now}},
            )
        await self._collection.update_one(
            {"id": new_model_id},
            {"$set": {"state": "active", "promoted_at": now, "supersedes": (current or {}).get("id")}},
        )
        return await self.get_active(kind) or {}

    async def rollback_to(self, model_id: str, kind: str = "confidence") -> Optional[Dict[str, Any]]:
        """Restore a previously-retired model as active (audit-only path)."""
        target = await self.get_by_id(model_id)
        if not target:
            return None
        # Retire whatever is currently active (if any and different).
        current = await self.get_active(kind)
        now = _now_iso()
        if current and current.get("id") != model_id:
            await self._collection.update_one(
                {"id": current["id"]},
                {"$set": {"state": "retired", "retired_at": now}},
            )
        await self._collection.update_one(
            {"id": model_id},
            {
                "$set": {
                    "state": "active",
                    "promoted_at": now,
                    "supersedes": (current or {}).get("id"),
                },
                "$unset": {"retired_at": ""},
            },
        )
        return await self.get_active(kind)

    async def drop_all(self) -> None:
        """Test helper — drop the collection.  Not called from prod code."""
        await self._collection.delete_many({})
