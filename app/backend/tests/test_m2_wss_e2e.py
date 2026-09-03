"""M2/M4 end-to-end: WSS stream → V3 decode → cache update → scan (SHADOW).

Drives the EXISTING BaseWssSubscriber / T2WssManager with a fake WSS client
(no network) carrying real-shape V3 Swap logs + newHeads, and asserts the cache
updates, a block scan runs, telemetry reflects real events, and broadcast=False.
"""
from __future__ import annotations

import asyncio

from eth_abi import encode as abi_encode

from arbicore.searcher import runtime as rt
from arbicore.searcher import v3_state as v3
from arbicore.searcher.live_base import BaseWssSubscriber
from arbicore.searcher.wss_ingest import T2WssManager
from arbicore.discovery import base_pool_registry as reg


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


POOL = reg.resolved_addresses()["uniswap_v3:USDC:WETH:500"].lower()


def _swap_msg(sqrt_p_raw, liq, tick, block):
    data = abi_encode(["int256", "int256", "uint160", "uint128", "int24"],
                      [-1, 1, int(sqrt_p_raw * 2**96), int(liq), int(tick)])
    return {"kind": "log", "log": {
        "address": POOL, "blockNumber": hex(block),
        "data": "0x" + data.hex(),
        "topics": [v3.V3_SWAP_TOPIC0,
                   "0x" + "1".rjust(64, "0"), "0x" + "2".rjust(64, "0")]}}


class _FakeWs:
    def __init__(self, messages):
        self._messages = messages

    async def __aiter__(self):
        for m in self._messages:
            yield m


def test_wss_v3_swap_updates_cache_and_scans_shadow():
    r = rt.build_base_searcher_runtime()          # registry-populated, tvl=None
    assert POOL in r.pool_addresses()
    msgs = [
        _swap_msg(2.0, 5_000_000, 10, 500),       # V3 Swap seeds live state
        {"kind": "newHead", "block": 501},        # triggers scan_block
    ]
    sub = BaseWssSubscriber(r, _FakeWs(msgs), ["WETH", "USDC"])
    out = _run(sub.run())
    assert out["logs_ingested"] == 1
    assert out["blocks_scanned"] == 1
    # V3 state landed in the cache (sqrt_p + liquidity from the Swap event).
    st = r.cache.get(POOL)
    assert st is not None and st.liquidity == 5_000_000.0 and st.tick == 10
    assert abs(st.sqrt_p - 2.0) < 1e-9
    # SHADOW invariant: never broadcasts.
    assert all(m.get("broadcasts", 0) == 0 for m in out["scans"])


def test_t2_manager_runs_v3_state_bootstrap_from_initializer():
    r = rt.build_base_searcher_runtime()
    x96 = int(1.5 * 2**96)
    slot0 = "0x" + abi_encode(
        ["uint160", "int24", "uint16", "uint16", "uint16", "uint8", "bool"],
        [x96, 3, 0, 1, 1, 0, True]).hex()
    liq = "0x" + abi_encode(["uint128"], [4_200_000]).hex()

    async def fake_eth_call(to, data):
        if data == v3.SLOT0_SELECTOR:
            return slot0
        if data == v3.LIQUIDITY_SELECTOR:
            return liq
        return None
    initializer = v3.make_v3_state_initializer(fake_eth_call)
    mgr = T2WssManager(r, "wss://x/y", state_initializer=initializer,
                       client_factory=lambda: _FakeWs([]))
    n = _run(mgr.bootstrap_v3_state())
    assert n == 19                                # all deterministic V3 pools seeded
    st = r.cache.get(POOL) if r.cache._head_block == 0 else None
    # head_block still 0 after bootstrap → not stale; state present.
    st = r.cache.all_states()[0]
    assert st.liquidity == 4_200_000.0 and abs(st.sqrt_p - 1.5) < 1e-9
    status = mgr.status()
    assert status["broadcast"] is False
    assert status["subscribed_pools"] == 19
    assert status["v3_pools_initialized"] == 19
