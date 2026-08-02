"""ArbiCore X — Autonomous Executor (P0-D).

Background asyncio worker that continuously drains discovered
opportunities through the unified pipeline (P0-C). Every tick:

    1. Pulls recent opportunities from ``DiscoveryRepo`` (populated by
       the already-running ``ContinuousDiscovery`` background task).
    2. Feeds each opportunity through ``OpportunityPipeline.evaluate``.
    3. The pipeline journals every stage — including discovery, quote,
       gas, profit, policy, certification, and the terminal state
       (SHADOW_RECORDED / POLICY_DENIED / REJECTED / BROADCAST_SENT).
    4. Learning Ledger (P0-B) is invoked periodically to convert
       journaled terminals into training samples for the pre-existing
       calibration + adaptive-weights workers.

Critical operator-safety invariants:

    * Never promotes mode. Only an operator, through
      ``POST /api/arbicore/execution/mode/{strategy}``, can move the
      ladder forward.
    * Never broadcasts unless the strategy's mode is LIMITED_LIVE or
      FULL_LIVE (the pipeline enforces this — the executor cannot
      bypass it).
    * On startup, if a strategy has no persisted mode row, the mode
      registry seeds it to PAPER (per the pre-existing defaults) and
      flash-loan defaults to SHADOW. The executor therefore begins in
      SHADOW/PAPER by default — it will *only* record what would have
      happened. No chain writes will occur until an explicit operator
      promotion.
    * Idempotent per-opportunity: the ``learning_consumed`` flag on the
      journal prevents re-processing of terminal rows. The executor
      skips journal entries that are already in a terminal state and
      already ``learning_consumed=True``.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..data.journal import ExecutionStatus, LearningLabel, TERMINAL_STATUSES


logger = logging.getLogger("arbicore.execution.auto_executor")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


TERMINAL_VALUES = {s.value for s in TERMINAL_STATUSES}


class AutoExecutor:
    """Runs the pipeline continuously against discovered opportunities."""

    def __init__(
        self,
        *,
        pipeline,
        discovery_repo,
        journal,
        learning_ledger=None,
        interval_s: float = 30.0,
        batch_size: int = 25,
        min_confidence: float = 0.0,
        learning_every_n_ticks: int = 4,
    ):
        self._pipeline = pipeline
        self._discovery = discovery_repo
        self._journal = journal
        self._ledger = learning_ledger
        self._interval = float(interval_s)
        self._batch = max(1, int(batch_size))
        self._min_conf = float(min_confidence)
        self._learning_every = max(1, int(learning_every_n_ticks))

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._running_flag: bool = False
        self._last_run_at: Optional[str] = None
        self._last_tick_summary: Optional[Dict[str, Any]] = None
        self._total_ticks: int = 0
        self._total_evaluated: int = 0
        self._total_actions: Dict[str, int] = {}
        self._last_error: Optional[str] = None

    # ---- lifecycle ---------------------------------------------------
    @property
    def running(self) -> bool:
        return self._running_flag and self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._running_flag = True
        self._task = asyncio.create_task(self._loop(), name="arbicore_auto_executor")
        logger.info("AutoExecutor started (interval=%ss, batch=%s)",
                     self._interval, self._batch)

    async def stop(self) -> None:
        if not self._running_flag:
            return
        self._stop.set()
        self._running_flag = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None
        logger.info("AutoExecutor stopped (ticks=%s, evaluated=%s)",
                     self._total_ticks, self._total_evaluated)

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self.tick_once()
                self._last_error = None
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("auto_executor tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    # ---- one tick ----------------------------------------------------
    async def tick_once(self) -> Dict[str, Any]:
        """Process one batch of recent opportunities through the pipeline."""
        t0 = _iso_now()
        rows = await self._read_batch()
        evaluated: List[str] = []
        skipped: List[str] = []
        actions: Dict[str, int] = {}
        errors: List[str] = []

        for row in rows:
            opp_id = row.get("opportunity_id")
            if not opp_id:
                continue
            if float(row.get("confidence") or 0.0) < self._min_conf:
                skipped.append(opp_id)
                continue
            # Skip if journal already reached a terminal state and was
            # consumed. Rows that are terminal but not yet consumed still
            # go back through evaluate() — which is a no-op in the
            # pipeline because record_discovery is idempotent — so a re-tick
            # never double-broadcasts.
            entry = await self._journal.get(opp_id)
            if entry is not None:
                if entry.execution_status in TERMINAL_VALUES and entry.learning_consumed:
                    skipped.append(opp_id)
                    continue
            try:
                result = await self._pipeline.evaluate(
                    row, strategy=row.get("strategy"),
                    scanner_family=row.get("scanner_family"),
                )
                evaluated.append(opp_id)
                actions[result.action] = actions.get(result.action, 0) + 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{opp_id}:{type(exc).__name__}:{exc}")

        # Periodically drain the learning ledger. We do this OUTSIDE the
        # per-opportunity loop so a single tick never blocks on a large
        # emission.
        learning_summary: Optional[Dict[str, Any]] = None
        self._total_ticks += 1
        if self._ledger is not None and (self._total_ticks % self._learning_every == 0):
            try:
                learning_summary = await self._ledger.emit_from_journal(batch=100)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"learning_ledger:{type(exc).__name__}:{exc}")

        summary = {
            "ran_at": t0,
            "batch_size": len(rows),
            "evaluated": len(evaluated),
            "skipped": len(skipped),
            "actions": actions,
            "errors": errors,
            "learning": learning_summary,
        }
        self._last_run_at = t0
        self._last_tick_summary = summary
        self._total_evaluated += len(evaluated)
        for k, v in actions.items():
            self._total_actions[k] = self._total_actions.get(k, 0) + int(v)
        return summary

    # ---- helpers -----------------------------------------------------
    async def _read_batch(self) -> List[Dict[str, Any]]:
        """Pull up to ``batch_size`` recent rows from DiscoveryRepo."""
        try:
            return await self._discovery.list_recent(limit=self._batch)
        except Exception as exc:  # noqa: BLE001
            logger.warning("auto_executor discovery read failed: %s", exc)
            return []

    # ---- status ------------------------------------------------------
    def status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "interval_s": self._interval,
            "batch_size": self._batch,
            "min_confidence": self._min_conf,
            "learning_every_n_ticks": self._learning_every,
            "last_run_at": self._last_run_at,
            "last_tick_summary": self._last_tick_summary,
            "total_ticks": self._total_ticks,
            "total_evaluated": self._total_evaluated,
            "total_actions": dict(self._total_actions),
            "last_error": self._last_error,
        }
