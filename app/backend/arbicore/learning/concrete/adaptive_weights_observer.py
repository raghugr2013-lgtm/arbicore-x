"""Wave 4 · Adaptive Weights Observer — OBSERVE-mode recommendation engine.

Implements ``AdaptiveWeightProvider`` in read-only mode:
    * ``get_weights()`` returns the currently-published *recommended*
      weights.  It does **not** feed the live scoring engine.
    * ``update_weights()`` is a no-op (OBSERVE mandate).
    * ``compute_recommendation()`` is the pure aggregation function —
      given a list of signal-metric rows, returns a full recommendation
      snapshot (recommended weight + baseline + delta + confidence +
      expected-score-impact + evidence per signal).

The math mirrors the canonical ``MongoBackedAdaptiveWeights`` +
``adaptive_weight`` primitive from
`arbicore/learning/concrete/adaptive_weights.py` verbatim so a future
Wave-5 flip from OBSERVE → APPLY is a config change, not a rewrite.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from ..weights import AdaptiveWeightProvider


def adaptive_weight(win_rate: float, sample_count: int, *,
                    prior_trials: int = 20,
                    neutral_weight: float = 1.0,
                    min_weight: float = 0.1,
                    max_weight: float = 2.0,
                    max_delta_scale: float = 4.0) -> float:
    """Bayesian-shrinkage weight — canonical algorithm.

    * ``n == 0`` → returns ``neutral_weight`` (reversibility invariant).
    * ``win_rate == 0.5`` → returns ``neutral_weight`` (no information).
    * Clamped to ``[min_weight, max_weight]``.
    """
    n = max(0, int(sample_count))
    if n <= 0:
        return float(neutral_weight)
    shrinkage = n / (n + max(1, int(prior_trials)))
    raw = math.tanh((float(win_rate) - 0.5) * float(max_delta_scale) * shrinkage)
    weight = float(neutral_weight) + raw
    return max(float(min_weight), min(float(max_weight), weight))


def confidence_score(sample_count: int, prior_trials: int = 20) -> float:
    """Confidence in [0, 1] as the Bayesian shrinkage factor.

    Same semantic used inside :func:`adaptive_weight` — but exposed as a
    scalar so operators can filter recommendations by confidence.  With
    ``n == 0`` returns ``0.0`` (no data).  Asymptotic to 1.0 as ``n``
    grows.
    """
    n = max(0, int(sample_count))
    if n <= 0:
        return 0.0
    return n / (n + max(1, int(prior_trials)))


def _expected_score_impact(recommended: float, baseline: float,
                           sample_count: int, win_rate: float) -> float:
    """Heuristic expected impact of the delta on a normalised score.

    Bounded to [-1, 1].  It is *not* a live-scoring input — it is only a
    directional operator hint on the recommendation card.  Formula:

        impact = tanh( (win_rate - 0.5) * (recommended - baseline)
                       * sqrt(min(sample_count, 100)) / 10 )

    Positive → recommending "trust this signal more, expect a lift".
    Negative → recommending "trust this signal less, expect a drag".
    Zero when the delta is zero, when win_rate is 0.5, or when n == 0.
    """
    if sample_count <= 0:
        return 0.0
    scale = math.sqrt(min(int(sample_count), 100)) / 10.0
    return math.tanh((float(win_rate) - 0.5) * (float(recommended) - float(baseline)) * scale)


class AdaptiveWeightsObserver(AdaptiveWeightProvider):
    """OBSERVE-mode adaptive weights provider — recommendations only.

    Live scoring MUST continue to use the static baseline; this class
    stores the latest recommendation snapshot in memory so operators
    can inspect it via the REST surface but never consumes it in the
    hot path.
    """

    def __init__(self, config):
        self._cfg = config
        self._snapshot: Dict[str, Any] = self._empty_snapshot()

    # --------- helpers ---------

    def _empty_snapshot(self) -> Dict[str, Any]:
        return {
            "mode": self._cfg.mode,
            "provider_version": self._cfg.provider_version,
            "n_signals": 0,
            "recommendations": [],
            "aggregate_confidence": 0.0,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": "awaiting sufficient real observations",
        }

    def snapshot(self) -> Dict[str, Any]:
        """Current in-memory recommendation snapshot."""
        return dict(self._snapshot)

    def load_snapshot(self, snapshot: Optional[Dict[str, Any]]) -> None:
        """Restore an in-memory snapshot from a persisted row."""
        if not snapshot:
            self._snapshot = self._empty_snapshot()
            return
        # Keep only recommendation-relevant fields; strip Mongo metadata.
        self._snapshot = {
            "mode": snapshot.get("mode", self._cfg.mode),
            "provider_version": snapshot.get("provider_version", self._cfg.provider_version),
            "n_signals": int(snapshot.get("n_signals", 0)),
            "recommendations": list(snapshot.get("recommendations", [])),
            "aggregate_confidence": float(snapshot.get("aggregate_confidence", 0.0)),
            "generated_at": snapshot.get("generated_at",
                                        datetime.now(timezone.utc).isoformat()),
            "note": snapshot.get("note", ""),
        }

    # --------- pure recommendation ---------

    def compute_recommendation(self, metrics_rows: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate signal-metric rows into a recommendation snapshot.

        ``metrics_rows`` — each row is a dict with keys
        ``signal_id``, ``win_rate``, ``sample_count`` (extra keys ignored).
        Multiple rows per ``signal_id`` are aggregated by weighted mean.
        """
        cfg = self._cfg
        per_signal: Dict[str, Dict[str, float]] = {}
        source_count = 0
        latest_aggregated_at: Optional[str] = None
        for r in metrics_rows or []:
            sig = r.get("signal_id")
            if not sig:
                continue
            n = int(r.get("sample_count", 0) or 0)
            if n <= 0:
                continue
            wr = float(r.get("win_rate", 0.5) or 0.5)
            entry = per_signal.setdefault(sig, {"weighted_wins": 0.0, "samples": 0})
            entry["weighted_wins"] += wr * n
            entry["samples"] += n
            source_count += 1
            agg_at = r.get("aggregated_at")
            if agg_at and (latest_aggregated_at is None or agg_at > latest_aggregated_at):
                latest_aggregated_at = agg_at

        recommendations: List[Dict[str, Any]] = []
        for sig, agg in per_signal.items():
            n = int(agg["samples"])
            wr = (agg["weighted_wins"] / n) if n > 0 else 0.5
            if n < cfg.min_samples_for_recommendation:
                # Not enough data — identity baseline entry, confidence 0.
                recommendations.append({
                    "signal_id": sig,
                    "baseline_weight": cfg.neutral_weight,
                    "recommended_weight": cfg.neutral_weight,
                    "delta": 0.0,
                    "delta_pct": 0.0,
                    "confidence": 0.0,
                    "expected_score_impact": 0.0,
                    "evidence": {
                        "sample_count": n,
                        "win_rate": round(wr, 4),
                        "insufficient_samples": True,
                        "min_samples_required": cfg.min_samples_for_recommendation,
                        "aggregated_at": latest_aggregated_at,
                        "source_metrics_count": source_count,
                    },
                    "note": "awaiting sufficient real observations",
                })
                continue
            rec = adaptive_weight(
                wr, n,
                prior_trials=cfg.prior_trials,
                neutral_weight=cfg.neutral_weight,
                min_weight=cfg.min_weight,
                max_weight=cfg.max_weight,
                max_delta_scale=cfg.max_delta_scale,
            )
            conf = confidence_score(n, prior_trials=cfg.prior_trials)
            delta = rec - cfg.neutral_weight
            delta_pct = (delta / cfg.neutral_weight) * 100.0 if cfg.neutral_weight else 0.0
            impact = _expected_score_impact(rec, cfg.neutral_weight, n, wr)
            recommendations.append({
                "signal_id": sig,
                "baseline_weight": round(cfg.neutral_weight, 4),
                "recommended_weight": round(rec, 4),
                "delta": round(delta, 4),
                "delta_pct": round(delta_pct, 2),
                "confidence": round(conf, 4),
                "expected_score_impact": round(impact, 4),
                "evidence": {
                    "sample_count": n,
                    "win_rate": round(wr, 4),
                    "aggregated_at": latest_aggregated_at,
                    "source_metrics_count": source_count,
                },
            })

        # Sort by absolute delta descending — largest recommendations first.
        recommendations.sort(key=lambda r: abs(r["delta"]), reverse=True)

        aggregate_confidence = (
            sum(r["confidence"] for r in recommendations) / len(recommendations)
            if recommendations else 0.0
        )

        return {
            "mode": cfg.mode,
            "provider_version": cfg.provider_version,
            "n_signals": len(recommendations),
            "recommendations": recommendations,
            "aggregate_confidence": round(aggregate_confidence, 4),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "note": (
                "insufficient real observations"
                if aggregate_confidence == 0.0
                else "recommendations available for operator review"
            ),
        }

    # --------- AdaptiveWeightProvider ABC ---------

    def get_weights(self, context: Dict) -> Dict[str, float]:
        """Snapshot of the *recommended* weights, keyed by signal_id.

        Never consumed by the scoring engine while ``mode == 'OBSERVE'``.
        """
        return {
            r["signal_id"]: float(r.get("recommended_weight", self._cfg.neutral_weight))
            for r in self._snapshot.get("recommendations", [])
        }

    def update_weights(self, feedback: Dict) -> None:
        # Wave 4 is OBSERVE-only.  Explicitly a no-op.
        return None
