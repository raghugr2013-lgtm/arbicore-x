"""Steps 1-3 foundation batch — offline, fail-closed, backward-compatible.

Covers:
  * Step 1: canonical model gains ``strategy`` + ``chain_id`` (additive, no break)
  * Step 2: flash-provider optimizer (multi-provider, actual fee/liquidity, DENY)
  * Step 3: ChainGasModel seam (Base pass-through, non-Base DENY, fail-closed)
No network I/O, no signing, no broadcast.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.models import (
    CanonicalOpportunity, OpportunityType, StrategyType,
)
from arbicore.scanners.flash_loan_arbitrage.flash_provider_optimizer import (
    FLASH_PROVIDER_CONSTRAINTS, optimize_flash_provider,
)
from arbicore.chains.gas_model import (
    BaseGasModel, ChainGasModel, get_chain_gas_model, supported_gas_model_chains,
)


# ---------------------------------------------------------------------------
# Step 1 — canonical model additive dimensions
# ---------------------------------------------------------------------------

def test_canonical_backward_compatible_without_new_fields():
    """Legacy construction (no strategy/chain_id) still works, defaults None."""
    opp = CanonicalOpportunity(opportunity_type=OpportunityType.DEX_ARBITRAGE,
                               asset="WETH/USDC")
    assert opp.strategy is None
    assert opp.chain_id is None
    # Serialization round-trips and contains the additive keys.
    d = opp.model_dump()
    assert d["strategy"] is None and d["chain_id"] is None


def test_canonical_accepts_strategy_and_chain_id():
    opp = CanonicalOpportunity(
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        asset="WETH/USDC", chain="base", chain_id=8453,
        strategy=StrategyType.TRIANGULAR)
    assert opp.strategy is StrategyType.TRIANGULAR
    assert opp.chain_id == 8453
    # Round-trip through dict re-validates.
    again = CanonicalOpportunity(**opp.model_dump())
    assert again.strategy is StrategyType.TRIANGULAR and again.chain_id == 8453


def test_strategy_enum_values():
    vals = {s.value for s in StrategyType}
    assert {"GENERIC_DEX", "TRIANGULAR", "STABLECOIN", "MULTI_HOP",
            "LST_LRT", "LIQUIDATION", "COLLATERAL_DEBT"} == vals


# ---------------------------------------------------------------------------
# Step 2 — flash-provider optimizer
# ---------------------------------------------------------------------------

def test_optimizer_picks_cheapest_feasible_provider():
    # Balancer (0 bps) and Aave (5 bps) both liquid → cheapest = balancer.
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 50_000, "aave_v3": 50_000})
    assert res.feasible is True
    assert res.provider == "balancer_v2"
    assert res.fee_bps == 0
    assert res.fee_usd == 0.0
    assert res.callback_extra_gas_units == FLASH_PROVIDER_CONSTRAINTS[
        "balancer_v2"]["callback_extra_gas_units"]


def test_optimizer_unknown_liquidity_is_denied_not_assumed():
    # Only balancer has KNOWN liquidity; aave/morpho/uniswap unreadable → refused.
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 20_000})
    assert res.feasible is True and res.provider == "balancer_v2"
    reasons = {c["provider"]: c["reason"] for c in res.considered}
    assert reasons["aave_v3"] == "liquidity_unreadable"


def test_optimizer_all_liquidity_unknown_denies():
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={})
    assert res.feasible is False
    assert res.reason == "no_feasible_provider"
    assert res.provider is None and res.fee_bps is None


def test_optimizer_insufficient_liquidity_denied():
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 500})
    assert res.feasible is False
    r = {c["provider"]: c["reason"] for c in res.considered}
    assert r["balancer_v2"].startswith("insufficient_liquidity")


def test_optimizer_uniswap_fee_unresolved_is_refused():
    # Uniswap V3 flash fee depends on the pool tier; without an explicit read it
    # must NOT be assumed — that provider is refused with fee_unresolved.
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"uniswap_v3": 1_000_000})
    r = {c["provider"]: c["reason"] for c in res.considered}
    assert r["uniswap_v3"] == "fee_unresolved"
    # No fixed-fee provider had liquidity → whole candidate denied.
    assert res.feasible is False


def test_optimizer_uniswap_with_resolved_tier_is_feasible():
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"uniswap_v3": 1_000_000},
        fee_bps_by_provider={"uniswap_v3": 5})
    assert res.feasible is True and res.provider == "uniswap_v3"
    assert res.fee_bps == 5
    assert res.fee_usd == pytest.approx(5.0)  # 10000 * 5/10000


def test_optimizer_explicit_read_overrides_and_beats_fixed():
    # Explicit uniswap tier of 1 bps should beat aave's 5 bps.
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"aave_v3": 50_000, "uniswap_v3": 50_000},
        fee_bps_by_provider={"uniswap_v3": 1})
    assert res.provider == "uniswap_v3" and res.fee_bps == 1


def test_optimizer_bad_explicit_fee_is_unreadable():
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"uniswap_v3": 50_000},
        fee_bps_by_provider={"uniswap_v3": "abc"})
    r = {c["provider"]: c["reason"] for c in res.considered}
    assert r["uniswap_v3"] == "fee_unreadable"


def test_optimizer_unsupported_chain_denied():
    res = optimize_flash_provider(
        chain="sepolia", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 50_000})
    assert res.feasible is False
    assert res.reason == "no_provider_supports_chain:sepolia"


def test_optimizer_unknown_borrow_amount_denied():
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=None,
        liquidity_by_provider={"balancer_v2": 50_000})
    assert res.feasible is False and res.reason == "borrow_amount_unknown"


def test_optimizer_never_assumes_zero_fee_for_unknown_provider():
    # A provider not in the catalog is simply not considered — no phantom 0-fee.
    res = optimize_flash_provider(
        chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"phantom_provider": 10 ** 9},
        fee_bps_by_provider={"phantom_provider": 0})
    considered_names = {c["provider"] for c in res.considered}
    assert "phantom_provider" not in considered_names


def test_optimizer_arbitrum_supported_by_catalog():
    # Arbitrum is already in the catalog's supports_chains for aave/balancer/uni.
    res = optimize_flash_provider(
        chain="arbitrum", borrow_token="WETH", borrow_amount_usd=10_000,
        liquidity_by_provider={"balancer_v2": 50_000, "aave_v3": 50_000})
    assert res.feasible is True and res.provider == "balancer_v2"


# ---------------------------------------------------------------------------
# Step 3 — ChainGasModel seam
# ---------------------------------------------------------------------------

def test_base_gas_model_registered_and_typed():
    assert "base" in supported_gas_model_chains()
    gm = get_chain_gas_model("base")
    assert gm is not None
    assert isinstance(gm, ChainGasModel)          # runtime Protocol check
    assert gm.chain == "base" and gm.supports_l1_data_fee is True


def test_unimplemented_chain_returns_none_for_fail_closed_deny():
    assert get_chain_gas_model("arbitrum") is None
    assert get_chain_gas_model("ethereum") is None
    assert get_chain_gas_model("") is None


def test_base_gas_model_without_rpc_returns_none_deny():
    # No Base RPC configured in the sandbox → wrapped estimator is None →
    # all_in_cost returns None (DENY), matching the prior composition behaviour.
    gm = BaseGasModel(None)
    out = asyncio.run(
        gm.all_in_cost(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                       notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0))
    assert out is None


def test_base_gas_model_passthrough_delegates_exactly():
    captured = {}

    async def fake_estimator(**kw):
        captured.update(kw)
        return {"all_in_cost_usd": 12.34, "net_profit_all_in_usd": 87.66}

    gm = BaseGasModel(fake_estimator)
    out = asyncio.run(
        gm.all_in_cost(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                       notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0))
    assert out == {"all_in_cost_usd": 12.34, "net_profit_all_in_usd": 87.66}
    # Every kwarg forwarded unchanged (pass-through, no behaviour change).
    assert captured["gross_profit_usd"] == 100.0
    assert captured["borrow_amount_usd"] == 10_000.0
    assert captured["gas_units"] == 250_000
    assert captured["eth_usd"] == 3000.0
    assert captured["tx_bytes"] is None
    assert captured["estimate_gas_fn"] is None


def test_base_gas_model_from_env_no_rpc_is_deny():
    # from_env in a no-RPC sandbox builds a model whose estimator is None → DENY.
    gm = BaseGasModel.from_env()
    out = asyncio.run(
        gm.all_in_cost(gross_profit_usd=100.0, borrow_amount_usd=10_000.0,
                       notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0))
    assert out is None  # fail-closed
