"""BlockDAG RPC client with automatic primary→secondary failover.

This module is the production chain-data layer for Wallet Observer. It uses
**RPC block-walking** (not explorer APIs) because the diagnostic proved:

  • rpc.bdagscan.com           — full EVM compat, chain_id 1404 ✓
  • rpc.blockdag.engineering   — 403 Forbidden to server-side requests
  • bdagscan.com               — HTML-only frontend (no JSON API)
  • explorer.blockdag.engineering — 403 Forbidden

Block walking detects every native BDAG transfer touching the operator's
address. We persist the last scanned block per address in
`observer_block_cursor` and only fetch the new range each tick (bounded by
`MAX_BLOCKS_PER_TICK` to keep poll latency predictable).

Failover semantics
------------------
Each RPC call:
  1. Try primary URL. Success → record HEALTHY for primary, return.
  2. On HTTP/transport/JSON-RPC error → mark primary DEGRADED, try secondary.
  3. On secondary success → record HEALTHY for secondary, return + log failover.
  4. On both fail → raise ChainRPCError (poller catches and logs).
Health snapshots are persisted in the observer_config doc under
`rpc_health` for the UI.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

DEFAULT_PRIMARY = "https://rpc.bdagscan.com"
DEFAULT_SECONDARY = "https://rpc.blockdag.engineering"
EXPECTED_CHAIN_ID = 1404
DEFAULT_HTTP_TIMEOUT_S = 12.0
MAX_BLOCKS_PER_TICK = 200


class ChainRPCError(RuntimeError):
    """All configured RPC endpoints failed for a given call."""


@dataclass
class _EndpointResult:
    url: str
    ok: bool
    latency_ms: float
    error: str | None = None
    chain_id: int | None = None
    block_number: int | None = None


class BlockDAGRPCClient:
    """Thin EVM JSON-RPC client with primary/secondary failover.

    *No* signing, *no* state-changing calls. All methods are read-only.
    """

    def __init__(self, primary: str | None = None, secondary: str | None = None,
                 timeout_s: float = DEFAULT_HTTP_TIMEOUT_S):
        self.primary = (primary or DEFAULT_PRIMARY).rstrip("/")
        self.secondary = (secondary or "").rstrip("/") or None
        self.timeout_s = timeout_s
        # health = {url: {"healthy": bool, "last_check_at": ts, "last_latency_ms": float,
        #                "last_error": str | None, "consecutive_failures": int}}
        self.health: dict[str, dict] = {self.primary: self._fresh_health()}
        if self.secondary:
            self.health[self.secondary] = self._fresh_health()
        self._lock = asyncio.Lock()
        # debug toggles (used by tests + the UI's "Force primary down" button)
        self._force_primary_down = (
            os.environ.get("ARBICORE_FORCE_PRIMARY_DOWN", "").lower() in ("1", "true", "yes")
        )

    # ----------------------------- internals ----------------------------------
    @staticmethod
    def _fresh_health():
        return {"healthy": True, "last_check_at": None,
                "last_latency_ms": None, "last_error": None,
                "consecutive_failures": 0, "consecutive_successes": 0,
                "total_calls": 0, "total_failures": 0}

    def force_primary_down(self, flag: bool) -> None:
        """UI/test hook — when True the primary is treated as offline so we can
        prove the failover path lives without taking the real endpoint down."""
        self._force_primary_down = bool(flag)

    def _endpoints(self) -> list[str]:
        out = []
        if not self._force_primary_down:
            out.append(self.primary)
        if self.secondary:
            out.append(self.secondary)
        if self._force_primary_down:
            # ensure primary is still recorded as forced-down
            out.append(self.primary)
        return out

    async def _call_one(self, url: str, method: str, params: list) -> dict:
        h = self.health[url]
        h["total_calls"] = h.get("total_calls", 0) + 1
        t0 = time.perf_counter()
        if self._force_primary_down and url == self.primary:
            h["healthy"] = False
            h["last_error"] = "forced-down (debug toggle)"
            h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
            h["last_check_at"] = time.time()
            raise httpx.ConnectError("forced-down")
        try:
            async with httpx.AsyncClient(timeout=self.timeout_s) as cx:
                r = await cx.post(url, json={"jsonrpc": "2.0", "id": 1,
                                              "method": method, "params": params})
                r.raise_for_status()
                body = r.json()
                if "error" in body and body["error"]:
                    raise ValueError(f"jsonrpc error: {body['error']}")
                h["healthy"] = True
                h["last_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
                h["last_check_at"] = time.time()
                h["last_error"] = None
                h["consecutive_failures"] = 0
                h["consecutive_successes"] = h.get("consecutive_successes", 0) + 1
                return body
        except (httpx.HTTPError, ValueError) as e:
            h["healthy"] = False
            h["last_latency_ms"] = round((time.perf_counter() - t0) * 1000, 1)
            h["last_check_at"] = time.time()
            h["last_error"] = f"{type(e).__name__}: {e}"
            h["consecutive_failures"] = h.get("consecutive_failures", 0) + 1
            h["consecutive_successes"] = 0
            h["total_failures"] = h.get("total_failures", 0) + 1
            raise

    async def _call(self, method: str, params: list) -> dict:
        last_err = None
        for url in self._endpoints():
            try:
                body = await self._call_one(url, method, params)
                if url != self.primary and not self._force_primary_down:
                    logger.warning("[blockdag_rpc] failover: served %s via SECONDARY (%s)", method, url)
                elif url == self.secondary and self._force_primary_down:
                    logger.info("[blockdag_rpc] primary forced-down → served %s via SECONDARY", method)
                return body
            except (httpx.HTTPError, ValueError) as e:
                logger.info("[blockdag_rpc] %s failed at %s: %s", method, url, e)
                last_err = e
                continue
        raise ChainRPCError(f"all endpoints failed for {method}: {last_err}")

    # ----------------------------- public RPC ---------------------------------
    async def chain_id(self) -> int:
        body = await self._call("eth_chainId", [])
        return int(body["result"], 16)

    async def block_number(self) -> int:
        body = await self._call("eth_blockNumber", [])
        return int(body["result"], 16)

    async def get_balance(self, address: str, block: str = "latest") -> int:
        body = await self._call("eth_getBalance", [address, block])
        return int(body["result"], 16)

    async def get_block_with_txs(self, block_number: int) -> dict:
        body = await self._call("eth_getBlockByNumber", [hex(block_number), True])
        return body.get("result") or {}

    async def get_tx(self, tx_hash: str) -> dict | None:
        body = await self._call("eth_getTransactionByHash", [tx_hash])
        return body.get("result")

    async def get_tx_receipt(self, tx_hash: str) -> dict | None:
        body = await self._call("eth_getTransactionReceipt", [tx_hash])
        return body.get("result")

    # ----------------------------- health snapshot ----------------------------
    def health_snapshot(self) -> dict:
        return {
            "primary": {"url": self.primary,
                        "force_down": self._force_primary_down,
                        **self.health.get(self.primary, self._fresh_health())},
            "secondary": ({"url": self.secondary,
                            **self.health.get(self.secondary, self._fresh_health())}
                          if self.secondary else None),
            "expected_chain_id": EXPECTED_CHAIN_ID,
        }

    # ----------------------------- block walker -------------------------------
    async def scan_address(self, address: str, from_block: int, to_block: int) -> list[dict]:
        """Walk [from_block..to_block] inclusive, return native txs touching
        the address (either side). Returns list of normalised dicts."""
        address_lc = address.lower()
        out: list[dict] = []
        if from_block > to_block:
            return out
        # cap range
        if to_block - from_block + 1 > MAX_BLOCKS_PER_TICK:
            from_block = to_block - MAX_BLOCKS_PER_TICK + 1
        for bn in range(from_block, to_block + 1):
            blk = await self.get_block_with_txs(bn)
            for tx in (blk.get("transactions") or []):
                frm = (tx.get("from") or "").lower()
                to = (tx.get("to") or "").lower()
                if frm != address_lc and to != address_lc:
                    continue
                try:
                    val_wei = int(tx.get("value", "0x0"), 16)
                except (TypeError, ValueError):
                    val_wei = 0
                out.append({
                    "tx_hash": tx.get("hash"),
                    "from": tx.get("from"),
                    "to": tx.get("to"),
                    "value": val_wei / 1e18,
                    "asset": "BDAG",
                    "block_number": bn,
                    "ts": blk.get("timestamp"),
                })
        return out
