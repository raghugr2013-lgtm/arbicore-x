"""Entity resolution — deterministic external_ref → entity_id mapping."""
from __future__ import annotations

import hashlib
import time
from typing import Dict, Optional

from ..data.mongo.arbicore_collections import get_collection
from ..models.enums import DataProvenance
from ..data.provenance import is_learning_eligible
from .entity_types import EntityType
from .models import Entity


def ref_id(ref_type: str, external_ref: str) -> str:
    """Deterministic, opaque entity_id from a (ref_type, external_ref) pair.
    The same pair always produces the same id; different pairs produce
    different ids."""
    raw = f"{ref_type}::{external_ref}".encode("utf-8")
    return "ent:" + hashlib.sha1(raw).hexdigest()[:20]


def ref_to_entity_id(refs: Dict[str, str]) -> str:
    """Pick the most stable ref (first key in deterministic order) and hash it.
    The deterministic order is alphabetical so callers cannot drift the id."""
    if not refs:
        raise ValueError("ref_to_entity_id requires at least one ref")
    keys = sorted(refs.keys())
    return ref_id(keys[0], refs[keys[0]])


class EntityResolver:
    """Mongo-backed resolver. Caches refs ↔ entity_id in
    ``arbicore_entity_refs`` so subsequent lookups skip the hash recompute."""

    @property
    def _refs(self):
        return get_collection("entity_refs")

    @property
    def _entities(self):
        return get_collection("entities")

    async def resolve_or_create(self,
                                ref_type: str,
                                external_ref: str,
                                *,
                                entity_type: EntityType = EntityType.UNKNOWN,
                                provenance: DataProvenance = DataProvenance.REAL,
                                ) -> Optional[str]:
        """Return the entity_id for (ref_type, external_ref). Creates the
        Entity and ref row on first sight. Provenance-gated: non-learning-
        eligible provenance returns None (no write)."""
        if not is_learning_eligible(provenance):
            return None
        if not external_ref:
            return None
        eid = ref_id(ref_type, external_ref)
        now = time.time()
        # Upsert ref row
        await self._refs.update_one(
            {"ref_type": ref_type, "external_ref": external_ref},
            {"$set": {"entity_id": eid, "updated_at": now},
             "$setOnInsert": {"first_seen_at": now}},
            upsert=True,
        )
        # Upsert entity row
        await self._entities.update_one(
            {"entity_id": eid},
            {"$setOnInsert": {
                "entity_id": eid,
                "entity_type": entity_type.value,
                "external_refs": {ref_type: external_ref},
                "labels": [],
                "first_seen_at": now,
                "provenance": provenance.value,
                "metadata": {},
             },
             "$set": {"last_seen_at": now},
             "$addToSet": {f"external_refs.{ref_type}": external_ref}
             if False else {}},
            upsert=True,
        )
        return eid

    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        doc = await self._entities.find_one({"entity_id": entity_id}, {"_id": 0})
        if not doc:
            return None
        return Entity(**{k: v for k, v in doc.items()
                          if k in Entity.__dataclass_fields__})

    async def lookup_by_ref(self, ref_type: str,
                            external_ref: str) -> Optional[str]:
        row = await self._refs.find_one(
            {"ref_type": ref_type, "external_ref": external_ref},
            {"_id": 0, "entity_id": 1},
        )
        return row["entity_id"] if row else None

    async def count_entities(self) -> int:
        return await self._entities.count_documents({})
