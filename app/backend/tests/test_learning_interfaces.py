"""Tests for Phase 3 learning interfaces (contracts only).

Verifies the ABCs cannot be instantiated and that the REAL-only learning gate
behaves correctly via a minimal concrete stub.
"""
import pytest

from arbicore.learning import (
    AdaptiveWeightProvider,
    ConfidenceCalibrator,
    OutcomeTracker,
    RouteSuccessTracker,
    ensure_real,
)
from arbicore.data import ContaminatedDataError
from arbicore.models import CanonicalOpportunity, DataProvenance, OpportunityType


def test_abcs_cannot_be_instantiated():
    for cls in (OutcomeTracker, AdaptiveWeightProvider, ConfidenceCalibrator, RouteSuccessTracker):
        with pytest.raises(TypeError):
            cls()


def _opp(provenance):
    return CanonicalOpportunity(
        opportunity_type=OpportunityType.DEX_ARBITRAGE,
        asset="WETH/USDC", source_data_quality=provenance,
    )


def test_ensure_real_allows_real():
    ensure_real(_opp(DataProvenance.REAL))  # no raise


def test_ensure_real_blocks_non_real():
    for p in (DataProvenance.SIMULATED, DataProvenance.CONTAMINATED, DataProvenance.DEAD):
        with pytest.raises(ContaminatedDataError):
            ensure_real(_opp(p))


def test_partial_implementation_still_abstract():
    class HalfTracker(OutcomeTracker):
        def record_prediction(self, opportunity):
            return None
    with pytest.raises(TypeError):
        HalfTracker()
