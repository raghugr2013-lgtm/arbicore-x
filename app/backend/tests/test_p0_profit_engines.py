"""P0-7/8/9 — Confidence v2, adaptive size optimizer, expected-value engine."""
from arbicore.economics.expected_value import (
    estimate_success_probability, compute_expected_value, evaluate_expected_value,
)
from arbicore.economics.size_optimizer import optimize_size, DEFAULT_SIZE_GRID_USD
from arbicore.intelligence.confidence_v2 import (
    compute_confidence, confidence_from_signals, FACTOR_WEIGHTS,
)


# ---------------------------------------------------------------- EV engine
def test_ev_formula_positive_and_negative():
    r = compute_expected_value(net_profit_usd=100.0, maximum_loss_usd=20.0,
                               success_probability=0.9)
    # 0.9*100 - 0.1*20 = 88
    assert abs(r.expected_value_usd - 88.0) < 1e-6
    assert r.failure_probability == 0.1
    r2 = compute_expected_value(net_profit_usd=5.0, maximum_loss_usd=200.0,
                                success_probability=0.5)
    assert r2.expected_value_usd < 0  # low prob, big downside → negative EV


def test_missing_evidence_penalises_probability():
    full = estimate_success_probability(
        simulation_passed=True, quote_age_sec=1, liquidity_ratio=0.01,
        gas_certainty=0.95, mev_risk=0.1, historical_success_rate=0.9)
    sparse = estimate_success_probability(simulation_passed=True)
    assert full["uncertainty_penalty"] == 0.0
    assert sparse["uncertainty_penalty"] > 0.0
    assert sparse["probability"] < full["probability"]


def test_failed_simulation_caps_probability():
    est = estimate_success_probability(
        simulation_passed=False, quote_age_sec=0, liquidity_ratio=0.001,
        gas_certainty=1.0, mev_risk=0.0, historical_success_rate=1.0)
    assert est["probability"] <= 0.10


def test_evaluate_ev_end_to_end():
    r = evaluate_expected_value(
        net_profit_usd=50.0, maximum_loss_usd=10.0,
        simulation_passed=True, quote_age_sec=2, liquidity_ratio=0.02,
        gas_certainty=0.9, mev_risk=0.15, historical_success_rate=0.85)
    assert 0.0 < r.success_probability <= 1.0
    assert "signals" in r.evidence


# ------------------------------------------------------- size optimizer
def _base_opt(**kw):
    params = dict(gross_spread_bps=30.0, pool_liquidity_usd=2_000_000.0,
                  gas_cost_usd=3.0, flash_loan_fee_bps=0.0,
                  buy_venue_fee_bps=5.0, sell_venue_fee_bps=5.0,
                  native_price_usd=3000.0,
                  prob_kwargs=dict(simulation_passed=True, quote_age_sec=1,
                                   gas_certainty=0.95, mev_risk=0.1,
                                   historical_success_rate=0.9))
    params.update(kw)
    return optimize_size(**params)


def test_optimizer_picks_max_ev_not_max_size():
    out = _base_opt()
    assert out["chosen"] is not None
    chosen = out["chosen"]
    # The largest grid size should NOT automatically be chosen (slippage eats it).
    assert chosen["notional_usd"] < max(DEFAULT_SIZE_GRID_USD)
    # chosen must be the max-EV feasible candidate
    feas = [c for c in out["candidates"] if c["feasible"]]
    assert chosen["expected_value_usd"] == max(c["expected_value_usd"] for c in feas)


def test_optimizer_respects_slippage_cap():
    out = _base_opt(max_slippage_bps=5.0, pool_liquidity_usd=50_000.0)
    for c in out["candidates"]:
        if c["slippage_bps"] > 5.0:
            assert c["feasible"] is False


def test_optimizer_rejects_when_unprofitable():
    out = _base_opt(gross_spread_bps=1.0, gas_cost_usd=500.0)
    assert out["chosen"] is None
    assert all(c["feasible"] is False for c in out["candidates"])


def test_optimizer_adaptive_refinement_adds_points():
    out = _base_opt()
    notionals = [c["notional_usd"] for c in out["candidates"]]
    # refinement should add at least one non-grid point
    assert any(n not in DEFAULT_SIZE_GRID_USD for n in notionals)


# ------------------------------------------------------- confidence v2
def test_confidence_weights_sum_to_one():
    assert abs(sum(FACTOR_WEIGHTS.values()) - 1.0) < 1e-9


def test_confidence_explainable_components():
    r = confidence_from_signals(
        quote_age_sec=1, liquidity_ratio=0.02, route_stability=0.95,
        price_discrepancy_bps=40, slippage_bps=20, max_slippage_bps=150,
        gas_certainty=0.97, flash_available=True, simulation_passed=True,
        venue_reliability=0.9, historical_success=0.88, mev_risk=0.15,
        net_profit_bps=25)
    assert 0 <= r.score <= 100
    assert r.score > 60
    assert "simulation_result" in r.components
    assert r.components["simulation_result"] == 100.0


def test_confidence_partial_reports_missing():
    r = confidence_from_signals(simulation_passed=True, quote_age_sec=1)
    assert len(r.missing_factors) > 0
    assert 0 <= r.score <= 100


def test_low_quality_signals_low_confidence():
    good = confidence_from_signals(
        quote_age_sec=0, liquidity_ratio=0.001, simulation_passed=True,
        slippage_bps=1, gas_certainty=1.0, mev_risk=0.0)
    bad = confidence_from_signals(
        quote_age_sec=30, liquidity_ratio=0.5, simulation_passed=False,
        slippage_bps=140, gas_certainty=0.1, mev_risk=0.9)
    assert good.score > bad.score
