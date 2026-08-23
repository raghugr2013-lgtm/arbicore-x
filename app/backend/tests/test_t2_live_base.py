"""Base live-SHADOW wiring — offline deterministic tests."""
import os
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")


def test_readiness_classifies_blockers(monkeypatch):
    from arbicore.searcher.live_base import base_live_readiness
    for k in ("ARBICORE_T2_SEARCHER_ENABLED", "ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE",
              "BASE_RPC_URL", "ARBICORE_WSS_URL_BASE", "ARBICORE_RPC_WSS_BASE",
              "ARBICORE_EXECUTOR_ADDRESS_BASE"):
        monkeypatch.delenv(k, raising=False)
    r = base_live_readiness()
    assert r["ready"] is False and r["mode"] == "SHADOW" and r["broadcast"] is False
    deps = {b["dependency"]: b["category"] for b in r["blockers"]}
    assert deps["base_rpc"] == "CONFIGURATION" and deps["tx_builder"] == "SOFTWARE"
    assert "base_wss" in deps and "anvil_binary" in deps


async def test_reserves_and_price_hooks_fail_closed():
    from arbicore.searcher.live_base import make_base_reserves_fn, make_base_price_fn
    r0 = 1000 * 10**18; r1 = 2000 * 10**18
    raw = "0x" + format(r0, "064x") + format(r1, "064x") + format(0, "064x")

    async def eth_call(pool, data): return raw
    rf = make_base_reserves_fn(eth_call, {"0xp": ("WETH", "USDC", 18, 18)})
    assert await rf("base", "0xp") == ("WETH", 1000.0, "USDC", 2000.0)
    assert await rf("base", "unknown") is None            # unknown pool → None

    async def bad_call(pool, data): return "0x"
    rf2 = make_base_reserves_fn(bad_call, {"0xp": ("WETH", "USDC", 18, 18)})
    assert await rf2("base", "0xp") is None               # malformed → None

    async def price_ok(t): return 3000.0
    async def price_zero(t): return 0.0
    assert await make_base_price_fn(price_ok)("base", "WETH") == 3000.0
    assert await make_base_price_fn(price_zero)("base", "WETH") is None  # fail closed


def test_decode_sync_log():
    from arbicore.searcher.live_base import decode_sync_log
    raw = {"address": "0xPOOL", "blockNumber": "0x10",
           "data": "0x" + format(500, "064x") + format(700, "064x")}
    d = decode_sync_log(raw)
    assert d["event"] == "Sync" and d["reserve0"] == 500 and d["block"] == 16
    assert decode_sync_log({"data": "0x"}) is None


async def test_wss_subscriber_feeds_runtime_shadow():
    from arbicore.searcher.pool_cache import PoolStateCache, PoolState
    from arbicore.searcher.route import RouteGraph
    from arbicore.searcher.runtime import BaseSearcherRuntime
    from arbicore.searcher.live_base import BaseWssSubscriber
    cache = PoolStateCache(max_staleness_blocks=10); g = RouteGraph()
    cache.upsert(PoolState(pool="0xp", kind="v2", token0="A", token1="B",
                           reserve0=1e6, reserve1=1e6, fee_bps=30, block=1))
    g.add_pool("0xp", "A", "B")
    rt = BaseSearcherRuntime(cache=cache, graph=g)

    async def stream():
        yield {"kind": "log", "log": {"address": "0xp", "blockNumber": "0x2",
               "data": "0x" + format(2000000, "064x") + format(1000000, "064x")}}
        yield {"kind": "newHead", "block": 2}

    sub = BaseWssSubscriber(rt, stream(), ["A"], amount_in=100.0)
    out = await sub.run(max_messages=2)
    assert out["blocks_scanned"] == 1
    assert cache.get("0xp").reserve0 == 2000000            # log applied to cache


def test_candidate_bridge_is_real_and_passes_write_gate(monkeypatch):
    from arbicore.searcher.live_base import candidate_to_canonical
    from arbicore.data.opportunity_repo import validate_for_upsert
    from arbicore.models.enums import DataProvenance
    opp = candidate_to_canonical({"route": ["p1", "p2", "p3"], "spot_ratio": 1.01,
                                  "expected_net_profit_usd": 120.0, "confidence": 0.8,
                                  "min_route_tvl_usd": 500000, "block": 42})
    assert opp.source_data_quality is DataProvenance.REAL
    monkeypatch.setenv("ARBICORE_CANONICAL_STRICT_PROVENANCE", "true")
    validate_for_upsert(opp)   # must NOT raise — REAL passes the T0-2 write-gate
    assert opp.metadata["mode"] == "SHADOW"
