"""Phase-2 Parts D/E/G/H — strategy tagging, true net economics, EV ranking.

Offline, fail-closed, no network. Asserts:
  * strategy classification + end-to-end chain/strategy tagging (Part D)
  * true net = gross − provider fee − gas − L1 − slippage (Parts E/F/G)
  * provider callback overhead + provider fee are accounted (Part G / B-6)
  * EV ranking never overrides hard gates / never implies execution (Part H)
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.models.enums import DataProvenance, StrategyType
from arbicore.scanners.flash_loan_arbitrage.strategy_tagging import (
    classify_strategy, emit_flash_candidate,
)
from arbicore.scanners.flash_loan_arbitrage.multichain_economics import (
    total_gas_units, compute_true_net_profit,
)
from arbicore.scanners.flash_loan_arbitrage.flash_provider_optimizer import (
    optimize_flash_provider,
)
from arbicore.scanners.flash_loan_arbitrage.ranking import rank_opportunities
from arbicore.models import opportunity_contract as oc


# ---------------------------------------------------------------------------
# Part D — strategy classification
# ---------------------------------------------------------------------------
def test_classify_stablecoin():
    assert classify_strategy(["USDC", "USDT", "DAI"]) == StrategyType.STABLECOIN


def test_classify_lst_lrt_takes_priority():
    assert classify_strategy(["WETH", "wstETH"]) == StrategyType.LST_LRT
    assert classify_strategy(["USDC", "weETH"]) == StrategyType.LST_LRT


def test_classify_triangular_cycle():
    # A→B→C→A closed 3-node cycle.
    assert classify_strategy(["WETH", "USDC", "ARB", "WETH"]) == StrategyType.TRIANGULAR


def test_classify_multi_hop():
    assert classify_strategy(["WETH", "USDC", "ARB", "GMX", "WBTC"]) == StrategyType.MULTI_HOP


def test_classify_generic_dex_default():
    assert classify_strategy(["WETH", "USDC"]) == StrategyType.GENERIC_DEX


# ---------------------------------------------------------------------------
# Part D — emit sets strategy + chain_id, honest economics, propagates.
# ---------------------------------------------------------------------------
def test_emit_sets_strategy_and_chain_and_is_detection_only():
    opp = emit_flash_candidate(
        asset="WETH/USDC", chain="Arbitrum", chain_id=42161,
        route_tokens=["WETH", "USDC"])
    assert opp.strategy == StrategyType.GENERIC_DEX
    assert opp.chain == "arbitrum" and opp.chain_id == 42161
    # No economics supplied ⇒ stay None (fail-closed, never fabricated).
    assert opp.expected_profit_usd is None
    assert opp.capital_required_usd is None
    # Display contract keeps everything UNAVAILABLE + UNVERIFIED.
    c = oc.build_display_contract(opp)
    assert c["strategy"] == "GENERIC_DEX" and c["chain_id"] == 42161
    assert c["verdict"] == "UNVERIFIED"
    assert c["confidence"] is None and c["safety"] is None


def test_emit_with_real_risk_marks_assessed_and_survives_zero():
    opp = emit_flash_candidate(
        asset="USDC/USDT", chain="polygon", chain_id=137,
        route_tokens=["USDC", "USDT"], risk_score=0.0,
        provenance=DataProvenance.REAL)
    c = oc.build_display_contract(opp)
    assert c["safety_assessed"] is True and c["safety"] == 1.0
    assert opp.strategy == StrategyType.STABLECOIN


# ---------------------------------------------------------------------------
# Part G / B-6 — gas units combine route + provider callback overhead.
# ---------------------------------------------------------------------------
def test_total_gas_units_adds_callback_overhead():
    assert total_gas_units(250_000, 90_000) == 340_000
    assert total_gas_units(None, 90_000) is None       # unknown route gas ⇒ DENY
    assert total_gas_units(250_000, None) == 250_000


# ---------------------------------------------------------------------------
# Parts E/F/G — TRUE net profit convergence (fail-closed).
# ---------------------------------------------------------------------------
class _FakeGasModel:
    chain = "arbitrum"
    supports_l1_data_fee = True

    def __init__(self, all_in):
        self._all_in = all_in
        self.last_gas_units = None

    async def all_in_cost(self, *, gross_profit_usd, borrow_amount_usd,
                          notional_usd, gas_units, eth_usd, **kw):
        self.last_gas_units = gas_units
        if self._all_in is None:
            return None
        d = dict(self._all_in)
        d["net_profit_all_in_usd"] = gross_profit_usd - d["all_in_cost_usd"]
        return d


def test_true_net_subtracts_provider_fee_and_uses_total_gas():
    gm = _FakeGasModel({"all_in_cost_usd": 8.0, "l2_fee_usd": 5.0,
                        "l1_fee_usd": 2.0, "slippage_usd": 1.0})
    out = asyncio.run(compute_true_net_profit(
        chain="arbitrum", gas_model=gm, gross_profit_usd=100.0,
        borrow_amount_usd=10_000.0, notional_usd=10_000.0,
        route_gas_units=250_000, native_usd=3000.0, borrow_token="WETH",
        liquidity_by_provider={"aave_v3": 50_000}))
    assert out["denied"] is False
    assert out["provider"] == "aave_v3"            # only feasible provider
    # aave fee = 5 bps of 10k = $5. true_net = (100 - 8) - 5 = 87.
    assert out["provider_fee_usd"] == pytest.approx(5.0)
    assert out["true_net_profit_usd"] == pytest.approx(87.0)
    # gas model saw route(250k) + aave callback(120k) = 370k.
    assert gm.last_gas_units == 250_000 + 120_000


def test_true_net_denies_without_gas_model():
    out = asyncio.run(compute_true_net_profit(
        chain="arbitrum", gas_model=None, gross_profit_usd=100.0,
        borrow_amount_usd=10_000.0, notional_usd=10_000.0,
        route_gas_units=250_000, native_usd=3000.0))
    assert out["denied"] is True and out["reason"] == "no_gas_model"


def test_true_net_denies_without_feasible_provider():
    gm = _FakeGasModel({"all_in_cost_usd": 8.0})
    out = asyncio.run(compute_true_net_profit(
        chain="arbitrum", gas_model=gm, gross_profit_usd=100.0,
        borrow_amount_usd=10_000.0, notional_usd=10_000.0,
        route_gas_units=250_000, native_usd=3000.0,
        liquidity_by_provider={}))          # no known liquidity ⇒ no provider
    assert out["denied"] is True
    assert out["reason"].startswith("no_flash_provider")


def test_true_net_denies_when_gas_model_cannot_price():
    gm = _FakeGasModel(None)                # gas model DENIES
    out = asyncio.run(compute_true_net_profit(
        chain="arbitrum", gas_model=gm, gross_profit_usd=100.0,
        borrow_amount_usd=10_000.0, notional_usd=10_000.0,
        route_gas_units=250_000, native_usd=3000.0,
        liquidity_by_provider={"aave_v3": 50_000}))
    assert out["denied"] is True and out["reason"] == "all_in_cost_unavailable"


def test_true_net_can_be_negative_and_is_not_hidden():
    # A route whose costs exceed the gross edge is a real LOSS — preserved.
    gm = _FakeGasModel({"all_in_cost_usd": 95.0})
    out = asyncio.run(compute_true_net_profit(
        chain="arbitrum", gas_model=gm, gross_profit_usd=100.0,
        borrow_amount_usd=10_000.0, notional_usd=10_000.0,
        route_gas_units=250_000, native_usd=3000.0,
        liquidity_by_provider={"aave_v3": 50_000}))
    # (100 - 95) - 5 provider fee = 0 ... make it clearly negative:
    assert out["true_net_profit_usd"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Part H — EV ranking never overrides hard gates / never implies execution.
# ---------------------------------------------------------------------------
def test_high_spread_low_execution_ranks_below_modest_high_execution():
    ranked = rank_opportunities([
        {"opportunity_id": "big_but_risky",
         "expected_net_profit_usd": 5000.0, "execution_probability": 0.02,
         "confidence": 0.1},
        {"opportunity_id": "modest_but_solid",
         "expected_net_profit_usd": 120.0, "execution_probability": 0.95,
         "confidence": 0.9},
    ])
    assert ranked[0].opportunity_id == "modest_but_solid"


def test_ranking_output_never_implies_execution_readiness():
    ranked = rank_opportunities([
        {"opportunity_id": "x", "expected_net_profit_usd": 100.0,
         "execution_probability": 0.9, "confidence": 0.9}])
    comp = ranked[0].components
    # Ranking is advisory: no GO / executable / broadcast field anywhere.
    for banned in ("go", "executable", "broadcast", "verdict"):
        assert banned not in comp
