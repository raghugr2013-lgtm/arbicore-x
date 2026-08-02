"""ArbiCore X — Adaptive Weighting contract.

Copied verbatim (semantically) from
`arbicore-x-v1.0.2.bundle::app/backend/arbicore/learning/weights.py` so
the preview pod compiles against the same ABC the canonical repo
already commits to.  Wave 4 uses this contract in OBSERVE mode only —
``update_weights`` is a no-op, and ``get_weights`` returns the
currently-persisted recommendation snapshot (never applied to scoring).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict


class AdaptiveWeightProvider(ABC):
    """Supplies scoring weights derived from realised outcomes.

    Wave 4 note — the observer implementation surfaces recommendations
    only.  Live scoring continues to use the static baseline until a
    future wave explicitly flips ``mode="OBSERVE"`` → ``mode="APPLY"``.
    """

    @abstractmethod
    def get_weights(self, context: Dict) -> Dict[str, float]:
        """Return current recommended weight set for the given context."""

    @abstractmethod
    def update_weights(self, feedback: Dict) -> None:
        """Update weights from outcome feedback.  Must consume REAL data only."""
