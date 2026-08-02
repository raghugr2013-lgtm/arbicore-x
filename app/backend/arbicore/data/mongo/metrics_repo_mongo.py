"""ArbiCore X — Mongo MetricsRepository (Phase B, Adj. A1)."""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List, Optional

from ..metrics_repo import MetricsRepository, SignalMetric, WalletMetric
from .arbicore_collections import get_collection


def _strip(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


class MongoMetricsRepository(MetricsRepository):

    @property
    def _signals(self):
        return get_collection("signal_metrics")

    @property
    def _wallets(self):
        return get_collection("wallet_metrics")

    async def upsert_signal_metric(self, metric: SignalMetric) -> bool:
        key = {
            "signal_id": metric.signal_id,
            "subject_id": metric.subject_id,
            "horizon_label": metric.horizon_label,
        }
        await self._signals.update_one(key, {"$set": asdict(metric)}, upsert=True)
        return True

    async def list_signal_metrics(self,
                                  signal_id: Optional[str] = None,
                                  subject_id: Optional[str] = None,
                                  limit: int = 200,
                                  ) -> List[SignalMetric]:
        f: Dict[str, Any] = {}
        if signal_id is not None:
            f["signal_id"] = signal_id
        if subject_id is not None:
            f["subject_id"] = subject_id
        cursor = self._signals.find(f, {"_id": 0}).sort("aggregated_at", -1).limit(limit)
        return [SignalMetric(**_strip(d)) async for d in cursor]

    async def upsert_wallet_metric(self, metric: WalletMetric) -> bool:
        await self._wallets.update_one(
            {"wallet_id": metric.wallet_id},
            {"$set": asdict(metric)},
            upsert=True,
        )
        return True

    async def list_wallet_metrics(self,
                                  entity_id: Optional[str] = None,
                                  limit: int = 200,
                                  ) -> List[WalletMetric]:
        f: Dict[str, Any] = {}
        if entity_id is not None:
            f["entity_id"] = entity_id
        cursor = self._wallets.find(f, {"_id": 0}).sort("updated_at", -1).limit(limit)
        return [WalletMetric(**_strip(d)) async for d in cursor]

    async def counts(self) -> Dict[str, int]:
        s = await self._signals.count_documents({})
        w = await self._wallets.count_documents({})
        return {"signals": s, "wallets": w}
