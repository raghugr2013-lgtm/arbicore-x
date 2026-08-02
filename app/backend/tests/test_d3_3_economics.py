"""Tests for D-3.3 — universal economics substrate (protocol-agnostic).

Verifies the cost vocabulary + aggregator that D-3 DEX, D-5 Cross-Chain, and
D-6 FlashLoan will all share.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from arbicore.models.enums import MevRiskLevel
from arbicore.scanners.economics import (
    DEFAULT_PER_CHAIN_GAS_USD, DEFAULT_MEV_RISK_FACTORS,
    EconomicAssessment, LegCost,
    aggregate_economics, mev_penalty_pct, per_chain_gas_estimate_usd,
)


# ----- LegCost shape -------------------------------------------------------

def test_leg_cost_minimal_construction():
    lc = LegCost(leg_role="buy", venue_id="uniswap_v3:ethereum")
    assert lc.leg_role == "buy"
    assert lc.fee_kind == "swap_fee"  # default tag


# ----- gas estimate --------------------------------------------------------

def test_per_chain_gas_known_chain_returns_default():
    for chain, expected in DEFAULT_PER_CHAIN_GAS_USD.items():
        assert per_chain_gas_estimate_usd(chain) == expected


def test_per_chain_gas_unknown_chain_returns_safe_fallback():
    assert per_chain_gas_estimate_usd("zksync") == 0.5


def test_per_chain_gas_override_wins():
    assert per_chain_gas_estimate_usd("ethereum",
                                      overrides={"ethereum": 12.0}) == 12.0


# ----- MEV penalty ---------------------------------------------------------

def test_mev_penalty_defaults():
    assert mev_penalty_pct(MevRiskLevel.LOW) == 0.0
    assert mev_penalty_pct(MevRiskLevel.MEDIUM) == 0.5
    assert mev_penalty_pct(MevRiskLevel.HIGH) == 1.5


def test_mev_penalty_overrides():
    custom = {"LOW": 0.1, "MEDIUM": 0.7, "HIGH": 2.0}
    assert mev_penalty_pct(MevRiskLevel.HIGH, factors=custom) == 2.0


# ----- aggregator: 2-leg DEX arb -------------------------------------------

def test_aggregate_2leg_dex_arb_happy():
    legs = [
        LegCost(leg_role="buy",  venue_id="u:eth", fee_bps=5,
                slippage_pct=0.05, gas_estimate_usd=4.0),
        LegCost(leg_role="sell", venue_id="p:eth", fee_bps=5,
                slippage_pct=0.04, gas_estimate_usd=4.0),
    ]
    a = aggregate_economics(legs=legs, gross_spread_pct=1.0,
                            notional_usd=1000.0,
                            mev_risk_level=MevRiskLevel.LOW)
    assert isinstance(a, EconomicAssessment)
    assert a.total_slippage_pct == pytest.approx(0.09)
    assert a.total_fee_pct == pytest.approx(0.10)             # (5+5)/100 == 0.10
    assert a.total_gas_usd == pytest.approx(8.0)
    assert a.gas_drag_pct == pytest.approx(0.8)               # 8 USD / 1000 USD * 100
    # gross - slip - fees = 1.0 - 0.09 - 0.10 = 0.81
    assert a.net_spread_after_slip_after_fees_pct == pytest.approx(0.81)
    # net_after_costs = 0.81 - 0.8 = 0.01
    assert a.net_after_costs_pct == pytest.approx(0.01)
    assert a.mev_penalty_pct == 0.0
    assert a.mev_adjusted_net_pct == pytest.approx(0.01)
    assert a.profitable is True
    assert a.expected_profit_usd == pytest.approx(0.10)        # 1000 * 0.0001


def test_aggregate_2leg_unprofitable_when_gas_eats_spread():
    legs = [
        LegCost(leg_role="buy",  venue_id="u:eth", fee_bps=5,
                slippage_pct=0.05, gas_estimate_usd=8.0),
        LegCost(leg_role="sell", venue_id="p:eth", fee_bps=5,
                slippage_pct=0.05, gas_estimate_usd=8.0),
    ]
    a = aggregate_economics(legs=legs, gross_spread_pct=0.5,
                            notional_usd=1000.0)
    # gross 0.5 - slip 0.10 - fee 0.10 - gas (16/1000)=1.60 = -1.30
    assert a.mev_adjusted_net_pct == pytest.approx(-1.3)
    assert a.profitable is False


def test_aggregate_2leg_mev_penalty_applied():
    legs = [LegCost(leg_role="buy", venue_id="u:eth", fee_bps=0,
                    slippage_pct=0.0, gas_estimate_usd=0.0)]
    a = aggregate_economics(legs=legs, gross_spread_pct=1.0,
                            notional_usd=1000.0,
                            mev_risk_level=MevRiskLevel.HIGH)
    assert a.mev_penalty_pct == 1.5
    assert a.mev_adjusted_net_pct == pytest.approx(-0.5)
    assert a.profitable is False


# ----- aggregator: D-5 cross-chain (bridge fee leg) ------------------------

def test_aggregate_cross_chain_with_bridge_fee_leg():
    """Cross-chain economics = 2 swap legs + 1 bridge_fee leg."""
    legs = [
        LegCost(leg_role="bridge_out", venue_id="u:eth", fee_bps=5,
                slippage_pct=0.02, gas_estimate_usd=8.0),
        LegCost(leg_role="bridge_in",  venue_id="u:arb", fee_bps=5,
                slippage_pct=0.02, gas_estimate_usd=0.3),
        LegCost(leg_role="bridge_fee", venue_id="layerzero",
                fee_kind="bridge_fee", extra_cost_usd=2.5),
    ]
    a = aggregate_economics(legs=legs, gross_spread_pct=0.6,
                            notional_usd=1000.0)
    assert a.breakdown["leg_count"] == 3
    assert a.breakdown["leg_fee_kinds"] == [
        "swap_fee", "swap_fee", "bridge_fee",
    ]
    # gas_drag = (8.0 + 0.3 + 2.5) / 1000 * 100 = 1.08
    assert a.gas_drag_pct == pytest.approx(1.08)


# ----- aggregator: D-6 flash-loan N-leg cycle ------------------------------

def test_aggregate_flash_loan_cycle_4_legs_plus_fee():
    """N-leg flash-loan cycle: borrow + hop + hop + repay + flash_loan_fee."""
    legs = [
        LegCost(leg_role="borrow",     venue_id="aave_v3:eth", fee_bps=0,
                slippage_pct=0.0, gas_estimate_usd=2.0),
        LegCost(leg_role="hop",        venue_id="u:eth", fee_bps=5,
                slippage_pct=0.03, gas_estimate_usd=3.0),
        LegCost(leg_role="hop",        venue_id="p:eth", fee_bps=5,
                slippage_pct=0.03, gas_estimate_usd=3.0),
        LegCost(leg_role="repay",      venue_id="aave_v3:eth", fee_bps=0,
                slippage_pct=0.0, gas_estimate_usd=2.0),
        LegCost(leg_role="flash_loan_fee", venue_id="aave_v3:eth",
                fee_kind="flash_loan_fee", extra_cost_usd=1.0),
    ]
    a = aggregate_economics(legs=legs, gross_spread_pct=0.50,
                            notional_usd=10_000.0)
    # gas_total=10 + extra=1 → 11 USD over 10k notional → drag = 0.11pct
    assert a.gas_drag_pct == pytest.approx(0.11)
    # fees = 10bps = 0.10pct; slip = 0.06; gross 0.50 - 0.06 - 0.10 = 0.34
    assert a.net_spread_after_slip_after_fees_pct == pytest.approx(0.34)
    assert a.net_after_costs_pct == pytest.approx(0.23)
    assert a.profitable is True
    assert a.breakdown["leg_count"] == 5


# ----- INV-1 / INV-2 module checks ----------------------------------------

def test_inv1_module_does_not_import_canonical_or_candidate():
    import arbicore.scanners.economics as mod
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in {
            "CanonicalOpportunity", "DiscoveryCandidate",
        }:
            raise AssertionError(
                f"economics module references {node.id} — must stay pure-compute"
            )


def test_inv2_module_does_not_call_emission_bus():
    import arbicore.scanners.economics as mod
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            raise AssertionError("economics module imports EmissionBus")
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            raise AssertionError("economics module uses .emit attribute")
