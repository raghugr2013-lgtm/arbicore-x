"""T2 Base WSS ingestion — application-level lifecycle wiring (SHADOW-only).

Connects the ALREADY-IMPLEMENTED `BaseSearcherRuntime` + `BaseWssSubscriber`
to a live Base WSS endpoint so per-block `newHeads` (and relevant Sync logs)
drive `runtime.scan_block()`. This module adds ONLY the missing runtime glue:

  * ``BaseWssClient``   — a minimal JSON-RPC-over-WSS async iterator that
    ``eth_subscribe``s to ``newHeads`` (+ Sync logs for known pools) and yields
    the normalized message shape the existing subscriber consumes. The websocket
    connector is injectable for deterministic tests.
  * ``T2WssManager``    — owns the start/stop lifecycle, reconnect-with-backoff,
    and observable telemetry. Reuses ONE ``BaseWssSubscriber`` across reconnects
    so counters accumulate.

INVARIANTS: never signs, never broadcasts (SHADOW). It NEVER fabricates blocks
or opportunities — telemetry only reflects messages actually received, and a
successful WSS connection does NOT flip any readiness gate to PASSED.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

from .live_base import BaseWssSubscriber
from .runtime import BaseSearcherRuntime, searcher_enabled

logger = logging.getLogger("arbicore.searcher.wss")

# Uniswap V2 / Aerodrome-classic `Sync(uint112,uint112)` topic0.
_SYNC_TOPIC0 = "0x1c411e9a96e071241c2f21f7726b17ae89e3cab4c78be50e062b03a9fffbbad1"


def resolve_base_wss_url() -> Optional[str]:
    """Primary ARBICORE_WSS_URL_BASE, fallback ARBICORE_RPC_WSS_BASE (matches the
    precedence the rest of the T2 runtime uses). None → no WSS configured."""
    return (os.environ.get("ARBICORE_WSS_URL_BASE")
            or os.environ.get("ARBICORE_RPC_WSS_BASE") or None)


class BaseWssClient:
    """One WSS session as an async iterator of normalized runtime messages.

    Ends (StopAsyncIteration / raises) when the connection drops — the manager
    handles reconnect. ``connect`` is injectable (defaults to websockets.connect).
    """

    def __init__(self, url: str, *,
                 pool_addresses: Optional[List[str]] = None,
                 connect: Optional[Callable[..., Any]] = None,
                 on_connected: Optional[Callable[[], None]] = None) -> None:
        self._url = url
        self._pools = [a.lower() for a in (pool_addresses or []) if a]
        self._connect = connect
        self._on_connected = on_connected

    def _default_connect(self):
        import websockets
        return websockets.connect(self._url, ping_interval=20, ping_timeout=20,
                                  max_size=8 * 1024 * 1024)

    async def __aiter__(self):
        connector = self._connect(self._url) if self._connect else self._default_connect()
        async with connector as ws:
            if self._on_connected:
                self._on_connected()
            # Subscribe to newHeads (always) + Sync logs for known pools (if any).
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": 1,
                                      "method": "eth_subscribe",
                                      "params": ["newHeads"]}))
            if self._pools:
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": 2, "method": "eth_subscribe",
                    "params": ["logs", {"address": self._pools,
                                        "topics": [_SYNC_TOPIC0]}]}))
            async for raw in ws:
                msg = self._normalize(raw)
                if msg is not None:
                    yield msg

    @staticmethod
    def _normalize(raw: Any) -> Optional[Dict[str, Any]]:
        try:
            obj = json.loads(raw) if isinstance(raw, (str, bytes, bytearray)) else raw
        except (ValueError, TypeError):
            return None
        if not isinstance(obj, dict):
            return None
        params = obj.get("params")
        if not isinstance(params, dict):
            return None                      # subscription-id acks etc.
        result = params.get("result")
        if not isinstance(result, dict):
            return None
        # newHeads carry a block "number"; logs carry "topics"/"data"/"address".
        if "number" in result and "topics" not in result:
            try:
                return {"kind": "newHead", "block": int(result["number"], 16)}
            except (ValueError, TypeError):
                return None
        if "topics" in result or ("data" in result and "address" in result):
            return {"kind": "log", "log": {
                "address": result.get("address", ""),
                "blockNumber": result.get("blockNumber", "0x0"),
                "data": result.get("data", "0x"),
                "topics": result.get("topics", []),
            }}
        return None


class T2WssManager:
    """Start/stop lifecycle + reconnect + telemetry for the T2 WSS subscriber.

    SHADOW-only: drives ``runtime.scan_block`` via the existing subscriber; never
    signs or broadcasts. Never fabricates — telemetry reflects only real events.
    """

    def __init__(self, runtime: BaseSearcherRuntime, wss_url: str, *,
                 start_tokens: Optional[List[str]] = None,
                 amount_in: float = 1.0,
                 client_factory: Optional[Callable[[], Any]] = None,
                 base_backoff_s: float = 1.0,
                 max_backoff_s: float = 30.0) -> None:
        self._runtime = runtime
        self._url = wss_url
        self._start_tokens = start_tokens or ["WETH", "USDC"]
        self._amount_in = amount_in
        self._client_factory = client_factory
        self._base_backoff = base_backoff_s
        self._max_backoff = max_backoff_s
        self._subscriber = BaseWssSubscriber(
            runtime, None, self._start_tokens, amount_in=amount_in)
        self._task: Optional[asyncio.Task] = None
        self._stopping = False
        self._connected = False
        self._reconnect_count = 0
        self._started_at: Optional[str] = None

    # ── lifecycle ──────────────────────────────────────────────────────────
    async def start(self) -> Dict[str, Any]:
        if self._task and not self._task.done():
            return {"started": False, "reason": "already_running", **self.status()}
        self._stopping = False
        from datetime import datetime, timezone
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._task = asyncio.create_task(self._run_forever())
        logger.info("T2 Base WSS subscriber started (SHADOW, no-broadcast) url=%s",
                    _mask(self._url))
        return {"started": True, **self.status()}

    async def stop(self) -> Dict[str, Any]:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._connected = False
        return {"stopped": True, **self.status()}

    def _new_client(self):
        if self._client_factory:
            return self._client_factory()
        return BaseWssClient(self._url, on_connected=self._mark_connected)

    def _mark_connected(self):
        self._connected = True
        logger.info("T2 Base WSS connected url=%s", _mask(self._url))

    async def _run_forever(self):
        backoff = self._base_backoff
        while not self._stopping:
            try:
                client = self._new_client()
                # injected fakes may not use on_connected — mark on stream start
                self._connected = True
                self._subscriber.ws = client
                await self._subscriber.run()      # consumes until disconnect
                # clean end of stream → treat as a disconnect, reconnect
                raise ConnectionError("wss_stream_ended")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — reconnect on ANY drop
                self._connected = False
                if self._stopping:
                    break
                self._reconnect_count += 1
                logger.warning("T2 Base WSS disconnected (%s) — reconnect #%d in %.1fs",
                               type(exc).__name__, self._reconnect_count, backoff)
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    raise
                backoff = min(self._max_backoff, backoff * 2)
            else:
                backoff = self._base_backoff

    # ── telemetry ───────────────────────────────────────────────────────────
    @property
    def running(self) -> bool:
        return bool(self._task and not self._task.done())

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": True,
            "mode": "SHADOW",
            "broadcast": False,
            "running": self.running,
            "connected": self._connected,
            "wss_url_present": bool(self._url),
            "wss_url_masked": _mask(self._url),
            "started_at": self._started_at,
            "newheads_received": self._subscriber.newheads_received,
            "blocks_scanned": self._subscriber.blocks_scanned,
            "logs_ingested": self._subscriber.logs_ingested,
            "last_block": self._subscriber.last_block,
            "reconnect_count": self._reconnect_count,
        }


def _mask(url: Optional[str]) -> Optional[str]:
    """Mask any API-key path/query in a WSS url for safe telemetry/logging."""
    if not url:
        return None
    try:
        head, _, tail = url.partition("://")
        host = tail.split("/", 1)[0]
        return f"{head}://{host}/***"
    except Exception:  # noqa: BLE001
        return "***"


def maybe_build_t2_wss_manager(
    runtime: Optional[BaseSearcherRuntime],
    *, client_factory: Optional[Callable[[], Any]] = None,
) -> Optional[T2WssManager]:
    """Flag-gated factory. Returns None unless the T2 searcher is enabled, a
    runtime exists, AND a Base WSS url is configured (SOFTWARE wiring only —
    presence of a URL is CONFIGURATION and enforced at deploy preflight)."""
    if runtime is None or not searcher_enabled():
        return None
    url = resolve_base_wss_url()
    if not url:
        logger.info("T2 WSS manager not started: ARBICORE_WSS_URL_BASE/"
                    "ARBICORE_RPC_WSS_BASE not configured")
        return None
    return T2WssManager(runtime, url, client_factory=client_factory)


__all__ = ["BaseWssClient", "T2WssManager", "resolve_base_wss_url",
           "maybe_build_t2_wss_manager"]
