"""ArbiCore X — Confidence Calibration contract.

Copied verbatim (semantically) from
`arbicore-x-v1.0.2.bundle::app/backend/arbicore/learning/calibration.py`
so the preview pod compiles against the same ABC signature the canonical
codebase already commits to.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Sequence, Tuple


class ConfidenceCalibrator(ABC):
    """Maps a raw confidence score to an empirically calibrated probability.

    Contract:
      * ``calibrate(raw, ctx)`` — return calibrated confidence in [0, 100].
      * ``fit(samples)`` — fit calibration from (raw_confidence, succeeded)
        pairs.  ``raw_confidence`` is in [0, 100]; ``succeeded`` is bool.
    """

    @abstractmethod
    def calibrate(self, raw_confidence: float, context: Dict) -> float:
        """Return calibrated confidence in [0, 100]."""

    @abstractmethod
    def fit(self, samples: Sequence[Tuple[float, bool]]) -> None:
        """Fit calibration from (raw_confidence, succeeded) pairs."""
