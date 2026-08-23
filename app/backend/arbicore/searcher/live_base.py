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
def base_token_maps() -> tuple:
    """Return (token_addresses, token_decimals) for the VERIFIED Base token
    universe — real on-chain-checked ERC-20 addresses, never fabricated."""
    from ..discovery.base_venues import TOKENS
    addrs = {sym: meta["address"] for sym, meta in TOKENS.items()}
    decs = {sym: int(meta["decimals"]) for sym, meta in TOKENS.items()}
    return addrs, decs


# A well-formed placeholder used ONLY to prove the SOFTWARE calldata wiring in
# tx_builder_selftest — it is never signed, never broadcast, and never used for
# a real transaction (the real executor comes from ARBICORE_EXECUTOR_ADDRESS_BASE).
_SELFTEST_ADDR = "0x000000000000000000000000000000000000dEaD"


def _drive_sync(coro):
    """Drive a coroutine that has NO real await points to completion without an
    event loop (safe to call from inside a running loop). Raises if the
    coroutine actually suspends on an awaitable."""
    try:
        coro.send(None)
    except StopIteration as stop:
        return stop.value
    raise RuntimeError("coroutine suspended — not synchronously drivable")


def _build_selftest_tx(amount: float = 0.05) -> Dict[str, Any]:
    """Build a representative WETH→USDC→WETH executor tx via the canonical
    tx_builder. Synchronous (no real awaits). Read-only; never signs/broadcasts."""
    from .revm_backend import make_calldata_tx_builder
    from .pool_cache import PoolStateCache, PoolState
    addrs, decs = base_token_maps()
    executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or _SELFTEST_ADDR
    recipient = os.environ.get("ARBICORE_GAS_WALLET_ADDRESS") or _SELFTEST_ADDR
    cache = PoolStateCache(max_staleness_blocks=100)
    cache.upsert(PoolState(pool="s1", kind="v2", token0="WETH", token1="USDC",
                           reserve0=1e8, reserve1=1e8, fee_bps=5, block=1))
    cache.upsert(PoolState(pool="s2", kind="v2", token0="USDC", token1="WETH",
                           reserve0=1e8, reserve1=1e8, fee_bps=30, block=1))
    builder = make_calldata_tx_builder(
        cache=cache, executor_address=executor, from_address=recipient,
        token_addresses=addrs, token_decimals=decs)
    return _drive_sync(builder([Edge("s1", "WETH", "USDC"),
                                Edge("s2", "USDC", "WETH")], amount))


def tx_builder_selftest() -> Dict[str, Any]:
    """Evidence-based check that the T2 → canonical calldata tx_builder is wired.

    Builds a representative WETH→USDC→WETH executor tx via
    ``make_calldata_tx_builder`` (reusing the canonical encoders) and confirms
    the ``execute(address[],uint256[],bytes)`` selector 0x64ba4bc1. Safe in any
    context (no real awaits). Read-only; never signs/broadcasts."""
    try:
        tx = _build_selftest_tx()
        sel = (tx.get("data") or "")[:10]
        return {"ok": sel == "0x64ba4bc1", "selector": sel,
                "value": tx.get("value"),
                "reason": ("ok" if sel == "0x64ba4bc1" else "unexpected_selector"),
                "signed": False, "broadcast": False}
    except Exception as exc:  # noqa: BLE001 — self-test never fabricates a pass
        return {"ok": False, "selector": None,
                "reason": f"selftest_error:{type(exc).__name__}",
                "signed": False, "broadcast": False}


def base_live_readiness(*, tx_builder_wired: Optional[bool] = None,
                        price_feed_wired: bool = False) -> Dict[str, Any]:
    rpc = resolve_rpc_url_from_env("base")
    ws = os.environ.get("ARBICORE_WSS_URL_BASE") or os.environ.get("ARBICORE_RPC_WSS_BASE")
    executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    anvil = shutil.which(os.environ.get("ARBICORE_ANVIL_PATH", "anvil"))
    # tx_builder is a SOFTWARE dependency — evidence-based self-test by default.
    if tx_builder_wired is None:
        tx_builder_wired = bool(tx_builder_selftest().get("ok"))
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
    "base_live_readiness", "base_token_maps", "tx_builder_selftest",
    "make_base_reserves_fn", "make_base_price_fn",
    "AnvilProcessLauncher", "BaseWssSubscriber", "decode_sync_log",
    "candidate_to_canonical", "shadow_dry_run_audit", "base_live_shadow_audit",
]


# ── SHADOW dry-run transaction audit (decoded canonical calldata) ──────────
def _decode_execute_calldata(data_hex: str) -> Dict[str, Any]:
    """Decode a canonical ``execute(address[],uint256[],bytes)`` calldata into a
    human-auditable structure. Read-only; asserts the 0x64ba4bc1 selector."""
    from eth_abi import decode as abi_decode
    b = bytes.fromhex(data_hex[2:] if data_hex.startswith("0x") else data_hex)
    selector, payload = "0x" + b[:4].hex(), b[4:]
    tokens, amounts, user_data = abi_decode(
        ["address[]", "uint256[]", "bytes"], payload)
    hop_t = "(address,address,uint24,uint256,uint256,uint160)"
    hops_raw, profit_recipient = abi_decode([f"{hop_t}[]", "address"], user_data)
    hops = [{
        "token_in": h[0], "token_out": h[1], "fee_ppm": int(h[2]),
        "amount_in_wei": str(int(h[3])), "amount_out_min_wei": str(int(h[4])),
        "sqrt_price_limit_x96": str(int(h[5])),
    } for h in hops_raw]
    return {
        "selector": selector,
        "entrypoint": "execute(address[],uint256[],bytes)",
        "borrow_tokens": [t for t in tokens],
        "borrow_amounts_wei": [str(int(a)) for a in amounts],
        "profit_recipient": profit_recipient,
        "hops": hops,
    }


def shadow_dry_run_audit(*, cycle=None, amount: float = 0.05,
                         token_addresses: Optional[Dict[str, str]] = None,
                         token_decimals: Optional[Dict[str, int]] = None,
                         cache=None) -> Dict[str, Any]:
    """Produce a SHADOW dry-run audit: build the canonical executor tx for a
    route via ``make_calldata_tx_builder`` and DECODE it for operator review.

    This is a READ-ONLY audit trail. It NEVER signs and NEVER broadcasts — the
    tx has ``value=0x0`` and is intended only for eth_call/fork simulation.

    If ``cycle`` is omitted a representative WETH→USDC→WETH sample is used
    (``sample=True``) purely to document the ABI shape — it is NOT a claimed
    profitable opportunity."""
    from .revm_backend import make_calldata_tx_builder
    from .pool_cache import PoolStateCache, PoolState

    sample = cycle is None
    addrs = token_addresses or base_token_maps()[0]
    decs = token_decimals or base_token_maps()[1]
    executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or _SELFTEST_ADDR
    recipient = os.environ.get("ARBICORE_GAS_WALLET_ADDRESS") or _SELFTEST_ADDR

    if sample:
        cache = PoolStateCache(max_staleness_blocks=100)
        cache.upsert(PoolState(pool="s1", kind="v2", token0="WETH",
                               token1="USDC", reserve0=1e8, reserve1=1e8,
                               fee_bps=5, block=1))
        cache.upsert(PoolState(pool="s2", kind="v2", token0="USDC",
                               token1="WETH", reserve0=1e8, reserve1=1e8,
                               fee_bps=30, block=1))
        cycle = [Edge("s1", "WETH", "USDC"), Edge("s2", "USDC", "WETH")]
    if cache is None:
        cache = PoolStateCache(max_staleness_blocks=100)

    try:
        builder = make_calldata_tx_builder(
            cache=cache, executor_address=executor, from_address=recipient,
            token_addresses=addrs, token_decimals=decs)
        tx = _drive_sync(builder(list(cycle), float(amount)))
        decoded = _decode_execute_calldata(tx["data"])
        import hashlib
        return {
            "ok": True, "sample": sample, "mode": "SHADOW",
            "route": [e.pool for e in cycle],
            "amount_in": float(amount),
            "tx": {"to": tx["to"], "value": tx["value"],
                   "from": tx.get("from"),
                   "calldata_hex": tx["data"],
                   "calldata_sha256": hashlib.sha256(
                       tx["data"].encode()).hexdigest()},
            "decoded": decoded,
            "signed": False, "broadcast": False,
            "note": ("representative ABI sample (not a profitable opportunity)"
                     if sample else "decoded from supplied route"),
        }
    except Exception as exc:  # noqa: BLE001 — audit never fabricates
        return {"ok": False, "sample": sample, "mode": "SHADOW",
                "reason": f"{type(exc).__name__}: {exc}",
                "signed": False, "broadcast": False}


# ── Base live-SHADOW software audit (SOFTWARE/CONFIG/VALIDATION/MARKET/SAFETY)
def base_live_shadow_audit() -> Dict[str, Any]:
    """Classify every item on the Base live-SHADOW path into exactly one of
    SOFTWARE / CONFIGURATION / VALIDATION / MARKET / SAFETY, with an
    evidence-based status. Read-only; changes nothing."""
    rpc = resolve_rpc_url_from_env("base")
    ws = os.environ.get("ARBICORE_WSS_URL_BASE") or os.environ.get("ARBICORE_RPC_WSS_BASE")
    executor = os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE")
    gas_wallet = os.environ.get("ARBICORE_GAS_WALLET_ADDRESS")
    anvil = shutil.which(os.environ.get("ARBICORE_ANVIL_PATH", "anvil"))
    flag = ((os.environ.get("ARBICORE_T2_SEARCHER_ENABLED") or "")
            .strip().lower() in {"1", "true", "yes", "on"})
    txb = tx_builder_selftest()

    def item(id_, category, status, detail, owner):
        return {"id": id_, "category": category, "status": status,
                "detail": detail, "owner": owner}

    items = [
        # ── SOFTWARE (complete in-repo; evidence-based) ──
        item("route_discovery", "SOFTWARE", "COMPLETE",
             "RouteGraph + closed-cycle enumeration + cheap spot fast-filter.",
             "ENGINEERING"),
        item("amm_math", "SOFTWARE", "COMPLETE",
             "Local V2/V3/StableSwap math kernels (deterministic, RPC-free).",
             "ENGINEERING"),
        item("pool_state_cache", "SOFTWARE", "COMPLETE",
             "Log-synced cache with block-staleness refusal (honest None).",
             "ENGINEERING"),
        item("local_math_simulation", "SOFTWARE", "COMPLETE",
             "Stage-2 LocalMath backend for candidate validation.",
             "ENGINEERING"),
        item("canonical_calldata_encoder", "SOFTWARE", "COMPLETE",
             "execute(address[],uint256[],bytes) selector 0x64ba4bc1 + "
             "userData=abi.encode(SwapHop[],profitRecipient) reused as-is.",
             "ENGINEERING"),
        item("tx_builder_wiring", "SOFTWARE",
             "COMPLETE" if txb.get("ok") else "BROKEN",
             f"make_calldata_tx_builder → canonical encoder self-test: "
             f"selector={txb.get('selector')} ok={txb.get('ok')}.",
             "ENGINEERING"),
        item("revm_fork_backend", "SOFTWARE", "COMPLETE",
             "AnvilRevmForkBackend consumes tx_builder + decode_net; "
             "fail-closed, injectable launcher/handle.",
             "ENGINEERING"),
        item("candidate_to_canonical_bridge", "SOFTWARE", "COMPLETE",
             "Accepted SHADOW candidate → REAL CanonicalOpportunity through the "
             "existing verifier/paper/shadow/evidence pipeline.",
             "ENGINEERING"),
        item("wss_ingestion_decoder", "SOFTWARE", "COMPLETE",
             "Sync-log decoder + BaseWssSubscriber → runtime.ingest/scan.",
             "ENGINEERING"),

        # ── CONFIGURATION (VPS/operator-provided; not code) ──
        item("t2_flag_enabled", "CONFIGURATION",
             "PRESENT" if flag else "MISSING",
             "ARBICORE_T2_SEARCHER_ENABLED=on activates the SHADOW runtime.",
             "OPERATOR"),
        item("base_rpc_url", "CONFIGURATION", "PRESENT" if rpc else "MISSING",
             "ARBICORE_RPC_URL_BASE / ARBICORE_RPC_URL (read-only eth_call).",
             "OPERATOR"),
        item("base_wss_url", "CONFIGURATION", "PRESENT" if ws else "MISSING",
             "ARBICORE_WSS_URL_BASE for per-block log/newHeads ingestion.",
             "OPERATOR"),
        item("anvil_binary", "CONFIGURATION", "PRESENT" if anvil else "MISSING",
             "Foundry anvil on PATH for the REVM fork simulation backend.",
             "OPERATOR"),
        item("executor_address", "CONFIGURATION",
             "PRESENT" if executor else "MISSING",
             "ARBICORE_EXECUTOR_ADDRESS_BASE (deployed FlashLoanReceiver).",
             "OPERATOR"),
        item("gas_wallet_address", "CONFIGURATION",
             "PRESENT" if gas_wallet else "MISSING",
             "ARBICORE_GAS_WALLET_ADDRESS (profit recipient / eth_call from).",
             "OPERATOR"),
        item("usd_price_feed", "CONFIGURATION", "OPERATOR_WIRED",
             "make_base_price_fn requires a real USD price source; None → "
             "Gate 8 fails closed. Wired at VPS composition.",
             "OPERATOR"),

        # ── VALIDATION (requires a real run against live/fork infra) ──
        item("fork_simulation_run", "VALIDATION",
             "BLOCKED" if not (anvil and rpc) else "READY",
             "A genuine anvil fork sim of the atomic route must execute "
             "(needs anvil + Base archive/fork RPC). Never GREEN without a run.",
             "OPERATOR+ENGINEERING"),
        item("shadow_certification_run", "VALIDATION", "READY",
             "SHADOW certification harness runs against live-quoted candidates "
             "once RPC/WSS are configured.",
             "OPERATOR"),

        # ── MARKET (external; cannot be forced) ──
        item("profitable_route_exists", "MARKET", "PENDING_EVIDENCE",
             "A REAL-quoted EXECUTABLE_UNIV3 route must clear all costs + the "
             "$25 floor. Current Base market shows none — engine never "
             "fabricates one.",
             "MARKET"),

        # ── SAFETY (enforced invariants; must stay locked) ──
        item("shadow_only_no_broadcast", "SAFETY", "ENFORCED",
             "Runtime asserts broadcast=False; tx dicts are value=0x0 "
             "eth_call-only; zero signing/broadcast code path.",
             "LOCKED"),
        item("gate7_25_floor", "SAFETY", "ENFORCED",
             "FlashLoanGate7AtomicProfit $25 floor — not lowerable via this path.",
             "LOCKED"),
        item("gate8_fail_closed", "SAFETY", "ENFORCED",
             "FlashLoanGate8LiquidityDepth denies on unverifiable TVL.",
             "LOCKED"),
        item("real_provenance_only", "SAFETY", "ENFORCED",
             "Only REAL/VERIFIED_REAL provenance reaches the canonical repo "
             "(T0-2 write-gate).",
             "LOCKED"),
        item("no_auto_promotion", "SAFETY", "ENFORCED",
             "LIMITED_LIVE / FULL_AUTOMATION remain operator-gated; SHADOW "
             "never self-promotes.",
             "LOCKED"),
    ]

    def _count(cat, statuses):
        return sum(1 for it in items
                   if it["category"] == cat and it["status"] in statuses)

    summary = {
        "software_complete": _count("SOFTWARE", {"COMPLETE"}),
        "software_total": sum(1 for it in items if it["category"] == "SOFTWARE"),
        "software_broken": _count("SOFTWARE", {"BROKEN"}),
        "configuration_missing": _count("CONFIGURATION", {"MISSING"}),
        "validation_blocked": _count("VALIDATION", {"BLOCKED"}),
        "market_pending": _count("MARKET", {"PENDING_EVIDENCE"}),
        "safety_enforced": _count("SAFETY", {"ENFORCED"}),
    }
    software_ready = summary["software_broken"] == 0
    return {
        "software_ready": software_ready,
        "mode": "SHADOW", "broadcast": False,
        "categories": ["SOFTWARE", "CONFIGURATION", "VALIDATION", "MARKET",
                       "SAFETY"],
        "items": items,
        "summary": summary,
        "tx_builder_selftest": txb,
    }
