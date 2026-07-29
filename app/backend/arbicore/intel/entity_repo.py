"""Universal entity Mongo repository — Phase C Wave 4."""
from __future__ import annotations

from typing import List, Optional

from ..data.mongo.arbicore_collections import get_collection
from .entity_types import EntityType
from .models import Entity


class MongoEntityRepository:
    @property
    def _col(self):
        return get_collection("entities")

    async def get(self, entity_id: str) -> Optional[Entity]:
        doc = await self._col.find_one({"entity_id": entity_id}, {"_id": 0})
        if not doc:
            return None
        return Entity(**{k: v for k, v in doc.items()
                          if k in Entity.__dataclass_fields__})

    async def list_by_type(self, entity_type: EntityType,
                           limit: int = 200) -> List[Entity]:
        cursor = self._col.find(
            {"entity_type": entity_type.value}, {"_id": 0},
        ).sort("last_seen_at", -1).limit(limit)
        return [
            Entity(**{k: v for k, v in d.items()
                      if k in Entity.__dataclass_fields__})
            async for d in cursor
        ]

    async def label(self, entity_id: str, label: str) -> bool:
        if not label:
            return False
        res = await self._col.update_one(
            {"entity_id": entity_id},
            {"$addToSet": {"labels": label}},
        )
        return res.modified_count > 0 or res.matched_count > 0

    async def count(self) -> int:
        return await self._col.count_documents({})
