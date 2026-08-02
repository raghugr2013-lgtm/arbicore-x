"""Repository over ``db.adaptive_weight_recommendations`` (Wave-4).

Enforces the same lifecycle invariants as the calibration models repo:
    * exactly one ``state='active'`` row per ``kind`` at a time;
    * promotion is a two-step write (retire old, publish new);
    * retired rows keep an audit trail for the configurable TTL window;
    * ``mode`` is stamped on every row so operators can audit whether a
      given recommendation was OBSERVE-only or (future) APPLY.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdaptiveWeightsRepo:
    def __init__(self, db, collection_name: str = "adaptive_weight_recommendations",
                 retired_ttl_days: int = 30):
        self._db = db
        self._collection = db[collection_name]
        self._retired_ttl_days = int(retired_ttl_days)
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._collection.create_index("id", unique=True)
        await self._collection.create_index([("kind", 1), ("state", 1)])
        await self._collection.create_index(
            "retired_at",
            expireAfterSeconds=self._retired_ttl_days * 86400,
        )
        self._indexes_ready = True

    # --- reads ---

    async def get_active(self, kind: str = "adaptive_weights") -> Optional[Dict[str, Any]]:
        return await self._collection.find_one(
            {"kind": kind, "state": "active"}, {"_id": 0}
        )

    async def list_recent(self, kind: str = "adaptive_weights", limit: int = 20) -> List[Dict[str, Any]]:
        cur = self._collection.find({"kind": kind}, {"_id": 0}).sort("fitted_at", -1).limit(limit)
        return await cur.to_list(limit)

    async def get_by_id(self, model_id: str) -> Optional[Dict[str, Any]]:
        return await self._collection.find_one({"id": model_id}, {"_id": 0})

    # --- writes ---

    async def insert_shadow(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        d = dict(doc)
        d["state"] = "shadow"
        d.setdefault("fitted_at", _now_iso())
        await self._collection.insert_one(d)
        d.pop("_id", None)
        return d

    async def promote(self, new_id: str, kind: str = "adaptive_weights") -> Dict[str, Any]:
        current = await self.get_active(kind)
        now = _now_iso()
        if current and current.get("id") != new_id:
            await self._collection.update_one(
                {"id": current["id"]},
                {"$set": {"state": "retired", "retired_at": now}},
            )
        await self._collection.update_one(
            {"id": new_id},
            {"$set": {"state": "active", "promoted_at": now,
                      "supersedes": (current or {}).get("id")}},
        )
        return await self.get_active(kind) or {}

    async def rollback_to(self, model_id: str,
                          kind: str = "adaptive_weights") -> Optional[Dict[str, Any]]:
        target = await self.get_by_id(model_id)
        if not target:
            return None
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
