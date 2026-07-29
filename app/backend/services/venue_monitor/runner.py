"""Venue monitor background runner.

Every POLL_INTERVAL_S, polls all 5 venues in parallel and persists:
  - `venue_health`            (single-doc-per-exchange, upsert)
  - `venue_prices`            (append-only with TTL)
  - `venue_depth`             (append-only with TTL — depth only, larger)
  - `venue_status_history`    (append-only — only on transitions)
  - `venue_alerts`            (append-only — only on full_cycle_ready False→True)

Read-only intelligence. Never proposes, never executes, never mutates the
proposal engine. Designed to coexist with the Coinstore-only Approval Mode.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from services import db
from services.venue_monitor import connectors, scorer

logger = logging.getLogger("venue_monitor")

POLL_INTERVAL_S = 30
PRICES_TTL_S = 60 * 60 * 24        # 24 h
DEPTH_TTL_S = 60 * 60 * 6          # 6 h
STATUS_HISTORY_TTL_S = 60 * 60 * 24 * 14   # 14 d
ALERTS_TTL_S = 60 * 60 * 24 * 30   # 30 d
HEALTH_HISTORY_KEEP = 50           # rolling per-venue


class VenueMonitor:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.last_run_at: str | None = None
        self.iterations = 0
        self.last_error: str | None = None
        self._history: dict[str, list[dict]] = {}   # in-memory rolling outcomes per venue

    async def ensure_indexes(self):
        await db.db.venue_health.create_index("exchange", unique=True)
        await db.db.venue_prices.create_index("ts_dt", expireAfterSeconds=PRICES_TTL_S)
        await db.db.venue_prices.create_index([("exchange", 1), ("ts_ts", -1)])
        await db.db.venue_depth.create_index("ts_dt", expireAfterSeconds=DEPTH_TTL_S)
        await db.db.venue_depth.create_index([("exchange", 1), ("ts_ts", -1)])
        await db.db.venue_status_history.create_index("ts_dt", expireAfterSeconds=STATUS_HISTORY_TTL_S)
        await db.db.venue_status_history.create_index([("exchange", 1), ("ts_ts", -1)])
        await db.db.venue_alerts.create_index("ts_dt", expireAfterSeconds=ALERTS_TTL_S)
        await db.db.venue_alerts.create_index([("ts_ts", -1)])
        await db.db.venue_intelligence.create_index("exchange", unique=True)

    async def _persist(self, snapshot: dict):
        ex = snapshot["exchange"]
        now_dt = datetime.now(timezone.utc)
        now_ts = int(time.time())

        # 1. rolling health history (in-memory)
        hist = self._history.setdefault(ex, [])
        hist.append({"ok": snapshot["ok"], "ts": now_ts, "latency_ms": snapshot["latency_ms"]})
        if len(hist) > HEALTH_HISTORY_KEEP:
            del hist[: len(hist) - HEALTH_HISTORY_KEEP]

        # 2. operator-verified intelligence (deposit_credit_verified, withdraw_credit_verified)
        intel = await db.db.venue_intelligence.find_one({"exchange": ex}, {"_id": 0}) or {}

        # 3. compute scores — derive trading_active from depth presence if the
        # venue's public status endpoint doesn't expose it explicitly
        cur_status = snapshot.get("status") or {}
        if cur_status.get("trading_active") is None and (snapshot.get("depth") or {}).get("best_bid") and (snapshot.get("depth") or {}).get("best_ask"):
            cur_status["trading_active"] = True
            snapshot["status"] = cur_status
        readiness = scorer.evaluate_readiness(snapshot, hist, intel)
        health_score = scorer.compute_health_score(snapshot, hist)

        # 4. status-history transition detection (deposit/withdraw/trading)
        prev_health = await db.db.venue_health.find_one({"exchange": ex}, {"_id": 0, "status": 1, "full_cycle_ready": 1}) or {}
        prev_status = prev_health.get("status") or {}
        cur_status = snapshot.get("status") or {}
        for k in ("deposit_enabled", "withdraw_enabled_usdt", "trading_active"):
            if prev_status.get(k) is not None and prev_status.get(k) != cur_status.get(k):
                await db.db.venue_status_history.insert_one({
                    "exchange": ex, "ts": now_dt.isoformat(), "ts_ts": now_ts, "ts_dt": now_dt,
                    "field": k, "prev": prev_status.get(k), "next": cur_status.get(k),
                })

        # 5. alert on full_cycle_ready False→True transition
        was_ready = bool(prev_health.get("full_cycle_ready"))
        if (not was_ready) and readiness["full_cycle_ready"]:
            await db.db.venue_alerts.insert_one({
                "exchange": ex, "type": "FULL_CYCLE_READY",
                "message": f"{ex} is now FULL CYCLE READY (all 6 checks passing)",
                "ts": now_dt.isoformat(), "ts_ts": now_ts, "ts_dt": now_dt,
                "snapshot_summary": {
                    "checks": readiness["checks"],
                    "profitable_buyer_depth_usd": readiness["profitable_buyer_depth_usd"],
                    "health_score": health_score,
                },
                "acknowledged": False,
            })
            logger.info("[venue_monitor] %s → FULL CYCLE READY", ex)
        elif was_ready and not readiness["full_cycle_ready"]:
            await db.db.venue_alerts.insert_one({
                "exchange": ex, "type": "READINESS_LOST",
                "message": f"{ex} dropped out of FULL CYCLE READY state",
                "ts": now_dt.isoformat(), "ts_ts": now_ts, "ts_dt": now_dt,
                "snapshot_summary": {"checks": readiness["checks"]},
                "acknowledged": False,
            })

        # 6. upsert health doc
        depth = snapshot.get("depth") or {}
        derived = {
            "best_bid": depth.get("best_bid"),
            "best_ask": depth.get("best_ask"),
            "spread_pct": (
                round((depth["best_ask"] - depth["best_bid"]) / depth["best_bid"] * 100, 4)
                if depth.get("best_bid") and depth.get("best_ask") else None
            ),
            "profitable_buyer_depth_usd": readiness["profitable_buyer_depth_usd"],
        }
        await db.db.venue_health.update_one(
            {"exchange": ex},
            {"$set": {
                "exchange": ex,
                "symbol": snapshot["symbol"],
                "ok": snapshot["ok"],
                "latency_ms": snapshot["latency_ms"],
                "ticker": snapshot.get("ticker"),
                "status": cur_status,
                "derived": derived,
                "errors": snapshot.get("errors") or [],
                "health_score": health_score,
                "api_health_fraction": readiness["api_health_fraction"],
                "readiness": readiness,
                "full_cycle_ready": readiness["full_cycle_ready"],
                "last_check_at": now_dt.isoformat(),
                "last_check_ts": now_ts,
            }},
            upsert=True,
        )

        # 7. append-only timeseries (small docs only — full depth goes into venue_depth)
        await db.db.venue_prices.insert_one({
            "exchange": ex, "symbol": snapshot["symbol"],
            "ts": now_dt.isoformat(), "ts_ts": now_ts, "ts_dt": now_dt,
            "last": (snapshot.get("ticker") or {}).get("last"),
            "bid": derived["best_bid"], "ask": derived["best_ask"],
            "spread_pct": derived["spread_pct"],
            "volume_24h_quote_usd": (snapshot.get("ticker") or {}).get("volume_24h_quote_usd"),
            "health_score": health_score,
        })
        if depth.get("bids") or depth.get("asks"):
            await db.db.venue_depth.insert_one({
                "exchange": ex, "symbol": snapshot["symbol"],
                "ts": now_dt.isoformat(), "ts_ts": now_ts, "ts_dt": now_dt,
                "bids": (depth.get("bids") or [])[:50],
                "asks": (depth.get("asks") or [])[:50],
                "derived": derived,
            })

    async def _run_once(self):
        snapshots = await connectors.fetch_all()
        for snap in snapshots:
            try:
                await self._persist(snap)
            except Exception as e:  # noqa: BLE001
                logger.warning("[venue_monitor] persist failed for %s: %s", snap.get("exchange"), e)

    async def _loop(self):
        await self.ensure_indexes()
        await asyncio.sleep(3)
        while not self._stop.is_set():
            t0 = time.time()
            try:
                await self._run_once()
                self.last_error = None
                self.iterations += 1
                self.last_run_at = datetime.now(timezone.utc).isoformat()
            except Exception as e:  # noqa: BLE001
                self.last_error = repr(e)
                logger.warning("[venue_monitor] iteration failed: %s", e)
            elapsed = time.time() - t0
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(1, POLL_INTERVAL_S - elapsed))
            except asyncio.TimeoutError:
                pass

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("[venue_monitor] started (interval=%ss)", POLL_INTERVAL_S)

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None

    async def status(self) -> dict:
        return {
            "running": bool(self._task and not self._task.done()),
            "interval_s": POLL_INTERVAL_S,
            "iterations": self.iterations,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
            "venues": list(connectors.VENUE_FETCHERS.keys()),
        }


venue_monitor = VenueMonitor()
