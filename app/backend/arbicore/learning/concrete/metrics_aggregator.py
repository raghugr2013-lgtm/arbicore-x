"""ArbiCore X — MetricsAggregator (Phase C Wave 1).

Reads evaluated OpportunityOutcomes from arbicore_outcomes (via
OutcomeRepository) and writes aggregated rows into arbicore_signal_metrics
via MetricsRepository.

In Wave 1 we have no signal layer yet (that lands in C-2 ConfidenceEngine),
so the only "signal" we aggregate is the *route outcome* itself. This gives
us a non-empty learning data row from day one and validates the aggregation
plumbing end-to-end.

Category-agnostic: aggregation is keyed by ``(subject_id, horizon_label)``
and ``(opportunity_type, horizon_label)``. No exchange/asset assumptions.
"""
from __future__ import annotations

import time
from typing import Dict, List, Optional

from ...data.metrics_repo import MetricsRepository, SignalMetric
from ...data.mongo.arbicore_collections import get_collection


class MetricsAggregator:
    """Manual-trigger aggregator. Phase C Wave 1 does not auto-run it; the
    composition root exposes a coroutine method that the operator (or the
    OutcomeTracker worker) may invoke."""

    def __init__(self, metrics_repo: MetricsRepository):
        self._metrics = metrics_repo

    @property
    def _outcomes_col(self):
        # Read directly from arbicore_outcomes — avoids round-tripping every
        # row through OutcomeRow dataclass.
        return get_collection("outcomes")

    async def aggregate_by_subject_horizon(self,
                                           subject_id: Optional[str] = None,
                                           horizon_label: Optional[str] = None,
                                           ) -> List[SignalMetric]:
        """Compute one SignalMetric per ``(subject_id, horizon_label)`` using
        evaluated outcomes only. Returns the metrics written."""
        match: Dict = {"evaluated": True}
        if subject_id is not None:
            match["subject_id"] = subject_id
        if horizon_label is not None:
            match["horizon_label"] = horizon_label
        pipeline = [
            {"$match": match},
            {"$group": {
                "_id": {"subject_id": "$subject_id",
                        "horizon_label": "$horizon_label"},
                "n": {"$sum": 1},
                "delta_sum": {"$sum": {"$ifNull": [
                    "$realized_outcome.realized_metric_delta", 0,
                ]}},
                "win_sum": {"$sum": {"$cond": [
                    {"$eq": ["$realized_outcome.succeeded", True]}, 1, 0,
                ]}},
            }},
        ]
        produced: List[SignalMetric] = []
        now = time.time()
        async for row in self._outcomes_col.aggregate(pipeline):
            n = int(row.get("n", 0) or 0)
            if n == 0:
                continue
            delta_sum = float(row.get("delta_sum", 0.0) or 0.0)
            win_sum = int(row.get("win_sum", 0) or 0)
            metric = SignalMetric(
                signal_id="route_outcome",
                subject_id=row["_id"].get("subject_id"),
                horizon_label=row["_id"].get("horizon_label") or "",
                sample_count=n,
                score_impact_sum=delta_sum,
                score_impact_mean=(delta_sum / n) if n else 0.0,
                win_rate=(win_sum / n) if n else 0.0,
                aggregated_at=now,
                extras={"win_count": win_sum},
            )
            await self._metrics.upsert_signal_metric(metric)
            produced.append(metric)
        return produced

    async def stats(self) -> Dict[str, int]:
        total_evaluated = await self._outcomes_col.count_documents({"evaluated": True})
        from ...data.mongo.arbicore_collections import get_collection as gc
        signals_n = await gc("signal_metrics").count_documents({})
        return {
            "evaluated_outcomes": total_evaluated,
            "signal_metric_rows": signals_n,
        }
