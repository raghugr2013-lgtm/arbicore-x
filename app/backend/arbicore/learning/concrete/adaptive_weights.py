"""ArbiCore X — Adaptive Weights concrete (Phase C Wave 2).

Derives a per-signal weight from accumulated outcomes in
``arbicore_signal_metrics``. The model is intentionally minimal and
reversible:

  - Start every signal at the neutral weight 1.0.
  - When a SignalMetric for the signal exists, shrink its win-rate signal
    by a Bayesian-style sample-size factor so signals with few trials stay
    near the neutral weight.
  - Allowed range: [0.1, 2.0]. Disabling adaptation (e.g. forcing
    sample_count=0 everywhere) yields all 1.0 weights — bit-for-bit
    equivalent to the static-weight baseline.

Category-agnostic. Reads only ``signal_id``, ``win_rate``, ``sample_count``
from ``arbicore_signal_metrics`` — no exchange/asset assumptions.
"""
from __future__ import annotations

import math
import time
from typing import Dict, Optional

from ...data.metrics_repo import MetricsRepository
from ...data.provenance import is_learning_eligible
from ...learning.weights import AdaptiveWeightProvider
from ...models.enums import DataProvenance


PRIOR_TRIALS = 20         # Bayesian shrinkage prior
NEUTRAL_WEIGHT = 1.0
MIN_WEIGHT = 0.1
MAX_WEIGHT = 2.0
MAX_DELTA_SCALE = 4.0     # tanh saturation for (win_rate - 0.5)


def adaptive_weight(win_rate: float, sample_count: int) -> float:
    """Pure function. Returns the adapted weight given a (win_rate, n).

    With n=0 → returns 1.0 (neutral, reversibility invariant P4).
    With win_rate=0.5 → returns 1.0 regardless of n (no information).
    With high n and high win_rate → asymptotic to ~2.0.
    With high n and low win_rate → asymptotic to ~0.1.
    """
    n = max(0, int(sample_count))
    if n <= 0:
        return NEUTRAL_WEIGHT
    shrinkage = n / (n + PRIOR_TRIALS)
    raw = math.tanh((win_rate - 0.5) * MAX_DELTA_SCALE * shrinkage)
    weight = NEUTRAL_WEIGHT + raw
    return max(MIN_WEIGHT, min(MAX_WEIGHT, weight))


class MongoBackedAdaptiveWeights(AdaptiveWeightProvider):
    """Concrete AdaptiveWeightProvider backed by `arbicore_signal_metrics`.

    Caches the latest weight per signal_id in-process. The cache is refreshed
    on a TTL (default 60 s) — readers always observe a recent snapshot
    without hammering Mongo on every confidence calculation.
    """

    def __init__(self, metrics_repo: MetricsRepository, ttl_s: float = 60.0):
        self._metrics = metrics_repo
        self._ttl_s = float(ttl_s)
        self._cache: Dict[str, float] = {}
        self._cache_loaded_at: float = 0.0

    async def _ensure_cache(self) -> None:
        if (time.time() - self._cache_loaded_at) < self._ttl_s and self._cache:
            return
        new_cache: Dict[str, float] = {}
        rows = await self._metrics.list_signal_metrics(limit=500)
        # Aggregate across horizons per signal_id — take the latest by
        # aggregated_at then average if multiple subjects exist.
        per_signal: Dict[str, Dict[str, float]] = {}
        for r in rows:
            entry = per_signal.setdefault(
                r.signal_id, {"weighted_wins": 0.0, "samples": 0}
            )
            entry["weighted_wins"] += r.win_rate * r.sample_count
            entry["samples"] += r.sample_count
        for sig, agg in per_signal.items():
            n = int(agg["samples"])
            wr = (agg["weighted_wins"] / n) if n else 0.5
            new_cache[sig] = adaptive_weight(wr, n)
        self._cache = new_cache
        self._cache_loaded_at = time.time()

    # ABC: synchronous get_weights ----------------------------------------------
    def get_weights(self, context: Dict) -> Dict[str, float]:
        """Synchronous snapshot from the cache. If the cache is empty, returns
        an empty dict — callers should ``await refresh()`` once at startup."""
        return dict(self._cache)

    def get_weight(self, signal_id: str) -> float:
        return self._cache.get(signal_id, NEUTRAL_WEIGHT)

    # ABC: synchronous update_weights -------------------------------------------
    def update_weights(self, feedback: Dict) -> None:
        """The provider does not accept direct feedback — weights are derived
        from MetricsRepository. This method is a no-op kept for ABC
        compatibility. Provenance gate still enforced when called."""
        prov = feedback.get("provenance")
        if isinstance(prov, DataProvenance) and not is_learning_eligible(prov):
            return

    # Async refresh -------------------------------------------------------------
    async def refresh(self) -> Dict[str, float]:
        await self._ensure_cache()
        return dict(self._cache)

    @property
    def cache_age_s(self) -> float:
        if self._cache_loaded_at == 0.0:
            return float("inf")
        return time.time() - self._cache_loaded_at
