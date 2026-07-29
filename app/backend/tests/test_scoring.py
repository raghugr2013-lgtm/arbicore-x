"""Tests for the chain scoring engine (parity with ArbitrageX formula)."""
from arbicore.intelligence import ChainProfile, ScoringEngine

POLYGON = ChainProfile("polygon", min_spread_percent=0.6, gas_score=1,
                       mev_risk_score=1.5, min_chain_score=8)


def test_spread_score_capped_at_10():
    e = ScoringEngine()
    assert e.spread_score(100, POLYGON) == 10.0


def test_persistence_score_steps():
    e = ScoringEngine()
    assert e.persistence_score(5) == 1.0
    assert e.persistence_score(20) == 4.0
    assert e.persistence_score(45) == 7.0
    assert e.persistence_score(90) == 10.0


def test_liquidity_score_ratio_and_cap():
    e = ScoringEngine()
    # required = 10000 * 2 = 20000; available 40000 -> 2.0
    assert e.liquidity_score(40_000, 20_000) == 2.0
    # capped at 10
    assert e.liquidity_score(10_000_000, 20_000) == 10.0


def test_chain_score_formula_matches_reference():
    e = ScoringEngine()
    b = e.score(spread_percent=1.2, duration_seconds=45,
                available_liquidity=1_000_000, trade_amount=10_000, profile=POLYGON)
    # spread = min(1.2/0.6*5,10)=10 ; persistence(45)=7 ; liq=min(1e6/2e4,10)=10
    # score = (10*7*10)/(1*1.5) = 466.67
    assert b.spread_score == 10.0
    assert b.persistence_score == 7.0
    assert b.liquidity_score == 10.0
    assert b.chain_score == round(700 / 1.5, 2)
    assert b.meets_threshold is True


def test_zero_min_spread_safe():
    e = ScoringEngine()
    p = ChainProfile("x", min_spread_percent=0, gas_score=1, mev_risk_score=1, min_chain_score=1)
    assert e.spread_score(5, p) == 0.0
