"""ArbiCore X — AuditLog writer (Phase C Wave 1).

Writes immutable records to ``arbicore_audit_log`` (TTL 90d). Category-agnostic.
Used by OutcomeTracker, RouteSuccessTracker, MetricsAggregator to record
state transitions, evaluations, and corrections.

Phase B created the collection + indexes. Wave 1 starts populating it.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ...data.mongo.arbicore_collections import get_collection


class MongoAuditLog:
    @property
    def _col(self):
        return get_collection("audit_log")

    async def write(self,
                    actor: str,
                    event: str,
                    *,
                    opportunity_id: Optional[str] = None,
                    subject_id: Optional[str] = None,
                    payload: Optional[Dict[str, Any]] = None,
                    ) -> None:
        """Append a single audit row. Never raises."""
        ts = time.time()
        doc = {
            "ts": ts,
            "ts_dt": datetime.fromtimestamp(ts, tz=timezone.utc),
            "actor": actor,
            "event": event,
            "opportunity_id": opportunity_id,
            "subject_id": subject_id,
            "payload": payload or {},
        }
        try:
            await self._col.insert_one(doc)
        except Exception:  # noqa: BLE001
            # Audit log MUST NOT break the caller.
            pass

    async def count(self) -> int:
        try:
            return await self._col.count_documents({})
        except Exception:  # noqa: BLE001
            return 0

    async def recent(self, limit: int = 100, actor: Optional[str] = None) -> list:
        filt: Dict[str, Any] = {}
        if actor is not None:
            filt["actor"] = actor
        cursor = self._col.find(filt, {"_id": 0, "ts_dt": 0}).sort("ts", -1).limit(limit)
        return [d async for d in cursor]
