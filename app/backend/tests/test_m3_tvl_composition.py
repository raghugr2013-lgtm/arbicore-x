"""M3 — real TVL/price composition into the T2 runtime (offline, deterministic).

Proves the existing OnChainReserveTVLProvider is genuinely wired with a
V3-aware reserves fn (balanceOf) + price source, that TVL is computed from REAL
state, and that Gate 8 stays FAIL-CLOSED on unknown price / missing pool.
"""
from __future__ import annotations

import asyncio

from arbicore.searcher import runtime as rt
from arbicore.searcher import v3_state as v3
from arbicore.searcher.route import Edge


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _bal(value_wei: int) -> str:
    return "0x" + int(value_wei).to_bytes(32, "big").hex()


# WETH(18)/USDC(6) pool with real-ish balances.
POOL = "0xd0b53d9277642d899df5c87a3966a349a798f224"
WETH_ADDR = "0x4200000000000000000000000000000000000006"
USDC_ADDR = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"
META = {POOL: ("WETH", WETH_ADDR, 18, "USDC", USDC_ADDR, 6)}


def _fake_eth_call(weth_bal_wei, usdc_bal_wei):
    async def eth_call(to, data):
        # data = balanceOf(pool); dispatch on token address `to`.
        if to.lower() == WETH_ADDR.lower():
            return _bal(weth_bal_wei)
        if to.lower() == USDC_ADDR.lower():
            return _bal(usdc_bal_wei)
        return None
    return eth_call


def _prices(mapping):
    async def price_source(token):
        return mapping.get(str(token).upper())
    return price_source


def test_v3_reserves_fn_reads_balances():
    eth_call = _fake_eth_call(3 * 10**18, 9000 * 10**6)   # 3 WETH, 9000 USDC
    rf = v3.make_base_v3_reserves_fn(eth_call, META)
    res = _run(rf("base", POOL))
    assert res == ("WETH", 3.0, "USDC", 9000.0)


def test_tvl_provider_computes_real_tvl():
    eth_call = _fake_eth_call(3 * 10**18, 9000 * 10**6)
    prov = rt.build_base_tvl_provider(
        eth_call, _prices({"WETH": 3000.0, "USDC": 1.0}), pools=[])
    # pools=[] would give empty meta; rebuild provider with our META directly.
    from arbicore.scanners.flash_loan_arbitrage.tvl_provider import (
        OnChainReserveTVLProvider)
    from arbicore.searcher.live_base import make_base_price_fn
    prov = OnChainReserveTVLProvider(
        v3.make_base_v3_reserves_fn(eth_call, META),
        make_base_price_fn(_prices({"WETH": 3000.0, "USDC": 1.0})))
    tvl = _run(prov.get_pool_tvl_usd("base", POOL))
    assert abs(tvl - (3 * 3000 + 9000 * 1)) < 1e-6   # 18000


def test_unknown_price_fails_closed():
    eth_call = _fake_eth_call(3 * 10**18, 9000 * 10**6)
    from arbicore.scanners.flash_loan_arbitrage.tvl_provider import (
        OnChainReserveTVLProvider)
    from arbicore.searcher.live_base import make_base_price_fn
    prov = OnChainReserveTVLProvider(
        v3.make_base_v3_reserves_fn(eth_call, META),
        make_base_price_fn(_prices({"WETH": 3000.0})))   # USDC price unknown
    assert _run(prov.get_pool_tvl_usd("base", POOL)) is None


def test_missing_pool_meta_fails_closed():
    eth_call = _fake_eth_call(3 * 10**18, 9000 * 10**6)
    rf = v3.make_base_v3_reserves_fn(eth_call, META)
    assert _run(rf("base", "0xUNKNOWN")) is None


def test_gate8_passes_with_real_tvl_and_fails_closed_without():
    from arbicore.searcher.pool_cache import PoolStateCache
    from arbicore.searcher.route import RouteGraph
    from arbicore.scanners.flash_loan_arbitrage.tvl_provider import (
        OnChainReserveTVLProvider)
    from arbicore.searcher.live_base import make_base_price_fn

    eth_call = _fake_eth_call(3 * 10**18, 9000 * 10**6)
    prov = OnChainReserveTVLProvider(
        v3.make_base_v3_reserves_fn(eth_call, META),
        make_base_price_fn(_prices({"WETH": 3000.0, "USDC": 1.0})))
    r = rt.BaseSearcherRuntime(cache=PoolStateCache(), graph=RouteGraph(),
                               tvl_provider=prov)
    cyc = [Edge(POOL, "WETH", "USDC")]
    assert _run(r._route_min_tvl(cyc)) == 18000.0
    # No provider → fail-closed None.
    r2 = rt.BaseSearcherRuntime(cache=PoolStateCache(), graph=RouteGraph(),
                                tvl_provider=None)
    assert _run(r2._route_min_tvl(cyc)) is None


def test_native_only_price_source_from_env(monkeypatch):
    monkeypatch.setenv("ARBICORE_NATIVE_PRICE_USD", "3200")
    ps = rt.make_base_price_source_from_env()
    assert _run(ps("WETH")) == 3200.0
    assert _run(ps("USDC")) is None            # unknown → None (fail-closed)
    monkeypatch.delenv("ARBICORE_NATIVE_PRICE_USD", raising=False)
    assert rt.make_base_price_source_from_env() is None
