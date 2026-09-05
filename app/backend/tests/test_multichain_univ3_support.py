"""Multichain UniV3 support — pool resolution + live quoting (fail-closed).

Covers the 9 required scenarios: pool resolution, token ordering, nonexistent
pool, malformed RPC response, liquidity unreadable, successful live quote,
quote RPC failure, multihop quote chaining, and Base regression. Deterministic +
offline (mocked eth_call / patched _eth_call). No signing/broadcast/live.
"""
from __future__ import annotations

import asyncio

import pytest
from eth_abi import encode as _enc
from eth_utils import to_checksum_address

from arbicore.chains.registries import tokens_for
from arbicore.discovery import univ3_pool_resolver as R
from arbicore.execution import quoter as Q

CHAIN = "arbitrum"
_toks = tokens_for(CHAIN)
WETH = _toks["WETH"]["address"]
USDC = _toks["USDC"]["address"]
FEE = 500
POOL = to_checksum_address("0x" + "a1" * 20)
FACTORY = R.univ3_factory_for(CHAIN)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _addr_word(a):
    return "0x" + _enc(["address"], [to_checksum_address(a)]).hex()


def _u(typ, v):
    return "0x" + _enc([typ], [v]).hex()


def _mk_eth_call(*, pool=POOL, t0=None, t1=None, fee=FEE, liquidity=10**18,
                 fail_on=None, malformed_on=None):
    t0 = t0 or WETH
    t1 = t1 or USDC
    fail_on = set(fail_on or [])
    malformed_on = set(malformed_on or [])

    async def eth_call(to, data):
        sel = data[:10]
        tag = ("factory" if to.lower() == (FACTORY or "").lower()
               else {R._SEL_TOKEN0: "token0", R._SEL_TOKEN1: "token1",
                     R._SEL_FEE: "fee", R._SEL_LIQUIDITY: "liquidity"}.get(sel, sel))
        if tag in fail_on:
            raise RuntimeError(f"rpc_down:{tag}")
        if tag in malformed_on:
            return "0xdead"                     # undecodable for the expected type
        if to.lower() == (FACTORY or "").lower():
            return _addr_word(pool)
        if sel == R._SEL_TOKEN0:
            return _addr_word(t0)
        if sel == R._SEL_TOKEN1:
            return _addr_word(t1)
        if sel == R._SEL_FEE:
            return _u("uint24", int(fee))
        if sel == R._SEL_LIQUIDITY:
            return _u("uint128", int(liquidity))
        raise AssertionError(f"unexpected call to={to} sel={sel}")

    return eth_call


# ── 1. pool resolution (happy path) ─────────────────────────────────────────
def test_pool_resolution_happy_path():
    res = _run(R.resolve_univ3_pool(CHAIN, WETH, USDC, FEE, eth_call=_mk_eth_call()))
    assert res is not None
    assert res["pool_address"] == POOL
    assert res["fee"] == FEE and res["liquidity"] == 10**18
    assert {res["token0"].lower(), res["token1"].lower()} == {WETH.lower(), USDC.lower()}
    assert res["factory"].lower() == FACTORY.lower()


# ── 2. token ordering (registry order vs on-chain order) ─────────────────────
def test_token_ordering_is_order_independent_and_validated():
    # Request in reverse order; pool reports canonical (t0=WETH,t1=USDC) — valid.
    res = _run(R.resolve_univ3_pool(CHAIN, USDC, WETH, FEE, eth_call=_mk_eth_call()))
    assert res is not None
    # Pool whose tokens DON'T match the requested pair must be rejected.
    other = to_checksum_address("0x" + "cc" * 20)
    bad = _run(R.resolve_univ3_pool(CHAIN, WETH, USDC, FEE,
                                    eth_call=_mk_eth_call(t1=other)))
    assert bad is None


# ── 3. nonexistent pool (factory returns zero address) ───────────────────────
def test_nonexistent_pool_excluded():
    res = _run(R.resolve_univ3_pool(CHAIN, WETH, USDC, FEE,
                                    eth_call=_mk_eth_call(pool=R._ZERO_ADDR)))
    assert res is None


# ── 4. malformed RPC response ────────────────────────────────────────────────
@pytest.mark.parametrize("bad", ["factory", "token0", "fee", "liquidity"])
def test_malformed_rpc_response_fails_closed(bad):
    res = _run(R.resolve_univ3_pool(CHAIN, WETH, USDC, FEE,
                                    eth_call=_mk_eth_call(malformed_on=[bad])))
    assert res is None


# ── 5. liquidity unreadable / zero ───────────────────────────────────────────
def test_liquidity_unreadable_or_zero_excluded():
    assert _run(R.resolve_univ3_pool(CHAIN, WETH, USDC, FEE,
                                     eth_call=_mk_eth_call(fail_on=["liquidity"]))) is None
    assert _run(R.resolve_univ3_pool(CHAIN, WETH, USDC, FEE,
                                     eth_call=_mk_eth_call(liquidity=0))) is None


def test_fee_inconsistency_excluded():
    res = _run(R.resolve_univ3_pool(CHAIN, WETH, USDC, FEE,
                                    eth_call=_mk_eth_call(fee=3000)))
    assert res is None


def test_no_registered_factory_fails_closed():
    assert _run(R.resolve_univ3_pool("solana", WETH, USDC, FEE,
                                     eth_call=_mk_eth_call())) is None


# ── 6/7/8. live quote, quote RPC failure, multihop chaining ──────────────────
def _uni_result(amount_out, sqrt=1, ticks=1, gas=90000):
    return "0x" + _enc(["uint256", "uint160", "uint32", "uint256"],
                       [int(amount_out), int(sqrt), int(ticks), int(gas)]).hex()


def test_successful_live_quote_multichain(monkeypatch):
    async def fake_eth_call(rpc_url, *, to, data, **kw):
        return _uni_result(2_000_000), 123, None
    monkeypatch.setattr(Q, "_eth_call", fake_eth_call)

    reg = Q.QuoterRegistry()
    rq = _run(reg.quote_route(
        chain="arbitrum", rpc_url="http://rpc.test",
        hops=[{"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
               "amount_in_wei": 10**18, "fee": FEE}]))
    assert rq.status == "ok" and rq.is_live
    assert rq.final_amount_out_wei == 2_000_000
    assert rq.hops[0].quoter_contract == Q.UniV3QuoterV2._CONTRACT_BY_CHAIN["arbitrum"]
    assert rq.hops[0].block_number == 123


def test_quote_rpc_failure_fails_closed(monkeypatch):
    async def boom(rpc_url, *, to, data, **kw):
        return None, None, {"code": -32000, "message": "execution reverted"}
    monkeypatch.setattr(Q, "_eth_call", boom)

    reg = Q.QuoterRegistry()
    rq = _run(reg.quote_route(
        chain="polygon", rpc_url="http://rpc.test",
        hops=[{"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
               "amount_in_wei": 10**18, "fee": FEE}]))
    assert rq.status == "fallback:break_even"
    assert rq.hops[0].status == "fallback:revert"   # fail-closed signal is status
    assert not rq.is_live                            # never treated as a live quote


def test_multihop_quote_chaining(monkeypatch):
    seen = []

    async def fake_eth_call(rpc_url, *, to, data, **kw):
        # amountIn is encoded in the calldata tuple; return 2x that so we can
        # assert the 2nd hop consumes the 1st hop's output.
        seen.append(data)
        # hop1 -> 3_000_000 ; hop2 -> depends on chaining
        idx = len(seen)
        return _uni_result(3_000_000 if idx == 1 else 7_777), 1, None
    monkeypatch.setattr(Q, "_eth_call", fake_eth_call)

    reg = Q.QuoterRegistry()
    rq = _run(reg.quote_route(
        chain="optimism", rpc_url="http://rpc.test",
        hops=[
            {"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
             "amount_in_wei": 10**18, "fee": FEE},
            {"dex": "uniswap_v3", "token_in": USDC, "token_out": WETH,
             "fee": FEE},   # no amount_in => chained from hop1 output
        ]))
    assert rq.status == "ok"
    assert rq.hops[0].amount_out_wei == 3_000_000
    assert rq.hops[1].amount_in_wei == 3_000_000     # chained
    assert rq.final_amount_out_wei == 7_777


# ── 9. Base regression (unchanged: address + quoting path intact) ────────────
def test_base_quoter_address_unchanged():
    assert (Q.UniV3QuoterV2._CONTRACT_BY_CHAIN["base"]
            == Q.BASE_UNIV3_QUOTER_V2)
    assert (Q.UniV3QuoterV2._CONTRACT_BY_CHAIN["base-sepolia"]
            == Q.BASE_SEPOLIA_UNIV3_QUOTER_V2)


def test_base_live_quote_still_works(monkeypatch):
    async def fake_eth_call(rpc_url, *, to, data, **kw):
        assert to == Q.BASE_UNIV3_QUOTER_V2       # base still routes to its quoter
        return _uni_result(1_234_567), 55, None
    monkeypatch.setattr(Q, "_eth_call", fake_eth_call)

    reg = Q.QuoterRegistry()
    rq = _run(reg.quote_route(
        chain="base", rpc_url="http://rpc.test",
        hops=[{"dex": "uniswap_v3", "token_in": WETH, "token_out": USDC,
               "amount_in_wei": 10**18, "fee": 3000}]))
    assert rq.status == "ok" and rq.final_amount_out_wei == 1_234_567
