"""D-6.1 — FlashLoanEconomicsAssessor + Gates tests."""
from __future__ import annotations

from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.enums import MevRiskLevel
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FLASH_LOAN_PROVIDERS, FlashLoanEconomicsAssessor, provider_fee_bps,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)


# ============================================================================
# Provider catalog
# ============================================================================

def test_provider_catalog_aave_v3():
    assert FLASH_LOAN_PROVIDERS["aave_v3"]["fee_bps_default"] == 5


def test_provider_catalog_balancer_v2_zero_fee():
    assert FLASH_LOAN_PROVIDERS["balancer_v2"]["fee_bps_default"] == 0


def test_provider_fee_bps_default():
    assert provider_fee_bps("aave_v3") == 5
    assert provider_fee_bps("balancer_v2") == 0


def test_provider_fee_bps_override():
    assert provider_fee_bps("uniswap_v3", override_tier_bps=5) == 5
    assert provider_fee_bps("uniswap_v3", override_tier_bps=100) == 100


def test_unknown_provider_conservative_fee():
    assert provider_fee_bps("madeup_provider") == 30


# ============================================================================
# FlashLoanEconomicsAssessor
# ============================================================================

def _assessor():
    return FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=2),
        default_borrow_amount_usd=10_000.0,
    )


def test_assessor_balancer_zero_fee():
    a = _assessor()
    out = a.assess(
        provider="balancer_v2", chain="ethereum",
        borrow_token="USDC", borrow_amount_usd=10_000.0,
        hop_legs=[{"venue_id": "uni:weth-usdc", "fee_bps": 30,
                    "slippage_pct": 0.1}],
        signal_categories=[], real_outcomes=[],
        gross_profit_pct=0.5, mev_risk_level=MevRiskLevel.LOW,
    )
    assert out.flash_loan_fee_usd == 0.0
    assert out.provider == "balancer_v2"
    assert out.borrow_amount_usd == 10_000.0


def test_assessor_aave_v3_fee_applied():
    a = _assessor()
    out = a.assess(
        provider="aave_v3", chain="ethereum",
        borrow_token="USDC", borrow_amount_usd=10_000.0,
        hop_legs=[{"venue_id": "uni:weth-usdc", "fee_bps": 30,
                    "slippage_pct": 0.1}],
        signal_categories=[], real_outcomes=[],
        gross_profit_pct=0.5, mev_risk_level=MevRiskLevel.LOW,
    )
    assert out.flash_loan_fee_usd == 5.0   # 5 bps × 10k


def test_assessor_uniswap_v3_with_tier_override():
    a = _assessor()
    out = a.assess(
        provider="uniswap_v3", chain="ethereum",
        borrow_token="USDC", borrow_amount_usd=10_000.0,
        hop_legs=[{"venue_id": "uni:weth-usdc", "fee_bps": 30,
                    "slippage_pct": 0.1}],
        signal_categories=[], real_outcomes=[],
        gross_profit_pct=0.5,
        flash_loan_fee_bps_override=5,
        mev_risk_level=MevRiskLevel.LOW,
    )
    assert out.flash_loan_fee_usd == 5.0


def test_assessor_to_metadata_keys():
    a = _assessor()
    out = a.assess(
        provider="aave_v3", chain="arbitrum",
        borrow_token="WETH",
        hop_legs=[{"venue_id": "uni:weth-usdc", "fee_bps": 30,
                    "slippage_pct": 0.1}],
        signal_categories=[], real_outcomes=[],
    )
    md = out.to_metadata()
    for k in ("chain", "flash_loan_provider", "flash_loan_borrow_token",
              "flash_loan_borrow_amount_usd", "flash_loan_fee_usd",
              "gas_cost_usd", "atomic_profit_usd",
              "atomic_profit_pct", "hop_count"):
        assert k in md


def test_assessor_tx_gas_units_scales_gas():
    a = _assessor()
    low = a.assess(
        provider="aave_v3", chain="ethereum", borrow_token="USDC",
        hop_legs=[{"venue_id": "x", "fee_bps": 30, "slippage_pct": 0.1}],
        signal_categories=[], real_outcomes=[],
        tx_gas_units=250_000,
    )
    high = a.assess(
        provider="aave_v3", chain="ethereum", borrow_token="USDC",
        hop_legs=[{"venue_id": "x", "fee_bps": 30, "slippage_pct": 0.1}],
        signal_categories=[], real_outcomes=[],
        tx_gas_units=2_000_000,
    )
    assert high.gas_cost_usd > low.gas_cost_usd


def test_inv2_economics_no_emission_bus():
    import arbicore.scanners.flash_loan_arbitrage.economics as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text


# ============================================================================
# Gate 7 — Atomic Profit
# ============================================================================

def test_gate7_pass():
    g = FlashLoanGate7AtomicProfit(thresholds={"min_atomic_profit_usd": 25.0})
    r = g.evaluate(atomic_profit_usd=50.0, borrow_amount_usd=10_000.0)
    assert r.passed


def test_gate7_fail():
    g = FlashLoanGate7AtomicProfit(thresholds={"min_atomic_profit_usd": 25.0})
    r = g.evaluate(atomic_profit_usd=10.0, borrow_amount_usd=10_000.0)
    assert not r.passed
    assert "atomic_profit" in r.reason


def test_gate7_floor_override():
    g = FlashLoanGate7AtomicProfit(thresholds={"min_atomic_profit_usd": 100.0})
    r = g.evaluate(atomic_profit_usd=50.0, borrow_amount_usd=10_000.0)
    assert not r.passed


# ============================================================================
# Gate 8 — Liquidity Depth
# ============================================================================

def test_gate8_pass():
    g = FlashLoanGate8LiquidityDepth(
        thresholds={"min_pool_tvl_usd_in_route": 100_000.0})
    r = g.evaluate(min_pool_tvl_usd_in_route=500_000.0)
    assert r.passed


def test_gate8_fail():
    g = FlashLoanGate8LiquidityDepth(
        thresholds={"min_pool_tvl_usd_in_route": 100_000.0})
    r = g.evaluate(min_pool_tvl_usd_in_route=50_000.0)
    assert not r.passed


# ============================================================================
# Gate 9 — Flash-Loan MEV
# ============================================================================

def test_gate9_pass_low():
    g = FlashLoanGate9FlashLoanMev(
        thresholds={"max_flash_loan_mev_risk_class": "MEDIUM"})
    r = g.evaluate(mev_risk_level=MevRiskLevel.LOW,
                    mev_risk_label="LOW", mev_score=20.0)
    assert r.passed


def test_gate9_fail_high():
    g = FlashLoanGate9FlashLoanMev(
        thresholds={"max_flash_loan_mev_risk_class": "MEDIUM"})
    r = g.evaluate(mev_risk_level=MevRiskLevel.HIGH,
                    mev_risk_label="HIGH", mev_score=85.0)
    assert not r.passed


def test_gate9_cap_override_to_low():
    g = FlashLoanGate9FlashLoanMev(
        thresholds={"max_flash_loan_mev_risk_class": "LOW"})
    r = g.evaluate(mev_risk_level=MevRiskLevel.MEDIUM,
                    mev_risk_label="MEDIUM", mev_score=55.0)
    assert not r.passed


def test_inv2_filter_no_emission_bus():
    import arbicore.scanners.flash_loan_arbitrage.filter as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
