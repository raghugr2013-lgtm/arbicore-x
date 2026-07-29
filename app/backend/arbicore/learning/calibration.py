"""ArbiCore X — Confidence Calibration contract (Phase 3 prep, interface only)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, Sequence, Tuple


class ConfidenceCalibrator(ABC):
    """Maps a raw confidence score to an empirically calibrated probability.

    Phase 1 confidence == persistence rate (uncalibrated). A future
    implementation will fit calibration on REAL outcomes. Not implemented yet.
    """

    @abstractmethod
    def calibrate(self, raw_confidence: float, context: Dict) -> float:
        """Return calibrated confidence in [0, 100]."""

    @abstractmethod
    def fit(self, samples: Sequence[Tuple[float, bool]]) -> None:
        """Fit calibration from (raw_confidence, succeeded) pairs (REAL only)."""
