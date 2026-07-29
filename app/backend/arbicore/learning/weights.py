"""ArbiCore X — Adaptive Weighting contract (Phase 3 prep, interface only)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class AdaptiveWeightProvider(ABC):
    """Supplies scoring weights that the learning loop adjusts over time.

    In Phase 1 the scoring engine uses static ``ScoringWeights``. A future
    implementation will derive weights from realized outcomes (REAL data only)
    and feed them into ``ScoringEngine``. Not implemented in Phase 1.
    """

    @abstractmethod
    def get_weights(self, context: Dict) -> Dict[str, float]:
        """Return current weight set for the given context (e.g. chain, regime)."""

    @abstractmethod
    def update_weights(self, feedback: Dict) -> None:
        """Update weights from outcome feedback. Must consume REAL data only."""
