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


__all__ = ["DecisionHistoryRepo"]
