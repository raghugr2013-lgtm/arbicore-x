"""Wave 4 · Adaptive Weights Worker — OBSERVE-mode recompute loop.

Runs hourly (configurable) and:
    1. Reads recent rows from ``arbicore_signal_metrics``.
    2. Computes a full recommendation snapshot via
       ``AdaptiveWeightsObserver.compute_recommendation``.
    3. Persists the snapshot to ``db.adaptive_weight_recommendations``
       (Fit → Validate → Promote → Archive → Publish).
    4. Refreshes the observer's in-memory cache so the read endpoints
       serve the newest snapshot.

Safety guarantees:
    * ``mode`` is always ``'OBSERVE'`` in Wave 4; scoring is never
      touched.
    * A tick failure logs + emits an alert but never breaks inference.
    * The first-ever tick with no metrics writes an identity-baseline
      row (empty recommendation set, ``aggregate_confidence == 0``) so
      operators can see the pipeline is alive.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...config.adaptive_weights_config import AdaptiveWeightsConfig
from ...data.mongo.adaptive_weights_repo import AdaptiveWeightsRepo
from .adaptive_weights_observer import AdaptiveWeightsObserver

logger = logging.getLogger("arbicore.adaptive_weights_worker")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AdaptiveWeightsWorker:
    def __init__(
        self,
        db,
        observer: AdaptiveWeightsObserver,
        repo: AdaptiveWeightsRepo,
        config: Optional[AdaptiveWeightsConfig] = None,
        metrics_collection: str = "arbicore_signal_metrics",
        alerts_collection: str = "alerts_log",
    ):
        self._db = db
        self._observer = observer
        self._repo = repo
        self._cfg = config or AdaptiveWeightsConfig()
        self._metrics_coll = db[metrics_collection]
        self._alerts_coll = db[alerts_collection]

        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._running: bool = False
        self._iterations: int = 0
        self._last_run_at: float = 0.0
        self._last_result: Dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self._consecutive_failures: int = 0

    @property
    def running(self) -> bool:
        return self._running

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "interval_s": self._cfg.tick_interval_s,
            "iterations": self._iterations,
            "last_run_at": self._last_run_at,
            "last_result": dict(self._last_result),
            "last_error": self._last_error,
            "mode": self._cfg.mode,
            "config": {
                "prior_trials": self._cfg.prior_trials,
                "neutral_weight": self._cfg.neutral_weight,
                "min_weight": self._cfg.min_weight,
                "max_weight": self._cfg.max_weight,
                "max_delta_scale": self._cfg.max_delta_scale,
                "min_samples_for_recommendation": self._cfg.min_samples_for_recommendation,
                "min_confidence_floor": self._cfg.min_confidence_floor,
                "max_signals_scanned": self._cfg.max_signals_scanned,
            },
        }

    async def start(self) -> None:
        if self._running:
            return
        await self._repo.ensure_indexes()
        await self._warm_start_cache()
        self._stop_event = asyncio.Event()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="arbicore_adaptive_weights_worker")
        logger.info("adaptive_weights_worker started (interval=%ss)", self._cfg.tick_interval_s)

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
        logger.info("adaptive_weights_worker stopped (iterations=%s)", self._iterations)

    async def _warm_start_cache(self) -> None:
        try:
            active = await self._repo.get_active("adaptive_weights")
        except Exception as exc:  # noqa: BLE001
            logger.warning("adaptive_weights_worker warm-start read failed: %s", exc)
            active = None
        self._observer.load_snapshot(active)

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            wait_s = self._cfg.tick_interval_s
            try:
                await self.tick_once()
                self._consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.exception("adaptive_weights_worker tick failed: %s", exc)
                self._consecutive_failures += 1
                wait_s = self._backoff_seconds(self._consecutive_failures)
                await self._record_alert("adaptive_weights_fit_failed", {"error": str(exc)})
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_s)
            except asyncio.TimeoutError:
                pass

    def _backoff_seconds(self, failure_count: int) -> int:
        ladder = self._cfg.backoff_ladder_s or (60,)
        idx = min(failure_count - 1, len(ladder) - 1)
        return int(ladder[idx])

    async def tick_once(self) -> Dict[str, Any]:
        """Execute one recompute → persist → publish cycle."""
        t0 = time.time()
        self._last_run_at = t0

        rows = await self._read_metrics()
        snapshot = self._observer.compute_recommendation(rows)

        model_id = f"adaptive_weights@{datetime.now(timezone.utc).strftime('%Y-%m-%d.%H%M%S')}"
        active = await self._repo.get_active("adaptive_weights")
        doc = {
            "id": model_id,
            "kind": "adaptive_weights",
            "mode": snapshot["mode"],
            "provider_version": snapshot["provider_version"],
            "n_signals": snapshot["n_signals"],
            "aggregate_confidence": snapshot["aggregate_confidence"],
            "recommendations": snapshot["recommendations"],
            "generated_at": snapshot["generated_at"],
            "note": snapshot["note"],
            "supersedes": (active or {}).get("id"),
            "n_metrics_rows": len(rows),
        }

        await self._repo.insert_shadow(doc)
        # OBSERVE-mode always publishes the newest snapshot as active — the
        # snapshot is read-only telemetry, so validation-against-previous is
        # not required (unlike calibration).  Rollback via repo remains the
        # audit-safe reversion path.
        promoted = await self._repo.promote(model_id, kind="adaptive_weights")
        self._observer.load_snapshot(promoted or doc)

        result = {
            "id": model_id,
            "mode": snapshot["mode"],
            "n_signals": snapshot["n_signals"],
            "aggregate_confidence": snapshot["aggregate_confidence"],
            "n_metrics_rows": len(rows),
            "promotion_state": "promoted",
            "took_ms": int((time.time() - t0) * 1000),
        }
        self._last_result = result
        self._iterations += 1
        self._last_error = None
        return result

    async def _read_metrics(self) -> List[Dict[str, Any]]:
        """Return recent rows from ``arbicore_signal_metrics``.

        The canonical shape has ``signal_id`` / ``win_rate`` /
        ``sample_count`` / ``aggregated_at``.  Preview pods may have an
        empty collection — in which case we return ``[]`` and the
        observer emits an empty recommendation set (identity baseline).
        """
        limit = int(self._cfg.max_signals_scanned)
        try:
            cur = self._metrics_coll.find(
                {},
                {
                    "_id": 0,
                    "signal_id": 1,
                    "win_rate": 1,
                    "sample_count": 1,
                    "aggregated_at": 1,
                },
            ).limit(limit)
            return await cur.to_list(limit)
        except Exception as exc:  # noqa: BLE001
            logger.warning("adaptive_weights_worker read failed: %s", exc)
            return []

    async def _record_alert(self, category: str, payload: Dict[str, Any]) -> None:
        try:
            await self._alerts_coll.insert_one({
                "category": "adaptive_weights",
                "kind": category,
                "at": _now_iso(),
                "payload": payload,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("adaptive_weights alert write failed: %s", exc)
