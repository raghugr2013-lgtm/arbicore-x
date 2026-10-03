"""Measured TVL reaches route search without lowering the $100,000 floor.

Graph builders store tvl_usd=0. RouteSearchEngine excludes anything below
min_pool_tvl_usd (default 100_000). These tests drive the existing comparison
with a measured snapshot. They do not start SHADOW, do not enable the live
scanner, and do not call a production RPC.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock

from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    _HopPlan, make_live_quote_provider,
)
from arbicore.scanners.flash_loan_arbitrage.pool_tvl_propagation import (
    ChainDispatchTVLProvider, PoolTVLOverlay, apply_measured_tvl,
    measure_graph_tvl, resolve_graph_pool_for_tvl,
    tvl_provider_usable_for_chain,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import (
    PoolNode, RouteSearchEngine,
)
from arbicore.scanners.flash_loan_arbitrage.scanner import (
    FlashLoanArbitrageScanner,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _node(pid, a="USDC", b="WETH", tvl=0.0, chain="ethereum", dex="uniswap_v3"):
    return PoolNode(
        pool_address=pid, dex_protocol=dex, chain=chain,
        token_a=a, token_b=b, tvl_usd=tvl, fee_bps=30,
    )


def _pair(chain="ethereum"):
    return [_node("p-low-fee", chain=chain), _node("p-high-fee", chain=chain)]


def _search(pools, chain="ethereum"):
    engine = RouteSearchEngine(pool_loader=lambda _c: pools)
    assert engine.min_pool_tvl_usd == 100_000.0
    return engine.search(chain=chain, borrow_token="USDC")


def test_default_floor_is_unchanged():
    assert RouteSearchEngine(pool_loader=lambda _c: []).min_pool_tvl_usd == 100_000.0


def test_graph_placeholder_stays_zero_until_measured():
    from arbicore.discovery.multichain_venues import build_pool_graph
    pools = build_pool_graph("ethereum")
    assert pools
    assert all(p.tvl_usd == 0.0 for p in pools)
    assert _search(pools) == []


def test_measured_150k_is_searchable_at_default_floor():
    annotated = apply_measured_tvl(_pair(), {"p-low-fee": 150_000.0,
                                             "p-high-fee": 150_000.0})
    assert all(p.tvl_usd == 150_000.0 for p in annotated)
    cycles = _search(annotated)
    assert cycles
    assert all(c.min_tvl_usd >= 100_000.0 for c in cycles)


def test_unknown_measurement_stays_zero_and_is_excluded():
    annotated = apply_measured_tvl(_pair(), {"p-low-fee": None, "p-high-fee": None})
    assert all(p.tvl_usd == 0.0 for p in annotated)
    assert _search(annotated) == []


def test_just_under_floor_is_excluded_and_floor_is_included():
    under = apply_measured_tvl(_pair(), {"p-low-fee": 99_999.0,
                                         "p-high-fee": 99_999.0})
    assert all(p.tvl_usd == 99_999.0 for p in under)
    assert _search(under) == []
    at = apply_measured_tvl(_pair(), {"p-low-fee": 100_000.0,
                                      "p-high-fee": 100_000.0})
    assert _search(at)


def test_provider_none_and_150k_propagate_through_measure():
    class _Prov:
        async def get_pool_tvl_usd(self, chain, addr):
            assert chain == "ethereum"
            return {"0xaaa": 150_000.0, "0xbbb": None}.get(addr)

    async def _resolve(_chain, pool, _eth):
        return ("0xaaa" if pool.pool_address == "p-low-fee" else "0xbbb", ())

    measured = _run(measure_graph_tvl(
        "ethereum", _pair(), tvl_provider=_Prov(), resolve=_resolve))
    annotated = apply_measured_tvl(_pair(), measured)
    by_id = {p.pool_address: p.tvl_usd for p in annotated}
    assert by_id["p-low-fee"] == 150_000.0
    assert by_id["p-high-fee"] == 0.0
    # One leg under the floor drops the cycle. The comparison is unchanged.
    assert _search(annotated) == []


def test_overlay_does_not_apply_base_tvl_to_ethereum():
    overlay = PoolTVLOverlay()
    overlay.replace("base", {"p-low-fee": 500_000.0, "p-high-fee": 500_000.0})
    eth = overlay.apply("ethereum", _pair("ethereum"))
    base = overlay.apply("base", _pair("base"))
    assert all(p.tvl_usd == 0.0 for p in eth)
    assert all(p.tvl_usd == 500_000.0 for p in base)
    assert _search(eth, chain="ethereum") == []
    assert _search(base, chain="base")


def test_dispatch_does_not_call_another_chains_provider():
    class _Rec:
        def __init__(self, value):
            self.calls = []
            self.value = value

        async def get_pool_tvl_usd(self, chain, addr):
            self.calls.append((chain, addr))
            return self.value

    base = _Rec(500_000.0)
    eth = _Rec(200_000.0)
    dispatch = ChainDispatchTVLProvider({"base": base, "ethereum": eth})
    assert _run(dispatch.get_pool_tvl_usd("ethereum", "0xeth")) == 200_000.0
    assert base.calls == []
    assert eth.calls == [("ethereum", "0xeth")]
    assert _run(dispatch.get_pool_tvl_usd("optimism", "0xopt")) is None
    assert tvl_provider_usable_for_chain(dispatch, "ethereum", "base") is True
    assert tvl_provider_usable_for_chain(dispatch, "optimism", "base") is False
    plain = _Rec(1.0)
    assert tvl_provider_usable_for_chain(plain, "base", "base") is True
    assert tvl_provider_usable_for_chain(plain, "ethereum", "base") is False


def test_non_base_without_eth_call_does_not_use_synthetic_id():
    node = _node("uniswap_v3:USDC:WETH:3000")
    assert _run(resolve_graph_pool_for_tvl("ethereum", node, None)) is None
    assert node.tvl_usd == 0.0


def test_base_resolution_uses_contract_address():
    from arbicore.discovery.base_pool_registry import (
        build_canonical_pool_graph, canonical_pool_by_id)
    nodes, _specs = build_canonical_pool_graph(resolved_only=True)
    node = next(n for n in nodes if n.dex_protocol == "uniswap_v3")
    assert node.tvl_usd == 0.0
    resolved = _run(resolve_graph_pool_for_tvl("base", node, None))
    assert resolved is not None
    addr, _meta = resolved
    cp = canonical_pool_by_id(node.pool_address)
    assert addr == cp.address
    assert addr.lower() != node.pool_address.lower()


def _quote_reg():
    hop = SimpleNamespace(
        dex="uniswap_v3", status="ok", block_number=7,
        amount_in_wei=10**16, amount_out_wei=10**16,
        token_in="0x" + "11" * 20, token_out="0x" + "22" * 20,
    )

    class _Reg:
        async def quote_route(self, *, chain, hops):
            return SimpleNamespace(
                status="ok", final_amount_out_wei=10**16,
                aggregate_gas_estimate_units=300_000, hops=[hop, hop])

    return _Reg()


def _planned(monkeypatch, chain_addr):
    import arbicore.scanners.flash_loan_arbitrage.live_quote_provider as lqp
    plan = _HopPlan(
        dex="uniswap_v3", token_in="0x" + "11" * 20, token_out="0x" + "22" * 20,
        fee=3000, tick_spacing=None, stable=None,
        tvl_key=chain_addr, tvl_addr=chain_addr, fee_bps=30,
        pool_address=chain_addr)

    async def _fake(_chain, _hm, _eth):
        return [plan, plan], ["WETH", "USDC", "WETH"], 10**16

    monkeypatch.setattr(lqp, "_plan_generic_evm", _fake)


def test_base_scoped_provider_not_used_for_ethereum_quote(monkeypatch):
    _planned(monkeypatch, "0xeth")

    class _Rec:
        def __init__(self):
            self.calls = []

        async def get_pool_tvl_usd(self, chain, addr):
            self.calls.append((chain, addr))
            return 500_000.0

    tvl = _Rec()
    prov = make_live_quote_provider(
        _quote_reg(), tvl_provider=tvl, tvl_provider_chain="base",
        eth_call_for_chain=lambda _c: (lambda *_a, **_k: None))
    facts = _run(prov({
        "chain": "ethereum",
        "route_hops": [{"dex": "uniswap_v3"}, {"dex": "uniswap_v3"}],
        "cycle_token_path": ["WETH", "USDC", "WETH"],
        "borrow_token": "WETH",
        "borrow_amount_wei": 10**16,
    }, 10_000.0))
    assert tvl.calls == []
    assert facts is not None
    assert facts["min_pool_tvl_usd_in_route"] == 0.0


def test_dispatch_quote_uses_only_the_route_chain(monkeypatch):
    _planned(monkeypatch, "0xeth")

    class _Rec:
        def __init__(self, value):
            self.calls = []
            self.value = value

        async def get_pool_tvl_usd(self, chain, addr):
            self.calls.append((chain, addr))
            return self.value

    base = _Rec(500_000.0)
    eth = _Rec(180_000.0)
    dispatch = ChainDispatchTVLProvider({"base": base, "ethereum": eth})
    prov = make_live_quote_provider(
        _quote_reg(), tvl_provider=dispatch,
        eth_call_for_chain=lambda _c: (lambda *_a, **_k: None))
    facts = _run(prov({
        "chain": "ethereum",
        "route_hops": [{"dex": "uniswap_v3"}, {"dex": "uniswap_v3"}],
        "cycle_token_path": ["WETH", "USDC", "WETH"],
        "borrow_token": "WETH",
        "borrow_amount_wei": 10**16,
    }, 10_000.0))
    assert base.calls == []
    assert eth.calls
    assert facts["min_pool_tvl_usd_in_route"] == 180_000.0


def test_disabled_tick_does_not_refresh_tvl():
    cache = {"state": {"enabled": False}}
    called = {"n": 0}

    async def _refresh():
        called["n"] += 1

    scanner = FlashLoanArbitrageScanner(
        emission_bus=MagicMock(),
        discovery_queue=MagicMock(),
        venue_capability_repo=MagicMock(),
        config_loader=lambda: {
            "route_search": {"min_pool_tvl_usd": 100_000.0},
            "gate_thresholds": {"default": {}},
            "chains": {"base": {"enabled": True}},
            "providers": {},
        },
        state_loader=lambda: cache["state"],
        pool_loader=lambda _c: [],
    )
    scanner.set_pool_tvl_refresh(_refresh)
    scanner._route_cfg_sig = scanner._route_sig(scanner.config_loader() or {})
    _run(scanner._tick())
    assert scanner.is_enabled() is False
    assert called["n"] == 0
    assert scanner.route_engine.min_pool_tvl_usd == 100_000.0

    cache["state"] = {"enabled": True}
    _run(scanner._tick())
    assert called["n"] == 1
    assert scanner.route_engine.min_pool_tvl_usd == 100_000.0
