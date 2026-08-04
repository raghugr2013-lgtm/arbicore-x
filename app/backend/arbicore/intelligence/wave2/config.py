"""Phase 2 — Lifetime tracker configuration.

All thresholds are env-driven so operators can retune the platform's
opportunity-lifetime semantics without a code deploy. Defaults follow
the values the user approved for v2.2.0:

  * ACTIVE_SECONDS       = 60           (observed within the last minute)
  * STALE_SECONDS        = 24 * 3600    (one day)
  * EXPIRED_SECONDS      = 7 * 24 * 3600 (one week — hard drop from ACTIVE cohort)
  * TREND_RING_BUFFER    = 100
  * REDISCOVERY_GAP_SEC  = 60           (rediscovery = gap > 60s)
  * RECURRENCE_GAP_SEC   = 5 * 60       (recurrence  = gap > 5m)
  * SWEEPER_INTERVAL_SEC = 60

Env-var names use the `ARBICORE_LIFETIME_*` prefix — consistent with the
rest of the platform.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def _get_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    try:
        return int(v)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    try:
        return float(v)
    except ValueError:
        return default


@dataclass(frozen=True)
class LifetimeConfig:
    active_seconds: float = 60.0
    stale_seconds: float = 24 * 3600.0
    expired_seconds: float = 7 * 24 * 3600.0
    trend_ring_buffer: int = 100
    rediscovery_gap_seconds: float = 60.0
    recurrence_gap_seconds: float = 5 * 60.0
    sweeper_interval_seconds: float = 60.0

    def status_for_age(self, seconds_since_last_seen: float) -> str:
        """Compute the current derived status from an inactivity duration."""
        if seconds_since_last_seen <= self.active_seconds:
            return "ACTIVE"
        if seconds_since_last_seen <= self.stale_seconds:
            return "STALE"
        return "EXPIRED"


def load_config_from_env() -> LifetimeConfig:
    return LifetimeConfig(
        active_seconds=_get_float("ARBICORE_LIFETIME_ACTIVE_SECONDS", 60.0),
        stale_seconds=_get_float("ARBICORE_LIFETIME_STALE_SECONDS",
                                 24 * 3600.0),
        expired_seconds=_get_float("ARBICORE_LIFETIME_EXPIRED_SECONDS",
                                   7 * 24 * 3600.0),
        trend_ring_buffer=_get_int("ARBICORE_LIFETIME_TREND_BUFFER", 100),
        rediscovery_gap_seconds=_get_float(
            "ARBICORE_LIFETIME_REDISCOVERY_GAP_SECONDS", 60.0),
        recurrence_gap_seconds=_get_float(
            "ARBICORE_LIFETIME_RECURRENCE_GAP_SECONDS", 5 * 60.0),
        sweeper_interval_seconds=_get_float(
            "ARBICORE_LIFETIME_SWEEPER_INTERVAL_SECONDS", 60.0),
    )
