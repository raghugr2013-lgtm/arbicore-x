"""Tests for the canonical opportunity model and lifecycle."""
import pytest

from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    InvalidTransitionError,
    OpportunityStatus,
    OpportunityType,
)


def _opp(**kw):
    base = dict(opportunity_type=OpportunityType.DEX_ARBITRAGE, asset="WETH/USDC",
               buy_venue="uniswap", sell_venue="sushiswap")
    base.update(kw)
    return CanonicalOpportunity(**base)


def test_defaults_and_identity():
    o = _opp()
    assert o.opportunity_id
    assert o.status == OpportunityStatus.CANDIDATE
    assert o.route == "uniswap->sushiswap"
    assert o.source_data_quality == DataProvenance.SIMULATED


def test_learning_eligibility_flag():
    assert _opp(source_data_quality=DataProvenance.REAL).is_learning_eligible is True
    assert _opp(source_data_quality=DataProvenance.CONTAMINATED).is_learning_eligible is False


def test_valid_lifecycle_transitions():
    o = _opp()
    o.mark_validated()
    assert o.status == OpportunityStatus.VALIDATED
    o.mark_approved()
    assert o.status == OpportunityStatus.APPROVED


def test_rejection_records_reason():
    o = _opp()
    o.mark_rejected("low liquidity")
    assert o.status == OpportunityStatus.REJECTED
    assert o.rejection_reason == "low liquidity"


def test_illegal_transition_raises():
    o = _opp()
    with pytest.raises(InvalidTransitionError):
        o.mark_approved()  # candidate cannot jump to approved


def test_extra_fields_forbidden():
    with pytest.raises(Exception):
        CanonicalOpportunity(opportunity_type=OpportunityType.DEX_ARBITRAGE,
                             asset="X", not_a_field=123)
