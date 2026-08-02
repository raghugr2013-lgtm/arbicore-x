"""ArbiCore X — Outcome Tracking contract (Phase 3 prep, interface only)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional

from ..models.canonical import CanonicalOpportunity


@dataclass(frozen=True)
class Prediction:
    opportunity_id: str
    predicted_spread_pct: float
    predicted_profit_usd: float
    predicted_confidence: float
    created_at: str


@dataclass(frozen=True)
class Outcome:
    opportunity_id: str
    realized_spread_pct: float
    realized_profit_usd: float
    succeeded: bool
    observed_at: str


class OutcomeTracker(ABC):
    """Records what was predicted vs what actually happened.

    Implementations MUST call ``learning.base.ensure_real`` before accepting a
    prediction. Not implemented in Phase 1.
    """

    @abstractmethod
    def record_prediction(self, opportunity: CanonicalOpportunity) -> Prediction: ...

    @abstractmethod
    def record_outcome(self, opportunity_id: str, outcome: Outcome) -> None: ...

    @abstractmethod
    def get_prediction(self, opportunity_id: str) -> Optional[Prediction]: ...

    @abstractmethod
    def list_outcomes(self, *, limit: int = 100) -> List[Outcome]: ...
