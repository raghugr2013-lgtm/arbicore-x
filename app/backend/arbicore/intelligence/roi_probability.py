"""ROIProbabilityEngine — historically-grounded probabilistic ROI ranges.

UNIVERSAL substrate module (D-4 first consumer). REUSE WITH REFINEMENT of
`archive/backend/investor/roi.py`. Refinements:
  - Relocated from `investor/` to `arbicore/intelligence/` because the
    engine is opportunity-type-agnostic — D-4 is its first consumer but
    D-5 / D-6 will reuse it unchanged.
  - Decoupled from legacy ``self.repo`` (took signals + outcomes via
    ``repo.list_signals`` and ``repo.find_signal_outcomes``). The engine
    now takes outcomes as a method parameter; the caller (future D-4.5
    LaunchArbitrageScanner / Phase C OutcomeTracker) is responsible for
    fetching them.
  - Returns a typed ``ROIProbability`` dataclass — stable shape.
  - Provenance-aware: callers MUST mark outcomes ``synthetic=True`` or
    ``synthetic=False``; the engine selects real-first, falls back to
    synthetic with ``data_basis="synthetic_only"`` and a degraded
    confidence label.

Discipline:
  - INV-1 — returns intelligence ONLY (never DiscoveryCandidate / Canonical).
  - INV-2 — no EmissionBus references.
  - Pure compute; no I/O.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional


MIN_SAMPLE: int = 6
WINSORIZE_PCT: float = 0.05


@dataclass
class ROIProbability:
    """Evidence-only ROI distribution payload."""

    sample_size: int
    n_basis: int
    data_basis: str                       # 'real' | 'synthetic_only' | 'insufficient'
    base_low: Optional[float]             # 25th percentile
    base_high: Optional[float]            # 75th percentile
    breakout_high: Optional[float]        # 90th percentile
    downside: Optional[float]             # 10th percentile
    median_roi: Optional[float]
    breakout_probability: Optional[float]  # share with roi >= +100%
    drawdown_probability: Optional[float]  # share with survival != "alive"
    confidence_label: str                 # 'insufficient' | 'low' | 'moderate' | 'high'
    categories_used: List[str] = field(default_factory=list)
    horizon_hours: int = 24
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sample_size": self.sample_size,
            "n_basis": self.n_basis,
            "data_basis": self.data_basis,
            "base_low": self.base_low,
            "base_high": self.base_high,
            "breakout_high": self.breakout_high,
            "downside": self.downside,
            "median_roi": self.median_roi,
            "breakout_probability": self.breakout_probability,
            "drawdown_probability": self.drawdown_probability,
            "confidence_label": self.confidence_label,
            "categories_used": list(self.categories_used),
            "horizon_hours": self.horizon_hours,
            "reason": self.reason,
        }


class ROIProbabilityEngine:
    """Stateless distribution estimator over an evaluated-outcomes corpus."""

    def __init__(self, *,
                 min_sample: int = MIN_SAMPLE,
                 winsorize_pct: float = WINSORIZE_PCT,
                 horizon_hours: int = 24,
                 ) -> None:
        self.min_sample = min_sample
        self.winsorize_pct = winsorize_pct
        self.horizon_hours = horizon_hours

    def estimate(self,
                  categories: List[str],
                  real_outcomes: Iterable[Dict[str, Any]],
                  synthetic_outcomes: Optional[Iterable[Dict[str, Any]]] = None,
                  ) -> ROIProbability:
        """``categories`` is the list of signal categories whose outcomes
        we're projecting. ``real_outcomes`` is the preferred corpus;
        ``synthetic_outcomes`` is the fallback only used when real
        sample size < min_sample."""
        if not categories:
            return _neutral("no signals fired on this token yet",
                             horizon=self.horizon_hours)

        real = list(real_outcomes or [])
        if len(real) >= self.min_sample:
            rows = real
            data_basis = "real"
        else:
            syn = list(synthetic_outcomes or [])
            if len(syn) < self.min_sample:
                return _neutral(
                    f"insufficient outcome history (n={len(real)}); "
                    f"need ≥{self.min_sample} evaluated outcomes",
                    horizon=self.horizon_hours,
                )
            rows = syn
            data_basis = "synthetic_only"

        rois = [
            float(r["roi_pct"]) for r in rows
            if isinstance(r.get("roi_pct"), (int, float))
        ]
        if not rois:
            return _neutral("no ROI samples in matching outcomes",
                             horizon=self.horizon_hours)

        rois_w = _winsorize(rois, self.winsorize_pct)
        n = len(rois_w)

        survivals = [r.get("survival") for r in rows]
        drawdown_prob = (sum(1 for s in survivals if s != "alive")
                          / max(1, len(survivals)))
        breakout_prob = sum(1 for r in rois_w if r >= 100.0) / max(1, n)

        median = float(statistics.median(rois_w))
        base_low = round(_pct(rois_w, 0.25), 1)
        base_high = round(_pct(rois_w, 0.75), 1)
        breakout_high = round(_pct(rois_w, 0.90), 1)
        downside = round(_pct(rois_w, 0.10), 1)

        if n >= 60 and abs(base_high - base_low) < 80:
            label = "high"
        elif n >= 25:
            label = "moderate"
        else:
            label = "low"

        return ROIProbability(
            sample_size=n,
            n_basis=len(categories),
            data_basis=data_basis,
            base_low=base_low,
            base_high=base_high,
            breakout_high=breakout_high,
            downside=downside,
            median_roi=round(median, 2),
            breakout_probability=round(breakout_prob, 3),
            drawdown_probability=round(drawdown_prob, 3),
            confidence_label=label,
            categories_used=list(categories),
            horizon_hours=self.horizon_hours,
        )


# ============================================================================
# helpers
# ============================================================================

def _winsorize(xs: List[float], pct: float) -> List[float]:
    if not xs:
        return xs
    s = sorted(xs)
    n = len(s)
    k = max(1, int(n * pct))
    if 2 * k >= n:
        return s
    lo = s[k]
    hi = s[-(k + 1)]
    return [min(max(x, lo), hi) for x in xs]


def _pct(xs: List[float], p: float) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    if f == c:
        return float(s[f])
    return float(s[f] + (s[c] - s[f]) * (k - f))


def _neutral(reason: str, *, horizon: int = 24) -> ROIProbability:
    return ROIProbability(
        sample_size=0,
        n_basis=0,
        data_basis="insufficient",
        base_low=None,
        base_high=None,
        breakout_high=None,
        downside=None,
        median_roi=None,
        breakout_probability=None,
        drawdown_probability=None,
        confidence_label="insufficient",
        categories_used=[],
        horizon_hours=horizon,
        reason=reason,
    )
