"""ArbiCore X — Regime Classification + Sequence Mining worker (Phase C Wave 3).

Idle-safe periodic worker. On each tick:
  - Classify the cross-subject regime over the rolling window (universe mode)
  - Run sequence mining over recent regime + outcome history

Default cadence: 300 s. When no state snapshots or no evaluated outcomes
exist, each tick is a sub-O(N) no-op.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List

from ...data.outcome_repo import OutcomeRepository
from .regime_classifier import HeuristicRegimeClassifier
from .sequence_miner import SequenceMiner

logger = logging.getLogger("arbicore.regime_worker")

DEFAULT_INTERVAL_S = 300


class RegimeClassifierWorker:
    def __init__(self,
                 classifier: HeuristicRegimeClassifier,
                 miner: SequenceMiner,
                 outcome_repo: OutcomeRepository,
                 interval_s: int = DEFAULT_INTERVAL_S):
        self._classifier = classifier
        self._miner = miner
        self._outcomes = outcome_repo
        self._interval = max(30, int(interval_s))
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
        self._task = asyncio.create_task(self._loop(),
                                         name="arbicore_regime_worker")
        logger.info("arbicore_regime_worker started (interval=%ss)", self._interval)

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
        logger.info("arbicore_regime_worker stopped (iterations=%s)", self._iterations)

    async def _gather_subject_ids(self) -> List[str]:
        """Pull a recent set of subject_ids from arbicore_outcomes."""
        from ...data.mongo.arbicore_collections import get_collection
        cursor = get_collection("outcomes").aggregate([
            {"$match": {"subject_id": {"$ne": None}}},
            {"$group": {"_id": "$subject_id"}},
            {"$limit": 500},
        ])
        return [d["_id"] async for d in cursor if d.get("_id")]

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                t0 = time.time()
                subject_ids = await self._gather_subject_ids()
                regime_result: Dict[str, Any] = {"classified": False}
                if subject_ids:
                    snap = await self._classifier.classify_universe(
                        subject_ids, now_ts=t0,
                    )
                    if snap is not None:
                        regime_result = {
                            "classified": True,
                            "dominant_regime": snap.dominant_regime,
                            "tags": list(snap.tags),
                            "confidence": snap.confidence,
                        }
                mining_result = await self._miner.mine()
                self._last_run_at = t0
                self._last_result = {
                    "subject_count": len(subject_ids),
                    "regime": regime_result,
                    "mining": mining_result,
                }
                self._last_error = None
                self._iterations += 1
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.exception("arbicore_regime_worker tick failed: %s", exc)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass
