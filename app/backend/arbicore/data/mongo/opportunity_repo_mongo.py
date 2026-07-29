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
from .arbicore_collections import get_collection


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
    @property
    def _col(self):
        return get_collection("opportunities")

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
