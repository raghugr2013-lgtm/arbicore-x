"""Phase-5c regression coverage — DEX/flash adapter route-construction expansion.

Proves the newly-implemented calldata adapters (Sushi V2, Sushi V3, Pancake V3,
Camelot V3, QuickSwap V3, Aerodrome Slipstream, Morpho Blue) are:
  * registered in the real ``AdapterRegistry`` (consumed by ExecutionPlanner),
  * emit the CORRECT per-family swap/borrow calldata shape,
  * FAIL CLOSED on an unconfigured router/singleton address (None — never a
    guessed on-chain address),
  * genuinely wired into the real ExecutionPlanner plan-construction path,
and that this expansion advances ROUTE_CONSTRUCTABLE WITHOUT fabricating
EXECUTION_CAPABLE (SUPPORTED_DEXES unchanged).

Offline, deterministic, no RPC / signing / broadcast.
"""
from __future__ import annotations

import pytest

from arbicore.execution.adapters import AdapterRegistry
from arbicore.execution.planner import ExecutionPlanner
from arbicore.scanners.flash_loan_arbitrage.executor_capability import SUPPORTED_DEXES
from scripts.executor_capability_audit import audit_execution_capability

NEW_DEX = ["sushiswap_v2", "sushiswap_v3", "pancakeswap_v3",
           "camelot_v3", "quickswap_v3", "aerodrome_slipstream"]


def test_new_dex_adapters_registered():
    reg = AdapterRegistry()
    keys = {d["dex"] for d in reg.catalog()["dex_providers"]}
    for d in NEW_DEX:
        assert d in keys, f"{d} adapter not registered"
    assert "morpho_blue" in {f["provider"]
                             for f in reg.catalog()["flash_loan_providers"]}


def test_univ2_swap_calldata_shape_and_failclosed_router(monkeypatch):
    reg = AdapterRegistry()
    monkeypatch.delenv("ETHEREUM_SUSHISWAP_V2_ROUTER", raising=False)
    step = reg.dex("sushiswap_v2").swap_step(
        chain="ethereum", token_in="0xA", token_out="0xB",
        amount_in_wei=1000, min_amount_out_wei=990, step_index=1, depends_on=[0])
    assert step["function_signature"].startswith("swapExactTokensForTokens(")
    assert step["contract_address"] is None            # fail-closed, no router
    assert step["args"][2] == ["0xA", "0xB"]
    monkeypatch.setenv("ETHEREUM_SUSHISWAP_V2_ROUTER", "0xRouter")
    step2 = reg.dex("sushiswap_v2").swap_step(
        chain="ethereum", token_in="0xA", token_out="0xB",
        amount_in_wei=1000, min_amount_out_wei=990, step_index=1, depends_on=[0])
    assert step2["contract_address"] == "0xRouter"     # operator-configured


def test_univ3_fork_swap_calldata_shape():
    reg = AdapterRegistry()
    step = reg.dex("sushiswap_v3").swap_step(
        chain="arbitrum", token_in="0xA", token_out="0xB",
        amount_in_wei=1000, min_amount_out_wei=990, step_index=1,
        depends_on=[0], fee_tier_bps=5)
    assert "exactInputSingle((address,address,uint24," in step["function_signature"]
    assert step["args"][0]["fee"] == 500       # 5 bps -> 500 hundredths


def test_algebra_swap_calldata_has_no_fee_tier():
    reg = AdapterRegistry()
    step = reg.dex("camelot_v3").swap_step(
        chain="arbitrum", token_in="0xA", token_out="0xB",
        amount_in_wei=1000, min_amount_out_wei=990, step_index=1, depends_on=[0])
    a = step["args"][0]
    assert "fee" not in a and "limitSqrtPrice" in a and "deadline" in a


def test_slipstream_swap_calldata_uses_tickspacing():
    reg = AdapterRegistry()
    step = reg.dex("aerodrome_slipstream").swap_step(
        chain="base", token_in="0xA", token_out="0xB",
        amount_in_wei=1000, min_amount_out_wei=990, step_index=1,
        depends_on=[0], fee_tier_bps=100)
    assert "int24" in step["function_signature"]
    assert step["args"][0]["tickSpacing"] == 100


def test_morpho_blue_flash_zero_fee_and_failclosed(monkeypatch):
    reg = AdapterRegistry()
    monkeypatch.delenv("ETHEREUM_MORPHO_BLUE", raising=False)
    m = reg.flash("morpho_blue")
    assert m.supports("ethereum") and not m.supports("bnb")
    borrow = m.borrow_step(chain="ethereum", asset="0xA", amount_wei=1000,
                           step_index=0, callback_receiver="0xR")
    assert borrow["function_signature"] == "flashLoan(address,uint256,bytes)"
    assert borrow["contract_address"] is None          # fail-closed singleton
    repay = m.repay_step(chain="ethereum", asset="0xA", amount_wei=1000,
                         fee_bps=None, step_index=2, depends_on=[1])
    assert repay["args"][2] == 0                        # 0 bps premium


def test_planner_integration_new_dex_wired_into_real_path():
    """A plan built with a NEW venue adapter runs the REAL ExecutionPlanner and
    emits the venue's swap step — proving genuine wiring (not registry-only)."""
    planner = ExecutionPlanner(AdapterRegistry())
    plan = planner.build(
        strategy="flash_loan_arbitrage", chain="ethereum",
        borrow_token="0xA", borrow_amount_wei=1_000_000,
        flash_loan_provider="balancer_v2",
        swap_hops=[{"dex": "sushiswap_v2", "token_in": "0xA", "token_out": "0xB",
                    "amount_in_wei": 1_000_000, "min_amount_out_wei": 990_000}],
        mode="SHADOW")
    sigs = [s.function_signature for s in plan.steps if s.kind == "swap"]
    assert any(sig and sig.startswith("swapExactTokensForTokens(") for sig in sigs)
    assert "sushiswap_v2" in plan.dex_route


def test_expansion_advances_route_construction_not_execution():
    rep = audit_execution_capability()
    s = rep["summary"]
    assert s["route_constructable"] == 13     # 7 -> 13 (real adapters added)
    assert s["execution_capable"] == 6        # UNCHANGED (on-chain receiver=UniV3)
    assert set(SUPPORTED_DEXES) == {"uniswap_v3"}   # NOT widened → no fabrication
    for v in rep["venues"]:
        if v["execution_capable"]:
            assert v["venue"] == "uniswap_v3"


def test_certification_state_model_present_and_runtime_gated():
    rep = audit_execution_capability()
    model = rep["certification_state_model"]
    assert model["states"][0] == "IMPLEMENTED"
    assert model["states"][-1] == "LIMITED_LIVE_ELIGIBLE"
    # A route-constructable-but-not-executable cell: runtime states deferred.
    aero = next(v for v in rep["venues"]
                if v["venue"] == "aerodrome" and v["chain"] == "base")
    st = aero["states"]
    assert st["ROUTE_CONSTRUCTABLE"] is True
    assert st["EXECUTION_CAPABLE"] is False
    assert st["SIMULATABLE"] == "requires_runtime"
    assert st["LIMITED_LIVE_ELIGIBLE"] == "requires_runtime"
    assert st["ECONOMICALLY_VALID"] == "requires_runtime"
