"""Audit 2026-08 — DEX swap-fee double-count fix (authoritative FlashLoan path).

Proves that when the FlashLoan gross comes from a real fee-inclusive on-chain
quote (gross_is_quote_inclusive=True — the verifier + M3 fresh-revalidation
default), the pool swap fee is NOT financially deducted a second time, while the
ESTIMATED/non-quoted path (=False) still deducts it. Gates, flash-loan premium,
gas, MEV and fail-closed behaviour are all preserved. Pure/offline.

Economics: aggregate_economics => expected_profit = notional * (mev_adj/100),
where mev_adj = gross - slippage - total_fee_pct - gas_drag - mev_penalty, and
total_fee_pct = sum(leg.fee_bps)/100 over ALL legs (hops + flash premium).
"""
from __future__ import annotations

from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.enums import MevRiskLevel
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FlashLoanEconomicsAssessor,
)

BORROW = 10_000.0


def _assessor():
    return FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=2),
        default_borrow_amount_usd=BORROW,
    )


def _one_hop(fee_bps=30):
    # slippage_pct omitted → 0.0 (live quote already contains price impact)
    return [{"venue_id": "uni:weth-usdc", "fee_bps": fee_bps}]


# ---- A. LIVE / FEE-INCLUSIVE QUOTE: no second swap-fee deduction ----
def test_A_quote_inclusive_does_not_deduct_swap_fee_again():
    a = _assessor()
    common = dict(provider="balancer_v2", chain="base", borrow_token="USDC",
                  borrow_amount_usd=BORROW, hop_legs=_one_hop(30),
                  signal_categories=[], real_outcomes=[], gross_profit_pct=0.5,
                  mev_risk_level=MevRiskLevel.LOW, gas_cost_usd_override=0.0)
    inclusive = a.assess(**common, gross_is_quote_inclusive=True)
    estimated = a.assess(**common, gross_is_quote_inclusive=False)

    # Swap fee (30 bps on $10k = $30) is deducted ONCE only in estimated mode.
    assert inclusive.economics.total_fee_pct == 0.0
    assert estimated.economics.total_fee_pct == 0.3
    delta = round(inclusive.atomic_profit_usd - estimated.atomic_profit_usd, 6)
    assert delta == 30.0  # exactly the previously double-counted swap fee
    # Telemetry still reports the OBSERVED pool fee even when not deducted.
    assert inclusive.total_swap_fee_pct == 0.3


def test_A_multi_hop_double_count_removed_scales_with_hops():
    a = _assessor()
    common = dict(provider="balancer_v2", chain="base", borrow_token="USDC",
                  borrow_amount_usd=BORROW,
                  hop_legs=[{"venue_id": "h0", "fee_bps": 30},
                            {"venue_id": "h1", "fee_bps": 30}],
                  signal_categories=[], real_outcomes=[], gross_profit_pct=1.0,
                  mev_risk_level=MevRiskLevel.LOW, gas_cost_usd_override=0.0)
    inclusive = a.assess(**common, gross_is_quote_inclusive=True)
    estimated = a.assess(**common, gross_is_quote_inclusive=False)
    assert inclusive.economics.total_fee_pct == 0.0
    assert estimated.economics.total_fee_pct == 0.6  # 2 × 30 bps
    assert round(inclusive.atomic_profit_usd - estimated.atomic_profit_usd, 6) == 60.0


# ---- B. ESTIMATED PATH still deducts (accounting not globally disabled) ----
def test_B_estimated_path_still_deducts_swap_fee():
    a = _assessor()
    out = a.assess(provider="balancer_v2", chain="base", borrow_token="USDC",
                   borrow_amount_usd=BORROW, hop_legs=_one_hop(30),
                   signal_categories=[], real_outcomes=[], gross_profit_pct=0.5,
                   mev_risk_level=MevRiskLevel.LOW, gas_cost_usd_override=0.0,
                   gross_is_quote_inclusive=False)
    assert out.economics.total_fee_pct == 0.3  # fee accounting intact


# ---- C. FLASH-LOAN PREMIUM remains deducted (even in quote-inclusive mode) ----
def test_C_flash_loan_premium_still_deducted():
    a = _assessor()
    common = dict(chain="base", borrow_token="USDC", borrow_amount_usd=BORROW,
                  hop_legs=_one_hop(30), signal_categories=[], real_outcomes=[],
                  gross_profit_pct=0.5, mev_risk_level=MevRiskLevel.LOW,
                  gas_cost_usd_override=0.0, gross_is_quote_inclusive=True)
    balancer = a.assess(provider="balancer_v2", **common)   # 0 bps premium
    aave = a.assess(provider="aave_v3", **common)           # 5 bps premium
    assert balancer.flash_loan_fee_usd == 0.0
    assert aave.flash_loan_fee_usd == 5.0
    # premium leg IS still financially deducted (aave lower by exactly $5).
    assert round(balancer.atomic_profit_usd - aave.atomic_profit_usd, 6) == 5.0


# ---- D. GAS accounting unchanged ----
def test_D_gas_accounting_unchanged():
    a = _assessor()
    common = dict(provider="balancer_v2", chain="base", borrow_token="USDC",
                  borrow_amount_usd=BORROW, hop_legs=_one_hop(30),
                  signal_categories=[], real_outcomes=[], gross_profit_pct=0.5,
                  mev_risk_level=MevRiskLevel.LOW, gross_is_quote_inclusive=True)
    no_gas = a.assess(**common, gas_cost_usd_override=0.0)
    with_gas = a.assess(**common, gas_cost_usd_override=20.0)
    # $20 gas on $10k notional ⇒ 0.2% drag ⇒ $20 less profit.
    assert round(no_gas.atomic_profit_usd - with_gas.atomic_profit_usd, 6) == 20.0
    assert with_gas.gas_cost_usd == 20.0


# ---- E. MEV adjustment unchanged ----
def test_E_mev_adjustment_unchanged():
    a = _assessor()
    common = dict(provider="balancer_v2", chain="base", borrow_token="USDC",
                  borrow_amount_usd=BORROW, hop_legs=_one_hop(30),
                  signal_categories=[], real_outcomes=[], gross_profit_pct=1.0,
                  gas_cost_usd_override=0.0, gross_is_quote_inclusive=True)
    low = a.assess(**common, mev_risk_level=MevRiskLevel.LOW)
    high = a.assess(**common, mev_risk_level=MevRiskLevel.HIGH)
    # Higher MEV risk ⇒ larger penalty ⇒ strictly lower atomic profit.
    assert high.atomic_profit_usd < low.atomic_profit_usd


# ---- F. GATE 7 threshold & shared aggregator untouched ----
def test_F_gate7_floor_and_shared_aggregator_untouched():
    # Gate-7 default atomic floor stays $25 (code-level), not weakened.
    import inspect
    import arbicore.scanners.flash_loan_arbitrage.filter as fmod
    src = inspect.getsource(fmod)
    assert "min_atomic_profit_usd" in src and "25.0" in src
    # shared aggregate_economics still sums ALL leg fee_bps (unchanged contract):
    from arbicore.scanners.economics import aggregate_economics, LegCost
    econ = aggregate_economics(
        legs=[LegCost(leg_role="h0", venue_id="v", fee_bps=30, fee_kind="swap_fee")],
        gross_spread_pct=1.0, notional_usd=BORROW, mev_risk_level=MevRiskLevel.LOW)
    assert econ.total_fee_pct == 0.3  # shared aggregator NOT modified


# ---- G. Fail-closed defaults preserved ----
def test_G_zero_gross_is_not_profitable():
    a = _assessor()
    out = a.assess(provider="balancer_v2", chain="base", borrow_token="USDC",
                   borrow_amount_usd=BORROW, hop_legs=_one_hop(30),
                   signal_categories=[], real_outcomes=[], gross_profit_pct=0.0,
                   mev_risk_level=MevRiskLevel.LOW, gas_cost_usd_override=0.0,
                   gross_is_quote_inclusive=True)
    # No fabricated profit: zero quoted gross ⇒ not profitable (≤0), below $25 gate.
    assert out.atomic_profit_usd <= 0.0
    assert out.economics.profitable is False
