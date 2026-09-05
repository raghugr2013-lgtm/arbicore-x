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
    # forks now DISCOVERABLE (real getPool/getPair seam)
    assert _cell(m, "arbitrum", "sushiswap_v3")["discoverable"] is True
    assert _cell(m, "bnb", "pancakeswap_v3")["discoverable"] is True
    assert _cell(m, "ethereum", "sushiswap_v2")["discoverable"] is True
    # ...but NOT quotable (no fork quoter adapter) — honest downstream blocker
    # (in this pod with no RPC the first miss is RPC; the quoter gap is proven
    # by quote_path_connected being false for the fork).
    assert _cell(m, "arbitrum", "sushiswap_v3")["quote_path_connected"] is False
    # Algebra / Solidly / Curve report an explicit, distinct family blocker
    assert _cell(m, "arbitrum", "camelot_v3")["discoverable"] is False
    assert _cell(m, "arbitrum", "camelot_v3")["blocker"] == "algebra_resolver_not_implemented"
    assert _cell(m, "polygon", "quickswap_v3")["blocker"] == "algebra_resolver_not_implemented"
    assert _cell(m, "optimism", "velodrome_v2")["blocker"] == "solidly_resolver_not_implemented"
    assert _cell(m, "ethereum", "curve_stable")["blocker"] == "curve_resolver_not_implemented"
    # nothing ever limited-live eligible from code/config alone
    assert m["summary"]["limited_live_eligible_count"] == 0
    assert all(r["limited_live_eligible"] is False for r in m["rows"])


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
