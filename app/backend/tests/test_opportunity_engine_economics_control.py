"""ArbiCore X — OpportunityEngine economics reconciliation + synthetic control.

Deterministic, offline. Proves (a) fee accounting is exact and not double-counted,
(b) a KNOWN-profitable input set is recognised as profitable, (c) the inverse
KNOWN-unprofitable set is rejected — so we can distinguish "no real opportunity
exists right now" from "the engine cannot recognise an opportunity".

Target: arbicore.economics.net_profit.compute_net_profit — the deterministic
economics core the OpportunityEngine feeds (marginal_spread_bps → gross_spread_bps,
with buy/sell_venue_fee_bps=0 because the live quote round-trip is already net of
DEX fees).
"""
from __future__ import annotations

from arbicore.economics.net_profit import compute_net_profit

# shared realistic Base gas triple: 0.05 gwei, 300k units, $2500 ETH ≈ $0.0375
GAS = dict(gas_native_wei=5 * 10**7, estimated_gas_units=300_000, native_price_usd=2500.0)
GAS_USD = 5 * 10**7 * 300_000 / 1e18 * 2500.0  # 0.0375


def test_reconciliation_components_sum_exactly():
    r = compute_net_profit(
        gross_spread_bps=50.0, notional_usd=100_000.0,
        buy_venue_fee_bps=0.0, sell_venue_fee_bps=0.0,
        slippage_bps=5.0, liquidity_impact_bps=3.0,
        flash_loan_notional_usd=100_000.0, flash_loan_fee_bps=0.0, **GAS)
    # every component reconciles: net == gross − Σcosts
    assert r.gross_profit_usd == 500.0
    assert r.total_cost_usd == round(
        r.trading_fees_usd + r.withdrawal_fees_usd + r.gas_cost_usd
        + r.slippage_cost_usd + r.flash_loan_fee_usd + r.liquidity_impact_usd, 6)
    assert r.net_profit_usd == round(r.gross_profit_usd - r.total_cost_usd, 6)


def test_fee_accounting_quote_inclusive_not_double_counted():
    # OpportunityEngine path: spread already net of DEX fees ⇒ fee_bps=0 ⇒ no fee cost.
    incl = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0,
                              buy_venue_fee_bps=0.0, sell_venue_fee_bps=0.0)
    assert incl.trading_fees_usd == 0.0
    # Estimated path: explicit venue fees ARE charged (accounting not disabled).
    est = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0,
                             buy_venue_fee_bps=30.0, sell_venue_fee_bps=30.0)
    assert est.trading_fees_usd == 600.0  # (60 bps on $100k)
    assert incl.net_profit_usd - est.net_profit_usd == 600.0


def test_flash_fee_charged_once_on_borrowed_notional():
    r = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0,
                           flash_loan_notional_usd=100_000.0, flash_loan_fee_bps=5.0)
    assert r.flash_loan_fee_usd == 50.0  # 5 bps × $100k, once
    zero = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0,
                              flash_loan_notional_usd=100_000.0, flash_loan_fee_bps=0.0)
    assert zero.flash_loan_fee_usd == 0.0  # Balancer V2 = 0 bps


def test_gas_model_separate_and_scaled():
    no_gas = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0)
    with_gas = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0, **GAS)
    assert no_gas.gas_cost_usd == 0.0  # incomplete triple ⇒ 0 (not fabricated)
    assert round(with_gas.gas_cost_usd, 6) == round(GAS_USD, 6)


def test_slippage_and_liquidity_impact_not_double_counted():
    base = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0)
    slip = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0, slippage_bps=5.0)
    liq = compute_net_profit(gross_spread_bps=50.0, notional_usd=100_000.0, liquidity_impact_bps=3.0)
    assert slip.slippage_cost_usd == 50.0 and slip.liquidity_impact_usd == 0.0
    assert liq.liquidity_impact_usd == 30.0 and liq.slippage_cost_usd == 0.0
    # they are independent, additive costs — no shared/duplicated term
    assert base.net_profit_usd - slip.net_profit_usd == 50.0
    assert base.net_profit_usd - liq.net_profit_usd == 30.0


# ---- §13 SYNTHETIC CONTROL ----
def test_synthetic_POSITIVE_control_is_recognised_profitable():
    r = compute_net_profit(
        gross_spread_bps=50.0, notional_usd=100_000.0,       # $500 gross
        buy_venue_fee_bps=0.0, sell_venue_fee_bps=0.0,
        slippage_bps=5.0, liquidity_impact_bps=3.0,          # $50 + $30
        flash_loan_notional_usd=100_000.0, flash_loan_fee_bps=0.0, **GAS)
    expected_net = 500.0 - (50.0 + 30.0 + GAS_USD)
    assert round(r.net_profit_usd, 4) == round(expected_net, 4)
    assert r.net_profit_usd > 0.0
    assert r.is_profitable is True


def test_synthetic_NEGATIVE_control_is_rejected():
    r = compute_net_profit(
        gross_spread_bps=5.0, notional_usd=100_000.0,        # $50 gross
        buy_venue_fee_bps=0.0, sell_venue_fee_bps=0.0,
        slippage_bps=10.0,                                   # $100
        flash_loan_notional_usd=100_000.0, flash_loan_fee_bps=5.0, **GAS)  # $50
    expected_net = 50.0 - (100.0 + 50.0 + GAS_USD)
    assert round(r.net_profit_usd, 4) == round(expected_net, 4)
    assert r.net_profit_usd < 0.0
    assert r.is_profitable is False


def test_larger_notional_does_not_magically_increase_bps_profit():
    # Same bps spread & bps costs ⇒ net_profit_bps invariant to notional (no free lunch).
    small = compute_net_profit(gross_spread_bps=50.0, notional_usd=10_000.0,
                               slippage_bps=5.0, liquidity_impact_bps=3.0)
    large = compute_net_profit(gross_spread_bps=50.0, notional_usd=500_000.0,
                               slippage_bps=5.0, liquidity_impact_bps=3.0)
    assert small.net_profit_bps == large.net_profit_bps  # profitability is scale-free in bps
