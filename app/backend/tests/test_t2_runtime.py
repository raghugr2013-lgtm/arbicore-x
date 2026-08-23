"""T2 Base runtime wiring + real Anvil REVM backend — offline deterministic."""
import os
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")


def _seed_runtime(with_tvl=True, tvl_usd=5_000_000.0):
    from arbicore.searcher.pool_cache import PoolStateCache, PoolState
    from arbicore.searcher.route import RouteGraph
    from arbicore.searcher.runtime import BaseSearcherRuntime
    from arbicore.scanners.flash_loan_arbitrage.tvl_provider import StaticTVLProvider
    cache = PoolStateCache(max_staleness_blocks=5)
    graph = RouteGraph()
    # deep pools; skew p3 to create a real arb; large size so net >> $25
    pools = [("p1", "A", "B", 1e8, 1e8), ("p2", "B", "C", 1e8, 1e8),
             ("p3", "C", "A", 1e8, 1.1e8)]
    tvl_map = {}
    for pool, t0, t1, r0, r1 in pools:
        cache.upsert(PoolState(pool=pool, kind="v2", token0=t0, token1=t1,
                               reserve0=r0, reserve1=r1, fee_bps=30, block=1))
        graph.add_pool(pool, t0, t1)
        tvl_map[pool] = tvl_usd
    tvl = StaticTVLProvider(tvl_map) if with_tvl else None
    return BaseSearcherRuntime(cache=cache, graph=graph, tvl_provider=tvl)


async def test_runtime_end_to_end_shadow_produces_real_candidates():
    rt = _seed_runtime()
    # ingest a live Sync log (block advance) → cache update path
    rt.ingest_log({"pool": "p3", "event": "Sync", "reserve0": 1e8,
                   "reserve1": 1.12e8, "block": 2})
    res = await rt.scan_block(2, ["A"], amount_in=100_000.0)
    m = res["metrics"]
    assert res["broadcast"] is False and m["broadcasts"] == 0     # SHADOW only
    assert m["cycles"] >= 1 and m["survivors"] >= 1
    assert m["candidates"] >= 1
    c = res["candidates"][0]
    assert c["mode"] == "SHADOW" and c["provenance"] == "REAL"
    assert c["atomic_profit_usd"] >= 25.0                          # Gate 7 held
    assert c["min_route_tvl_usd"] == 5_000_000.0
    assert res["ranking"] and res["ranking"][0][1] > 0


async def test_gate8_fail_closed_without_tvl():
    rt = _seed_runtime(with_tvl=False)
    res = await rt.scan_block(1, ["A"], amount_in=100_000.0)
    m = res["metrics"]
    # arb exists + passes Gate 7 but Gate 8 fails closed → no candidates
    assert m["candidates"] == 0 and m["gate8_rejected"] >= 1


async def test_gate7_25_floor_blocks_tiny_profit():
    rt = _seed_runtime()
    # tiny size → sub-$25 native net → Gate 7 rejects (floor unchanged)
    res = await rt.scan_block(1, ["A"], amount_in=1.0)
    assert res["metrics"]["candidates"] == 0
    assert res["metrics"]["gate7_rejected"] >= 1


async def test_stale_state_protection_blocks_scan():
    rt = _seed_runtime()
    # advance head far beyond staleness window → all hops stale → no candidates
    res = await rt.scan_block(999, ["A"], amount_in=100_000.0)
    assert res["metrics"]["candidates"] == 0


def test_flag_gated_factory_off_by_default(monkeypatch):
    from arbicore.searcher.runtime import maybe_build_base_searcher, searcher_enabled
    monkeypatch.delenv("ARBICORE_T2_SEARCHER_ENABLED", raising=False)
    assert searcher_enabled() is False and maybe_build_base_searcher() is None
    monkeypatch.setenv("ARBICORE_T2_SEARCHER_ENABLED", "true")
    rt = maybe_build_base_searcher()
    assert rt is not None and rt.mode == "SHADOW"


# ── Real Anvil REVM backend: fail-closed + injected happy path ──────────────
async def test_revm_backend_fails_closed():
    from arbicore.searcher.revm_backend import AnvilRevmForkBackend
    from arbicore.searcher.route import Edge
    cyc = [Edge("p1", "A", "B")]
    # no RPC → fail closed
    r = await AnvilRevmForkBackend(None).simulate(cyc, 100.0)
    assert r.ok is False and "no_base_rpc" in r.reason
    # rpc + injected launcher (skips anvil check) but no tx_builder → fail closed
    class _H:
        async def eth_call(self, tx): return "0x"
        async def close(self): pass
    class _L:
        async def launch(self, rpc, blk): return _H()
    r2 = await AnvilRevmForkBackend("https://rpc", launcher=_L()).simulate(cyc, 100.0)
    assert r2.ok is False and "tx_builder_not_wired" in r2.reason


async def test_revm_backend_injected_happy_path():
    from arbicore.searcher.revm_backend import AnvilRevmForkBackend
    from arbicore.searcher.route import Edge
    calls = {}
    class _H:
        async def eth_call(self, tx): calls["tx"] = tx; return "0xdead"
        async def close(self): calls["closed"] = True
    class _L:
        async def launch(self, rpc, blk): return _H()
    async def builder(cycle, amt): return {"to": "0xexec", "data": "0xroute"}
    def decode(raw, amt): return 500.0            # genuine decoded net from fork
    b = AnvilRevmForkBackend("https://rpc", tx_builder=builder, launcher=_L(),
                             decode_net=decode)
    r = await b.simulate([Edge("p1", "A", "B")], 100.0)
    assert r.ok is True and r.net_native == 500.0 and r.backend == "revm_fork"
    assert calls.get("closed") is True and calls["tx"]["to"] == "0xexec"
