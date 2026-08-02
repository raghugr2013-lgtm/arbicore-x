"""ArbiCore X — Heuristic Regime Classifier (Phase C Wave 3).

Category-agnostic regime classifier. Reads recent OpportunityState snapshots
across the universe (or a single subject), computes:

  - volatility       = stddev(primary_metric) / |mean(primary_metric)|
  - trend            = (last − first) / |first|
  - liquidity_proxy  = mean of any "depth*"-named secondary_metric, if present

…and turns those statistics into a dominant ``MarketRegime`` enum plus a
multi-label list of context tags (Adjustment B1b). The output is a
``RegimeSnapshot`` written to ``arbicore_regime_snapshots`` (TTL 90d).

The model is deliberately simple and reversible. Thresholds are constants —
tuning them changes regime decisions only, not the platform contract.
"""
from __future__ import annotations

import statistics
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from ...data.outcome_repo import OutcomeRepository, StateRow
from ...data.regime_snapshot_repo import RegimeSnapshot, RegimeSnapshotRepository
from ...models.enums import MarketRegime


# Volatility thresholds — fraction of mean (coefficient of variation).
LOW_VOL = 0.005    # 0.5 %
HIGH_VOL = 0.02    # 2 %
# Trend magnitude thresholds.
TREND_FLAT = 0.005
TREND_STRONG = 0.03
# Liquidity (depth proxy) thresholds — operator-tunable.
DEEP_LIQ = 5000.0
THIN_LIQ = 500.0


@dataclass
class RegimeStats:
    n: int
    volatility: float
    trend: float
    liquidity_proxy: Optional[float]

    def to_dict(self) -> Dict[str, object]:
        return {"n": self.n, "volatility": self.volatility,
                "trend": self.trend, "liquidity_proxy": self.liquidity_proxy}


def _compute_stats(states: List[StateRow]) -> Optional[RegimeStats]:
    if len(states) < 2:
        return None
    metrics = [float(s.primary_metric) for s in states
               if s.primary_metric is not None]
    if len(metrics) < 2:
        return None
    mean = statistics.mean(metrics)
    stdev = statistics.pstdev(metrics)
    volatility = (stdev / abs(mean)) if mean != 0 else stdev
    trend = ((metrics[-1] - metrics[0]) / abs(metrics[0])) if metrics[0] != 0 else 0.0
    depth_values: List[float] = []
    for s in states:
        for k, v in (s.secondary_metrics or {}).items():
            if "depth" in k.lower():
                try:
                    depth_values.append(float(v))
                except (TypeError, ValueError):
                    continue
    liquidity_proxy = (statistics.mean(depth_values)
                       if depth_values else None)
    return RegimeStats(
        n=len(metrics), volatility=volatility, trend=trend,
        liquidity_proxy=liquidity_proxy,
    )


def _classify(stats: RegimeStats) -> Tuple[MarketRegime, List[str]]:
    tags: List[str] = []

    # Volatility tags
    if stats.volatility >= HIGH_VOL:
        tags.append("high_volatility")
    elif stats.volatility <= LOW_VOL:
        tags.append("low_volatility")

    # Trend tags
    if stats.trend >= TREND_STRONG:
        tags.append("uptrend")
    elif stats.trend <= -TREND_STRONG:
        tags.append("downtrend")
    elif abs(stats.trend) < TREND_FLAT:
        tags.append("flat")

    # Liquidity tags (only if observed)
    if stats.liquidity_proxy is not None:
        if stats.liquidity_proxy >= DEEP_LIQ:
            tags.append("deep_liquidity")
        elif stats.liquidity_proxy <= THIN_LIQ:
            tags.append("thin_liquidity")

    # Dominant regime
    if "thin_liquidity" in tags:
        return MarketRegime.ILLIQUID, tags
    if "high_volatility" in tags:
        return MarketRegime.VOLATILE, tags
    if "uptrend" in tags or "downtrend" in tags:
        return MarketRegime.TRENDING, tags
    if "low_volatility" in tags or "flat" in tags:
        return MarketRegime.CALM, tags
    return MarketRegime.UNKNOWN, tags


class HeuristicRegimeClassifier:
    """Computes a RegimeSnapshot from recent state snapshots.

    The classifier never reads/writes anything category-specific. Inputs come
    from the foundation ``OutcomeRepository.list_states`` (universal); outputs
    go to ``RegimeSnapshotRepository`` (universal).
    """

    def __init__(self,
                 outcome_repo: OutcomeRepository,
                 regime_repo: RegimeSnapshotRepository,
                 window_s: int = 30 * 60,        # 30-minute rolling window
                 min_samples: int = 3,
                 ):
        self._outcomes = outcome_repo
        self._regimes = regime_repo
        self._window_s = int(window_s)
        self._min_samples = int(min_samples)

    async def classify_for_subject(self, subject_id: str,
                                   now_ts: Optional[float] = None
                                   ) -> Optional[RegimeSnapshot]:
        if now_ts is None:
            now_ts = time.time()
        states = await self._outcomes.list_states(
            subject_id, t0=now_ts - self._window_s, t1=now_ts, limit=2000,
        )
        if len(states) < self._min_samples:
            return None
        stats = _compute_stats(states)
        if stats is None:
            return None
        regime, tags = _classify(stats)
        snap = RegimeSnapshot(
            captured_at=now_ts,
            dominant_regime=regime.value,
            tags=tags,
            confidence=min(1.0, stats.n / 30.0),   # confidence climbs with sample size
            source=f"heuristic:subject:{subject_id}",
            extras=stats.to_dict(),
        )
        await self._regimes.append(snap)
        return snap

    async def classify_universe(self,
                                subject_ids: List[str],
                                now_ts: Optional[float] = None,
                                ) -> Optional[RegimeSnapshot]:
        """Cross-subject classification — useful when many subjects are live."""
        if now_ts is None:
            now_ts = time.time()
        all_states: List[StateRow] = []
        for sid in subject_ids:
            all_states.extend(await self._outcomes.list_states(
                sid, t0=now_ts - self._window_s, t1=now_ts, limit=500,
            ))
        all_states.sort(key=lambda s: s.captured_at_ts)
        if len(all_states) < self._min_samples:
            return None
        stats = _compute_stats(all_states)
        if stats is None:
            return None
        regime, tags = _classify(stats)
        snap = RegimeSnapshot(
            captured_at=now_ts,
            dominant_regime=regime.value,
            tags=tags,
            confidence=min(1.0, stats.n / 60.0),
            source=f"heuristic:universe:{len(subject_ids)}",
            extras=stats.to_dict(),
        )
        await self._regimes.append(snap)
        return snap
