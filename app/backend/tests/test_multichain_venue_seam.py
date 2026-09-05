"""Multichain venue-aware resolver seam (fail-closed, offline).

Covers the genuine capability activation added in the takeover:
  * UniV3-family DIRECT forks (Sushi V3 on arbitrum, Pancake V3 on bnb) resolve
    via the shared ``getPool(address,address,uint24)`` ABI through the same
    resolver as canonical Uniswap V3.
  * UniswapV2-family (Sushi V2 on ethereum) resolves via ``getPair`` +
    ``getReserves`` and fails closed on empty reserves / mismatch / no factory.
  * The opportunity matrix now marks these forks DISCOVERABLE with an HONEST
    downstream quoter blocker, while Algebra / Solidly / Curve families report an
    explicit ``*_resolver_not_implemented`` blocker (never fabricated as UniV3).
  * Registry ABI classification helpers.

Deterministic, injected eth_call, no RPC / signing / broadcast / Mongo.
"""
from __future__ import annotations

import asyncio

from eth_abi import encode as _enc
from eth_utils import to_checksum_address

from arbicore.chains import registries as REG
from arbicore.discovery import opportunity_engine as E
from arbicore.discovery import univ3_pool_resolver as R


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _addr_word(a):
    return "0x" + _enc(["address"], [to_checksum_address(a)]).hex()


# ── registry ABI classification ─────────────────────────────────────────────
def test_registry_abi_classification_is_honest():
    assert REG.dex_abi("arbitrum", "uniswap_v3") == "univ3"
    assert REG.dex_abi("arbitrum", "sushiswap_v3") == "univ3"
    assert REG.dex_abi("bnb", "pancakeswap_v3") == "univ3"
    assert REG.dex_abi("arbitrum", "camelot_v3") == "algebra"
    assert REG.dex_abi("polygon", "quickswap_v3") == "algebra"
    assert REG.dex_abi("ethereum", "sushiswap_v2") == "univ2"
    assert REG.dex_abi("optimism", "velodrome_v2") == "solidly"
    assert REG.dex_abi("ethereum", "curve_stable") == "curve"
    assert REG.dex_abi("arbitrum", "nonexistent") is None
    assert REG.factory_for("arbitrum", "sushiswap_v3")


# ── UniV3-family fork resolution ─────────────────────────────────────────────
def _univ3_eth_call(factory, pool, t0, t1, fee=500, liq=10**18):
    async def eth_call(to, data):
        sel = data[:10]
        if to.lower() == factory.lower():
            return _addr_word(pool)
        if sel == R._SEL_TOKEN0:
            return _addr_word(t0)
        if sel == R._SEL_TOKEN1:
            return _addr_word(t1)
        if sel == R._SEL_FEE:
            return "0x" + _enc(["uint24"], [int(fee)]).hex()
        if sel == R._SEL_LIQUIDITY:
            return "0x" + _enc(["uint128"], [int(liq)]).hex()
        raise AssertionError(sel)
    return eth_call


def test_sushiswap_v3_fork_resolves_via_shared_univ3_abi():
    toks = REG.tokens_for("arbitrum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    factory = REG.factory_for("arbitrum", "sushiswap_v3")
    pool = to_checksum_address("0x" + "5e" * 20)
    res = _run(R.resolve_univ3_pool(
        "arbitrum", weth, usdc, 500, dex="sushiswap_v3",
        eth_call=_univ3_eth_call(factory, pool, weth, usdc)))
    assert res is not None
    assert res["dex"] == "sushiswap_v3"
    assert res["pool_address"] == pool
    assert res["factory"].lower() == factory.lower()


def test_pancakeswap_v3_fork_resolves_on_bnb():
    toks = REG.tokens_for("bnb")
    wbnb, usdt = toks["WBNB"]["address"], toks["USDT"]["address"]
    factory = REG.factory_for("bnb", "pancakeswap_v3")
    pool = to_checksum_address("0x" + "9c" * 20)
    res = _run(R.resolve_univ3_pool(
        "bnb", wbnb, usdt, 500, dex="pancakeswap_v3",
        eth_call=_univ3_eth_call(factory, pool, wbnb, usdt)))
    assert res is not None and res["dex"] == "pancakeswap_v3"


def test_univ3_family_rejects_non_univ3_abi_venue():
    # Algebra venue must NOT be resolvable through the univ3 factory lookup.
    assert R.univ3_family_factory_for("arbitrum", "camelot_v3") is None
    toks = REG.tokens_for("arbitrum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    res = _run(R.resolve_univ3_pool(
        "arbitrum", weth, usdc, 500, dex="camelot_v3",
        eth_call=_univ3_eth_call("0x" + "00" * 20, "0x" + "11" * 20, weth, usdc)))
    assert res is None


# ── UniV2-family resolution ──────────────────────────────────────────────────
def _univ2_eth_call(factory, pair, t0, t1, r0=10**18, r1=2_000_000_000):
    async def eth_call(to, data):
        sel = data[:10]
        if to.lower() == factory.lower():
            return _addr_word(pair)
        if sel == R._SEL_TOKEN0:
            return _addr_word(t0)
        if sel == R._SEL_TOKEN1:
            return _addr_word(t1)
        if sel == R._SEL_GET_RESERVES:
            return "0x" + _enc(["uint112", "uint112", "uint32"],
                               [int(r0), int(r1), 0]).hex()
        raise AssertionError(sel)
    return eth_call


def test_sushiswap_v2_pair_resolves_and_validates_reserves():
    toks = REG.tokens_for("ethereum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    factory = REG.factory_for("ethereum", "sushiswap_v2")
    pair = to_checksum_address("0x" + "77" * 20)
    res = _run(R.resolve_univ2_pool(
        "ethereum", weth, usdc, dex="sushiswap_v2",
        eth_call=_univ2_eth_call(factory, pair, weth, usdc)))
    assert res is not None
    assert res["dex"] == "sushiswap_v2"
    assert res["pool_address"] == pair
    assert res["resolution"] == "onchain_factory_getPair"


def test_univ2_zero_reserves_fails_closed():
    toks = REG.tokens_for("ethereum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    factory = REG.factory_for("ethereum", "sushiswap_v2")
    pair = to_checksum_address("0x" + "77" * 20)
    res = _run(R.resolve_univ2_pool(
        "ethereum", weth, usdc, dex="sushiswap_v2",
        eth_call=_univ2_eth_call(factory, pair, weth, usdc, r0=0, r1=0)))
    assert res is None


def test_univ2_token_mismatch_fails_closed():
    toks = REG.tokens_for("ethereum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    other = to_checksum_address("0x" + "cc" * 20)
    factory = REG.factory_for("ethereum", "sushiswap_v2")
    pair = to_checksum_address("0x" + "77" * 20)
    res = _run(R.resolve_univ2_pool(
        "ethereum", weth, usdc, dex="sushiswap_v2",
        eth_call=_univ2_eth_call(factory, pair, weth, other)))
    assert res is None


def test_univ2_no_factory_fails_closed():
    toks = REG.tokens_for("ethereum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]

    async def never(to, data):
        raise AssertionError("must not be called")
    # uniswap_v3 has no univ2 factory ⇒ resolver returns None without any call.
    res = _run(R.resolve_univ2_pool(
        "ethereum", weth, usdc, dex="uniswap_v3", eth_call=never))
    assert res is None


# ── opportunity matrix venue-awareness ───────────────────────────────────────
def _cell(m, chain, venue):
    return next(r for r in m["rows"] if r["chain"] == chain and r["venue"] == venue)


def test_matrix_activates_forks_and_is_honest_about_families():
    m = E.build_opportunity_matrix()
    # UniV3-fork + UniV2 forks now DISCOVERABLE (real resolver seam)
    assert _cell(m, "arbitrum", "sushiswap_v3")["discoverable"] is True
    assert _cell(m, "bnb", "pancakeswap_v3")["discoverable"] is True
    assert _cell(m, "ethereum", "sushiswap_v2")["discoverable"] is True
    # ...and now QUOTE-CONNECTED (verified fork QuoterV2 / V2 router adapters)
    assert _cell(m, "arbitrum", "sushiswap_v3")["quote_path_connected"] is True
    assert _cell(m, "bnb", "pancakeswap_v3")["quote_path_connected"] is True
    assert _cell(m, "ethereum", "sushiswap_v2")["quote_path_connected"] is True
    # Algebra (Camelot V3 / QuickSwap V3) DISCOVERABLE via poolByPair AND now
    # QUOTE-CONNECTED via the verified Algebra dynamic-fee quoter.
    assert _cell(m, "arbitrum", "camelot_v3")["discoverable"] is True
    assert _cell(m, "polygon", "quickswap_v3")["discoverable"] is True
    assert _cell(m, "arbitrum", "camelot_v3")["quote_path_connected"] is True
    assert _cell(m, "polygon", "quickswap_v3")["quote_path_connected"] is True
    # Solidly / Curve still have no resolver ⇒ explicit family blocker
    assert _cell(m, "optimism", "velodrome_v2")["blocker"] == "solidly_resolver_not_implemented"
    assert _cell(m, "ethereum", "curve_stable")["blocker"] == "curve_resolver_not_implemented"
    # nothing ever limited-live eligible from code/config alone
    assert m["summary"]["limited_live_eligible_count"] == 0
    assert all(r["limited_live_eligible"] is False for r in m["rows"])


def test_quoter_registry_registers_fork_backends():
    from arbicore.execution.quoter import QuoterRegistry
    supported = set(QuoterRegistry().supported_dexes)
    for dex in ("uniswap_v3", "sushiswap_v3", "pancakeswap_v3", "sushiswap_v2",
                "camelot_v3", "quickswap_v3"):
        assert dex in supported, dex


def test_algebra_quoter_uses_dynamic_fee_abi(monkeypatch):
    from arbicore.execution import quoter as Q
    seen = {}

    async def fake_eth_call(rpc_url, *, to, data, **kw):
        seen["to"] = to
        seen["selector"] = data[:10]
        # Algebra returns (uint256 amountOut, uint16 fee) — NOT the UniV3 tuple
        return ("0x" + _enc(["uint256", "uint16"], [4_444_444, 300]).hex()), 55, None
    monkeypatch.setattr(Q, "_eth_call", fake_eth_call)
    reg = Q.QuoterRegistry()
    rq = _run(reg.quote_route(
        chain="arbitrum", rpc_url="http://rpc.test",
        hops=[{"dex": "camelot_v3", "token_in": "0x" + "11" * 20,
               "token_out": "0x" + "22" * 20, "amount_in_wei": 10**18}]))
    assert rq.status == "ok" and rq.final_amount_out_wei == 4_444_444
    assert seen["to"] == Q.CAMELOT_V3_QUOTER_ARBITRUM
    assert seen["selector"] == Q._SEL["algebra_quoteExactInputSingle"]


def test_algebra_multihop_route_chains_with_provenance_and_fails_closed(monkeypatch):
    """Genuine Algebra multi-hop via quote_route_strict: each hop is a real
    Algebra quote (own provenance); an unsupported hop fails closed (ok=False),
    never a passthrough."""
    from arbicore.execution import quoter as Q

    async def fake_eth_call(rpc_url, *, to, data, **kw):
        return ("0x" + _enc(["uint256", "uint16"], [5 * 10**17, 300]).hex()), 42, None
    monkeypatch.setattr(Q, "_eth_call", fake_eth_call)
    reg = Q.QuoterRegistry()
    a, b, c = "0x" + "11" * 20, "0x" + "22" * 20, "0x" + "33" * 20
    ok, rq = _run(reg.quote_route_strict(
        chain="arbitrum", rpc_url="http://rpc.test",
        hops=[{"dex": "camelot_v3", "token_in": a, "token_out": b, "amount_in_wei": 10**18},
              {"dex": "camelot_v3", "token_in": b, "token_out": c}]))
    assert ok is True and rq.status == "ok" and len(rq.hops) == 2
    assert all(h.status == "ok" and h.quoter_contract == Q.CAMELOT_V3_QUOTER_ARBITRUM
               for h in rq.hops)
    assert rq.hops[1].amount_in_wei == rq.hops[0].amount_out_wei   # chained
    ok2, rq2 = _run(reg.quote_route_strict(
        chain="arbitrum", rpc_url="http://rpc.test",
        hops=[{"dex": "camelot_v3", "token_in": a, "token_out": b, "amount_in_wei": 10**18},
              {"dex": "balancer_v2", "token_in": b, "token_out": c}]))
    assert ok2 is False and rq2.hops[1].status == "fallback:no_adapter"


def test_algebra_quoter_fails_closed_off_map():
    from arbicore.execution import quoter as Q
    reg = Q.QuoterRegistry()
    # camelot_v3 has no ethereum quoter ⇒ fail closed (no fabrication)
    rq = _run(reg.quote_route(
        chain="ethereum", rpc_url="http://rpc.test",
        hops=[{"dex": "camelot_v3", "token_in": "0x" + "11" * 20,
               "token_out": "0x" + "22" * 20, "amount_in_wei": 10**18}]))
    assert rq.status == "fallback:break_even"
    assert rq.hops[0].status == "fallback:no_adapter"


def test_sushi_v3_quoter_uses_its_own_address_not_uniswap():
    from arbicore.execution import quoter as Q
    sushi = Q.SushiV3QuoterV2._CONTRACT_BY_CHAIN["arbitrum"]
    uni = Q.UniV3QuoterV2._CONTRACT_BY_CHAIN["arbitrum"]
    assert sushi != uni                       # fork quoter is factory-specific
    assert sushi == Q.SUSHI_V3_QUOTER_V2_ARBITRUM


def test_sushi_v3_live_quote_routes_to_sushi_quoter(monkeypatch):
    from arbicore.execution import quoter as Q
    seen = {}

    async def fake_eth_call(rpc_url, *, to, data, **kw):
        seen["to"] = to
        return ("0x" + _enc(["uint256", "uint160", "uint32", "uint256"],
                            [2_222_222, 1, 1, 90000]).hex()), 77, None
    monkeypatch.setattr(Q, "_eth_call", fake_eth_call)
    reg = Q.QuoterRegistry()
    rq = _run(reg.quote_route(
        chain="arbitrum", rpc_url="http://rpc.test",
        hops=[{"dex": "sushiswap_v3", "token_in": "0x" + "11" * 20,
               "token_out": "0x" + "22" * 20, "amount_in_wei": 10**18, "fee": 500}]))
    assert rq.status == "ok" and rq.final_amount_out_wei == 2_222_222
    assert seen["to"] == Q.SUSHI_V3_QUOTER_V2_ARBITRUM


def test_sushi_v2_router_getamountsout_quote(monkeypatch):
    from arbicore.execution import quoter as Q
    seen = {}

    async def fake_eth_call(rpc_url, *, to, data, **kw):
        seen["to"] = to
        return ("0x" + _enc(["uint256[]"], [[10**18, 3_500_000]]).hex()), 88, None
    monkeypatch.setattr(Q, "_eth_call", fake_eth_call)
    reg = Q.QuoterRegistry()
    rq = _run(reg.quote_route(
        chain="ethereum", rpc_url="http://rpc.test",
        hops=[{"dex": "sushiswap_v2", "token_in": "0x" + "11" * 20,
               "token_out": "0x" + "22" * 20, "amount_in_wei": 10**18}]))
    assert rq.status == "ok" and rq.final_amount_out_wei == 3_500_000
    assert seen["to"] == Q.SUSHI_V2_ROUTER02_ETHEREUM


def test_fork_quoter_fails_closed_off_map():
    from arbicore.execution import quoter as Q
    reg = Q.QuoterRegistry()
    # sushiswap_v3 has no ethereum quoter address ⇒ fail closed (no fabrication)
    rq = _run(reg.quote_route(
        chain="ethereum", rpc_url="http://rpc.test",
        hops=[{"dex": "sushiswap_v3", "token_in": "0x" + "11" * 20,
               "token_out": "0x" + "22" * 20, "amount_in_wei": 10**18, "fee": 500}]))
    assert rq.status == "fallback:break_even"
    assert rq.hops[0].status == "fallback:no_adapter"


# ── Algebra (poolByPair) resolver ────────────────────────────────────────────
def _algebra_eth_call(factory, pool, t0, t1, liq=10**18):
    from arbicore.discovery import algebra_pool_resolver as A

    async def eth_call(to, data):
        sel = data[:10]
        if to.lower() == factory.lower():
            return _addr_word(pool)
        if sel == A._SEL_TOKEN0:
            return _addr_word(t0)
        if sel == A._SEL_TOKEN1:
            return _addr_word(t1)
        if sel == A._SEL_LIQUIDITY:
            return "0x" + _enc(["uint128"], [int(liq)]).hex()
        raise AssertionError(sel)
    return eth_call


def test_algebra_pool_resolves_camelot_v3():
    from arbicore.discovery import algebra_pool_resolver as A
    toks = REG.tokens_for("arbitrum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    factory = REG.factory_for("arbitrum", "camelot_v3")
    pool = to_checksum_address("0x" + "ca" * 20)
    res = _run(A.resolve_algebra_pool(
        "arbitrum", weth, usdc, dex="camelot_v3",
        eth_call=_algebra_eth_call(factory, pool, weth, usdc)))
    assert res is not None
    assert res["dex"] == "camelot_v3"
    assert res["pool_address"] == pool
    assert res["resolution"] == "onchain_algebra_poolByPair"


def test_algebra_zero_liquidity_and_nonexistent_fail_closed():
    from arbicore.discovery import algebra_pool_resolver as A
    toks = REG.tokens_for("polygon")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    factory = REG.factory_for("polygon", "quickswap_v3")
    pool = to_checksum_address("0x" + "cb" * 20)
    # zero liquidity excluded
    assert _run(A.resolve_algebra_pool(
        "polygon", weth, usdc, dex="quickswap_v3",
        eth_call=_algebra_eth_call(factory, pool, weth, usdc, liq=0))) is None
    # nonexistent pool (factory returns zero address)
    assert _run(A.resolve_algebra_pool(
        "polygon", weth, usdc, dex="quickswap_v3",
        eth_call=_algebra_eth_call(factory, A._ZERO_ADDR, weth, usdc))) is None


def test_parallel_discovery_routes_algebra_family():
    toks = REG.tokens_for("arbitrum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    factory = REG.factory_for("arbitrum", "camelot_v3")
    pool = to_checksum_address("0x" + "ca" * 20)

    def eth_call_for_chain(chain):
        return _algebra_eth_call(factory, pool, weth, usdc)

    tasks = [{"chain": "arbitrum", "dex": "camelot_v3",
              "token_a": weth, "token_b": usdc, "fee": 0}]
    res = _run(E.discover_pools_parallel(tasks, eth_call_for_chain=eth_call_for_chain))
    assert res[0]["resolved"] is True
    assert res[0]["pool"]["dex"] == "camelot_v3"


def test_parallel_discovery_routes_univ2_family():
    toks = REG.tokens_for("ethereum")
    weth, usdc = toks["WETH"]["address"], toks["USDC"]["address"]
    factory = REG.factory_for("ethereum", "sushiswap_v2")
    pair = to_checksum_address("0x" + "77" * 20)

    def eth_call_for_chain(chain):
        return _univ2_eth_call(factory, pair, weth, usdc)

    tasks = [{"chain": "ethereum", "dex": "sushiswap_v2",
              "token_a": weth, "token_b": usdc, "fee": 0}]
    res = _run(E.discover_pools_parallel(tasks, eth_call_for_chain=eth_call_for_chain))
    assert res[0]["resolved"] is True
    assert res[0]["pool"]["dex"] == "sushiswap_v2"


def test_multichain_universe_includes_v2_and_excludes_algebra():
    # ethereum now includes sushiswap_v2 (univ2) nodes.
    eth_nodes = {p.dex_protocol for p in __import__(
        "arbicore.discovery.multichain_venues", fromlist=["build_pool_graph"]
    ).build_pool_graph("ethereum")}
    assert "sushiswap_v2" in eth_nodes
    assert "uniswap_v3" in eth_nodes
    # arbitrum probe graph must NOT fabricate Algebra (camelot_v3) as a UniV3 node
    arb_nodes = {p.dex_protocol for p in __import__(
        "arbicore.discovery.multichain_venues", fromlist=["build_pool_graph"]
    ).build_pool_graph("arbitrum")}
    assert "camelot_v3" not in arb_nodes
    assert "sushiswap_v3" in arb_nodes and "uniswap_v3" in arb_nodes
