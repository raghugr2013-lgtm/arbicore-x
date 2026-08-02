"""ArbiCore X — Phase D D-1: Discovery Source Metrics aggregator + repo.

Per PHASE_D_DISCOVERY_LAYER_SPEC.md §6.

Aggregates per-source rolling metrics from arbicore_discovery_candidates:
  - hit_rate = confirmed / (confirmed + denied + error)
  - false_positive_rate = denied_venue_disagrees / (confirmed + denied_venue_disagrees)
  - verification_latency_p50/p95 over confirmed candidates
  - emission_rate (per minute, rolling window)
  - survival_to_canonical

Persists into arbicore_discovery_source_metrics with TTL 90 days.
"""
from __future__ import annotations

import math
import time
from typing import Any, Dict, List, Optional

CANDIDATE_COLLECTION = "arbicore_discovery_candidates"
METRICS_COLLECTION = "arbicore_discovery_source_metrics"
WINDOWS_S = {"1h": 3600, "24h": 86400, "7d": 7 * 86400}


class DiscoverySourceMetricsRepo:
    def __init__(self, db) -> None:
        self._db = db
        self._candidates = db[CANDIDATE_COLLECTION]
        self._metrics = db[METRICS_COLLECTION]

    async def ensure_indexes(self) -> None:
        await self._metrics.create_index(
            [("source_id", 1), ("window", 1), ("captured_at_ts", -1)]
        )
        await self._metrics.create_index(
            "captured_at_ts",
            expireAfterSeconds=90 * 86400,
        )

    async def aggregate_all(self) -> int:
        """Aggregate every source × window combination and persist."""
        now = time.time()
        sources = await self._candidates.distinct("hint_source")
        rows_written = 0
        for source_id in sources:
            for window_label, window_s in WINDOWS_S.items():
                cutoff = now - window_s
                row = await self._compute_window(source_id, cutoff)
                row.update({
                    "source_id": source_id,
                    "window": window_label,
                    "captured_at_ts": now,
                })
                await self._metrics.insert_one(row)
                rows_written += 1
        return rows_written

    async def _compute_window(self, source_id: str,
                              cutoff_ts: float) -> Dict[str, Any]:
        cur = self._candidates.find({
            "hint_source": source_id,
            "hint_observed_at": {"$gte": cutoff_ts},
        }, projection={
            "verified_outcome": 1, "verification_latency_ms": 1,
            "hint_observed_at": 1, "verified_at": 1,
        })
        n = 0
        n_confirmed = 0
        n_denied_disagree = 0
        n_denied_other = 0
        n_error = 0
        n_expired = 0
        latencies: List[int] = []
        async for doc in cur:
            n += 1
            outcome = doc.get("verified_outcome")
            if outcome is None:
                continue  # still in-flight; not counted
            if outcome.startswith("confirmed_canonical:"):
                n_confirmed += 1
                lat = doc.get("verification_latency_ms")
                if lat is not None:
                    latencies.append(int(lat))
            elif outcome == "denied:venue_disagrees":
                n_denied_disagree += 1
            elif outcome.startswith("error:"):
                n_error += 1
            elif outcome == "expired_unclaimed":
                n_expired += 1
            else:
                n_denied_other += 1

        decided = n_confirmed + n_denied_disagree + n_denied_other + n_error
        hit_rate = round(n_confirmed / decided, 4) if decided > 0 else None
        fp_denom = n_confirmed + n_denied_disagree
        fp_rate = round(n_denied_disagree / fp_denom, 4) if fp_denom > 0 else None
        latencies.sort()
        p50 = self._quantile(latencies, 0.5)
        p95 = self._quantile(latencies, 0.95)

        return {
            "sample_size": n,
            "metrics": {
                "n_observed":      n,
                "n_confirmed":     n_confirmed,
                "n_denied":        n_denied_disagree + n_denied_other,
                "n_denied_disagree": n_denied_disagree,
                "n_error":         n_error,
                "n_expired":       n_expired,
                "hit_rate":        hit_rate,
                "false_positive_rate": fp_rate,
                "verification_latency_ms_p50": p50,
                "verification_latency_ms_p95": p95,
                "survival_to_canonical": (
                    round(n_confirmed / n, 4) if n > 0 else None
                ),
            },
        }

    @staticmethod
    def _quantile(sorted_xs: List[int], q: float) -> Optional[int]:
        if not sorted_xs:
            return None
        i = max(0, min(len(sorted_xs) - 1, int(math.ceil(q * len(sorted_xs)) - 1)))
        return int(sorted_xs[i])

    async def latest_per_source(self, window: str = "24h"
                                ) -> List[Dict[str, Any]]:
        cur = self._metrics.aggregate([
            {"$match": {"window": window}},
            {"$sort": {"captured_at_ts": -1}},
            {"$group": {
                "_id": "$source_id",
                "doc": {"$first": "$$ROOT"},
            }},
            {"$replaceRoot": {"newRoot": "$doc"}},
        ])
        out = []
        async for d in cur:
            d.pop("_id", None)
            out.append(d)
        return out

    async def write_weekly_digest(self) -> Dict[str, Any]:
        """Snapshot the 24h metrics across sources into a single digest doc."""
        sources_24h = await self.latest_per_source("24h")
        ranked = sorted(
            sources_24h,
            key=lambda r: (r.get("metrics", {}).get("hit_rate") or -1),
            reverse=True,
        )
        digest = {
            "captured_at_ts": time.time(),
            "n_sources": len(sources_24h),
            "top_by_hit_rate": [
                {"source_id": r["source_id"],
                 "hit_rate": r["metrics"].get("hit_rate"),
                 "n_observed": r["metrics"].get("n_observed")}
                for r in ranked[:3]
            ],
            "bottom_by_hit_rate": [
                {"source_id": r["source_id"],
                 "hit_rate": r["metrics"].get("hit_rate"),
                 "n_observed": r["metrics"].get("n_observed")}
                for r in reversed(ranked[-3:])
            ],
            "highest_fp_rate": sorted(
                [r for r in sources_24h
                 if r["metrics"].get("false_positive_rate") is not None],
                key=lambda r: r["metrics"]["false_positive_rate"],
                reverse=True,
            )[:3],
            "latency_outliers_p95_ms": sorted(
                [r for r in sources_24h
                 if r["metrics"].get("verification_latency_ms_p95") is not None],
                key=lambda r: r["metrics"]["verification_latency_ms_p95"],
                reverse=True,
            )[:3],
        }
        await self._db["arbicore_discovery_weekly_digest"].insert_one(dict(digest))
        return digest

    async def latest_weekly_digests(self, limit: int = 7
                                    ) -> List[Dict[str, Any]]:
        cur = self._db["arbicore_discovery_weekly_digest"].find({}).sort(
            "captured_at_ts", -1
        ).limit(limit)
        out = []
        async for d in cur:
            d.pop("_id", None)
            out.append(d)
        return out
