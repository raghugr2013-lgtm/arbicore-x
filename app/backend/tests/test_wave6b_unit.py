"""Wave 6B · Execution DAG + adapters + planner + dry-run — unit tests."""
from __future__ import annotations

import copy

import pytest

from arbicore.execution.adapters import (
    ADDRESS_BOOK, AdapterRegistry, AaveV3FlashLoanAdapter,
    AerodromeSwapAdapter, BalancerV2FlashLoanAdapter,
    UniswapV3FlashLoanAdapter, UniswapV3SwapAdapter,
)
from arbicore.execution.dag import (
    ExecutionStep, STEP_KINDS, plan_hash, validate_dag,
)
from arbicore.execution.planner import (
    DryRunEngine, ExecutionPlanner,
)


# ---------- Adapter registry ----------

class TestAdapterRegistry:
    def test_default_flash_adapters(self):
        r = AdapterRegistry()
        assert isinstance(r.flash("aave_v3"), AaveV3FlashLoanAdapter)
        assert isinstance(r.flash("balancer_v2"), BalancerV2FlashLoanAdapter)
        assert isinstance(r.flash("uniswap_v3"), UniswapV3FlashLoanAdapter)

    def test_default_dex_adapters(self):
        r = AdapterRegistry()
        assert isinstance(r.dex("uniswap_v3"), UniswapV3SwapAdapter)
        assert isinstance(r.dex("aerodrome"), AerodromeSwapAdapter)

    def test_unknown_flash_provider_raises(self):
        r = AdapterRegistry()
        with pytest.raises(ValueError, match="unknown flash-loan provider"):
            r.flash("mystery")

    def test_catalog_exposes_versions_and_addresses(self):
        r = AdapterRegistry()
        c = r.catalog()
        for k in ("flash_loan_providers", "dex_providers", "address_book"):
            assert k in c
        aave = next(p for p in c["flash_loan_providers"] if p["provider"] == "aave_v3")
        assert aave["version"] == "aave_v3_flashloan@1"
        assert aave["fee_bps_default"] == 5
        assert "base" in c["address_book"]


class TestAdapterChainSupport:
    def test_aerodrome_only_supports_base(self):
        a = AerodromeSwapAdapter()
        assert a.supports("base") is True
        assert a.supports("ethereum") is False

    def test_aave_v3_supports_base(self):
        assert AaveV3FlashLoanAdapter().supports("base") is True

    def test_balancer_v2_supports_base(self):
        assert BalancerV2FlashLoanAdapter().supports("base") is True


class TestAdapterStepShapes:
    def test_aave_v3_borrow_step_shape(self):
        step = AaveV3FlashLoanAdapter().borrow_step(
            chain="base", asset="0xA", amount_wei=1_000_000, step_index=0,
            callback_receiver="0xB",
        )
        assert step["kind"] == "borrow"
        assert step["provider"] == "aave_v3"
        assert "flashLoanSimple" in step["function_signature"]
        assert step["contract_address"] == ADDRESS_BOOK["base"]["aave_v3_pool"]
        assert step["args"][0] == "0xB"

    def test_balancer_v2_repay_is_zero_bps(self):
        r = BalancerV2FlashLoanAdapter().repay_step(
            chain="base", asset="0xA", amount_wei=1_000_000,
            fee_bps=None, step_index=3, depends_on=[2],
        )
        assert r["args"][2] == 0

    def test_uniswap_v3_flash_repay_uses_pool_tier(self):
        r = UniswapV3FlashLoanAdapter().repay_step(
            chain="base", asset="0xA", amount_wei=10_000,
            fee_bps=100, step_index=3, depends_on=[2],
        )
        # 10_000 * 100 bps / 10_000 = 100
        assert r["args"][2] == 100

    def test_uniswap_v3_swap_step_encodes_fee_in_hundredths_of_bps(self):
        step = UniswapV3SwapAdapter().swap_step(
            chain="base", token_in="0xA", token_out="0xB",
            amount_in_wei=1, min_amount_out_wei=1,
            step_index=1, depends_on=[0], fee_tier_bps=30,
        )
        # UniV3 fee is expressed in units of 0.0001 → tier * 100.
        assert step["args"][0]["fee"] == 3000


# ---------- DAG validation ----------

def _steps(kinds):
    out = []
    for i, k in enumerate(kinds):
        deps = [i - 1] if i > 0 else []
        out.append(ExecutionStep(
            step_index=i, kind=k, provider="x", chain="base",
            contract_address=None, function_signature=None, args=[],
            value_wei=0, depends_on=deps, notes="",
        ))
    return out


class TestDagValidator:
    def test_happy_path(self):
        validate_dag(_steps(["borrow", "swap", "repay", "profit"]))

    def test_first_must_be_borrow(self):
        with pytest.raises(ValueError, match="first step must be 'borrow'"):
            validate_dag(_steps(["swap", "borrow", "repay", "profit"]))

    def test_last_must_be_profit(self):
        with pytest.raises(ValueError, match="last step must be 'profit'"):
            validate_dag(_steps(["borrow", "swap", "repay"]))

    def test_repay_required(self):
        with pytest.raises(ValueError, match="'repay'"):
            validate_dag(_steps(["borrow", "swap", "swap", "profit"]))

    def test_swap_required_between_borrow_and_repay(self):
        with pytest.raises(ValueError):
            validate_dag(_steps(["borrow", "repay", "profit"]))

    def test_unknown_kind_rejected(self):
        with pytest.raises(ValueError):
            validate_dag(_steps(["borrow", "bogus", "repay", "profit"]))

    def test_forward_dep_rejected(self):
        s = _steps(["borrow", "swap", "repay", "profit"])
        s[1].depends_on = [3]  # forward reference
        with pytest.raises(ValueError):
            validate_dag(s)


# ---------- Planner ----------

def _base_kwargs(**over):
    d = dict(
        strategy="flash_loan_arbitrage",
        chain="base",
        borrow_token="0x" + "aa" * 20,
        borrow_amount_wei=1_000_000_000,
        flash_loan_provider="aave_v3",
        swap_hops=[{
            "dex": "uniswap_v3",
            "token_in": "0x" + "aa" * 20,
            "token_out": "0x" + "bb" * 20,
            "amount_in_wei": 1_000_000_000,
            "min_amount_out_wei": 999_500_000,
            "fee_tier_bps": 5,
        }, {
            "dex": "aerodrome",
            "token_in": "0x" + "bb" * 20,
            "token_out": "0x" + "aa" * 20,
            "amount_in_wei": 999_500_000,
            "min_amount_out_wei": 1_001_000_000,
        }],
    )
    d.update(over)
    return d


class TestPlanner:
    def _planner(self): return ExecutionPlanner(AdapterRegistry())

    def test_happy_plan_shape(self):
        plan = self._planner().build(**_base_kwargs())
        kinds = [s.kind for s in plan.steps]
        assert kinds == ["borrow", "swap", "swap", "repay", "profit"]
        assert plan.mode == "SHADOW"
        assert plan.dex_route == ["uniswap_v3", "aerodrome"]
        # Every version referenced in provider_versions.
        assert plan.provider_versions["aave_v3"].startswith("aave_v3_flashloan@")
        assert plan.provider_versions["uniswap_v3"].startswith("uniswap_v3_swap@")
        assert plan.provider_versions["aerodrome"].startswith("aerodrome_swap@")

    def test_reject_empty_swaps(self):
        with pytest.raises(ValueError, match="swap_hops"):
            self._planner().build(**_base_kwargs(swap_hops=[]))

    def test_reject_unknown_flash_provider(self):
        with pytest.raises(ValueError):
            self._planner().build(**_base_kwargs(flash_loan_provider="mystery"))

    def test_reject_unknown_dex(self):
        with pytest.raises(ValueError):
            self._planner().build(**_base_kwargs(swap_hops=[{
                "dex": "unknown", "token_in": "0x" + "a"*40,
                "token_out": "0x" + "b"*40,
                "amount_in_wei": 1, "min_amount_out_wei": 1,
            }]))

    def test_reject_provider_chain_mismatch(self):
        # Aerodrome does not support ethereum.
        with pytest.raises(ValueError, match="aerodrome"):
            self._planner().build(**_base_kwargs(
                chain="ethereum",
                swap_hops=[{
                    "dex": "aerodrome",
                    "token_in": "0x" + "a"*40, "token_out": "0x" + "b"*40,
                    "amount_in_wei": 1, "min_amount_out_wei": 1,
                }],
            ))

    def test_deterministic_plan_hash_excluding_volatile_fields(self):
        p1 = self._planner().build(**_base_kwargs())
        p2 = self._planner().build(**_base_kwargs())
        # plan_id and created_at differ; but plan_hash covers only the
        # deterministic payload (steps, args, providers, chain, etc.).
        assert p1.plan_hash == p2.plan_hash

    def test_hash_changes_on_amount_change(self):
        p1 = self._planner().build(**_base_kwargs())
        p2 = self._planner().build(**_base_kwargs(borrow_amount_wei=2_000_000_000,
                                                    swap_hops=[{
                                                        "dex": "uniswap_v3",
                                                        "token_in": "0x" + "aa"*20,
                                                        "token_out": "0x" + "bb"*20,
                                                        "amount_in_wei": 2_000_000_000,
                                                        "min_amount_out_wei": 1_999_000_000,
                                                        "fee_tier_bps": 5,
                                                    }, {
                                                        "dex": "aerodrome",
                                                        "token_in": "0x" + "bb"*20,
                                                        "token_out": "0x" + "aa"*20,
                                                        "amount_in_wei": 1_999_000_000,
                                                        "min_amount_out_wei": 2_002_000_000,
                                                    }]))
        assert p1.plan_hash != p2.plan_hash


# ---------- Dry-run engine ----------

class TestDryRun:
    def _plan(self, **over):
        return ExecutionPlanner(AdapterRegistry()).build(**_base_kwargs(**over))

    def test_break_even_when_no_quote_supplied(self):
        p = self._plan()
        e = DryRunEngine(AdapterRegistry()).evaluate(p)
        # Aave V3 default 5 bps → premium = 500_000
        assert e["flash_fee_bps"] == 5
        assert e["flash_fee_wei"] == 500_000
        # No quote supplied → dry-run assumes break-even.
        assert e["gross_profit_wei"] == 0
        assert e["profitable"] is False

    def test_profitable_with_quote(self):
        p = self._plan(borrow_amount_usd=1000.0)
        e = DryRunEngine(AdapterRegistry()).evaluate(
            p, quote_effective_out_wei=1_002_000_000, gas_estimate_usd=1.0,
        )
        # Expected out - (borrow + premium) = 1_002_000_000 - 1_000_500_000 = 1_500_000
        assert e["gross_profit_wei"] == 1_500_000
        # gross_profit_usd ≈ 1.5 (borrow amount is 1000 USD for 1e9 wei).
        assert abs(e["gross_profit_usd"] - 1.5) < 1e-6
        # net = gross - gas
        assert abs(e["net_profit_usd"] - 0.5) < 1e-6
        assert e["profitable"] is True

    def test_engine_records_version(self):
        p = self._plan()
        e = DryRunEngine(AdapterRegistry()).evaluate(p)
        assert e["engine_version"] == "dry_run@1"
