"""MID reader façade — parameterised query surface with metadata filters.

Every reader method accepts the full strategy-agnostic metadata block as
optional filters plus a time range.  All queries stream through the same
filter builder so the metadata contract is uniform across domains.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import DOMAINS, MID_COLLECTION_MAP


class MidReader:
    def __init__(self, db: Any) -> None:
        self._db = db

    @staticmethod
    def _build_filter(*, strategy_type: Optional[str] = None,
                       opportunity_type: Optional[str] = None,
                       capital_source: Optional[str] = None,
                       chain: Optional[str] = None,
                       protocol: Optional[str] = None,
                       execution_mode: Optional[str] = None,
                       market_regime: Optional[str] = None,
                       ts_gte: Optional[str] = None,
                       ts_lte: Optional[str] = None,
                       extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        q: Dict[str, Any] = {}
        if strategy_type:      q["meta.strategy_type"] = strategy_type
        if opportunity_type:   q["meta.opportunity_type"] = opportunity_type
        if capital_source:     q["meta.capital_source"] = capital_source
        if chain:              q["meta.chain"] = chain
        if protocol:           q["meta.protocol"] = protocol
        if execution_mode:     q["meta.execution_mode"] = execution_mode
        if market_regime:      q["meta.market_regime"] = market_regime
        if ts_gte or ts_lte:
            q["ts"] = {}
            if ts_gte: q["ts"]["$gte"] = ts_gte
            if ts_lte: q["ts"]["$lte"] = ts_lte
        if extra:
            q.update(extra)
        return q

    async def query(self, domain: str, *, limit: int = 100,
                     sort_field: str = "ts", sort_dir: int = -1,
                     **filters: Any) -> List[Dict[str, Any]]:
        if domain not in DOMAINS:
            raise ValueError(f"unknown MID domain: {domain}")
        coll = self._db[MID_COLLECTION_MAP[domain]]
        q = self._build_filter(**filters)
        cur = coll.find(q, {"_id": 0}).sort(sort_field, sort_dir).limit(min(int(limit), 1000))
        return [d async for d in cur]

    async def get_by_mid_id(self, domain: str, mid_id: str) -> Optional[Dict[str, Any]]:
        if domain not in DOMAINS:
            raise ValueError(f"unknown MID domain: {domain}")
        return await self._db[MID_COLLECTION_MAP[domain]].find_one({"mid_id": mid_id}, {"_id": 0})

    async def status(self) -> Dict[str, Any]:
        """Return per-domain collection size + last-write timestamp."""
        out: Dict[str, Any] = {"domains": {}}
        for domain in DOMAINS:
            coll = self._db[MID_COLLECTION_MAP[domain]]
            try:
                count = await coll.estimated_document_count()
            except Exception:
                count = 0
            latest = await coll.find_one({}, {"_id": 0, "ts": 1}, sort=[("ts", -1)])
            out["domains"][domain] = {
                "collection": MID_COLLECTION_MAP[domain],
                "count": count,
                "last_ts": (latest or {}).get("ts"),
            }
        # enum warnings
        try:
            out["enum_warnings_count"] = await self._db["mid_enum_warnings"].estimated_document_count()
        except Exception:
            out["enum_warnings_count"] = 0
        return out
