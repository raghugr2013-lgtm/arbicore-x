"""ArbiCore X — Learning domain models (Phase C Wave 1).

Category-agnostic. Each model references only the foundation schema:
``CanonicalOpportunity``, ``OpportunityType``, ``DataProvenance``, ``subject_id``.
No exchange / asset / network strings appear here.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class OpportunityOutcome:
    """One *evaluated* outcome row — the gold output of Wave 1."""
    opportunity_id: str
    subject_id: Optional[str]
    opportunity_type: str               # OpportunityType.value
    horizon_label: str                  # "5m", "15m", "1h", "6h", "24h"
    horizon_s: int
    emission_ts: float
    evaluated_at_ts: float
    realized_metric: Optional[float]
    realized_metric_delta: Optional[float]   # relative to emission-time state
    succeeded: bool
    provenance: str                     # DataProvenance.value at emission
    route_key: Optional[str] = None     # "buy_venue->sell_venue" if both present
    note: Optional[str] = None
    extras: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RoutePerformance:
    """Aggregated per-(buy_venue, sell_venue) realized stats — used by
    ``RouteSuccessTracker``. Not coupled to any specific category."""
    route_key: str                      # canonical "{buy}->{sell}"
    trials: int = 0
    wins: int = 0
    realized_outcome_sum: float = 0.0   # may be negative
    realized_outcome_mean: float = 0.0
    win_rate: float = 0.0
    last_outcome_at: float = 0.0
    updated_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
