"""Regression tests for the Frontend Data-Truth audit fixes (Phase 2).

Covers P0-1 (safety), P0-2 (USD-vs-% return units + no fabricated band) and
P0-3 (verdict is economic/safety-authoritative, never lifecycle-only), plus
the P1 zero-coercion → UNAVAILABLE (None) rules. Pure, offline, no Mongo/RPC.
"""
import importlib

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.enums import (
    DataProvenance, OpportunityStatus, OpportunityType,
)

server = importlib.import_module("server")
to_contract = server._canonical_opp_to_contract
to_discovery = server._canonical_opp_to_discovery
econ_state = server._opp_economic_state


def _opp(**kw):
    base = dict(
        opportunity_type=OpportunityType.DEX_ARBITRAGE,
        asset="WETH/USDC",
        chain="base",
    )
    base.update(kw)
    return CanonicalOpportunity(**base)


# --------------------------------------------------------------------------
# P0-1 · Safety must never fake 100% from a missing/default risk assessment.
# --------------------------------------------------------------------------
def test_p0_1_unassessed_risk_is_unavailable_not_100pct():
    o = _opp(risk_score=0.0, source_data_quality=DataProvenance.SIMULATED)
    c = to_contract(o)
    assert c["safety"] is None, "unassessed risk must be None (UNAVAILABLE), not 1.0"
    assert c["safety_assessed"] is False


def test_p0_1_real_provenance_allows_genuine_zero_risk():
    # A genuine, REAL-provenance zero risk stays a real safety=1.0 (confirmed).
    o = _opp(risk_score=0.0, source_data_quality=DataProvenance.REAL)
    c = to_contract(o)
    assert c["safety_assessed"] is True
    assert c["safety"] == 1.0


def test_p0_1_real_risk_score_maps_to_safety():
    o = _opp(risk_score=40.0, source_data_quality=DataProvenance.REAL)
    c = to_contract(o)
    assert c["safety"] == round(1.0 - 0.4, 4)
    assert c["safety_assessed"] is True


# --------------------------------------------------------------------------
# P0-2 · Return units: USD stays USD; % is a real fraction; no ±10% band.
# --------------------------------------------------------------------------
def test_p0_2_no_return_band_fields():
    o = _opp(expected_profit_usd=1000.0, capital_required_usd=20000.0)
    c = to_contract(o)
    assert "return_low" not in c and "return_high" not in c
    assert c["expected_profit_usd"] == 1000.0  # USD stays USD


def test_p0_2_extreme_profit_is_not_a_percentage():
    # $1,000 profit must NOT become a 90,000% return anywhere.
    o = _opp(expected_profit_usd=1000.0, capital_required_usd=20000.0,
             source_data_quality=DataProvenance.REAL)
    c = to_contract(o)
    # return_pct is a genuine fraction profit/capital = 0.05 (=5%), never 900.
    assert c["return_pct"] == 0.05
    assert c["expected_profit_usd"] == 1000.0


def test_p0_2_return_pct_none_without_capital():
    o = _opp(expected_profit_usd=1000.0, capital_required_usd=None)
    c = to_contract(o)
    assert c["return_pct"] is None  # cannot compute a % without capital
    assert c["expected_profit_usd"] == 1000.0


def test_p0_2_missing_economics_stay_none():
    o = _opp()  # nothing priced
    c = to_contract(o)
    assert c["spread_bps"] is None
    assert c["capital_required_usd"] is None
    assert c["expected_profit_usd"] is None
    assert c["return_pct"] is None
    assert c["depth_usd"] is None  # real TVL not available on canonical rows


# --------------------------------------------------------------------------
# P0-3 · Verdict must reflect economic/safety validation, not lifecycle.
# --------------------------------------------------------------------------
def test_p0_3_validated_but_unpriced_is_not_go():
    o = _opp(status=OpportunityStatus.VALIDATED,
             source_data_quality=DataProvenance.SIMULATED)
    c = to_contract(o)
    assert c["verdict"] == "UNVERIFIED"
    assert c["verdict"] != "GO"


def test_p0_3_approved_but_unpriced_is_not_go():
    o = _opp(status=OpportunityStatus.APPROVED,
             source_data_quality=DataProvenance.SIMULATED)
    c = to_contract(o)
    assert c["verdict"] != "GO"


def test_p0_3_go_requires_approved_and_economically_valid():
    o = _opp(status=OpportunityStatus.APPROVED,
             source_data_quality=DataProvenance.REAL,
             spread_pct=0.5, expected_profit_usd=120.0,
             capital_required_usd=10000.0)
    assert econ_state(o) == "ECONOMICALLY_VALID"
    c = to_contract(o)
    assert c["verdict"] == "GO"


def test_p0_3_economically_valid_but_not_approved_is_soft_no():
    o = _opp(status=OpportunityStatus.VALIDATED,
             source_data_quality=DataProvenance.REAL,
             spread_pct=0.5, expected_profit_usd=120.0,
             capital_required_usd=10000.0)
    c = to_contract(o)
    assert c["verdict"] == "SOFT_NO"


def test_p0_3_rejected_is_hard_no():
    o = _opp(status=OpportunityStatus.REJECTED, rejection_reason="x")
    c = to_contract(o)
    assert c["verdict"] == "HARD_NO"


# --------------------------------------------------------------------------
# P1 · confidence/score/spread coercion + economic_state ladder.
# --------------------------------------------------------------------------
def test_p1_confidence_unavailable_when_unassessed():
    o = _opp(confidence_score=0.0, source_data_quality=DataProvenance.SIMULATED)
    c = to_contract(o)
    assert c["confidence"] is None
    assert c["confidence_assessed"] is False


def test_p1_confidence_present_when_scored():
    o = _opp(confidence_score=72.0)  # 0-100 scale tolerated
    c = to_contract(o)
    assert c["confidence"] == 0.72
    assert c["confidence_assessed"] is True


def test_p1_spread_percent_to_bps_and_none():
    assert to_contract(_opp(spread_pct=0.5))["spread_bps"] == 50
    assert to_contract(_opp(spread_pct=None))["spread_bps"] is None


def test_p1_economic_state_ladder():
    assert econ_state(_opp()) == "DISCOVERED"
    assert econ_state(_opp(spread_pct=0.3)) == "LIVE_QUOTED"
    assert econ_state(_opp(spread_pct=0.3,
                           source_data_quality=DataProvenance.REAL)) == "VERIFIED"
    assert econ_state(_opp(spread_pct=0.3, expected_profit_usd=50.0,
                           source_data_quality=DataProvenance.REAL)) == "ECONOMICALLY_VALID"


def test_p1_discovery_score_unavailable_when_unassessed():
    o = _opp(confidence_score=0.0, source_data_quality=DataProvenance.SIMULATED)
    d = to_discovery(o)
    assert d["score"] is None
    assert d["score_assessed"] is False


def test_p1_provenance_surfaced_in_contract():
    o = _opp(source_data_quality=DataProvenance.VERIFIED_REAL)
    assert to_contract(o)["source_data_quality"] == "VERIFIED_REAL"
