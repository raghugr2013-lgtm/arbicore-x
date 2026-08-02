"""ArbiCore X — RouteSuccessTracker concrete (Phase C Wave 1).

Mongo-backed implementation tracking realized success per (buy_venue, sell_venue)
route. Category-agnostic — works for any pair of venue strings, regardless of
whether they're CEX, DEX, bridge endpoints, or otherwise.

Provenance gate enforced at the write path: only opportunities with
``source_data_quality`` in ``LEARNING_ELIGIBLE_PROVENANCE`` move the counters.
"""
from __future__ import annotations

import time
from typing import List, Optional

from ...data.mongo.arbicore_collections import get_collection
from ...data.provenance import is_learning_eligible
from ...learning.route_success import RouteSuccessTracker as RouteSuccessTrackerABC
from ...models.enums import DataProvenance
from .models import RoutePerformance


def route_key_for(buy_venue: Optional[str], sell_venue: Optional[str]) -> Optional[str]:
    """Canonical route key. Returns None when either side is missing — i.e.
    the opportunity isn't a venue-routed trade (Funding, Launch, etc.)."""
    if not buy_venue or not sell_venue:
        return None
    return f"{buy_venue}->{sell_venue}"


class MongoRouteSuccessTracker(RouteSuccessTrackerABC):
    """Concrete impl backed by ``arbicore_route_stats``."""

    @property
    def _col(self):
        return get_collection("route_stats")

    # ABC compliance — keep sync signatures defined in arbicore.learning.route_success
    # while exposing async variants for the actual write path. The ABC's sync
    # methods are intentionally not used by Wave 1; the async methods are
    # canonical going forward.

    def record_result(self, route, *, succeeded, profit_usd):  # pragma: no cover
        raise NotImplementedError("Use record_outcome (async) in ArbiCore X")

    def get_success_rate(self, route):  # pragma: no cover
        raise NotImplementedError("Use get_async in ArbiCore X")

    def sample_size(self, route):  # pragma: no cover
        raise NotImplementedError("Use get_async in ArbiCore X")

    # Async canonical interface ------------------------------------------------

    async def record_outcome(self,
                             route_key: str,
                             *,
                             succeeded: bool,
                             realized_outcome: float,
                             provenance: DataProvenance,
                             ) -> bool:
        """Record one outcome for a route. Provenance-gated.

        Returns True if the row was written; False if the provenance was not
        learning-eligible (no-op, but logged via the audit_log elsewhere).
        """
        if not is_learning_eligible(provenance):
            return False
        if not route_key:
            return False
        now = time.time()
        # Atomic counter update + recompute means via pipeline-style ops.
        update = {
            "$inc": {
                "trials": 1,
                "wins": 1 if succeeded else 0,
                "realized_outcome_sum": float(realized_outcome),
            },
            "$set": {
                "last_outcome_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {
                "route_key": route_key,
            },
        }
        await self._col.update_one({"route_key": route_key}, update, upsert=True)
        # Refresh derived fields (win_rate, mean). One extra round-trip is fine
        # for a low-cadence learning write path.
        doc = await self._col.find_one({"route_key": route_key}, {"_id": 0})
        if doc:
            trials = int(doc.get("trials", 0) or 0)
            wins = int(doc.get("wins", 0) or 0)
            outcome_sum = float(doc.get("realized_outcome_sum", 0.0) or 0.0)
            win_rate = (wins / trials) if trials else 0.0
            mean = (outcome_sum / trials) if trials else 0.0
            await self._col.update_one(
                {"route_key": route_key},
                {"$set": {"win_rate": win_rate, "realized_outcome_mean": mean}},
            )
        return True

    async def get(self, route_key: str) -> Optional[RoutePerformance]:
        doc = await self._col.find_one({"route_key": route_key}, {"_id": 0})
        if not doc:
            return None
        return RoutePerformance(
            route_key=doc["route_key"],
            trials=int(doc.get("trials", 0) or 0),
            wins=int(doc.get("wins", 0) or 0),
            realized_outcome_sum=float(doc.get("realized_outcome_sum", 0.0) or 0.0),
            realized_outcome_mean=float(doc.get("realized_outcome_mean", 0.0) or 0.0),
            win_rate=float(doc.get("win_rate", 0.0) or 0.0),
            last_outcome_at=float(doc.get("last_outcome_at", 0.0) or 0.0),
            updated_at=float(doc.get("updated_at", 0.0) or 0.0),
        )

    async def list_top(self, limit: int = 50) -> List[RoutePerformance]:
        cursor = self._col.find({}, {"_id": 0}).sort("trials", -1).limit(limit)
        return [
            RoutePerformance(
                route_key=d["route_key"],
                trials=int(d.get("trials", 0) or 0),
                wins=int(d.get("wins", 0) or 0),
                realized_outcome_sum=float(d.get("realized_outcome_sum", 0.0) or 0.0),
                realized_outcome_mean=float(d.get("realized_outcome_mean", 0.0) or 0.0),
                win_rate=float(d.get("win_rate", 0.0) or 0.0),
                last_outcome_at=float(d.get("last_outcome_at", 0.0) or 0.0),
                updated_at=float(d.get("updated_at", 0.0) or 0.0),
            )
            async for d in cursor
        ]

    async def count(self) -> int:
        return await self._col.count_documents({})
