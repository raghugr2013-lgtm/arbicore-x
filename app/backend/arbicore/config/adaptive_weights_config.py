"""Configuration for the Wave-4 Adaptive Weights (OBSERVE) pipeline.

Every threshold and cadence is configuration-driven via environment
variable per the Wave-4 constraints.  The observer engine + worker
consume ``AdaptiveWeightsConfig`` — nothing in the algorithm modules is
hard-coded.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _int(env: str, default: int) -> int:
    try:
        return int(os.environ.get(env, default))
    except (TypeError, ValueError):
        return default


def _float(env: str, default: float) -> float:
    try:
        return float(os.environ.get(env, default))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class AdaptiveWeightsConfig:
    # --- Mode: OBSERVE (recommend-only) or APPLY (Wave 5+; not yet wired) ---
    mode: str = "OBSERVE"
    # --- Adaptive-weight algorithm (mirrors canonical constants) ---
    prior_trials: int = 20
    neutral_weight: float = 1.0
    min_weight: float = 0.1
    max_weight: float = 2.0
    max_delta_scale: float = 4.0
    # --- Recommendation quality gates ---
    min_samples_for_recommendation: int = 30
    min_confidence_floor: float = 0.10
    # --- Rolling recompute cadence ---
    tick_interval_s: int = 3600
    backoff_ladder_s: tuple = (60, 120, 300, 600)
    # --- Persistence ---
    retired_ttl_days: int = 30
    max_signals_scanned: int = 500
    # --- Semantic ---
    provider_version: str = "adaptive_weights_observer@1"

    @classmethod
    def from_env(cls) -> "AdaptiveWeightsConfig":
        return cls(
            mode=os.environ.get("ADAPTIVE_WEIGHTS_MODE", "OBSERVE"),
            prior_trials=_int("ADAPTIVE_WEIGHTS_PRIOR_TRIALS", 20),
            neutral_weight=_float("ADAPTIVE_WEIGHTS_NEUTRAL", 1.0),
            min_weight=_float("ADAPTIVE_WEIGHTS_MIN", 0.1),
            max_weight=_float("ADAPTIVE_WEIGHTS_MAX", 2.0),
            max_delta_scale=_float("ADAPTIVE_WEIGHTS_MAX_DELTA_SCALE", 4.0),
            min_samples_for_recommendation=_int("ADAPTIVE_WEIGHTS_MIN_SAMPLES", 30),
            min_confidence_floor=_float("ADAPTIVE_WEIGHTS_MIN_CONFIDENCE", 0.10),
            tick_interval_s=_int("ADAPTIVE_WEIGHTS_TICK_INTERVAL_S", 3600),
            retired_ttl_days=_int("ADAPTIVE_WEIGHTS_RETIRED_TTL_DAYS", 30),
            max_signals_scanned=_int("ADAPTIVE_WEIGHTS_MAX_SIGNALS", 500),
            provider_version=os.environ.get(
                "ADAPTIVE_WEIGHTS_PROVIDER_VERSION", "adaptive_weights_observer@1"
            ),
        )
