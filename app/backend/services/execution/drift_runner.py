"""Historical Drift Runner — background worker that periodically recomputes
the drift_analysis_cache for the configured (symbol, venue) pairs.

This is a parallel intelligence layer; it never blocks, never mutates other
state, and is fully optional. If the engine raises, the worker logs and retries
on the next tick.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Iterable

from services import db
from services.execution import drift_engine

logger = logging.getLogger("drift_runner")
# History TTL (7 days) for the append-only drift_analysis_history collection
HISTORY_TTL_SECONDS = 7 * 86400


class DriftRunner:
    """Async polling worker. Default cadence 10 min; configurable via execution_config."""

    def __init__(self, default_period_s: int = 600):
        self.default_period_s = default_period_s
        self._task: asyncio.Task | None = None
        self._running = False
        self._last_run_at: str | None = None
        self._last_error: str | None = None
        self._last_snapshot_meta: dict | None = None

    # --------------------------------------------------------------
    # Lifecycle
    # --------------------------------------------------------------
    async def start(self):
        if self._running:
            return
        self._running = True
        await ensure_indexes()
        self._task = asyncio.create_task(self._loop())
        logger.info("drift_runner started (default period %ss)", self.default_period_s)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self):
        # First-run delay so we don't compete with collector boot
        await asyncio.sleep(30)
        while self._running:
            try:
                await self.run_once()
            except asyncio.CancelledError:
                return
            except Exception as e:  # noqa: BLE001 — never crash the worker
                self._last_error = str(e)[:300]
                logger.warning("drift_runner tick failed: %s", e)
            await asyncio.sleep(self._period_s())

    def _period_s(self) -> int:
        # Could be reloaded from execution_config in future; safe default for v1.
        return self.default_period_s

    # --------------------------------------------------------------
    # Compute + persist
    # --------------------------------------------------------------
    async def run_once(self, symbols: Iterable[tuple[str, str]] | None = None) -> list[dict]:
        """Recompute snapshots for the configured pairs. Returns list of summaries."""
        pairs = list(symbols) if symbols else [("BDAGUSDT", "coinstore")]
        # Resolve live entry-price + current-spread context once per tick.
        ctx = await _resolve_live_context()
        summaries: list[dict] = []
        for symbol, venue in pairs:
            try:
                snap = await drift_engine.compute_snapshot(
                    symbol=symbol, venue=venue,
                    entry_price=ctx.get("entry_price"),
                    entry_price_source=ctx.get("entry_price_source"),
                    current_spread_pct=ctx.get("current_spread_pct"),
                    expected_cycle_s=ctx.get("expected_cycle_s") or 600,
                    cycle_source=ctx.get("cycle_source") or "fallback_default",
                )
                await _persist_snapshot(snap)
                self._last_run_at = snap["computed_at"]
                self._last_error = None
                self._last_snapshot_meta = {
                    "symbol": symbol, "venue": venue,
                    "computed_at": snap["computed_at"],
                    "compute_time_ms": snap.get("compute_time_ms"),
                    "regime": (snap.get("regime") or {}).get("label"),
                    "risk_label": (snap.get("risk_score") or {}).get("label"),
                    "risk_score": (snap.get("risk_score") or {}).get("score_0_100"),
                }
                summaries.append(self._last_snapshot_meta)
            except Exception as e:  # noqa: BLE001
                self._last_error = f"{symbol}@{venue}: {str(e)[:200]}"
                logger.warning("drift_runner pair %s@%s failed: %s", symbol, venue, e)
                summaries.append({"symbol": symbol, "venue": venue, "error": str(e)[:200]})
        return summaries

    # --------------------------------------------------------------
    # Status (for /api/execution/drift-analysis/status)
    # --------------------------------------------------------------
    async def status(self) -> dict:
        latest_count = await db.client.get_database(
            db.db.name).get_collection("drift_analysis_cache").count_documents({})
        return {
            "running": self._running,
            "default_period_s": self.default_period_s,
            "last_run_at": self._last_run_at,
            "last_error": self._last_error,
            "last_snapshot": self._last_snapshot_meta,
            "cache_size": latest_count,
        }


# ------------------------------------------------------------------
# Persistence helpers (kept local to the runner module)
# ------------------------------------------------------------------
async def ensure_indexes():
    cache = db.db.drift_analysis_cache
    history = db.db.drift_analysis_history
    await cache.create_index([("symbol", 1), ("venue", 1)], unique=True)
    await cache.create_index([("computed_at_ts", -1)])
    await history.create_index([("symbol", 1), ("venue", 1), ("computed_at_ts", -1)])
    await history.create_index("expires_at", expireAfterSeconds=0)


async def _persist_snapshot(snap: dict):
    """Upsert into drift_analysis_cache (single latest), append into drift_analysis_history."""
    if not snap or "symbol" not in snap or "venue" not in snap:
        return
    snap_with_expiry = dict(snap)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=HISTORY_TTL_SECONDS)
    snap_with_expiry["expires_at"] = expires_at
    cache = db.db.drift_analysis_cache
    history = db.db.drift_analysis_history
    # Cache: upsert the single latest per (symbol, venue)
    await cache.update_one({"symbol": snap["symbol"], "venue": snap["venue"]},
                           {"$set": snap}, upsert=True)
    # History: insert a copy (with TTL marker)
    await history.insert_one(snap_with_expiry)


# ------------------------------------------------------------------
# Public read accessors used by routes
# ------------------------------------------------------------------
async def latest(symbol: str = "BDAGUSDT", venue: str = "coinstore") -> dict | None:
    doc = await db.db.drift_analysis_cache.find_one(
        {"symbol": symbol, "venue": venue}, {"_id": 0})
    return doc


async def history(symbol: str = "BDAGUSDT", venue: str = "coinstore",
                  limit: int = 50) -> list[dict]:
    cur = db.db.drift_analysis_history.find(
        {"symbol": symbol, "venue": venue}, {"_id": 0, "expires_at": 0}
    ).sort("computed_at_ts", -1).limit(limit)
    return await cur.to_list(limit)


async def symbols() -> list[dict]:
    cur = db.db.drift_analysis_cache.find(
        {}, {"_id": 0, "symbol": 1, "venue": 1, "computed_at": 1,
             "risk_score.label": 1, "regime.label": 1})
    docs = await cur.to_list(50)
    out = []
    for d in docs:
        out.append({
            "symbol": d.get("symbol"), "venue": d.get("venue"),
            "computed_at": d.get("computed_at"),
            "risk_label": (d.get("risk_score") or {}).get("label"),
            "regime": (d.get("regime") or {}).get("label"),
        })
    return out


# ------------------------------------------------------------------
# Live context — READ-ONLY mirror of buy_price authority chain.
# Used solely to feed entry_price + current_spread_pct into the drift
# engine. Never writes back, never modifies any authority module.
# ------------------------------------------------------------------
async def _resolve_live_context() -> dict:
    """Mirror the buy_price authority chain (read-only) + latest Coinstore
    best_bid to derive the live gross spread. Returns a dict of optional
    fields; the engine treats absent fields as 'unknown'."""
    ctx: dict = {
        "entry_price": None,
        "entry_price_source": None,
        "current_spread_pct": None,
        "expected_cycle_s": 600,
        "cycle_source": "fallback_default",
    }
    # 1) entry_price via buy_price authority — pick the most recently active route
    try:
        from services.execution import buy_price
        route = await db.routes_col.find_one({"active": True}, {"_id": 0},
                                             sort=[("created_at", -1)])
        if route:
            resolution = await buy_price.resolve(route)
            fresh = buy_price.select_fresh(resolution) or {}
            if fresh.get("value"):
                ctx["entry_price"] = float(fresh["value"])
                ctx["entry_price_source"] = fresh.get("source")
    except Exception as e:  # noqa: BLE001
        logger.debug("drift_runner ctx: buy_price mirror failed: %s", e)

    # 2) current_spread_pct from latest Coinstore best_bid vs entry_price
    try:
        latest_snap = await db.orderbook_snapshots.find_one(
            {"exchange": "coinstore"}, {"_id": 0},
            sort=[("created_at", -1)])
        best_bid = ((latest_snap or {}).get("derived") or {}).get("best_bid")
        if best_bid and ctx["entry_price"]:
            ctx["current_spread_pct"] = round(
                (float(best_bid) - ctx["entry_price"]) / ctx["entry_price"] * 100.0, 4)
    except Exception as e:  # noqa: BLE001
        logger.debug("drift_runner ctx: spread mirror failed: %s", e)

    # 3) expected_cycle_s from cycle_timing.aggregate_only (if any closed cycles)
    try:
        from services.execution import cycle_timing
        agg = await cycle_timing.aggregate_only()
        total = ((agg or {}).get("total_duration_s") or {}).get("avg")
        if total and total > 0:
            ctx["expected_cycle_s"] = int(total)
            ctx["cycle_source"] = "real_cycles"
    except Exception as e:  # noqa: BLE001
        logger.debug("drift_runner ctx: cycle_timing mirror failed: %s", e)

    return ctx


# Singleton
drift_runner = DriftRunner()
