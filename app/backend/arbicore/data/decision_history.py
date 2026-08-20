"""ArbiCore X — Decision History (evidence / learning dataset).

Persists every opportunity evaluation: quote, freshness, route, flash
provider/size, gross/net profit, costs, confidence, EV, simulation result,
decision and rejection reason. Read-only evidence — never an execution path.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DecisionHistoryRepo:
    def __init__(self, db, collection: str = "decision_history"):
        self._coll = db[collection]

    async def ensure_indexes(self) -> None:
        await self._coll.create_index("recorded_at")
        await self._coll.create_index("route_id")
        await self._coll.create_index("scan_id")

    async def record_many(self, scan_id: str, results: List[Dict[str, Any]]) -> int:
        if not results:
            return 0
        now = _now_iso()
        docs = []
        for r in results:
            prov = r.get("quote_provenance") or {}
            docs.append({
                "scan_id": scan_id,
                "route_id": r.get("route_id"),
                "opportunity_type": r.get("opportunity_type"),
                "chain": r.get("chain"),
                "borrow_token": r.get("borrow_token"),
                "token_path": r.get("token_path"),
                "dex_path": r.get("dex_path"),
                "hop_count": r.get("hop_count"),
                "quote_status": prov.get("quote_status"),
                "quote_age_sec": prov.get("quote_age_sec"),
                "block_number": prov.get("block_number"),
                "realized_gross_spread_bps": prov.get("realized_gross_spread_bps"),
                "gross_spread_bps": r.get("gross_spread_bps"),
                "gas_cost_usd": r.get("gas_cost_usd"),
                "net_profit_usd": r.get("net_profit_usd"),
                "confidence": r.get("confidence"),
                "expected_value_usd": r.get("expected_value_usd"),
                "optimal_notional_usd": r.get("optimal_notional_usd"),
                "flash_loan_provider": (r.get("decision") or {}).get("ev", {}) and "balancer_v2",
                "simulation_passed": (r.get("simulation") or {}).get("passed"),
                "simulation_failures": (r.get("simulation") or {}).get("failures"),
                "would_execute": r.get("would_execute"),
                "reason": r.get("reason"),
                "recorded_at": now,
            })
        res = await self._coll.insert_many(docs)
        return len(res.inserted_ids)

    async def recent(self, limit: int = 50,
                     only_executable: bool = False) -> List[Dict[str, Any]]:
        q: Dict[str, Any] = {}
        if only_executable:
            q["would_execute"] = True
        cur = self._coll.find(q, {"_id": 0}).sort("recorded_at", -1).limit(
            max(1, min(int(limit), 200)))
        return await cur.to_list(length=limit)

    async def stats(self) -> Dict[str, Any]:
        total = await self._coll.count_documents({})
        executable = await self._coll.count_documents({"would_execute": True})
        real_quotes = await self._coll.count_documents({"quote_status": "REAL"})
        return {"total": total, "executable": executable,
                "real_quotes": real_quotes, "generated_at": _now_iso()}

    async def checkpoint(self, top_n: int = 5) -> Dict[str, Any]:
        """Aggregated evidence snapshot for the operator checkpoint report."""
        total = await self._coll.count_documents({})
        real_quotes = await self._coll.count_documents({"quote_status": "REAL"})
        positive = await self._coll.count_documents({"expected_value_usd": {"$gt": 0}})
        executable = await self._coll.count_documents({"would_execute": True})

        # Rejection-reason histogram (short prefix before ':').
        rej_cur = self._coll.aggregate([
            {"$match": {"would_execute": False}},
            {"$group": {"_id": {"$arrayElemAt": [{"$split": ["$reason", ":"]}, 0]},
                        "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}, {"$limit": 15}])
        rejection_histogram = {r["_id"]: r["count"] async for r in rej_cur}

        # Opportunity-type coverage.
        type_cur = self._coll.aggregate([
            {"$group": {"_id": "$opportunity_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}])
        type_coverage = {r["_id"]: r["count"] async for r in type_cur}

        top_cur = self._coll.find({}, {"_id": 0}).sort(
            [("expected_value_usd", -1)]).limit(max(1, min(int(top_n), 25)))
        top = await top_cur.to_list(length=top_n)
        return {
            "records": total, "real_quotes": real_quotes,
            "positive_after_costs": positive, "executable": executable,
            "rejection_histogram": rejection_histogram,
            "opportunity_type_coverage": type_coverage,
            "top_opportunities": top,
            "generated_at": _now_iso(),
        }


__all__ = ["DecisionHistoryRepo", "RouteRecurrenceRepo"]


class RouteRecurrenceRepo:
    """Tracks how often each route recurs across scans (recurring-route signal)."""

    def __init__(self, db, collection: str = "route_recurrence"):
        self._coll = db[collection]

    async def ensure_indexes(self) -> None:
        await self._coll.create_index("route_id", unique=True)
        await self._coll.create_index("times_positive")

    async def record_many(self, results: List[Dict[str, Any]]) -> None:
        now = _now_iso()
        for r in results:
            rid = r.get("route_id")
            if not rid:
                continue
            spread = float(r.get("gross_spread_bps") or 0.0)
            positive_inc = 1 if float(r.get("expected_value_usd") or 0.0) > 0 else 0
            await self._coll.update_one(
                {"route_id": rid},
                {"$set": {"opportunity_type": r.get("opportunity_type"),
                          "token_path": r.get("token_path"),
                          "dex_path": r.get("dex_path"),
                          "last_spread_bps": spread,
                          "last_seen": now},
                 "$max": {"best_spread_bps": spread},
                 "$inc": {"times_seen": 1, "times_positive": positive_inc},
                 "$setOnInsert": {"route_id": rid, "first_seen": now}},
                upsert=True)

    async def recurring(self, limit: int = 25, min_seen: int = 2) -> List[Dict[str, Any]]:
        cur = self._coll.find({"times_seen": {"$gte": min_seen}}, {"_id": 0}) \
            .sort([("times_positive", -1), ("best_spread_bps", -1)]).limit(
                max(1, min(int(limit), 100)))
        return await cur.to_list(length=limit)


class ProfitAlertRepo:
    """Fires ONLY for opportunities that pass the complete economic chain
    (real quote → net profit → confidence → EV → optimal size → simulation →
    would_execute). Never fires on raw price spread alone."""

    def __init__(self, db, collection: str = "profit_alerts"):
        self._coll = db[collection]

    async def ensure_indexes(self) -> None:
        await self._coll.create_index("created_at")
        await self._coll.create_index("route_id")

    async def record_qualified(self, scan_id: str,
                               results: List[Dict[str, Any]]) -> int:
        now = _now_iso()
        docs = []
        for r in results:
            if not r.get("would_execute"):
                continue
            docs.append({
                "scan_id": scan_id, "route_id": r.get("route_id"),
                "opportunity_type": r.get("opportunity_type"),
                "token_path": r.get("token_path"), "dex_path": r.get("dex_path"),
                "net_profit_usd": r.get("net_profit_usd"),
                "expected_value_usd": r.get("expected_value_usd"),
                "confidence": r.get("confidence"),
                "optimal_notional_usd": r.get("optimal_notional_usd"),
                "gross_spread_bps": r.get("gross_spread_bps"),
                "quote_status": (r.get("quote_provenance") or {}).get("quote_status"),
                "created_at": now,
            })
        if not docs:
            return 0
        res = await self._coll.insert_many(docs)
        return len(res.inserted_ids)

    async def recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        cur = self._coll.find({}, {"_id": 0}).sort("created_at", -1).limit(
            max(1, min(int(limit), 200)))
        return await cur.to_list(length=limit)

    async def count(self) -> int:
        return await self._coll.count_documents({})


__all__ = ["DecisionHistoryRepo", "RouteRecurrenceRepo", "ProfitAlertRepo"]
