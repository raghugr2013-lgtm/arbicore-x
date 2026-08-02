"""ArbiCore X — Survival Analytics (Phase C Wave 3).

Measures how long an opportunity-subject's primary metric stays in a
"persisting" band before significant degradation. Category-agnostic: works
on any time series of OpportunityState snapshots regardless of opportunity
type or origin.

The model is intentionally simple and reversible:
  - "Alive" while |primary_metric − baseline| ≤ tolerance × |baseline|
  - "Dead"  when the gap exceeds tolerance (in either direction)
  - lifetime_s = first_dead_ts − baseline_ts; ∞ if never crossed

Returns per-subject + cross-subject distribution statistics. No exchange-
specific assumptions; the tolerance is a free parameter.
"""
from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from ...data.outcome_repo import OutcomeRepository


@dataclass
class SubjectSurvival:
    subject_id: str
    baseline_ts: float
    baseline_metric: float
    sample_count: int
    lifetime_s: Optional[float]   # None = still alive within window
    degraded: bool
    tolerance: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SurvivalDistribution:
    sample_size: int
    median_lifetime_s: Optional[float]
    p25_lifetime_s: Optional[float]
    p75_lifetime_s: Optional[float]
    survived_pct: float            # fraction with lifetime_s is None
    tolerance: float
    horizon_s: int
    subjects: List[SubjectSurvival] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["subjects"] = [s.to_dict() for s in self.subjects]
        return d


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None
    vals = sorted(values)
    k = (len(vals) - 1) * p
    f = int(k)
    c = min(f + 1, len(vals) - 1)
    if f == c:
        return vals[f]
    return vals[f] + (vals[c] - vals[f]) * (k - f)


class SurvivalAnalytics:
    """Pure read service — does not write to Mongo. Category-agnostic."""

    def __init__(self,
                 outcome_repo: OutcomeRepository,
                 default_tolerance: float = 0.05,    # 5 % band
                 default_horizon_s: int = 24 * 3600,
                 ):
        self._outcomes = outcome_repo
        self._default_tolerance = float(default_tolerance)
        self._default_horizon_s = int(default_horizon_s)

    async def for_subject(self,
                          subject_id: str,
                          tolerance: Optional[float] = None,
                          horizon_s: Optional[int] = None,
                          ) -> Optional[SubjectSurvival]:
        tol = self._default_tolerance if tolerance is None else float(tolerance)
        h = self._default_horizon_s if horizon_s is None else int(horizon_s)
        states = await self._outcomes.list_states(
            subject_id, t0=0.0, t1=1e15, limit=2000,
        )
        if len(states) < 2:
            return None
        baseline = states[0]
        cutoff = baseline.captured_at_ts + h
        lifetime: Optional[float] = None
        degraded = False
        for s in states[1:]:
            if s.captured_at_ts > cutoff:
                break
            if baseline.primary_metric == 0:
                # Avoid div-by-zero — treat baseline of 0 with abs diff
                diff = abs(s.primary_metric)
            else:
                diff = abs(s.primary_metric - baseline.primary_metric) / abs(baseline.primary_metric)
            if diff > tol:
                lifetime = s.captured_at_ts - baseline.captured_at_ts
                degraded = True
                break
        return SubjectSurvival(
            subject_id=subject_id,
            baseline_ts=baseline.captured_at_ts,
            baseline_metric=baseline.primary_metric,
            sample_count=len(states),
            lifetime_s=lifetime,
            degraded=degraded,
            tolerance=tol,
        )

    async def distribution(self,
                           subject_ids: List[str],
                           tolerance: Optional[float] = None,
                           horizon_s: Optional[int] = None,
                           ) -> SurvivalDistribution:
        tol = self._default_tolerance if tolerance is None else float(tolerance)
        h = self._default_horizon_s if horizon_s is None else int(horizon_s)
        rows: List[SubjectSurvival] = []
        for sid in subject_ids:
            r = await self.for_subject(sid, tolerance=tol, horizon_s=h)
            if r is not None:
                rows.append(r)
        lifetimes = [r.lifetime_s for r in rows if r.lifetime_s is not None]
        survived = sum(1 for r in rows if r.lifetime_s is None)
        survived_pct = (survived / len(rows)) if rows else 0.0
        return SurvivalDistribution(
            sample_size=len(rows),
            median_lifetime_s=statistics.median(lifetimes) if lifetimes else None,
            p25_lifetime_s=_percentile(lifetimes, 0.25),
            p75_lifetime_s=_percentile(lifetimes, 0.75),
            survived_pct=round(survived_pct, 4),
            tolerance=tol,
            horizon_s=h,
            subjects=rows,
        )
