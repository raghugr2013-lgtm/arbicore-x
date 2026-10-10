"""Async reads of the opportunity ledger collection. No other collections."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .read_model import apply_filters, detail, paginate, run_index, sort_rows, summarize
from .repo import COLLECTION


async def _to_list(cursor: Any) -> List[Dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        rows = await cursor.to_list(length=20000)
    else:
        rows = list(cursor)
    return [{key: value for key, value in row.items() if key != "_id"} for row in rows]


_LIST_PROJECTION = {
    "_id": 0,
    "ledger_id": 1,
    "opportunity_id": 1,
    "run_id": 1,
    "candidate_id": 1,
    "verifier_bundle_id": 1,
    "evidence.strategy.primary_family": 1,
    "evidence.provenance.chain": 1,
    "evidence.provenance.flash_loan_provider": 1,
    "evidence.provenance.timestamps.verified_at": 1,
    "evidence.gates.decision_net_usd": 1,
    "evidence.gates.gate_7": 1,
    "evidence.gates.final_observed_status": 1,
}


async def load_rows(
    db: Any,
    run_id: Optional[str] = None,
    projection: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    query: Dict[str, Any] = {}
    if run_id:
        query["run_id"] = run_id
    cursor = db[COLLECTION].find(query, projection or {"_id": 0})
    return await _to_list(cursor)


async def list_runs(db: Any) -> Dict[str, Any]:
    rows = await load_rows(db)
    return {"runs": run_index(rows)}


async def run_summary(db: Any, run_id: str) -> Optional[Dict[str, Any]]:
    rows = await load_rows(db, run_id)
    if not rows:
        return None
    return summarize(rows)


async def list_opportunities(db: Any, **filters: Any) -> Dict[str, Any]:
    page = int(filters.pop("page", 1) or 1)
    page_size = int(filters.pop("page_size", 25) or 25)
    sort = filters.pop("sort", "net") or "net"
    order = filters.pop("order", "desc") or "desc"
    run_id = filters.get("run_id")
    rows = await load_rows(db, run_id, _LIST_PROJECTION)
    filtered = apply_filters(rows, **filters)
    ordered = sort_rows(filtered, sort, order)
    return paginate(ordered, page, page_size)


async def opportunity_detail(db: Any, ledger_id: str) -> Optional[Dict[str, Any]]:
    row = await db[COLLECTION].find_one({"ledger_id": ledger_id}, {"_id": 0})
    if row is None:
        return None
    return detail(row)
