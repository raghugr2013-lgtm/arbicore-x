"""ArbiCore X — Mongo OutcomeRepository (Phase B)."""
from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..outcome_repo import OutcomeRepository, OutcomeRow, StateRow
from .arbicore_collections import get_collection


def _strip_id(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


class MongoOutcomeRepository(OutcomeRepository):

    @property
    def _outcomes(self):
        return get_collection("outcomes")

    @property
    def _states(self):
        return get_collection("state_snapshots")

    async def upsert_outcome(self, outcome: OutcomeRow, only_insert: bool = False) -> bool:
        now = time.time()
        outcome.updated_at = now
        if not outcome.created_at:
            outcome.created_at = now
        doc = asdict(outcome)
        if only_insert:
            existing = await self._outcomes.find_one({"id": outcome.id}, {"_id": 1})
            if existing:
                return False
            await self._outcomes.insert_one(doc)
            return True
        await self._outcomes.update_one(
            {"id": outcome.id}, {"$set": doc}, upsert=True,
        )
        return True

    async def list_due(self, now_ts: float, limit: int = 200) -> List[OutcomeRow]:
        cursor = self._outcomes.find(
            {"evaluated": False, "due_at": {"$lte": float(now_ts)}},
            {"_id": 0},
        ).sort("due_at", 1).limit(limit)
        return [OutcomeRow(**_strip_id(d)) async for d in cursor]

    async def list_for_subject(self,
                               subject_id: str,
                               evaluated: Optional[bool] = None,
                               provenance_filter: Optional[frozenset] = None,
                               ) -> List[OutcomeRow]:
        f: Dict[str, Any] = {"subject_id": subject_id}
        if evaluated is not None:
            f["evaluated"] = bool(evaluated)
        if provenance_filter is not None:
            f["provenance"] = {"$in": [p.value for p in provenance_filter]}
        cursor = self._outcomes.find(f, {"_id": 0}).sort("due_at", -1)
        return [OutcomeRow(**_strip_id(d)) async for d in cursor]

    async def append_state_snapshot(self, state: StateRow) -> None:
        doc = asdict(state)
        # add ttl marker
        doc["captured_at_dt"] = datetime.fromtimestamp(
            state.captured_at_ts, tz=timezone.utc,
        )
        await self._states.insert_one(doc)

    async def latest_state(self, subject_id: str) -> Optional[StateRow]:
        doc = await self._states.find_one(
            {"subject_id": subject_id},
            {"_id": 0, "captured_at_dt": 0},
            sort=[("captured_at_ts", -1)],
        )
        if not doc:
            return None
        return StateRow(**doc)

    async def list_states(self,
                          subject_id: str,
                          t0: float,
                          t1: float,
                          limit: int = 1500,
                          ) -> List[StateRow]:
        cursor = self._states.find(
            {"subject_id": subject_id,
             "captured_at_ts": {"$gte": float(t0), "$lte": float(t1)}},
            {"_id": 0, "captured_at_dt": 0},
        ).sort("captured_at_ts", 1).limit(limit)
        return [StateRow(**d) async for d in cursor]

    async def count_outcomes_by_evaluated(self) -> Dict[str, int]:
        total = await self._outcomes.count_documents({})
        ev = await self._outcomes.count_documents({"evaluated": True})
        return {"evaluated": ev, "unevaluated": max(0, total - ev)}
