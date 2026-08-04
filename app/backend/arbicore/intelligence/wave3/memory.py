"""OpportunityMemory — Phase 3 read-side aggregator.

Turns raw MID rows into progressively-smarter answers to operator
questions:

  * Which opportunities keep coming back?
  * How does confidence for one opportunity trend over time?
  * Which routes are consistently profitable?
  * Which venues underperform?
  * How has the market regime moved in the last 24h?
  * How persistent is opportunity X vs. its peers?

Every query reuses the same ``db`` handle the writer/reader use. This
module never persists derived state — repeat calls are idempotent and
always reflect the newest MID rows.
"""
from __future__ import annotations

import statistics
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _iso_offset(hours: float) -> str:
    return (_now_dt() - timedelta(hours=hours)).isoformat().replace(
        "+00:00", "Z")


class OpportunityMemory:
    """Read-only aggregator. Constructed with a Motor ``db`` handle."""

    LIFETIME_COLL      = "mid_opportunity_lifetime"
    CONFIDENCE_COLL    = "mid_confidence"
    ROUTES_COLL        = "mid_routes"
    PROVIDERS_COLL     = "mid_providers"
    OPPORTUNITIES_COLL = "mid_opportunities"

    def __init__(self, db: Any) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Recurring opportunities
    # ------------------------------------------------------------------

    async def top_recurring(
        self, *, limit: int = 20,
        min_recurrence: int = 1,
        opportunity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Opportunities sorted by recurrence_count descending — the
        "which ones keep coming back" answer."""
        q: Dict[str, Any] = {"recurrence_count": {"$gte": min_recurrence}}
        if opportunity_type:
            q["opportunity_type"] = opportunity_type
        cursor = self._db[self.LIFETIME_COLL].find(q, {
            "_id": 0, "opp_id": 1, "opportunity_type": 1, "chain": 1,
            "first_seen": 1, "last_seen": 1, "observation_count": 1,
            "recurrence_count": 1, "rediscovery_count": 1,
            "opportunity_status": 1, "last_confidence": 1,
            "last_profitability": 1, "lifetime_seconds": 1,
        }).sort([("recurrence_count", -1),
                 ("observation_count", -1)]).limit(limit)
        return [d async for d in cursor]

    async def most_persistent(
        self, *, limit: int = 20,
        min_observations: int = 2,
    ) -> List[Dict[str, Any]]:
        """Opportunities sorted by lifetime_seconds — the longest-lived."""
        cursor = self._db[self.LIFETIME_COLL].find({
            "observation_count": {"$gte": min_observations},
        }, {
            "_id": 0, "opp_id": 1, "opportunity_type": 1, "chain": 1,
            "first_seen": 1, "last_seen": 1, "lifetime_seconds": 1,
            "observation_count": 1, "opportunity_status": 1,
        }).sort("lifetime_seconds", -1).limit(limit)
        return [d async for d in cursor]

    # ------------------------------------------------------------------
    # Confidence + profitability history
    # ------------------------------------------------------------------

    async def confidence_history(
        self, opp_id: str, *, limit: int = 100,
    ) -> Dict[str, Any]:
        """All confidence samples for one opp_id + rolling statistics."""
        cursor = self._db[self.CONFIDENCE_COLL].find(
            {"opp_id": opp_id}, {"_id": 0, "ts": 1, "score": 1}
        ).sort("ts", 1).limit(limit)
        rows = [d async for d in cursor]
        scores = [r["score"] for r in rows if r.get("score") is not None]
        stats: Dict[str, Any] = {
            "sample_count": len(scores),
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
            "mean": (sum(scores) / len(scores)) if scores else None,
            "median": statistics.median(scores) if scores else None,
            "stdev": (statistics.pstdev(scores)
                       if len(scores) >= 2 else None),
        }
        trend = "flat"
        if len(scores) >= 4:
            half = len(scores) // 2
            first_half_mean  = sum(scores[:half]) / half
            second_half_mean = sum(scores[half:]) / (len(scores) - half)
            if second_half_mean > first_half_mean * 1.05:
                trend = "rising"
            elif second_half_mean < first_half_mean * 0.95:
                trend = "falling"
        stats["trend"] = trend
        return {"opp_id": opp_id, "history": rows, "stats": stats}

    async def profitability_history(
        self, opp_id: str, *, limit: int = 100,
    ) -> Dict[str, Any]:
        """Profitability samples for one opp_id, taken from the
        Phase-2 ``profitability_trend`` ring buffer on the lifetime
        doc. Falls back to opportunity events with a ``profitability``
        payload when the ring buffer is empty."""
        doc = await self._db[self.LIFETIME_COLL].find_one(
            {"opp_id": opp_id},
            {"_id": 0, "profitability_trend": 1, "last_profitability": 1},
        )
        rows = list((doc or {}).get("profitability_trend") or [])[:limit]
        if not rows:
            cursor = self._db[self.OPPORTUNITIES_COLL].find(
                {"opp_id": opp_id,
                 "payload.profitability": {"$exists": True}},
                {"_id": 0, "ts": 1, "payload.profitability": 1},
            ).sort("ts", 1).limit(limit)
            rows = [{"ts": r["ts"],
                     "value": r.get("payload", {}).get("profitability")}
                    async for r in cursor]
        values = [r["value"] for r in rows if r.get("value") is not None]
        return {
            "opp_id": opp_id, "history": rows,
            "stats": {
                "sample_count": len(values),
                "min":  min(values) if values else None,
                "max":  max(values) if values else None,
                "mean": (sum(values) / len(values)) if values else None,
                "last": doc.get("last_profitability") if doc else None,
            },
        }

    # ------------------------------------------------------------------
    # Route quality
    # ------------------------------------------------------------------

    async def route_quality(
        self, *, limit: int = 20, chain: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Top routes by sample_count — high-volume routes are the ones
        the platform observes most. Combines mid_routes.sample_count
        with a join into the count of related lifetime docs whose
        recurrence_count > 0."""
        q: Dict[str, Any] = {}
        if chain:
            q["fingerprint_parts.chain"] = chain
        cursor = self._db[self.ROUTES_COLL].find(q, {
            "_id": 0, "route_id": 1, "sample_count": 1,
            "fingerprint_parts": 1, "first_seen": 1, "last_seen": 1,
        }).sort("sample_count", -1).limit(limit)
        return [d async for d in cursor]

    # ------------------------------------------------------------------
    # Venue quality
    # ------------------------------------------------------------------

    async def venue_quality(
        self, *, limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Provider snapshots aggregated by provider_id — the
        Sprint 1B ``mid_providers`` domain already stores available /
        cost / revert observations per provider, so we just group on it.
        """
        cursor = self._db[self.PROVIDERS_COLL].aggregate([
            {"$group": {
                "_id": "$provider_id",
                "sample_count":       {"$sum": 1},
                "avg_cost_bps":       {"$avg": "$observed_cost_bps"},
                "revert_count":       {"$sum": "$observed_revert_count"},
                "available_true":     {"$sum": {"$cond": [
                    {"$eq": ["$available", True]}, 1, 0]}},
                "available_false":    {"$sum": {"$cond": [
                    {"$eq": ["$available", False]}, 1, 0]}},
                "last_ts":            {"$max": "$ts"},
            }},
            {"$sort": {"sample_count": -1}},
            {"$limit": limit},
        ])
        return [{"provider_id": r["_id"], **{k: v for k, v in r.items()
                                              if k != "_id"}}
                async for r in cursor]

    # ------------------------------------------------------------------
    # Market regime history
    # ------------------------------------------------------------------

    async def regime_history(self, *, hours: float = 24.0,
                              limit: int = 200) -> Dict[str, Any]:
        """All regime classifications in the last N hours.

        Comes from the ``mid_opportunities`` collection where
        Wave 1B-α's regime bridge writes rows with
        ``event_type = "intel.regime.classified"``.
        """
        since = _iso_offset(hours)
        cursor = self._db[self.OPPORTUNITIES_COLL].find(
            {"event_type": "intel.regime.classified",
             "ts": {"$gte": since}},
            {"_id": 0, "ts": 1, "payload": 1},
        ).sort("ts", -1).limit(limit)
        rows = [d async for d in cursor]
        # roll-up
        counts: Dict[str, int] = {}
        for r in rows:
            regime = r.get("payload", {}).get("dominant_regime", "UNKNOWN")
            counts[regime] = counts.get(regime, 0) + 1
        return {"since": since, "count": len(rows),
                "by_regime": counts, "rows": rows}

    # ------------------------------------------------------------------
    # Global memory snapshot
    # ------------------------------------------------------------------

    async def summary(self) -> Dict[str, Any]:
        """Single call the dashboard uses to hydrate its memory panel."""
        total_opps = await self._db[
            self.LIFETIME_COLL].count_documents({})
        recurring = await self._db[
            self.LIFETIME_COLL].count_documents(
                {"recurrence_count": {"$gte": 1}})
        stale = await self._db[self.LIFETIME_COLL].count_documents(
            {"opportunity_status": "STALE"})
        expired = await self._db[
            self.LIFETIME_COLL].count_documents(
                {"opportunity_status": "EXPIRED"})
        active = await self._db[self.LIFETIME_COLL].count_documents(
            {"opportunity_status": "ACTIVE"})

        confidence_sample = await self._db[
            self.CONFIDENCE_COLL].count_documents({})
        route_sample = await self._db[self.ROUTES_COLL].count_documents({})
        provider_sample = await self._db[
            self.PROVIDERS_COLL].count_documents({})

        return {
            "opportunities": {
                "total": total_opps,
                "recurring": recurring,
                "by_status": {
                    "ACTIVE": active, "STALE": stale, "EXPIRED": expired,
                },
            },
            "evidence": {
                "confidence_rows": confidence_sample,
                "route_rows":      route_sample,
                "provider_rows":   provider_sample,
            },
        }
