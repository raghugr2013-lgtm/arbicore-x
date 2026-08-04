"""LifetimeSweeper — Phase 2 background status transition worker.

Every ``sweeper_interval_seconds`` (default 60s) the sweeper calls
``OpportunityLifetimeTracker.sweep_status_transitions`` which walks the
``mid_opportunity_lifetime`` collection and transitions any document
whose derived status differs from its stored status:

  ACTIVE → STALE   (inactivity > ACTIVE_SECONDS)
  STALE → EXPIRED  (inactivity > STALE_SECONDS)

Reactivations (a stale/expired doc receiving a fresh observation) are
handled synchronously by the tracker on write — the sweeper only picks
up the pure time-based decay case.

The sweeper is operator-controllable via ``start`` / ``stop`` (mirrors
the Wave 1B-β scanner adapter contract). Never autostarts.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .config import LifetimeConfig
from .tracker import OpportunityLifetimeTracker

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class LifetimeSweeper:
    def __init__(
        self,
        tracker: OpportunityLifetimeTracker,
        config: Optional[LifetimeConfig] = None,
    ) -> None:
        self._tracker = tracker
        self._cfg = config or tracker.config
        self._task: Optional[asyncio.Task] = None
        self._stop_evt = asyncio.Event()
        self._enabled = False
        self._stats: Dict[str, Any] = {
            "sweeps":              0,
            "total_transitions":   0,
            "active_to_stale":     0,
            "stale_to_expired":    0,
            "reactivated":         0,
            "started_at":          None,
            "stopped_at":          None,
            "last_run_at":         None,
            "last_error":          None,
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def is_enabled(self) -> bool:
        return self._enabled

    async def start(self) -> Dict[str, Any]:
        if self.is_running():
            return {"already_running": True,
                    "started_at": self._stats["started_at"]}
        self._enabled = True
        self._stop_evt.clear()
        self._stats["started_at"] = _now_iso()
        self._stats["stopped_at"] = None
        self._task = asyncio.create_task(self._run())
        logger.info(
            "lifetime.sweeper: STARTED interval=%.1fs",
            self._cfg.sweeper_interval_seconds)
        return {"started": True, "started_at": self._stats["started_at"]}

    async def stop(self) -> Dict[str, Any]:
        if not self.is_running():
            self._enabled = False
            return {"already_stopped": True}
        self._enabled = False
        self._stop_evt.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._stats["stopped_at"] = _now_iso()
        logger.info("lifetime.sweeper: STOPPED")
        return {"stopped": True, "stopped_at": self._stats["stopped_at"]}

    async def _run(self) -> None:
        while not self._stop_evt.is_set():
            t0 = time.time()
            try:
                moved = await self._tracker.sweep_status_transitions()
                self._stats["sweeps"] += 1
                self._stats["active_to_stale"]  += moved.get(
                    "active_to_stale", 0)
                self._stats["stale_to_expired"] += moved.get(
                    "stale_to_expired", 0)
                self._stats["reactivated"]      += moved.get(
                    "reactivated", 0)
                self._stats["total_transitions"] += sum(moved.values())
                self._stats["last_run_at"] = _now_iso()
            except Exception as exc:  # noqa: BLE001
                self._stats["last_error"] = f"sweep: {exc!r}"
                logger.exception("lifetime.sweeper tick failed: %s", exc)
            elapsed = time.time() - t0
            remaining = max(
                0.0, self._cfg.sweeper_interval_seconds - elapsed)
            try:
                await asyncio.wait_for(
                    self._stop_evt.wait(), timeout=remaining)
            except asyncio.TimeoutError:
                pass
