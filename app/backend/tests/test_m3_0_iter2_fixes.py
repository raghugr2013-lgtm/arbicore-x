"""Iteration-2 re-test: the two defects reported in iteration_1.

FIX 1 — base_venues symbol resolution must be case-insensitive and fail-closed
        (None, never KeyError) for unknown symbols; live_quote_provider must
        not KeyError on mixed-case Base tokens (cbETH/USDbC/cbBTC/...).
FIX 2 — scripts.m3_0_vps_validate._first_blocking_stage must attribute a
        stage_6_facts ERROR string to stage=live_quote (before mev).
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.discovery import base_venues as bv
from scripts.m3_0_vps_validate import _first_blocking_stage, _probe_fresh_stages


# --- FIX 1: base_venues case-insensitive resolvers -------------------------
MIXED = ["CBETH", "USDBC", "CBBTC", "RETH", "WSTETH", "WEETH"]


@pytest.mark.parametrize("sym", MIXED)
def test_token_address_case_insensitive(sym):
    addr = bv.token_address(sym)
    assert isinstance(addr, str), f"{sym} did not resolve"
    assert addr.startswith("0x") and len(addr) == 42
    canon = bv.canonical_symbol(sym)
    assert canon in bv.TOKENS
    assert bv.TOKENS[canon]["address"] == addr


@pytest.mark.parametrize("sym", ["NOPE", "", None, "0x1234", "weth "])
def test_token_address_unknown_is_none(sym):
    assert bv.token_address(sym) is None
    assert bv.canonical_symbol(sym) is None
    assert bv.is_stable(sym) is False


def test_canonical_symbol_roundtrip_all_tokens():
    for canon in bv.TOKENS:
        assert bv.canonical_symbol(canon) == canon
        assert bv.canonical_symbol(canon.upper()) == canon
        assert bv.canonical_symbol(canon.lower()) == canon


def test_is_stable_case_insensitive():
    assert bv.is_stable("USDBC") is True
    assert bv.is_stable("usdc") is True
    assert bv.is_stable("CBETH") is False


def test_probe_amount_case_insensitive_and_decimals_aware():
    assert bv.probe_amount("CBETH") == bv.PROBE_AMOUNT["cbETH"]
    assert bv.probe_amount("USDBC") == bv.PROBE_AMOUNT["USDbC"]
    # unknown symbol -> safe default, never KeyError
    assert bv.probe_amount("NOPE") == 10 ** 16
    # 6-decimal tokens must NOT get an 18-decimal-ish notional
    assert bv.probe_amount("USDBC") == 200 * 10 ** 6


# --- FIX 1: live_quote_provider must not KeyError --------------------------
CBETH_PLAN = {
    "strategy": "flash_loan_arbitrage", "chain": "base",
    "opportunity_id": "cbeth-test", "borrow_token": "cbETH",
    "borrow_amount_usd": 10000, "flash_loan_provider": "balancer_v2",
    "route_pools": ["uniswap_v3:WETH:cbETH:500",
                    "aerodrome_slipstream:WETH:cbETH:1",
                    "uniswap_v3:WETH:cbETH:3000"],
    "cycle_token_path": ["cbETH", "WETH", "cbETH", "cbETH"],
}


def test_live_quote_provider_no_keyerror_on_mixed_case():
    from arbicore.execution.quoter import QuoterRegistry
    from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
        make_live_quote_provider)

    prov = make_live_quote_provider(QuoterRegistry(), tvl_provider=None)
    hm = {"chain": "base", "provider": "balancer_v2",
          "borrow_token": "cbETH",
          "route_pools": CBETH_PLAN["route_pools"],
          "cycle_token_path": [t.upper() for t in CBETH_PLAN["cycle_token_path"]]}
    # No RPC configured -> must return None (fail-closed), NOT raise KeyError.
    res = asyncio.get_event_loop().run_until_complete(prov(hm, 10000.0))
    assert res is None or isinstance(res, dict)


def test_probe_stage5_has_real_addresses_and_no_keyerror():
    """Capture the hops stage_5 actually sends to the quoter and assert they
    carry REAL addresses (not raw 'CBETH' symbols) and never KeyError."""
    from arbicore.execution.quoter import QuoterRegistry

    captured = []
    reg = QuoterRegistry()
    orig = reg.quote_route

    async def _spy(*, chain, hops, **kw):
        captured.append(hops)
        return await orig(chain=chain, hops=hops, **kw)

    reg.quote_route = _spy  # type: ignore[assignment]

    out = asyncio.get_event_loop().run_until_complete(
        _probe_fresh_stages(CBETH_PLAN, reg))
    assert out["stage_1_plan_shape"]["shape_ok"] is True
    s5 = out["stage_5_route_quote"]
    assert isinstance(s5, dict), f"stage_5 not a dict: {s5}"
    assert "KeyError" not in str(out), str(out)[:2000]

    assert captured, "stage_5 never called quote_route"
    hops = captured[0]
    assert len(hops) == 3
    cbeth = bv.token_address("cbETH").lower()
    weth = bv.token_address("WETH").lower()
    for h in hops:
        assert h["token_in"].lower().startswith("0x"), h
        assert h["token_out"].lower().startswith("0x"), h
        assert h["token_in"].lower() in (cbeth, weth), h
        assert h["token_out"].lower() in (cbeth, weth), h
    assert hops[0]["amount_in_wei"] == bv.PROBE_AMOUNT["cbETH"]


def test_probe_stage5_hops_use_addresses_not_symbols():
    """Build the hop list the same way stage_5 does and assert addresses."""
    from arbicore.discovery.base_venues import build_pool_graph
    _, specs = build_pool_graph()
    token_path = [t.upper() for t in CBETH_PLAN["cycle_token_path"]]
    for i, pid in enumerate(CBETH_PLAN["route_pools"]):
        tin, tout = token_path[i], token_path[i + 1]
        a_in, a_out = bv.token_address(tin), bv.token_address(tout)
        assert a_in and a_in.startswith("0x"), (pid, tin)
        assert a_out and a_out.startswith("0x"), (pid, tout)
        assert specs.get(pid) is not None, f"spec missing for {pid}"


# --- FIX 2: _first_blocking_stage ERROR-string branch ----------------------
_OK_SHAPE = {"stage_1_plan_shape": {"shape_ok": True}}


def test_first_blocking_stage_error_string_attributed_to_live_quote():
    o = dict(_OK_SHAPE)
    o["stage_6_facts"] = "ERROR KeyError: 'CBETH'"
    o["stage_8_mev"] = {"congestion_pct": None, "mev_ok": None}
    got = _first_blocking_stage(o)
    assert "live_quote (before mev)" in got, got
    assert "stage_8_mev" not in got, got


def test_first_blocking_stage_none_facts_still_live_quote():
    o = dict(_OK_SHAPE)
    o["stage_6_facts"] = None
    o["stage_5_route_quote"] = {"hops": [{"idx": 0, "status": "error"}]}
    got = _first_blocking_stage(o)
    assert "stage_6_facts=None" in got, got


def test_first_blocking_stage_mev_when_facts_ok():
    o = dict(_OK_SHAPE)
    o["stage_6_facts"] = {"route_quote_status": "ok", "n_hop_legs": 3}
    o["stage_8_mev"] = {"congestion_pct": None, "mev_ok": None}
    got = _first_blocking_stage(o)
    assert "stage=mev" in got, got


def test_first_blocking_stage_shape_first():
    got = _first_blocking_stage({"stage_1_plan_shape": {"shape_ok": False}})
    assert "stage_1_plan_shape" in got


def test_probe_first_blocking_stage_for_cbeth_plan_is_live_quote_or_earlier():
    from arbicore.execution.quoter import QuoterRegistry
    out = asyncio.get_event_loop().run_until_complete(
        _probe_fresh_stages(CBETH_PLAN, QuoterRegistry()))
    culprit = out["FIRST_BLOCKING_STAGE"]
    assert "stage_8_mev" not in culprit, culprit
    assert "stage_6" in culprit or "live_quote" in culprit, culprit
