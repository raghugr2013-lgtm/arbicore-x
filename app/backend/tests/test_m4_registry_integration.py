"""M4 — canonical registry integration into the Base searcher composition.

Proves the T2 runtime now consumes base_pool_registry as the source of truth:
graph populated from REAL addresses, cache keyed by real address, full
composition wires TVL when injectables are present, and the empty-graph /
tvl_provider=None blocker is eliminated — without weakening any gate.
"""
from __future__ import annotations

import asyncio

from arbicore.searcher import runtime as rt
from arbicore.searcher.pool_cache import PoolStateCache
from arbicore.searcher.route import RouteGraph
from arbicore.searcher import v3_state as v3
from arbicore.discovery import base_pool_registry as reg


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_populate_from_registry_adds_only_addressed_pools():
    cache = PoolStateCache()
    graph = RouteGraph()
    added = rt.populate_from_registry(cache, graph)
    resolved = [p for p in reg.get_canonical_pools() if p.address]
    assert added == len(resolved) == 19          # the deterministic UniV3 set
    # cache keyed by REAL contract address (lowercased), not synthetic id.
    keys = set(cache.pools())
    assert all(k.startswith("0x") and len(k) == 42 for k in keys)
    assert reg.resolved_addresses()["uniswap_v3:USDC:WETH:500"].lower() in keys


def test_graph_has_edges_and_cache_skeletons_are_v3():
    cache = PoolStateCache()
    graph = RouteGraph()
    rt.populate_from_registry(cache, graph)
    # Non-empty adjacency → cycles are now enumerable (was empty before M4).
    assert len(graph.adjacency) > 0
    assert any(len(v) > 0 for v in graph.adjacency.values())
    for st in cache.all_states():
        assert st.kind in ("v2", "v3", "stable")
        assert st.token0 and st.token1 and st.fee_bps > 0


def test_pool_address_orientation_matches_registry():
    cache = PoolStateCache()
    graph = RouteGraph()
    rt.populate_from_registry(cache, graph)
    by_addr = {p.address.lower(): p for p in reg.get_canonical_pools() if p.address}
    for st in cache.all_states():
        p = by_addr[st.pool]
        assert st.token0 == p.token0_symbol and st.token1 == p.token1_symbol


def test_build_runtime_without_injectables_is_fail_closed():
    r = rt.build_base_searcher_runtime()
    assert r.tvl_provider is None               # Gate 8 fail-closed preserved
    assert len(r.pool_addresses()) == 19        # graph/cache still populated


def test_build_runtime_with_injectables_wires_real_tvl():
    WETH_ADDR = "0x4200000000000000000000000000000000000006"

    async def eth_call(to, data):              # 1000 units of each token
        wei = 1000 * 10**18 if to.lower() == WETH_ADDR.lower() else 1000 * 10**6
        return "0x" + wei.to_bytes(32, "big").hex()

    async def price_source(token):
        return 1.0
    r = rt.build_base_searcher_runtime(eth_call=eth_call, price_source=price_source)
    assert r.tvl_provider is not None
    # real address of the WETH/USDC 0.05% pool resolves TVL (both priced at 1.0)
    pool = reg.resolved_addresses()["uniswap_v3:USDC:WETH:500"].lower()
    tvl = _run(r.tvl_provider.get_pool_tvl_usd("base", pool))
    assert tvl == 2000.0                        # 1000 + 1000


def test_maybe_build_base_searcher_flag_gated(monkeypatch):
    monkeypatch.delenv("ARBICORE_T2_SEARCHER_ENABLED", raising=False)
    assert rt.maybe_build_base_searcher() is None
    monkeypatch.setenv("ARBICORE_T2_SEARCHER_ENABLED", "true")
    monkeypatch.delenv("ARBICORE_RPC_URL_BASE", raising=False)
    monkeypatch.delenv("ARBICORE_RPC_URL", raising=False)
    monkeypatch.delenv("ARBICORE_NATIVE_PRICE_USD", raising=False)
    r = rt.maybe_build_base_searcher()
    assert r is not None
    assert len(r.pool_addresses()) == 19        # populated from registry
    assert r.tvl_provider is None               # no RPC/price env → fail-closed


def test_univ3_getpool_verifier_builds_calldata():
    captured = {}

    async def eth_call(to, data):
        captured["to"] = to
        captured["data"] = data
        return "0x" + reg.resolved_addresses()[
            "uniswap_v3:USDC:WETH:500"].lower().replace("0x", "").rjust(64, "0")
    verify = v3.make_univ3_getpool_verifier(eth_call, reg.BASE_UNIV3_FACTORY)
    out = _run(verify(
        "0x4200000000000000000000000000000000000006",
        "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913", 500))
    assert captured["data"].startswith("0x1698ee82")
    assert out.lower() == reg.resolved_addresses()["uniswap_v3:USDC:WETH:500"].lower()
