"""D-6.1 — RouteSearchEngine tests."""
from __future__ import annotations

from typing import List

from arbicore.scanners.flash_loan_arbitrage.route_search import (
    PoolNode, RouteSearchEngine,
)


def _p(addr: str, a: str, b: str, *, tvl=1_000_000.0,
        fee_bps=30, dex="uniswap_v3", chain="ethereum") -> PoolNode:
    return PoolNode(pool_address=addr, dex_protocol=dex, chain=chain,
                     token_a=a, token_b=b, tvl_usd=tvl, fee_bps=fee_bps)


def test_simple_2hop_cycle():
    pools = [
        _p("p1", "USDC", "WETH"),
        _p("p2", "WETH", "USDC", dex="sushiswap"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    assert cycles
    assert all(c.token_path[0] == "USDC" for c in cycles)
    assert all(c.token_path[-1] == "USDC" for c in cycles)
    assert all(c.hop_count == 2 for c in cycles)


def test_3hop_cycle_through_intermediate():
    pools = [
        _p("p1", "USDC", "WETH"),
        _p("p2", "WETH", "DAI"),
        _p("p3", "DAI", "USDC"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, max_hops=3)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    paths = [tuple(c.token_path) for c in cycles]
    assert ("USDC", "WETH", "DAI", "USDC") in paths


def test_tvl_floor_filters_thin_pool():
    pools = [
        _p("p1", "USDC", "WETH", tvl=50_000),     # below default 100k floor
        _p("p2", "WETH", "USDC", tvl=2_000_000),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools,
                                min_pool_tvl_usd=100_000)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    assert cycles == []


def test_max_hops_caps_depth():
    pools = [
        _p("p1", "USDC", "A"), _p("p2", "A", "B"),
        _p("p3", "B", "C"),    _p("p4", "C", "D"),
        _p("p5", "D", "USDC"),  # 5-hop cycle exists
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, max_hops=4)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    # No 5-hop cycle reachable within budget; assert no cycle exceeds 4 hops.
    for c in cycles:
        assert c.hop_count <= 4


def test_candidate_cap():
    # Many parallel 2-hop cycles via different sushi pools.
    pools: List[PoolNode] = [_p(f"a{i}", "USDC", "WETH") for i in range(40)]
    pools += [_p(f"b{i}", "WETH", "USDC", dex="sushiswap") for i in range(40)]
    engine = RouteSearchEngine(pool_loader=lambda c: pools, candidate_cap=10)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    assert len(cycles) <= 10


def test_route_id_uniqueness():
    pools = [
        _p("p1", "USDC", "WETH"),
        _p("p2", "WETH", "USDC"),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    ids = {c.route_id for c in cycles}
    assert len(ids) == len(cycles)


def test_no_pool_reused_in_single_cycle():
    pools = [_p("p1", "USDC", "WETH")]  # only one pool — no closed cycle
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    assert cycles == []


def test_wall_clock_cap_records_latency():
    pools = [_p("p1", "USDC", "WETH"), _p("p2", "WETH", "USDC")]
    engine = RouteSearchEngine(pool_loader=lambda c: pools,
                                wall_clock_cap_s=5.0)
    engine.search(chain="ethereum", borrow_token="USDC")
    assert engine.last_wall_ms >= 0
    assert engine.last_explored > 0


def test_min_tvl_recorded_in_cycle():
    pools = [
        _p("p1", "USDC", "WETH", tvl=500_000),
        _p("p2", "WETH", "USDC", tvl=2_000_000),
    ]
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    assert all(c.min_tvl_usd == 500_000.0 for c in cycles)


def test_inv2_no_emission_bus_in_route_search():
    import arbicore.scanners.flash_loan_arbitrage.route_search as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "_bus.emit(" not in text


def test_to_dict_complete_keys():
    pools = [_p("p1", "USDC", "WETH"), _p("p2", "WETH", "USDC")]
    engine = RouteSearchEngine(pool_loader=lambda c: pools)
    cycles = engine.search(chain="ethereum", borrow_token="USDC")
    d = cycles[0].to_dict()
    for k in ("chain", "borrow_token", "route_pools",
              "route_dex_protocols", "cycle_token_path",
              "hop_count", "min_tvl_usd", "route_id"):
        assert k in d
