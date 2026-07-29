"""ArbiCore X — Mongo RegimeSnapshotRepository (Phase B, Adj. A3)."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import List, Optional

from ..regime_snapshot_repo import RegimeSnapshot, RegimeSnapshotRepository
from .arbicore_collections import get_collection


class MongoRegimeSnapshotRepository(RegimeSnapshotRepository):
    @property
    def _col(self):
        return get_collection("regime_snapshots")

    async def append(self, snapshot: RegimeSnapshot) -> bool:
        doc = asdict(snapshot)
        doc["captured_at_dt"] = datetime.fromtimestamp(
            snapshot.captured_at, tz=timezone.utc,
        )
        await self._col.insert_one(doc)
        return True

    async def latest(self) -> Optional[RegimeSnapshot]:
        doc = await self._col.find_one({}, {"_id": 0, "captured_at_dt": 0},
                                       sort=[("captured_at", -1)])
        if not doc:
            return None
        return RegimeSnapshot(**doc)

    async def list_since(self, t0: float, limit: int = 500) -> List[RegimeSnapshot]:
        cursor = self._col.find(
            {"captured_at": {"$gte": float(t0)}},
            {"_id": 0, "captured_at_dt": 0},
        ).sort("captured_at", -1).limit(limit)
        return [RegimeSnapshot(**d) async for d in cursor]

    async def count(self) -> int:
        return await self._col.count_documents({})
