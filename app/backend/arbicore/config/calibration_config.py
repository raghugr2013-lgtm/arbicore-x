"""Configuration for the Wave-3 Confidence Calibration pipeline.

All values are configuration-driven per the Wave-3 constraints — no
hard-coded window / cadence / thresholds inside the algorithm modules.
Every value can be overridden via environment variable so operators can
tune the pipeline without a redeploy.
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
class CalibrationConfig:
    # --- Rolling window ---
    window_days: int = 30
    # --- Cadence ---
    tick_interval_s: int = 3600
    # Backoff progression on tick failure (seconds).
    backoff_ladder_s: tuple = (60, 120, 300, 600)
    # --- Sample thresholds (algorithm ladder) ---
    min_samples_isotonic: int = 200
    min_samples_platt: int = 30
    # --- Bucketing for reliability diagram ---
    n_buckets: int = 10
    # --- Validation ---
    # A newly fitted candidate is only promoted if its ECE does not
    # exceed the current active ECE by more than `promotion_ece_slack`.
    promotion_ece_slack: float = 0.02
    # --- Drift detection ---
    drift_history_len: int = 30
    drift_ece_absolute_floor: float = 0.05
    drift_stdev_mult_on: float = 2.0
    drift_stdev_mult_off: float = 1.0
    drift_off_consecutive_ticks: int = 3
    # --- Retention ---
    retired_ttl_days: int = 30
    # --- Semantic ---
    calibrator_version: str = "isotonic@1"

    @classmethod
    def from_env(cls) -> "CalibrationConfig":
        return cls(
            window_days=_int("CALIBRATION_WINDOW_DAYS", 30),
            tick_interval_s=_int("CALIBRATION_TICK_INTERVAL_S", 3600),
            min_samples_isotonic=_int("CALIBRATION_MIN_SAMPLES_ISOTONIC", 200),
            min_samples_platt=_int("CALIBRATION_MIN_SAMPLES_PLATT", 30),
            n_buckets=_int("CALIBRATION_N_BUCKETS", 10),
            promotion_ece_slack=_float("CALIBRATION_PROMOTION_ECE_SLACK", 0.02),
            drift_history_len=_int("CALIBRATION_DRIFT_HISTORY_LEN", 30),
            drift_ece_absolute_floor=_float("CALIBRATION_DRIFT_ECE_FLOOR", 0.05),
            drift_stdev_mult_on=_float("CALIBRATION_DRIFT_STDEV_ON", 2.0),
            drift_stdev_mult_off=_float("CALIBRATION_DRIFT_STDEV_OFF", 1.0),
            drift_off_consecutive_ticks=_int("CALIBRATION_DRIFT_OFF_TICKS", 3),
            retired_ttl_days=_int("CALIBRATION_RETIRED_TTL_DAYS", 30),
            calibrator_version=os.environ.get("CALIBRATOR_VERSION", "isotonic@1"),
        )
