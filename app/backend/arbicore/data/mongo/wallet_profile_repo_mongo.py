"""Mongo implementation of WalletProfileRepository.

Persists to ``arbicore_wallet_metrics`` — collection already exists with
the unique ``wallet_id`` index (see ``arbicore_collections.py:103-108``).
This wave only adds documents; index schema is unchanged.

Document shape::

    {
        "wallet_id":     str,        # = WalletProfile.address (unique)
        "address":       str,
        "chain":         str,
        "label":         str | None,
        "label_source":  str | None,
        "first_seen":    int,
        "last_seen":     int,
        "scores":        dict,
        "stats":         dict,
        "cluster_id":    str | None,
        "entity_id":     str | None,
        "funding_source": str | None,
        "tags":          list[str],
        "updated_at":    float,      # epoch seconds; monotonic write ordering
    }

INV compliance unchanged (see wallet_profile_repo.py module docstring).
"""
from __future__ import annotations

import time
from typing import Any, Dict, Iterable, List, Optional

from ...intel.launch.wallet_profile import WalletProfile, merge_stats
from ..wallet_profile_repo import WalletProfileRepository
from .arbicore_collections import get_collection


def _strip_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in (doc or {}).items() if k != "_id"}


class MongoWalletProfileRepository(WalletProfileRepository):
    """Mongo-backed WalletProfileRepository."""

    @property
    def _col(self):
        return get_collection("wallet_metrics")

    async def get_many(self,
                       addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        if not addresses:
            return {}
        cursor = self._col.find(
            {"wallet_id": {"$in": list(addresses)}},
            {"_id": 0},
        )
        out: Dict[str, Dict[str, Any]] = {}
        async for doc in cursor:
            addr = doc.get("address") or doc.get("wallet_id")
            if addr:
                out[addr] = _strip_id(doc)
        return out

    async def get(self, address: str) -> Optional[Dict[str, Any]]:
        if not address:
            return None
        doc = await self._col.find_one(
            {"wallet_id": address}, {"_id": 0},
        )
        return _strip_id(doc) if doc else None

    async def upsert(self, profile: WalletProfile) -> None:
        if not profile or not profile.address:
            return
        # Idempotent stats merge against any pre-existing document.
        existing = await self._col.find_one(
            {"wallet_id": profile.address}, {"stats": 1, "_id": 0},
        )
        existing_stats = (existing or {}).get("stats") or {}
        merged_stats = merge_stats(existing_stats, profile.stats or {})

        doc = profile.to_storage()
        # `to_storage()` returns ``id = address``; we use ``wallet_id`` to
        # keep field naming aligned with the existing index. Both forms are
        # stored for ergonomic lookup symmetry.
        doc["wallet_id"] = profile.address
        doc["stats"] = merged_stats
        doc["updated_at"] = time.time()

        await self._col.update_one(
            {"wallet_id": profile.address},
            {"$set": doc},
            upsert=True,
        )

    async def bulk_upsert(self,
                          profiles: Iterable[WalletProfile]) -> int:
        n = 0
        for p in profiles:
            await self.upsert(p)
            n += 1
        return n

    async def count(self) -> int:
        return await self._col.count_documents({})
