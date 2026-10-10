"""Persistence for Opportunity Ledger projections.

Writes only the ledger collection passed to the repository. Re-projecting
the same ``ledger_id`` updates the evidence fields and leaves
``annotations`` untouched. Annotations are created empty on insert.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

COLLECTION = "arbicore_opportunity_ledger"


class OpportunityLedgerRepo:
    def __init__(self, db: Any, collection_name: str = COLLECTION) -> None:
        self._col = db[collection_name]

    async def ensure_indexes(self) -> None:
        await self._col.create_index("ledger_id", unique=True)
        await self._col.create_index([("run_id", 1), ("candidate_id", 1)])

    async def upsert(self, record: Dict[str, Any]) -> Dict[str, Any]:
        ledger_id = record.get("ledger_id")
        if not isinstance(ledger_id, str) or not ledger_id:
            raise ValueError("ledger_id is required")
        body = {key: value for key, value in record.items() if key != "annotations"}
        await self._col.update_one(
            {"ledger_id": ledger_id},
            {"$set": body, "$setOnInsert": {"annotations": {}}},
            upsert=True,
        )
        stored = await self._col.find_one({"ledger_id": ledger_id}, {"_id": 0})
        if stored is None:
            raise RuntimeError("ledger upsert did not store a row")
        return stored

    async def get(self, ledger_id: str) -> Optional[Dict[str, Any]]:
        return await self._col.find_one({"ledger_id": ledger_id}, {"_id": 0})
