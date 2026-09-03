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



# ── Canonical calldata tx_builder wiring (Edge cycle → executor eth_call) ───
# Real Base addresses (checksummed) so the canonical encoder accepts them.
_WETH = "0x4200000000000000000000000000000000000006"
_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
_AERO = "0x940181a94A35A4569E4529A3CDfB74e38FD98631"
_EXECUTOR = "0x91c0Bf289f3e5e93F8F8a9db3F4f0f4f4f4F3DE3"
_GAS = "0x998d6efF2b28b72c44f7a334c42678eb4cCaad25"

_TOKEN_ADDRS = {"WETH": _WETH, "USDC": _USDC, "AERO": _AERO}
_TOKEN_DECIMALS = {"WETH": 18, "USDC": 6, "AERO": 18}


def _triangle_cache_real():
    from arbicore.searcher.pool_cache import PoolStateCache, PoolState
    c = PoolStateCache(max_staleness_blocks=100)
    # fee_bps are TRUE basis points (5=0.05%, 30=0.30%, 100=1%); the canonical
    # encoder multiplies ×100 → Uniswap ppm (500, 3000, 10000).
    pools = [("p1", "WETH", "USDC", 5), ("p2", "USDC", "AERO", 30),
             ("p3", "AERO", "WETH", 100)]
    for pool, t0, t1, fee in pools:
        c.upsert(PoolState(pool=pool, kind="v2", token0=t0, token1=t1,
                           reserve0=1e8, reserve1=1e8, fee_bps=fee, block=1))
    return c


def _decode_execute_calldata(data_hex: str):
    """Decode execute(address[],uint256[],bytes) → (tokens, amounts, userData)."""
    from eth_abi import decode as abi_decode
    from eth_utils import keccak
    b = bytes.fromhex(data_hex[2:] if data_hex.startswith("0x") else data_hex)
    selector, payload = b[:4], b[4:]
    expected_sel = keccak(text="execute(address[],uint256[],bytes)")[:4]
    assert selector == expected_sel, "wrong entrypoint selector"
    tokens, amounts, user_data = abi_decode(
        ["address[]", "uint256[]", "bytes"], payload)
    return tokens, amounts, user_data


def _decode_user_data(user_data: bytes):
    """Decode abi.encode(SwapHop[] hops, address profitRecipient)."""
    from eth_abi import decode as abi_decode
    hop_t = "(address,address,uint24,uint256,uint256,uint160)"
    hops, recipient = abi_decode([f"{hop_t}[]", "address"], user_data)
    return hops, recipient


async def test_calldata_tx_builder_produces_canonical_execute_tx():
    from arbicore.searcher.revm_backend import make_calldata_tx_builder
    from arbicore.searcher.route import Edge
    cache = _triangle_cache_real()
    builder = make_calldata_tx_builder(
        cache=cache, executor_address=_EXECUTOR, from_address=_GAS,
        token_addresses=_TOKEN_ADDRS, token_decimals=_TOKEN_DECIMALS)
    cycle = [Edge("p1", "WETH", "USDC"), Edge("p2", "USDC", "AERO"),
             Edge("p3", "AERO", "WETH")]
    tx = await builder(cycle, 2.0)                    # borrow 2 WETH

    # tx envelope
    assert tx["to"].lower() == _EXECUTOR.lower()
    assert tx["value"] == "0x0"
    assert tx["from"].lower() == _GAS.lower()
    assert tx["data"].startswith("0x64ba4bc1")        # execute() selector

    # entrypoint args
    tokens, amounts, user_data = _decode_execute_calldata(tx["data"])
    assert [t.lower() for t in tokens] == [_WETH.lower()]
    assert list(amounts) == [2 * 10 ** 18]            # 2 WETH, 18 decimals

    # userData hops + profit recipient
    hops, recipient = _decode_user_data(user_data)
    assert recipient.lower() == _GAS.lower()
    assert len(hops) == 3
    # fee tiers = pool fee_bps × 100 (ppm): 5bps→500ppm, 30bps→3000, 100bps→10000
    assert hops[0][2] == 5 * 100 and hops[1][2] == 30 * 100
    assert hops[2][2] == 100 * 100
    # first hop carries the borrowed amount; later hops forward (amountIn=0)
    assert hops[0][3] == 2 * 10 ** 18
    assert hops[1][3] == 0 and hops[2][3] == 0
    # token routing preserved
    assert hops[0][0].lower() == _WETH.lower() and hops[0][1].lower() == _USDC.lower()
    assert hops[2][1].lower() == _WETH.lower()


async def test_calldata_tx_builder_is_deterministic():
    from arbicore.searcher.revm_backend import make_calldata_tx_builder
    from arbicore.searcher.route import Edge
    cache = _triangle_cache_real()
    builder = make_calldata_tx_builder(
        cache=cache, executor_address=_EXECUTOR, from_address=_GAS,
        token_addresses=_TOKEN_ADDRS, token_decimals=_TOKEN_DECIMALS)
    cycle = [Edge("p1", "WETH", "USDC"), Edge("p3", "AERO", "WETH")]
    a = await builder(cycle, 1.5)
    b = await builder(cycle, 1.5)
    assert a["data"] == b["data"]                     # deterministic bytes


async def test_calldata_tx_builder_fails_closed():
    from arbicore.searcher.revm_backend import make_calldata_tx_builder
    from arbicore.searcher.route import Edge
    cache = _triangle_cache_real()
    # unmapped token → raises (never fabricates placeholder addresses)
    builder = make_calldata_tx_builder(
        cache=cache, executor_address=_EXECUTOR, from_address=_GAS,
        token_addresses={"WETH": _WETH}, token_decimals=_TOKEN_DECIMALS)
    with pytest.raises(ValueError):
        await builder([Edge("p1", "WETH", "USDC")], 1.0)
    # empty cycle → raises
    ok_builder = make_calldata_tx_builder(
        cache=cache, executor_address=_EXECUTOR, from_address=_GAS,
        token_addresses=_TOKEN_ADDRS, token_decimals=_TOKEN_DECIMALS)
    with pytest.raises(ValueError):
        await ok_builder([], 1.0)
    # missing executor → raises
    no_exec = make_calldata_tx_builder(
        cache=cache, executor_address=None, from_address=_GAS, chain="ethereum",
        token_addresses=_TOKEN_ADDRS, token_decimals=_TOKEN_DECIMALS)
    with pytest.raises(ValueError):
        await no_exec([Edge("p1", "WETH", "USDC")], 1.0)


async def test_calldata_tx_builder_feeds_revm_backend_shadow():
    """End-to-end: canonical tx_builder → AnvilRevmForkBackend (injected fork).
    No signing/broadcast; the fork eth_call receives the canonical calldata."""
    from arbicore.searcher.revm_backend import (AnvilRevmForkBackend,
                                                 make_calldata_tx_builder)
    from arbicore.searcher.route import Edge
    cache = _triangle_cache_real()
    seen = {}

    class _H:
        async def eth_call(self, tx):
            seen["tx"] = tx
            return "0x" + format(0, "064x")           # fork returns net=0 hex
        async def close(self):
            seen["closed"] = True

    class _L:
        async def launch(self, rpc, blk):
            return _H()

    builder = make_calldata_tx_builder(
        cache=cache, executor_address=_EXECUTOR, from_address=_GAS,
        token_addresses=_TOKEN_ADDRS, token_decimals=_TOKEN_DECIMALS)

    def decode_net(raw, amt):
        return float(int(raw, 16)) if raw and raw != "0x" else -amt

    backend = AnvilRevmForkBackend(
        "https://base.example", tx_builder=builder, launcher=_L(),
        decode_net=decode_net)
    cycle = [Edge("p1", "WETH", "USDC"), Edge("p3", "AERO", "WETH")]
    res = await backend.simulate(cycle, 1.0)

    # fork received the CANONICAL executor calldata (selector 0x64ba4bc1)
    assert seen["tx"]["to"].lower() == _EXECUTOR.lower()
    assert seen["tx"]["data"].startswith("0x64ba4bc1")
    assert seen.get("closed") is True
    # net=0 → non-positive → honest reject (no fabricated pass), no broadcast
    assert res.ok is False and res.net_native == 0.0
    assert res.backend == "revm_fork"
