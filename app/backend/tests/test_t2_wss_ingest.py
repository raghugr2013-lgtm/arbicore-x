"""T2 Base WSS ingestion lifecycle — deterministic offline tests.

Proves the application-level wiring: the manager starts the existing
BaseWssSubscriber, feeds injected newHead/log events into the existing
BaseSearcherRuntime (invoking scan_block / ingest_log), exposes telemetry, and
reconnects safely — all SHADOW, broadcast=false, no fabrication.
"""
import asyncio
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_test")


def _runtime():
    from arbicore.searcher.pool_cache import PoolStateCache, PoolState
    from arbicore.searcher.route import RouteGraph
    from arbicore.searcher.runtime import BaseSearcherRuntime
    cache = PoolStateCache(max_staleness_blocks=100)
    graph = RouteGraph()
    cache.upsert(PoolState(pool="0xp", kind="v2", token0="WETH", token1="USDC",
                           reserve0=1e8, reserve1=1e8, fee_bps=30, block=1))
    graph.add_pool("0xp", "WETH", "USDC")
    return BaseSearcherRuntime(cache=cache, graph=graph)


class _FakeClient:
    """Async-iterable fake WSS session (mirrors BaseWssClient's contract)."""
    def __init__(self, messages, *, raise_exc=None, hang_after=False):
        self._messages = messages
        self._raise = raise_exc
        self._hang = hang_after

    async def __aiter__(self):
        if self._raise is not None:
            raise self._raise
        for m in self._messages:
            yield m
        if self._hang:
            await asyncio.Event().wait()   # stay "connected" (never end)


# ── normalization ──────────────────────────────────────────────────────────
def test_wss_client_normalizes_newhead_log_and_ignores_acks():
    from arbicore.searcher.wss_ingest import BaseWssClient
    nh = BaseWssClient._normalize(
        '{"params":{"subscription":"0x1","result":{"number":"0x10"}}}')
    assert nh == {"kind": "newHead", "block": 16}
    lg = BaseWssClient._normalize({"params": {"result": {
        "address": "0xPOOL", "blockNumber": "0x11",
        "data": "0x" + format(5, "064x") + format(7, "064x"),
        "topics": ["0xsync"]}}})
    assert lg["kind"] == "log" and lg["log"]["address"] == "0xPOOL"
    # subscription-id ack (no params.result dict) → ignored
    assert BaseWssClient._normalize('{"id":1,"result":"0xsubid"}') is None


# ── flag/config gating ──────────────────────────────────────────────────────
def test_maybe_build_manager_gating(monkeypatch):
    from arbicore.searcher.wss_ingest import maybe_build_t2_wss_manager
    rt = _runtime()
    for k in ("ARBICORE_WSS_URL_BASE", "ARBICORE_RPC_WSS_BASE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.delenv("ARBICORE_T2_SEARCHER_ENABLED", raising=False)
    assert maybe_build_t2_wss_manager(rt) is None            # flag off
    monkeypatch.setenv("ARBICORE_T2_SEARCHER_ENABLED", "true")
    assert maybe_build_t2_wss_manager(rt) is None            # no WSS url
    monkeypatch.setenv("ARBICORE_WSS_URL_BASE", "wss://base.example/ws/KEY")
    mgr = maybe_build_t2_wss_manager(rt)
    assert mgr is not None and mgr.status()["mode"] == "SHADOW"
    # url masked in telemetry (no key leak)
    assert "KEY" not in (mgr.status()["wss_url_masked"] or "")


# ── lifecycle: startup path invokes subscriber + processes events ───────────
async def test_manager_start_processes_newheads_and_logs_shadow():
    from arbicore.searcher.wss_ingest import T2WssManager
    rt = _runtime()
    log_msg = {"kind": "log", "log": {
        "address": "0xp", "blockNumber": "0x2",
        "data": "0x" + format(2_000_000, "064x") + format(1_000_000, "064x")}}
    msgs = [{"kind": "newHead", "block": 10}, log_msg,
            {"kind": "newHead", "block": 11}]
    # hang_after=True keeps the single session open → no reconnect, stays connected
    mgr = T2WssManager(rt, "wss://base.example/ws", start_tokens=["WETH"],
                       amount_in=100.0,
                       client_factory=lambda: _FakeClient(msgs, hang_after=True),
                       base_backoff_s=0.01)
    await mgr.start()
    # wait until both newHeads are scanned
    for _ in range(200):
        if mgr.status()["blocks_scanned"] >= 2:
            break
        await asyncio.sleep(0.01)
    st = mgr.status()
    await mgr.stop()

    assert st["running"] is True and st["connected"] is True
    assert st["mode"] == "SHADOW" and st["broadcast"] is False
    assert st["newheads_received"] == 2 and st["blocks_scanned"] == 2
    assert st["last_block"] == 11
    assert st["logs_ingested"] == 1                      # Sync log applied
    assert rt.cache.get("0xp").reserve0 == 2_000_000     # cache updated via ingest
    assert st["reconnect_count"] == 0


# ── reconnect safety ─────────────────────────────────────────────────────────
async def test_manager_reconnects_on_disconnect():
    from arbicore.searcher.wss_ingest import T2WssManager
    rt = _runtime()
    calls = {"n": 0}

    def factory():
        calls["n"] += 1
        if calls["n"] == 1:
            # first session drops immediately (raises) → triggers reconnect
            return _FakeClient([], raise_exc=ConnectionError("drop"))
        # subsequent sessions deliver a block then hang (stable)
        return _FakeClient([{"kind": "newHead", "block": 20}], hang_after=True)

    mgr = T2WssManager(rt, "wss://base.example/ws", start_tokens=["WETH"],
                       amount_in=100.0, client_factory=factory,
                       base_backoff_s=0.01, max_backoff_s=0.05)
    await mgr.start()
    for _ in range(300):
        if mgr.status()["blocks_scanned"] >= 1 and mgr.status()["reconnect_count"] >= 1:
            break
        await asyncio.sleep(0.01)
    st = mgr.status()
    await mgr.stop()

    assert st["reconnect_count"] >= 1        # recovered from the drop
    assert st["blocks_scanned"] >= 1         # scanned after reconnect
    assert st["last_block"] == 20
    assert st["broadcast"] is False


async def test_manager_stop_is_clean():
    from arbicore.searcher.wss_ingest import T2WssManager
    rt = _runtime()
    mgr = T2WssManager(rt, "wss://base.example/ws",
                       client_factory=lambda: _FakeClient(
                           [{"kind": "newHead", "block": 1}], hang_after=True),
                       base_backoff_s=0.01)
    await mgr.start()
    await asyncio.sleep(0.05)
    out = await mgr.stop()
    assert out["stopped"] is True and mgr.running is False
