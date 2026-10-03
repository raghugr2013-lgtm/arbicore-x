"""Triangular and route search select quotable pools, not the first name.

Alphabetical venue ids used to prefer Sushi, Camelot, QuickSwap, Pancake,
or Aerodrome even when that DEX could not be quoted. The pick is now the
lowest id among pools the capability predicate accepts. The $100,000 TVL
floor and the candidate cap are unchanged. No RPC.
"""
from __future__ import annotations

import asyncio

from arbicore.scanners.flash_loan_arbitrage.activation_sources import (
    BalancerV2DiscoverySource, TriangularDiscoverySource,
)
from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
    hop_quote_capable,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import (
    PoolNode, RouteSearchEngine,
)
from arbicore.scanners.flash_loan_arbitrage.triangular import enumerate_cycles


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _pool(pid, dex, chain, a, b, tvl=200_000.0):
    return PoolNode(pid, dex, chain, a, b, tvl, 30)


def _only(*dexes):
    allowed = set(dexes)

    def _pred(_chain, pool):
        return pool.dex_protocol in allowed

    return _pred


def _tri(chain, pools, predicate=None):
    cfg = {
        "chains": {chain: {"enabled": True}},
        "providers": {"aave_v3": {"enabled": True}},
        "discovery_sources": {"triangular": {"enabled": True}},
    }
    engine = RouteSearchEngine(pool_loader=lambda _c: pools)
    assert engine.min_pool_tvl_usd == 100_000.0
    assert engine.candidate_cap == 64
    return TriangularDiscoverySource(
        route_engine=engine, config_loader=lambda: cfg,
        borrow_token_set=["USDC"], intermediates=["WETH", "DAI"],
        hop_predicate=predicate)


def _dexes(cands):
    return [c.hint_metric["route_dex_protocols"] for c in cands]


def test_enumerate_cycles_keeps_sorted_intermediate_order():
    cycles = enumerate_cycles("USDC", ["WETH", "DAI", "WBTC"])
    pairs = [(c[1], c[2]) for c in cycles]
    assert pairs == list(__import__("itertools").permutations(
        ["DAI", "WBTC", "WETH"], 2))


def test_incapable_sushi_does_not_win_the_leg():
    pools = [
        _pool("sushiswap_v2:DAI:USDC:v2", "sushiswap_v2", "ethereum", "USDC", "DAI"),
        _pool("sushiswap_v2:USDC:WETH:v2", "sushiswap_v2", "ethereum", "USDC", "WETH"),
        _pool("sushiswap_v2:DAI:WETH:v2", "sushiswap_v2", "ethereum", "DAI", "WETH"),
        _pool("uniswap_v3:DAI:USDC:500", "uniswap_v3", "ethereum", "USDC", "DAI"),
        _pool("uniswap_v3:USDC:WETH:500", "uniswap_v3", "ethereum", "USDC", "WETH"),
        _pool("uniswap_v3:DAI:WETH:500", "uniswap_v3", "ethereum", "DAI", "WETH"),
    ]
    out = _run(_tri("ethereum", pools, _only("uniswap_v3")).discover())
    assert out
    assert all(set(d) == {"uniswap_v3"} for d in _dexes(out))


def test_capable_sushi_may_sort_ahead_of_univ3():
    pools = [
        _pool("sushiswap_v2:DAI:USDC:v2", "sushiswap_v2", "ethereum", "USDC", "DAI"),
        _pool("sushiswap_v2:USDC:WETH:v2", "sushiswap_v2", "ethereum", "USDC", "WETH"),
        _pool("sushiswap_v2:DAI:WETH:v2", "sushiswap_v2", "ethereum", "DAI", "WETH"),
        _pool("uniswap_v3:DAI:USDC:500", "uniswap_v3", "ethereum", "USDC", "DAI"),
        _pool("uniswap_v3:USDC:WETH:500", "uniswap_v3", "ethereum", "USDC", "WETH"),
        _pool("uniswap_v3:DAI:WETH:500", "uniswap_v3", "ethereum", "DAI", "WETH"),
    ]
    # Real map: Sushi V2 is quotable on Ethereum, and its id sorts first.
    assert hop_quote_capable("ethereum", pools[0])
    out = _run(_tri("ethereum", pools).discover())
    assert out
    assert all(set(d) == {"sushiswap_v2"} for d in _dexes(out))


def test_camelot_wins_only_when_capable():
    pools = [
        _pool("camelot_v3:DAI:USDC:algebra", "camelot_v3", "arbitrum", "USDC", "DAI"),
        _pool("camelot_v3:USDC:WETH:algebra", "camelot_v3", "arbitrum", "USDC", "WETH"),
        _pool("camelot_v3:DAI:WETH:algebra", "camelot_v3", "arbitrum", "DAI", "WETH"),
        _pool("uniswap_v3:DAI:USDC:500", "uniswap_v3", "arbitrum", "USDC", "DAI"),
        _pool("uniswap_v3:USDC:WETH:500", "uniswap_v3", "arbitrum", "USDC", "WETH"),
        _pool("uniswap_v3:DAI:WETH:500", "uniswap_v3", "arbitrum", "DAI", "WETH"),
    ]
    blocked = _run(_tri("arbitrum", pools, _only("uniswap_v3")).discover())
    assert blocked and all(set(d) == {"uniswap_v3"} for d in _dexes(blocked))
    # camelot_v3 sorts before uniswap_v3 and is quotable on Arbitrum.
    assert hop_quote_capable("arbitrum", pools[0])
    open_ = _run(_tri("arbitrum", pools).discover())
    assert open_ and all(set(d) == {"camelot_v3"} for d in _dexes(open_))


def test_aerodrome_wins_only_when_capable():
    pools = [
        _pool("aerodrome:DAI:USDC:volatile", "aerodrome", "base", "USDC", "DAI"),
        _pool("aerodrome:USDC:WETH:volatile", "aerodrome", "base", "USDC", "WETH"),
        _pool("aerodrome:DAI:WETH:volatile", "aerodrome", "base", "DAI", "WETH"),
        _pool("uniswap_v3:DAI:USDC:500", "uniswap_v3", "base", "USDC", "DAI"),
        _pool("uniswap_v3:USDC:WETH:500", "uniswap_v3", "base", "USDC", "WETH"),
        _pool("uniswap_v3:DAI:WETH:500", "uniswap_v3", "base", "DAI", "WETH"),
    ]
    blocked = _run(_tri("base", pools, _only("uniswap_v3")).discover())
    assert blocked and all(set(d) == {"uniswap_v3"} for d in _dexes(blocked))
    assert hop_quote_capable("base", pools[0])
    open_ = _run(_tri("base", pools).discover())
    assert open_ and all(set(d) == {"aerodrome"} for d in _dexes(open_))


def test_leg_with_only_an_incapable_dex_emits_nothing():
    pools = [
        _pool("curve_stable:DAI:USDC:x", "curve_stable", "ethereum", "USDC", "DAI"),
        _pool("curve_stable:USDC:WETH:x", "curve_stable", "ethereum", "USDC", "WETH"),
        _pool("curve_stable:DAI:WETH:x", "curve_stable", "ethereum", "DAI", "WETH"),
    ]
    assert _run(_tri("ethereum", pools).discover()) == []


def test_predicate_does_not_let_sushi_fill_the_cap():
    pools = [
        _pool("sushiswap_v2:a", "sushiswap_v2", "ethereum", "USDC", "WETH"),
        _pool("sushiswap_v2:b", "sushiswap_v2", "ethereum", "USDC", "WETH"),
        _pool("uniswap_v3:a", "uniswap_v3", "ethereum", "USDC", "WETH"),
        _pool("uniswap_v3:b", "uniswap_v3", "ethereum", "USDC", "WETH"),
    ]
    capped = RouteSearchEngine(
        pool_loader=lambda _c: pools, candidate_cap=1,
        hop_predicate=_only("uniswap_v3"))
    cycles = capped.search(chain="ethereum", borrow_token="USDC")
    assert len(cycles) == 1
    assert {p.dex_protocol for p in cycles[0].pools} == {"uniswap_v3"}

    untouched = RouteSearchEngine(
        pool_loader=lambda _c: pools, candidate_cap=1)
    first = untouched.search(chain="ethereum", borrow_token="USDC")
    assert len(first) == 1
    assert {p.dex_protocol for p in first[0].pools} == {"sushiswap_v2"}


def test_mixed_cycle_requires_every_hop_capable():
    pools = [
        _pool("s", "sushiswap_v2", "ethereum", "USDC", "WETH"),
        _pool("u1", "uniswap_v3", "ethereum", "USDC", "WETH"),
        _pool("u2", "uniswap_v3", "ethereum", "WETH", "DAI"),
        _pool("u3", "uniswap_v3", "ethereum", "DAI", "USDC"),
    ]
    engine = RouteSearchEngine(
        pool_loader=lambda _c: pools, max_hops=3,
        hop_predicate=_only("uniswap_v3"))
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    assert cycles
    assert all(p.dex_protocol == "uniswap_v3" for c in cycles for p in c.pools)
    assert any(c.hop_count == 3 for c in cycles)


def test_complement_skips_an_incapable_alphabetical_first():
    pools = [
        _pool("curve_stable:USDC:WETH:x", "curve_stable", "ethereum", "USDC", "WETH"),
        _pool("uniswap_v3:USDC:WETH:500", "uniswap_v3", "ethereum", "USDC", "WETH"),
    ]
    src = BalancerV2DiscoverySource(
        route_engine=RouteSearchEngine(pool_loader=lambda _c: pools),
        config_loader=lambda: {})
    chosen = src._complement_venue("ethereum", pools, "USDC", "WETH")
    assert chosen is not None and chosen.dex_protocol == "uniswap_v3"
    only_curve = pools[:1]
    assert src._complement_venue("ethereum", only_curve, "USDC", "WETH") is None
