"""Entity cluster detection via co-occurrence — Phase C Wave 4."""
from __future__ import annotations

import hashlib
import time
from typing import Any, Dict, List

from ..data.mongo.arbicore_collections import get_collection


def _cluster_id(entity_ids: List[str]) -> str:
    raw = "|".join(sorted(entity_ids)).encode("utf-8")
    return "cl:" + hashlib.sha1(raw).hexdigest()[:16]


class EntityClusterDetector:
    """Detects clusters by counting co-occurrence of entity_ids on the same
    subject_id within a recent time window. Category-agnostic — operates on
    audit_log payloads carrying ``entity_id`` arrays.
    """

    @property
    def _audit(self):
        return get_collection("audit_log")

    @property
    def _clusters(self):
        return get_collection("entity_clusters")

    async def detect(self, min_cooccur: int = 2,
                     window_s: int = 7 * 86400,
                     limit: int = 5000) -> Dict[str, Any]:
        """One pass. Aggregates audit_log payloads that include
        ``payload.entities`` (a list of entity_ids) and counts co-occurrence
        pairs. Records pairs meeting ``min_cooccur`` into
        ``arbicore_entity_clusters``."""
        cutoff = time.time() - window_s
        cursor = self._audit.find(
            {"ts": {"$gte": cutoff},
             "payload.entities": {"$exists": True, "$ne": []}},
            {"_id": 0, "payload.entities": 1, "subject_id": 1},
        ).limit(limit)
        pair_counts: Dict[tuple, int] = {}
        async for doc in cursor:
            ents = doc.get("payload", {}).get("entities") or []
            # Defensive: legacy/foreign payloads may emit a scalar value
            # for ``entities``. The cluster detector only consumes a list
            # of entity_id strings; anything else is silently ignored.
            if not isinstance(ents, list):
                continue
            ents = sorted(set([e for e in ents if isinstance(e, str)]))
            if len(ents) < 2:
                continue
            # Count all unique pairs in this event.
            for i in range(len(ents)):
                for j in range(i + 1, len(ents)):
                    pair = (ents[i], ents[j])
                    pair_counts[pair] = pair_counts.get(pair, 0) + 1
        now = time.time()
        written = 0
        for pair, n in pair_counts.items():
            if n < min_cooccur:
                continue
            cid = _cluster_id(list(pair))
            score = min(1.0, n / 10.0)   # bounded saturation
            await self._clusters.update_one(
                {"cluster_id": cid},
                {"$set": {
                    "cluster_id": cid,
                    "entity_ids": list(pair),
                    "sample_count": n,
                    "cluster_score": score,
                    "detected_at": now,
                    "method": "cooccurrence",
                }},
                upsert=True,
            )
            written += 1
        return {"pairs_seen": len(pair_counts), "clusters_written": written}

    async def list_top(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self._clusters.find({}, {"_id": 0}) \
            .sort("cluster_score", -1).limit(limit)
        return [d async for d in cursor]

    async def count(self) -> int:
        return await self._clusters.count_documents({})
