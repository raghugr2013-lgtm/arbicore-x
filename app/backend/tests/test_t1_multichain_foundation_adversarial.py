"""T1 independent adversarial tests — Steps 1-3 foundation batch.

Offline only (no network, no signing, no broadcast). Complements
tests/test_flash_multichain_foundation.py with edge cases the dev suite
does not cover.
"""
from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from arbicore.models import CanonicalOpportunity, OpportunityType, StrategyType
from arbicore.models.enums import StrategyType as StrategyTypeDirect
from arbicore.chains.gas_model import (
    BaseGasModel, ChainGasModel, get_chain_gas_model,
    supported_gas_model_chains,
)
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FLASH_LOAN_PROVIDERS,
)
from arbicore.scanners.flash_loan_arbitrage.flash_provider_optimizer import (
    FLASH_PROVIDER_CONSTRAINTS, optimize_flash_provider,
)


# --------------------------------------------------------------------------
# Step 1 — canonical model additive dimensions (edge cases)
# --------------------------------------------------------------------------

class TestCanonicalAdditive:
    def test_enum_exports_and_identity(self):
        assert StrategyType is StrategyTypeDirect
        assert len(list(StrategyType)) == 7
        assert isinstance(StrategyType.GENERIC_DEX, str)
        assert StrategyType("MULTI_HOP") is StrategyType.MULTI_HOP

    def test_extra_fields_still_forbidden(self):
        with pytest.raises(ValidationError):
            CanonicalOpportunity(
                opportunity_type=OpportunityType.DEX_ARBITRAGE,
                asset="WETH/USDC", not_a_real_field=1)

    def test_invalid_strategy_rejected(self):
        with pytest.raises(ValidationError):
            CanonicalOpportunity(
                opportunity_type=OpportunityType.DEX_ARBITRAGE,
                asset="WETH/USDC", strategy="NOT_A_STRATEGY")

    def test_strategy_string_value_accepted(self):
        opp = CanonicalOpportunity(
            opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
            asset="WETH/USDC", strategy="STABLECOIN", chain_id=42161)
        assert opp.strategy is StrategyType.STABLECOIN
        assert opp.chain_id == 42161

    def test_json_round_trip_preserves_new_fields(self):
        opp = CanonicalOpportunity(
            opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
            asset="WETH/USDC", chain="base", chain_id=8453,
            strategy=StrategyType.LST_LRT)
        raw = opp.model_dump_json()
        again = CanonicalOpportunity.model_validate_json(raw)
        assert again.strategy is StrategyType.LST_LRT
        assert again.chain_id == 8453
        # legacy behaviour intact
        assert again.status.value == "candidate"
        assert again.route == "->"

    def test_lifecycle_unchanged_with_new_fields(self):
        opp = CanonicalOpportunity(
            opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
            asset="WETH/USDC", strategy=StrategyType.LIQUIDATION)
        opp.mark_validated()
        opp.mark_approved()
        assert opp.can_transition(opp.status) is False
        assert opp.strategy is StrategyType.LIQUIDATION


# --------------------------------------------------------------------------
# Step 2 — flash provider optimizer (adversarial)
# --------------------------------------------------------------------------

class TestOptimizerAdversarial:
    def test_chain_name_case_insensitive(self):
        res = optimize_flash_provider(
            chain="BASE", borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"balancer_v2": 5_000})
        assert res.feasible is True and res.provider == "balancer_v2"

    def test_zero_bps_tie_breaks_on_deepest_liquidity(self):
        # balancer_v2 and morpho_blue are both real 0-bps on base.
        res = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"balancer_v2": 5_000, "morpho_blue": 90_000})
        assert res.feasible is True
        assert res.fee_bps == 0
        assert res.provider == "morpho_blue"
        assert res.available_liquidity_usd == 90_000

    def test_morpho_not_available_on_arbitrum(self):
        res = optimize_flash_provider(
            chain="arbitrum", borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"morpho_blue": 10 ** 9})
        names = {c["provider"] for c in res.considered}
        assert "morpho_blue" not in names
        assert res.feasible is False

    def test_negative_explicit_fee_is_unreadable(self):
        res = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"uniswap_v3": 10_000},
            fee_bps_by_provider={"uniswap_v3": -5})
        r = {c["provider"]: c["reason"] for c in res.considered}
        assert r["uniswap_v3"] == "fee_unreadable"
        assert res.feasible is False

    def test_none_explicit_fee_falls_back_to_unresolved_for_uniswap(self):
        res = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"uniswap_v3": 10_000},
            fee_bps_by_provider={"uniswap_v3": None})
        r = {c["provider"]: c["reason"] for c in res.considered}
        assert r["uniswap_v3"] == "fee_unresolved"

    def test_explicit_zero_fee_read_for_uniswap_is_allowed(self):
        res = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"uniswap_v3": 10_000},
            fee_bps_by_provider={"uniswap_v3": 0})
        assert res.feasible is True and res.provider == "uniswap_v3"
        assert res.fee_bps == 0

    def test_liquidity_exactly_equal_is_feasible(self):
        res = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=10_000,
            liquidity_by_provider={"balancer_v2": 10_000})
        assert res.feasible is True

    def test_zero_and_negative_borrow_amount_denied(self):
        for amt in (0, -1, 0.0):
            res = optimize_flash_provider(
                chain="base", borrow_token="WETH", borrow_amount_usd=amt,
                liquidity_by_provider={"balancer_v2": 10_000})
            assert res.feasible is False
            assert res.reason == "borrow_amount_unknown"

    def test_none_chain_denied(self):
        res = optimize_flash_provider(
            chain=None, borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"balancer_v2": 10_000})
        assert res.feasible is False
        assert res.reason.startswith("no_provider_supports_chain")

    def test_require_liquidity_false_never_used_as_silent_bypass_default(self):
        # default must be strict
        strict = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=1_000)
        assert strict.feasible is False
        relaxed = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=1_000,
            require_liquidity=False)
        assert relaxed.feasible is True
        assert relaxed.reason == "cheapest_feasible_provider"

    def test_fee_usd_math_is_exact(self):
        res = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=250_000,
            liquidity_by_provider={"aave_v3": 10 ** 9})
        assert res.provider == "aave_v3" and res.fee_bps == 5
        assert res.fee_usd == pytest.approx(250_000 * 5 / 10_000)

    def test_every_catalog_provider_has_constraints_entry(self):
        missing = set(FLASH_LOAN_PROVIDERS) - set(FLASH_PROVIDER_CONSTRAINTS)
        assert not missing, f"catalog providers without constraints: {missing}"

    def test_fixed_fee_flag_matches_protocol_reality(self):
        assert FLASH_PROVIDER_CONSTRAINTS["uniswap_v3"]["fee_fixed"] is False
        for p in ("balancer_v2", "aave_v3", "morpho_blue"):
            assert FLASH_PROVIDER_CONSTRAINTS[p]["fee_fixed"] is True

    def test_considered_list_is_complete_audit_trail(self):
        res = optimize_flash_provider(
            chain="base", borrow_token="WETH", borrow_amount_usd=1_000,
            liquidity_by_provider={"balancer_v2": 5_000, "aave_v3": 10})
        names = {c["provider"] for c in res.considered}
        base_supported = {n for n, m in FLASH_LOAN_PROVIDERS.items()
                          if "base" in m["supports_chains"]}
        assert names == base_supported


# --------------------------------------------------------------------------
# Step 3 — ChainGasModel seam (adversarial)
# --------------------------------------------------------------------------

class TestGasModelSeam:
    def test_registry_canonical_multichain(self):
        # Reconciled (audit 2026-06): the seam now ships genuine per-chain gas
        # models for every canonical Phase-2 chain via the evm_gas layer
        # (own L1/security math, fail-closed without RPC), not base-only.
        assert supported_gas_model_chains() == [
            "arbitrum", "base", "bnb", "ethereum", "optimism", "polygon"]

    def test_case_insensitive_and_none_chain(self):
        assert get_chain_gas_model("BASE") is not None
        assert get_chain_gas_model("Base") is not None
        assert get_chain_gas_model(None) is None
        # Genuine EVM gas models now exist for the other Phase-2 chains
        # (fail-closed at all_in_cost time when no RPC is configured).
        assert get_chain_gas_model("polygon") is not None
        assert get_chain_gas_model("optimism") is not None
        assert get_chain_gas_model("nonexistent-chain") is None
        assert get_chain_gas_model(" base ") is None  # no silent trimming

    def test_protocol_conformance(self):
        gm = get_chain_gas_model("base")
        assert isinstance(gm, ChainGasModel)
        assert gm.chain == "base"
        assert gm.supports_l1_data_fee is True

    def test_passthrough_forwards_tx_bytes_and_estimate_fn(self):
        captured = {}

        async def est():
            return 210_000

        async def fake(**kw):
            captured.update(kw)
            return {"all_in_cost_usd": 1.0, "net_profit_all_in_usd": 9.0}

        gm = BaseGasModel(fake)
        out = asyncio.run(gm.all_in_cost(
            gross_profit_usd=10.0, borrow_amount_usd=1.0, notional_usd=1.0,
            gas_units=None, eth_usd=None, tx_bytes="0xdeadbeef",
            estimate_gas_fn=est))
        assert out["all_in_cost_usd"] == 1.0
        assert captured["tx_bytes"] == "0xdeadbeef"
        assert captured["estimate_gas_fn"] is est
        assert captured["gas_units"] is None
        assert captured["eth_usd"] is None
        assert set(captured) == {
            "gross_profit_usd", "borrow_amount_usd", "notional_usd",
            "gas_units", "eth_usd", "tx_bytes", "estimate_gas_fn"}

    def test_passthrough_returns_none_when_estimator_denies(self):
        async def deny(**kw):
            return None

        gm = BaseGasModel(deny)
        assert asyncio.run(gm.all_in_cost(
            gross_profit_usd=10.0, borrow_amount_usd=1.0, notional_usd=1.0,
            gas_units=250_000, eth_usd=3000.0)) is None

    def test_from_env_no_rpc_is_fail_closed(self):
        gm = BaseGasModel.from_env()
        assert gm.chain == "base"
        assert asyncio.run(gm.all_in_cost(
            gross_profit_usd=1000.0, borrow_amount_usd=10_000.0,
            notional_usd=10_000.0, gas_units=250_000, eth_usd=3000.0)) is None


# --------------------------------------------------------------------------
# Safety envelope — no signing / no broadcast introduced by this batch
# --------------------------------------------------------------------------

class TestSafetyEnvelope:
    def test_new_modules_import_no_web3_signing(self):
        import inspect
        from arbicore.chains import gas_model as gm_mod
        from arbicore.scanners.flash_loan_arbitrage import (
            flash_provider_optimizer as opt_mod)
        for mod in (gm_mod, opt_mod):
            src = inspect.getsource(mod)
            for banned in ("send_raw_transaction", "sign_transaction",
                           "PRIVATE_KEY", "eth_sendRawTransaction",
                           "LocalAccount"):
                assert banned not in src, f"{banned} found in {mod.__name__}"

    def test_composition_uses_gas_model_seam(self):
        import inspect
        from arbicore.runtime import composition
        src = inspect.getsource(composition)
        assert 'get_chain_gas_model("base")' in src
        assert "gas_model.all_in_cost(" in src
