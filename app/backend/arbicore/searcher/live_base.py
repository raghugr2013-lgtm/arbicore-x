"""Base live-SHADOW wiring (VPS-ready; fail-closed; no broadcasting).

Ties the proven T0/T1/T2 components to live Base infrastructure. Everything is
injectable so it is deterministically testable offline, and every dependency
fails closed when unconfigured (no fabricated liquidity/quotes/sims). SHADOW
only — nothing here can broadcast a transaction.

Pieces:
  * base_live_readiness()      — classifies each dependency ready/blocker.
  * make_base_reserves_fn/price_fn — real eth_call reserve reads + price feed
                                     for OnChainReserveTVLProvider.
  * AnvilProcessLauncher       — real `anvil --fork-url` launcher (ForkLauncher).
  * BaseWssSubscriber          — newHeads/logs → runtime.ingest_log/scan_block.
  * candidate_to_canonical     — bridge accepted SHADOW candidate → REAL
                                 CanonicalOpportunity (reuses T0-2 write-gate +
                                 existing verifier/paper/shadow/evidence).
"""
from __future__ import annotations

import os
import shutil
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ..config.persistent import resolve_rpc_url_from_env
from .route import Edge


# ── Readiness / blocker classification ─────────────────────────────────────
def base_live_readiness(*, tx_builder_wired: bool = False,
                        price_feed_wired: bool = False) -> Dict[str, Any]:
    rpc = resolve_rpc_url_from_env("base")
    ws = os.environ.get("ARBICORE_WSS_URL_BASE") or os.environ.get("ARBICORE_RPC_WSS_BASE")
    executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    anvil = shutil.which(os.environ.get("ARBICORE_ANVIL_PATH", "anvil"))
    checks = {
        "flag_enabled": ((os.environ.get("ARBICORE_T2_SEARCHER_ENABLED") or "")
                         .strip().lower() in {"1", "true", "yes", "on"}),
        "base_rpc": bool(rpc),
        "base_wss": bool(ws),
        "anvil_binary": bool(anvil),
        "executor_address": bool(executor),
        "tx_builder": bool(tx_builder_wired),
        "price_feed": bool(price_feed_wired),
    }
    # category per missing dependency
    cat = {
        "flag_enabled": "CONFIGURATION", "base_rpc": "CONFIGURATION",
        "base_wss": "CONFIGURATION", "anvil_binary": "CONFIGURATION",
        "executor_address": "CONFIGURATION", "tx_builder": "SOFTWARE",
        "price_feed": "CONFIGURATION",
    }
    blockers = [{"dependency": k, "category": cat[k]}
                for k, ok in checks.items() if not ok]
    return {"ready": len(blockers) == 0, "checks": checks, "blockers": blockers,
            "mode": "SHADOW", "broadcast": False}


# ── Real on-chain TVL hooks (eth_call injectable) ──────────────────────────
_GET_RESERVES_SELECTOR = "0x0902f1ac"   # UniswapV2Pair.getReserves()


def make_base_reserves_fn(
    eth_call: Callable[[str, str], Awaitable[Optional[str]]],
    pool_tokens: Dict[str, tuple],
):
    """Returns reserves_fn(chain,pool)->(t0,r0,t1,r1)|None using a real
    eth_call. pool_tokens maps pool->(token0,token1,dec0,dec1). Fail-closed."""
    async def reserves_fn(chain: str, pool: str):
        meta = pool_tokens.get(pool)
        if meta is None:
            return None
        t0, t1, d0, d1 = meta
        raw = await eth_call(pool, _GET_RESERVES_SELECTOR)
        if not raw or len(raw) < 2 + 64 * 2:
            return None
        h = raw[2:]
        try:
            r0 = int(h[0:64], 16) / (10 ** d0)
            r1 = int(h[64:128], 16) / (10 ** d1)
        except ValueError:
            return None
        if r0 <= 0 or r1 <= 0:
            return None
        return (t0, r0, t1, r1)
    return reserves_fn


def make_base_price_fn(price_source: Callable[[str], Awaitable[Optional[float]]]):
    """Wrap a real USD price source; None → fail closed (Gate 8 denies)."""
    async def price_fn(chain: str, token: str):
        try:
            p = await price_source(token)
        except Exception:  # noqa: BLE001
            return None
        return float(p) if p and p > 0 else None
    return price_fn


# ── Real Anvil fork launcher (ForkLauncher) ────────────────────────────────
class AnvilProcessLauncher:
    """Launches `anvil --fork-url <rpc>` and returns a JSON-RPC ForkHandle.

    Uses an injectable http_post for testability. Fail-closed: raises if the
    binary/port cannot be obtained (caller's backend converts to fail-closed).
    """

    def __init__(self, anvil_path: str = "anvil",
                 http_post: Optional[Callable[..., Awaitable[dict]]] = None) -> None:
        self._anvil_path = anvil_path
        self._http_post = http_post

    async def launch(self, rpc_url: str, block_number: Optional[int]):
        import asyncio
        args = [self._anvil_path, "--fork-url", rpc_url, "--port", "8546",
                "--silent"]
        if block_number is not None:
            args += ["--fork-block-number", str(int(block_number))]
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        # readiness poll
        url = "http://127.0.0.1:8546"
        post = self._http_post or _default_http_post
        for _ in range(50):
            try:
                r = await post(url, {"jsonrpc": "2.0", "id": 1,
                                     "method": "eth_blockNumber", "params": []})
                if r.get("result"):
                    return _AnvilHandle(proc, url, post)
            except Exception:  # noqa: BLE001
                pass
            await asyncio.sleep(0.1)
        proc.terminate()
        raise RuntimeError("anvil_fork_not_ready")


class _AnvilHandle:
    def __init__(self, proc, url, post):
        self._proc, self._url, self._post = proc, url, post

    async def eth_call(self, tx: dict) -> str:
        r = await self._post(self._url, {"jsonrpc": "2.0", "id": 1,
                                         "method": "eth_call",
                                         "params": [tx, "latest"]})
        return r.get("result", "0x")

    async def close(self) -> None:
        try:
            self._proc.terminate()
        except Exception:  # noqa: BLE001
            pass


async def _default_http_post(url, payload):  # pragma: no cover (needs network)
    import httpx
    async with httpx.AsyncClient(timeout=5.0) as c:
        return (await c.post(url, json=payload)).json()


# ── WSS subscriber: logs/newHeads → runtime ────────────────────────────────
def decode_sync_log(raw_log: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Decode a UniswapV2 Sync(uint112,uint112) event log → cache log dict."""
    data = raw_log.get("data", "")
    if not data or len(data) < 2 + 64 * 2:
        return None
    h = data[2:]
    try:
        r0 = int(h[0:64], 16); r1 = int(h[64:128], 16)
    except ValueError:
        return None
    return {"pool": (raw_log.get("address") or "").lower(), "event": "Sync",
            "reserve0": r0, "reserve1": r1,
            "block": int(raw_log.get("blockNumber", "0x0"), 16)}


class BaseWssSubscriber:
    """Feeds a BaseSearcherRuntime from a Base WSS stream. ``ws_client`` is an
    async iterator yielding decoded messages (injectable for tests)."""

    def __init__(self, runtime, ws_client, start_tokens: List[str],
                 *, amount_in: float = 1.0) -> None:
        self.runtime = runtime
        self.ws = ws_client
        self.start_tokens = start_tokens
        self.amount_in = amount_in
        self.blocks_scanned = 0

    async def run(self, max_messages: Optional[int] = None) -> Dict[str, Any]:
        results = []
        n = 0
        async for msg in self.ws:
            kind = msg.get("kind")
            if kind == "log":
                dec = decode_sync_log(msg["log"])
                if dec:
                    self.runtime.ingest_log(dec)
            elif kind == "newHead":
                block = int(msg.get("block", 0))
                res = await self.runtime.scan_block(block, self.start_tokens,
                                                    amount_in=self.amount_in)
                assert res["broadcast"] is False   # SHADOW invariant
                self.blocks_scanned += 1
                results.append(res["metrics"])
            n += 1
            if max_messages is not None and n >= max_messages:
                break
        return {"blocks_scanned": self.blocks_scanned, "scans": results}


# ── Bridge: accepted SHADOW candidate → REAL CanonicalOpportunity ──────────
def candidate_to_canonical(candidate: Dict[str, Any]):
    """Maps a SHADOW searcher candidate to a REAL CanonicalOpportunity so the
    EXISTING verifier/paper/shadow/certification/evidence pipeline consumes it
    (passes the T0-2 REAL-provenance write-gate). No new evidence path."""
    from ..models.canonical import CanonicalOpportunity
    from ..models.enums import (
        OpportunityType, OpportunityStatus, DataProvenance, MevRiskLevel,
    )
    route = candidate.get("route", [])
    return CanonicalOpportunity(
        opportunity_id="fl-base-" + "-".join(route),
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id="-".join(route), asset="WETH", chain="base",
        spread_pct=float(candidate.get("spot_ratio", 1.0) - 1.0) * 100.0,
        expected_profit_usd=float(candidate.get("expected_net_profit_usd", 0.0)),
        capital_required_usd=0.0,
        confidence_score=float(candidate.get("confidence", 0.7)) * 100.0,
        risk_score=25.0, mev_risk_level=MevRiskLevel.MEDIUM,
        source_data_quality=DataProvenance.REAL,        # live-quoted → REAL
        status=OpportunityStatus.CANDIDATE,
        metadata={"engine": "base_searcher_t2", "mode": "SHADOW",
                  "min_route_tvl_usd": candidate.get("min_route_tvl_usd"),
                  "block": candidate.get("block")},
    )


__all__ = [
    "base_live_readiness", "make_base_reserves_fn", "make_base_price_fn",
    "AnvilProcessLauncher", "BaseWssSubscriber", "decode_sync_log",
    "candidate_to_canonical",
]
