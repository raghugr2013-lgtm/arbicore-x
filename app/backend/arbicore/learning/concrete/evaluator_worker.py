"""ArbiCore X — Outcome Evaluator worker (Phase C Wave 1).

Periodic background loop that calls ``OutcomeTracker.evaluate_due(now)`` on
a cadence. Idle-safe: when no outcomes are due (or no opportunities exist),
each tick is a no-op O(1) Mongo query.

Category-agnostic. No exchange/asset/category-specific code.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

from .outcome_tracker import OutcomeTracker

logger = logging.getLogger("arbicore.outcome_evaluator")

DEFAULT_INTERVAL_S = 60  # tick once per minute


class OutcomeEvaluator:
    def __init__(self, tracker: OutcomeTracker,
                 interval_s: int = DEFAULT_INTERVAL_S):
        self._tracker = tracker
        self._interval = max(5, int(interval_s))
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._iterations = 0
        self._last_run_at: float = 0.0
        self._last_result: Dict[str, Any] = {}
        self._last_error: str | None = None
        self._running = False

    @property
    def running(self) -> bool:
        return self._running

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "interval_s": self._interval,
            "iterations": self._iterations,
            "last_run_at": self._last_run_at,
            "last_result": self._last_result,
            "last_error": self._last_error,
        }

    async def start(self) -> None:
        if self._running:
            return
        self._stop_event = asyncio.Event()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="arbicore_outcome_evaluator")
        logger.info("arbicore_outcome_evaluator started (interval=%ss)", self._interval)

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._stop_event:
            self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        logger.info("arbicore_outcome_evaluator stopped (iterations=%s)", self._iterations)

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                t0 = time.time()
                result = await self._tracker.evaluate_due(now_ts=t0)
                self._last_run_at = t0
                self._last_result = result
                self._last_error = None
                self._iterations += 1
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.exception("arbicore_outcome_evaluator tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
