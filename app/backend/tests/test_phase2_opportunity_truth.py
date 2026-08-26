"""Phase-2 Part A — end-to-end Opportunity Truth Contract regression tests.

Protects the SHARED data-truth pattern at the single contract boundary
(``arbicore.models.opportunity_contract``). Reproduces the exact validator-UI
symptom combination the newest frontend exposed:

    UNVERIFIED · CONF 0 · SAFE 100 · CAPITAL $0 · PROVENANCE REAL ·
    ENORMOUS ESTIMATED PROFIT

and asserts none of those can occur through the contract. Pure/offline.
"""
import importlib

import pytest

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.enums import (
    DataProvenance, OpportunityStatus, OpportunityType, StrategyType,
)
from arbicore.models import opportunity_contract as oc


def _opp(**kw):
    base = dict(opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
                asset="WETH/USDC", chain="base")
    base.update(kw)
    return CanonicalOpportunity(**base)


# --------------------------------------------------------------------------
# THE headline: the exact bad combination must be impossible.
# --------------------------------------------------------------------------
def test_real_unverified_discovery_row_is_all_unavailable():
    """A REAL-provenance row that was discovered but never assessed / priced
    must NOT show CONF 0 / SAFE 100 / a profit — every authoritative field is
    UNAVAILABLE (None)."""
    o = _opp(source_data_quality=DataProvenance.REAL)  # nothing else assessed
    c = oc.build_display_contract(o)
    assert c["verdict"] == "UNVERIFIED"
    assert c["economic_state"] == "DISCOVERED"
    assert c["confidence"] is None and c["confidence_assessed"] is False
    assert c["safety"] is None and c["safety_assessed"] is False
    assert c["capital_required_usd"] is None
    assert c["expected_profit_usd"] is None
    assert c["return_pct"] is None
    assert c["spread_bps"] is None
    assert c["source_data_quality"] == "REAL"


# --------------------------------------------------------------------------
# Plausibility: absurd values are REJECTED & SURFACED, never clamped/shown.
# --------------------------------------------------------------------------
def test_implausible_return_is_rejected_and_flagged():
    # $50M profit on $1k capital == 50000x return — a unit/mapping bug.
    o = _opp(source_data_quality=DataProvenance.REAL, spread_pct=0.4,
             expected_profit_usd=50_000_000.0, capital_required_usd=1_000.0)
    c = oc.build_display_contract(o)
    assert c["expected_profit_usd"] is None      # not shown as authoritative
    assert c["return_pct"] is None
    assert "implausible_return" in c["data_quality_flags"]


def test_uncontextualized_large_profit_is_rejected_and_flagged():
    # Huge profit with NO capital to validate against → cannot be trusted.
    o = _opp(source_data_quality=DataProvenance.REAL, spread_pct=0.4,
             expected_profit_usd=10_000_000.0, capital_required_usd=None)
    c = oc.build_display_contract(o)
    assert c["expected_profit_usd"] is None
    assert "uncontextualized_large_profit" in c["data_quality_flags"]


def test_negative_capital_is_rejected_and_flagged():
    o = _opp(source_data_quality=DataProvenance.REAL,
             capital_required_usd=-500.0)
    c = oc.build_display_contract(o)
    assert c["capital_required_usd"] is None
    assert "invalid_negative_capital" in c["data_quality_flags"]


def test_plausible_economics_pass_through_untouched():
    o = _opp(source_data_quality=DataProvenance.REAL, spread_pct=0.5,
             expected_profit_usd=120.0, capital_required_usd=10_000.0)
    c = oc.build_display_contract(o)
    assert c["expected_profit_usd"] == 120.0
    assert c["return_pct"] == 0.012
    assert c["data_quality_flags"] == []


# --------------------------------------------------------------------------
# Genuine zero / negative preserved (only) with an explicit assessment marker.
# --------------------------------------------------------------------------
def test_genuine_negative_profit_is_preserved():
    o = _opp(source_data_quality=DataProvenance.REAL, spread_pct=0.1,
             expected_profit_usd=-42.0, capital_required_usd=10_000.0)
    c = oc.build_display_contract(o)
    assert c["expected_profit_usd"] == -42.0
    assert c["return_pct"] == -0.0042


def test_confidence_marker_allows_genuine_zero():
    o = _opp(confidence_score=0.0, source_data_quality=DataProvenance.REAL,
             metadata={"confidence_assessed": True})
    c = oc.build_display_contract(o)
    assert c["confidence_assessed"] is True
    assert c["confidence"] == 0.0


# --------------------------------------------------------------------------
# Strategy + chain dimensions carried end-to-end (Parts B/C propagation).
# --------------------------------------------------------------------------
def test_strategy_and_chain_id_propagate_to_contract():
    o = _opp(chain="arbitrum", chain_id=42161,
             strategy=StrategyType.TRIANGULAR)
    c = oc.build_display_contract(o)
    assert c["chain"] == "arbitrum"
    assert c["chain_id"] == 42161
    assert c["strategy"] == "TRIANGULAR"


def test_discovery_contract_surfaces_strategy_signal():
    o = _opp(chain="optimism", chain_id=10, strategy=StrategyType.STABLECOIN)
    d = oc.build_discovery_contract(o)
    assert "strategy:stablecoin" in d["signals"]
    assert "chain:optimism" in d["signals"]


# --------------------------------------------------------------------------
# Economic-state ladder (Part I semantics) is single-sourced.
# --------------------------------------------------------------------------
def test_economic_state_ladder():
    assert oc.economic_state(_opp()) == "DISCOVERED"
    assert oc.economic_state(_opp(spread_pct=0.3)) == "LIVE_QUOTED"
    assert oc.economic_state(_opp(
        spread_pct=0.3, source_data_quality=DataProvenance.REAL)) == "VERIFIED"
    assert oc.economic_state(_opp(
        spread_pct=0.3, expected_profit_usd=50.0,
        source_data_quality=DataProvenance.REAL)) == "ECONOMICALLY_VALID"


def test_go_requires_approved_and_economically_valid():
    o = _opp(status=OpportunityStatus.APPROVED,
             source_data_quality=DataProvenance.REAL, spread_pct=0.5,
             expected_profit_usd=120.0, capital_required_usd=10_000.0)
    assert oc.build_display_contract(o)["verdict"] == "GO"


def test_validated_unpriced_is_never_go():
    o = _opp(status=OpportunityStatus.VALIDATED,
             source_data_quality=DataProvenance.SIMULATED)
    assert oc.build_display_contract(o)["verdict"] == "UNVERIFIED"


# --------------------------------------------------------------------------
# Server delegates to the single boundary (no drift between endpoints).
# --------------------------------------------------------------------------
def test_server_translators_delegate_to_contract():
    server = importlib.import_module("server")
    o = _opp(source_data_quality=DataProvenance.REAL, spread_pct=0.5,
             expected_profit_usd=120.0, capital_required_usd=10_000.0)
    assert server._canonical_opp_to_contract(o) == oc.build_display_contract(o)
    assert server._canonical_opp_to_discovery(o) == oc.build_discovery_contract(o)
    assert server._opp_economic_state(o) == oc.economic_state(o)
