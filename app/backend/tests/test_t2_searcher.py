"""T2 universal searcher core — deterministic offline tests."""
import os
import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")


# ── AMM math ──────────────────────────────────────────────────────────────
def test_v2_amount_out_exact_and_guards():
    from arbicore.searcher.amm_math import v2_amount_out
    # equal reserves, small trade: out < in (fee+slippage), > 0
    out = v2_amount_out(10.0, 1000.0, 1000.0, fee_bps=30)
    assert 0 < out < 10.0
    # exact Uniswap-V2 value check
    ain = 10.0 * 0.997
    assert abs(out - (ain * 1000.0) / (1000.0 + ain)) < 1e-9
    # guards
    assert v2_amount_out(0, 1000, 1000) == 0.0
    assert v2_amount_out(10, 0, 1000) == 0.0


def test_v3_monotonic_and_guards():
    from arbicore.searcher.amm_math import v3_amount_out
    a = v3_amount_out(1.0, liquidity=1e6, sqrt_p=2.0, zero_for_one=True)
    b = v3_amount_out(2.0, liquidity=1e6, sqrt_p=2.0, zero_for_one=True)
    assert 0 < a < b                       # more in → more out
    assert v3_amount_out(1.0, liquidity=0, sqrt_p=2.0, zero_for_one=True) == 0.0


def test_stableswap_near_parity_and_fee():
    from arbicore.searcher.amm_math import stable_amount_out
    out = stable_amount_out(1000.0, 0, 1, [1_000_000.0, 1_000_000.0],
                            amp=200.0, fee_bps=4)
    assert 980.0 < out < 1000.0            # ~1:1, minus fee/slippage
    assert stable_amount_out(1000.0, 0, 1, [0.0, 1_000_000.0]) == 0.0


# ── Pool cache + staleness ─────────────────────────────────────────────────
def test_pool_cache_quote_and_stale_protection():
    from arbicore.searcher.pool_cache import PoolStateCache, PoolState
    c = PoolStateCache(max_staleness_blocks=3)
    c.upsert(PoolState(pool="P", kind="v2", token0="A", token1="B",
                       reserve0=1000, reserve1=1000, fee_bps=30, block=100))
    assert c.quote("P", "A", 10.0) and c.quote("P", "A", 10.0) > 0
    # advance head beyond staleness window → refuse (None), no fabrication
    c.set_head_block(105)
    assert c.get("P") is None and c.quote("P", "A", 10.0) is None
    assert c.quote("MISSING", "A", 10.0) is None


def test_pool_cache_apply_log():
    from arbicore.searcher.pool_cache import PoolStateCache, PoolState
    c = PoolStateCache(max_staleness_blocks=10)
    c.upsert(PoolState(pool="P", kind="v2", token0="A", token1="B",
                       reserve0=1000, reserve1=1000, block=1))
    c.apply_log({"pool": "P", "event": "Sync", "reserve0": 2000,
                 "reserve1": 500, "block": 2})
    st = c.get("P")
    assert st.reserve0 == 2000 and st.reserve1 == 500 and st.block == 2


# ── Route graph + fast filter (stage 1) ────────────────────────────────────
def _triangle_cache():
    from arbicore.searcher.pool_cache import PoolStateCache, PoolState
    from arbicore.searcher.route import RouteGraph
    c = PoolStateCache(max_staleness_blocks=100)
    pools = [("p1", "A", "B", 1000, 1000), ("p2", "B", "C", 1000, 1000),
             ("p3", "C", "A", 1000, 1100)]  # skew p3 → arb A→B→C→A
    g = RouteGraph()
    for pool, t0, t1, r0, r1 in pools:
        c.upsert(PoolState(pool=pool, kind="v2", token0=t0, token1=t1,
                           reserve0=r0, reserve1=r1, fee_bps=30, block=1))
        g.add_pool(pool, t0, t1)
    return c, g


def test_route_enumeration_and_fast_filter():
    from arbicore.searcher.route import enumerate_cycles, fast_filter
    c, g = _triangle_cache()
    cycles = enumerate_cycles(g, "A", max_hops=3)
    assert any(len(cy) == 3 for cy in cycles)
    survivors = fast_filter(c, cycles, min_ratio=1.0005, probe_amount=1.0)
    assert survivors and survivors[0][1] > 1.0005   # arb cycle survives


# ── Two-stage: local sim + honest REVM refusal ─────────────────────────────
async def test_two_stage_local_sim_and_revm_refusal():
    from arbicore.searcher.route import enumerate_cycles, fast_filter
    from arbicore.searcher.simulation import (
        two_stage_pipeline, RevmForkBackend, LocalMathSimulationBackend,
    )
    c, g = _triangle_cache()
    survivors = fast_filter(c, enumerate_cycles(g, "A", 3), min_ratio=1.0005)
    results = await two_stage_pipeline(c, survivors, amount_in=1.0)
    assert results and results[0][2].ok and results[0][2].net_native > 0
    # REVM stub refuses to fabricate a result
    r = await RevmForkBackend().simulate(survivors[0][0], 100.0)
    assert r.ok is False and "refusing to fabricate" in r.reason


# ── Adapters ────────────────────────────────────────────────────────────────
def test_dex_and_flashloan_adapters():
    from arbicore.chains.dex_adapter import (
        BaseAerodromeUniAdapter, CatalogFlashLoanAdapter,
    )
    dex = BaseAerodromeUniAdapter()
    assert dex.chain == "base" and len(dex.pools()) > 0
    fl = CatalogFlashLoanAdapter("morpho_blue")
    assert fl.supports_chain("base") is True and fl.fee_bps() == 0
    assert CatalogFlashLoanAdapter("aave_v3").fee_bps() == 5
