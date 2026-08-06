"""Decision Analytics service (v2.11.10).

Read-only aggregator over :collection:`arbicore_paper_evidence`.  Every
call streams the collection with a bounded scan (``limit``) and
projects each raw doc into a :class:`DecisionRecord`; the aggregator
then computes:

* Acceptance / rejection summary (`summary`)
* Rejection reason histogram (`rejection_breakdown`)
* Scanner performance table (`by_scanner`)
* Bottleneck stages (`bottlenecks`)
* Hourly executable-rate trend (`trend`)

None of these mutate anything.  Analytics are computed on-demand from
the immutable EvidenceBundle collection so historical data always
re-projects deterministically.
"""

from __future__ import annotations

import logging
import math
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from . import DecisionRecord, RejectionCategory, classify_evidence

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 500
MAX_LIMIT = 5_000


def _iso_hour(created_at: Optional[str]) -> Optional[str]:
    if not created_at:
        return None
    try:
        dt = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return dt.isoformat()
    except ValueError:
        return None


def _percentile(vals: List[float], q: float) -> float:
    if not vals:
        return 0.0
    if len(vals) == 1:
        return float(vals[0])
    xs = sorted(vals)
    idx = max(0, math.ceil(q * len(xs)) - 1)
    return float(xs[idx])


class DecisionAnalyticsService:
    """Read-only projection over the Paper Validation evidence collection."""

    def __init__(self, evidence_repo) -> None:
        if evidence_repo is None:
            raise ValueError("DecisionAnalyticsService requires an evidence repo")
        self._evidence = evidence_repo

    async def _load_records(
        self,
        *,
        limit: int,
        since: Optional[str] = None,
        scanner_family: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> List[DecisionRecord]:
        limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
        query: Dict[str, Any] = {}
        if since:
            query["created_at"] = {"$gt": since}
        if scanner_family:
            query["scanner_family"] = scanner_family
        if outcome:
            query["outcome"] = outcome
        col = getattr(self._evidence, "_col", None)
        if col is None:
            # Fallback for in-memory / stub repos
            items = await self._evidence.list_recent(limit=limit)
            docs = [i if isinstance(i, dict) else i.to_mongo() for i in items]
            if scanner_family:
                docs = [d for d in docs if d.get("scanner_family") == scanner_family]
            if outcome:
                docs = [d for d in docs if d.get("outcome") == outcome]
            docs.sort(key=lambda d: d.get("created_at") or "", reverse=True)
            docs = docs[:limit]
        else:
            try:
                cur = col.find(query, sort=[("created_at", -1)]).limit(limit)
                docs = []
                async for d in cur:
                    docs.append(d)
            except Exception as exc:  # noqa: BLE001
                logger.warning("decision analytics fetch failed: %s", exc)
                return []
        return [classify_evidence(d) for d in docs]

    async def summary(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        since: Optional[str] = None,
    ) -> Dict[str, Any]:
        recs = await self._load_records(limit=limit, since=since)
        total = len(recs)
        executable = sum(1 for r in recs if r.executable)
        real_rejects = [r for r in recs if not r.executable and r.category != RejectionCategory.OBSERVE_ONLY.value]
        observed = sum(1 for r in recs if r.category == RejectionCategory.OBSERVE_ONLY.value)
        exec_rate     = (executable / total) if total else 0.0
        # "Effective" exec rate excludes OBSERVE-only meta rejections
        effective_denom = executable + len(real_rejects)
        effective_rate  = (executable / effective_denom) if effective_denom else 0.0

        by_category: Counter[str] = Counter(r.category for r in recs)
        by_outcome:  Counter[str] = Counter(r.outcome  for r in recs)
        return {
            "window": {
                "since":            since,
                "sampled":          total,
                "limit_applied":    limit,
            },
            "executable_count":         executable,
            "executable_rate":          exec_rate,
            "effective_executable_rate": effective_rate,
            "observed_only_count":      observed,
            "real_rejection_count":     len(real_rejects),
            "outcome_counts":           dict(by_outcome),
            "category_counts":          dict(by_category),
        }

    async def rejection_breakdown(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        since: Optional[str] = None,
    ) -> Dict[str, Any]:
        recs = await self._load_records(limit=limit, since=since)
        rejected = [r for r in recs if not r.executable]
        total = len(rejected)
        by_cat: Dict[str, Dict[str, Any]] = {}
        for r in rejected:
            cat = r.category
            entry = by_cat.setdefault(cat, {
                "count":              0,
                "share":              0.0,
                "sub_codes":          Counter(),
                "attributing_stages": Counter(),
                "sample_reasons":     [],
            })
            entry["count"] += 1
            if r.sub_code:
                entry["sub_codes"][r.sub_code] += 1
            if r.attributing_stage:
                entry["attributing_stages"][r.attributing_stage] += 1
            if r.reason_text and len(entry["sample_reasons"]) < 3 and r.reason_text not in entry["sample_reasons"]:
                entry["sample_reasons"].append(r.reason_text)
        # finalise
        for cat, entry in by_cat.items():
            entry["share"] = (entry["count"] / total) if total else 0.0
            entry["sub_codes"] = dict(entry["sub_codes"].most_common(5))
            entry["attributing_stages"] = dict(entry["attributing_stages"].most_common(5))
        # Deterministic order — biggest first.
        ordered = sorted(by_cat.items(), key=lambda kv: -kv[1]["count"])
        return {
            "window": {
                "since":         since,
                "sampled":       len(recs),
                "rejected":      total,
                "limit_applied": limit,
            },
            "categories": [{"category": c, **e} for c, e in ordered],
        }

    async def by_scanner(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        since: Optional[str] = None,
    ) -> Dict[str, Any]:
        recs = await self._load_records(limit=limit, since=since)
        agg: Dict[str, Dict[str, Any]] = {}
        for r in recs:
            key = r.scanner_family or "unknown"
            entry = agg.setdefault(key, {
                "family":              key,
                "sampled":             0,
                "executable":          0,
                "rejected":            0,
                "observe_only":        0,
                "top_category":        None,
                "category_counts":     Counter(),
                "avg_e2e_ms":          0.0,
                "_e2e_sum":            0.0,
            })
            entry["sampled"] += 1
            if r.executable:
                entry["executable"] += 1
            elif r.category == RejectionCategory.OBSERVE_ONLY.value:
                entry["observe_only"] += 1
            else:
                entry["rejected"] += 1
            entry["category_counts"][r.category] += 1
            entry["_e2e_sum"] += r.e2e_duration_ms

        rows: List[Dict[str, Any]] = []
        for f, e in agg.items():
            n = max(1, e["sampled"])
            cat_counter = e["category_counts"]
            e["category_counts"] = dict(cat_counter.most_common(6))
            e["top_category"] = cat_counter.most_common(1)[0][0] if cat_counter else None
            e["executable_rate"] = (e["executable"] / e["sampled"]) if e["sampled"] else 0.0
            e["avg_e2e_ms"] = e["_e2e_sum"] / n
            e.pop("_e2e_sum")
            rows.append(e)
        rows.sort(key=lambda r: -r["sampled"])
        return {
            "window": {
                "since":         since,
                "sampled":       len(recs),
                "limit_applied": limit,
            },
            "families": rows,
        }

    async def bottlenecks(
        self,
        *,
        limit: int = DEFAULT_LIMIT,
        since: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Where are opportunities dying?

        Combines stage-level rejection count with stage p95 latency —
        both are "bottleneck" signals but for different reasons:
        rejection concentration means the *logic* at that stage is
        eating opps; latency concentration means the *implementation*
        of that stage is slowing everything down.
        """
        recs = await self._load_records(limit=limit, since=since)
        rejects_by_stage: Counter[str] = Counter()
        durations_by_stage: Dict[str, List[float]] = defaultdict(list)
        for r in recs:
            for name, dur in r.stage_durations_ms.items():
                durations_by_stage[name].append(dur)
            if r.attributing_stage and not r.executable and r.category != RejectionCategory.OBSERVE_ONLY.value:
                rejects_by_stage[r.attributing_stage] += 1

        total_real_rejects = sum(rejects_by_stage.values())
        rows: List[Dict[str, Any]] = []
        for stage_name, dur_list in durations_by_stage.items():
            reject_count = rejects_by_stage.get(stage_name, 0)
            rows.append({
                "stage":            stage_name,
                "rejections":       reject_count,
                "rejection_share":  (reject_count / total_real_rejects) if total_real_rejects else 0.0,
                "duration_p50_ms":  _percentile(dur_list, 0.50),
                "duration_p95_ms":  _percentile(dur_list, 0.95),
                "duration_max_ms":  max(dur_list) if dur_list else 0.0,
                "sample_size":      len(dur_list),
            })
        rows.sort(key=lambda r: (-r["rejections"], -r["duration_p95_ms"]))
        return {
            "window": {
                "since":               since,
                "sampled":             len(recs),
                "limit_applied":       limit,
                "total_real_rejects":  total_real_rejects,
            },
            "stages": rows,
        }

    async def trend(
        self,
        *,
        hours: int = 24,
        limit: int = MAX_LIMIT,
    ) -> Dict[str, Any]:
        """Hourly executable-rate trend over the last N hours."""
        hours = max(1, min(int(hours), 168))  # cap 1 week
        since_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
        since = since_dt.isoformat()
        recs = await self._load_records(limit=limit, since=since)
        by_hour: Dict[str, Dict[str, int]] = {}
        for r in recs:
            h = _iso_hour(r.created_at)
            if not h:
                continue
            entry = by_hour.setdefault(h, {"total": 0, "executable": 0, "real_rejected": 0, "observed": 0})
            entry["total"] += 1
            if r.executable:
                entry["executable"] += 1
            elif r.category == RejectionCategory.OBSERVE_ONLY.value:
                entry["observed"] += 1
            else:
                entry["real_rejected"] += 1
        # Emit a complete series (fill missing hours with zeros).
        points: List[Dict[str, Any]] = []
        for i in range(hours - 1, -1, -1):
            dt = (datetime.now(timezone.utc) - timedelta(hours=i)).replace(
                minute=0, second=0, microsecond=0
            )
            key = dt.isoformat()
            entry = by_hour.get(key, {"total": 0, "executable": 0, "real_rejected": 0, "observed": 0})
            denom = entry["executable"] + entry["real_rejected"]
            rate = (entry["executable"] / denom) if denom else 0.0
            points.append({
                "hour":               key,
                "total":              entry["total"],
                "executable":         entry["executable"],
                "real_rejected":      entry["real_rejected"],
                "observed":           entry["observed"],
                "effective_rate":     rate,
            })
        return {
            "window": {"hours": hours, "since": since, "sampled": len(recs)},
            "points": points,
        }

    async def recent_decisions(
        self,
        *,
        limit: int = 50,
        scanner_family: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> Dict[str, Any]:
        recs = await self._load_records(
            limit=limit,
            scanner_family=scanner_family,
            outcome=outcome,
        )
        return {
            "count": len(recs),
            "items": [r.to_dict() for r in recs],
        }
