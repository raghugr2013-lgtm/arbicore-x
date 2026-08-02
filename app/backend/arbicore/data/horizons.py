"""ArbiCore X — Checkpoint horizons helper (Phase B, Adjustment A4).

Single source of truth for the time-horizons used by:
  - OutcomeRepository.list_due()
  - MetricsRepository aggregations
  - SequenceMiner sliding windows (Phase C)

Changing these values changes the cadence of the learning loop. Make the
edit deliberate — and document the change in CHANGELOG.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

# Default checkpoint horizons (seconds since opportunity emission).
# Tuned for the BDAG reference dataset but valid as a baseline for any
# category. Per-category overrides may land in Phase C if friction emerges
# (Decision C2).
DEFAULT_HORIZONS_S: List[int] = [
    5 * 60,           # 5 minutes
    15 * 60,          # 15 minutes
    60 * 60,          # 1 hour
    6 * 60 * 60,      # 6 hours
    24 * 60 * 60,     # 24 hours
]


@dataclass(frozen=True)
class HorizonSpec:
    label: str
    seconds: int


def default_horizon_specs() -> List[HorizonSpec]:
    return [
        HorizonSpec("5m",  5 * 60),
        HorizonSpec("15m", 15 * 60),
        HorizonSpec("1h",  60 * 60),
        HorizonSpec("6h",  6 * 60 * 60),
        HorizonSpec("24h", 24 * 60 * 60),
    ]


def due_at_for(emission_ts: float, horizon_s: int) -> float:
    """When an outcome row scheduled at ``emission_ts`` for ``horizon_s``
    becomes evaluable."""
    return float(emission_ts) + float(horizon_s)
