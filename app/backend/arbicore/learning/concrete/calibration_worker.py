"""Calibration Worker — sibling to ``OutcomeEvaluator``.

Runs an hourly loop (configurable) that:
    1. Reads the resolved-sample window from ``db.calibration_log``.
    2. Computes reliability buckets, Brier, ECE against the current
       window.
    3. Fits a candidate calibrator via the isotonic → platt → identity
       ladder.
    4. Validates the candidate against the currently-active model
       (`new_ece <= current_ece + promotion_ece_slack`).
    5. Promotes on validation success; keeps the previous active
       otherwise (persisted as ``state='shadow'`` for audit).
    6. Detects drift via a rolling ECE state-machine (hysteresis).
    7. Updates the in-memory cache read by ``ConfidenceCalibrator.calibrate``.

Failure isolation:  a tick failure is logged and surfaced via
``status``.  The previously-active model continues to serve
``calibrate()``.  Calibration MUST NEVER interrupt inference.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from ...config.calibration_config import CalibrationConfig
from ...data.mongo.calibration_models_repo import CalibrationModelsRepo
from .calibrator_isotonic import IsotonicConfidenceCalibrator, compute_metrics

logger = logging.getLogger("arbicore.calibration_worker")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CalibrationWorker:
    """Periodic Wave-3 calibration fit / validate / promote loop."""

    def __init__(
        self,
        db,
        calibrator: IsotonicConfidenceCalibrator,
        repo: CalibrationModelsRepo,
        config: Optional[CalibrationConfig] = None,
        calibration_log_collection: str = "calibration_log",
        alerts_log_collection: str = "alerts_log",
    ):
        self._db = db
        self._calibrator = calibrator
        self._repo = repo
        self._cfg = config or CalibrationConfig()
        self._log_coll = db[calibration_log_collection]
        self._alerts_coll = db[alerts_log_collection]

        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._running: bool = False
        self._iterations: int = 0
        self._last_run_at: float = 0.0
        self._last_result: Dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self._consecutive_failures: int = 0

        # Drift state-machine.
        self._ece_history: List[float] = []
        self._drift_on: bool = False
        self._drift_off_streak: int = 0

    # ------- lifecycle -------

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
            "drift_on": self._drift_on,
            "config": {
                "window_days": self._cfg.window_days,
                "min_samples_isotonic": self._cfg.min_samples_isotonic,
                "min_samples_platt": self._cfg.min_samples_platt,
                "promotion_ece_slack": self._cfg.promotion_ece_slack,
                "n_buckets": self._cfg.n_buckets,
            },
        }

    async def start(self) -> None:
        """Non-blocking start.

        Boot-time init (``ensure_indexes`` + warm-start cache read) requires
        Mongo. If Mongo is unreachable at process boot (e.g. DNS not yet
        resolvable on a shared Docker network) those calls would block for
        pymongo's serverSelectionTimeoutMS and stall Uvicorn's startup.

        We therefore defer init into the background task so ``start()``
        returns immediately. If init fails, the failure is logged and the
        main tick loop's existing backoff-and-retry ladder picks it up on
        the next cycle. Calibration MUST NEVER interrupt inference — and
        that guarantee now extends to boot as well.
        """
        if self._running:
            return
        self._stop_event = asyncio.Event()
        self._running = True
        self._task = asyncio.create_task(
            self._run_with_init(), name="arbicore_calibration_worker",
        )
        logger.info("calibration_worker started (interval=%ss)", self._cfg.tick_interval_s)

    async def _run_with_init(self) -> None:
        """Boot-init + main-loop wrapper — resilient to Mongo unavailability."""
        try:
            await self._repo.ensure_indexes()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "calibration_worker ensure_indexes deferred (will retry on tick): %s",
                exc,
            )
        try:
            await self._warm_start_cache()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "calibration_worker warm_start_cache deferred (will retry on tick): %s",
                exc,
            )
        await self._loop()

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
        logger.info("calibration_worker stopped (iterations=%s)", self._iterations)

    async def _warm_start_cache(self) -> None:
        """Load the currently-active model curve into the calibrator cache."""
        try:
            active = await self._repo.get_active("confidence")
        except Exception as exc:  # noqa: BLE001
            logger.warning("calibration_worker warm-start read failed: %s", exc)
            active = None
        if active:
            self._calibrator.load_curve(active.get("curve"))
        else:
            self._calibrator.load_curve(None)

    # ------- main loop -------

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            wait_s = self._cfg.tick_interval_s
            try:
                await self.tick_once()
                self._consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                logger.exception("calibration_worker tick failed: %s", exc)
                self._consecutive_failures += 1
                wait_s = self._backoff_seconds(self._consecutive_failures)
                await self._record_alert("calibration_fit_failed", {"error": str(exc)})
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_s)
            except asyncio.TimeoutError:
                pass

    def _backoff_seconds(self, failure_count: int) -> int:
        ladder = self._cfg.backoff_ladder_s or (60,)
        idx = min(failure_count - 1, len(ladder) - 1)
        return int(ladder[idx])

    # ------- one tick (exposed for tests) -------

    async def tick_once(self) -> Dict[str, Any]:
        """Execute a single fit / validate / promote cycle."""
        t0 = time.time()
        self._last_run_at = t0

        samples, drops = await self._read_samples()
        metrics = compute_metrics(samples, self._cfg.n_buckets)

        # Choose algorithm based on sample count.
        candidate = IsotonicConfidenceCalibrator(
            min_samples_isotonic=self._cfg.min_samples_isotonic,
            min_samples_platt=self._cfg.min_samples_platt,
        )
        candidate.fit(samples)
        algorithm = candidate.algorithm

        # Drift check against rolling ECE history.
        drift_alert = self._update_drift_state(metrics["ece"])

        # Validate against current active.
        active = await self._repo.get_active("confidence")
        current_ece = float(active["ece"]) if active and "ece" in active else None
        candidate_ece = float(metrics["ece"])
        should_promote = self._should_promote(current_ece, candidate_ece, samples_n=len(samples))

        # Build the persistence row.
        model_id = f"confidence_calibrator@{datetime.now(timezone.utc).strftime('%Y-%m-%d.%H%M%S')}"
        window_end = datetime.now(timezone.utc)
        window_start = window_end - timedelta(days=self._cfg.window_days)
        doc = {
            "id": model_id,
            "kind": "confidence",
            "algorithm": algorithm,
            "calibrator_version": self._cfg.calibrator_version,
            "fitted_at": _now_iso(),
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "n_samples": metrics["n_samples"],
            "n_pending_dropped": drops["pending"],
            "n_unresolved_dropped": drops["unresolved"],
            "brier_score": metrics["brier_score"],
            "ece": metrics["ece"],
            "drift_alert": drift_alert,
            "buckets": metrics["buckets"],
            "curve": candidate.curve(),
            "supersedes": active["id"] if active else None,
        }

        await self._repo.insert_shadow(doc)

        if should_promote:
            promoted = await self._repo.promote(model_id, kind="confidence")
            # Refresh in-memory cache for the hot path.
            self._calibrator.load_curve(promoted.get("curve") if promoted else candidate.curve())
            promotion_state = "promoted"
        else:
            promotion_state = "shadowed_below_threshold"
            await self._record_alert("calibration_candidate_shadowed", {
                "candidate_id": model_id,
                "candidate_ece": candidate_ece,
                "current_ece": current_ece,
            })

        result = {
            "id": model_id,
            "algorithm": algorithm,
            "n_samples": metrics["n_samples"],
            "brier_score": metrics["brier_score"],
            "ece": metrics["ece"],
            "drift_alert": drift_alert,
            "promotion_state": promotion_state,
            "took_ms": int((time.time() - t0) * 1000),
        }
        self._last_result = result
        self._iterations += 1
        self._last_error = None
        return result

    # ------- helpers -------

    async def _read_samples(self) -> Tuple[List[Tuple[float, bool]], Dict[str, int]]:
        """Return ``(samples, dropped_counters)`` from the resolved window.

        ``samples`` is a list of ``(raw_confidence in [0,100], survived)``
        pairs.  Unresolved rows are treated as ``survived=False`` per the
        approved design.  Pending rows are dropped and counted.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=self._cfg.window_days)
        cutoff_iso = cutoff.isoformat()
        samples: List[Tuple[float, bool]] = []
        counters = {"pending": 0, "unresolved": 0}
        # created_at is the TTL anchor and is an ISO string in this codebase.
        cursor = self._log_coll.find(
            {"created_at": {"$gte": cutoff_iso}},
            {"_id": 0, "predicted_confidence": 1, "survived": 1, "status": 1},
        )
        async for row in cursor:
            status = row.get("status")
            if status == "pending":
                counters["pending"] += 1
                continue
            raw = row.get("predicted_confidence")
            if raw is None:
                continue
            if status == "resolved":
                samples.append((float(raw), bool(row.get("survived", False))))
            elif status == "unresolved":
                counters["unresolved"] += 1
                # Treat as failure per the approved design (matches
                # existing "_mark_no_data" pattern in canonical code).
                samples.append((float(raw), False))
        return samples, counters

    def _should_promote(self, current_ece: Optional[float],
                        candidate_ece: float, samples_n: int) -> bool:
        # Bootstrap guard — never promote a below-Platt-threshold (or empty)
        # candidate.  Serve identity from in-memory cache until real data
        # arrives.  This keeps the audit trail honest (no fake "active" rows).
        if samples_n < self._cfg.min_samples_platt:
            return False
        # No prior active — promote first sufficiently-sized fitted model.
        if current_ece is None:
            return True
        # New ECE must not be worse than current + slack.
        return candidate_ece <= (current_ece + self._cfg.promotion_ece_slack)

    def _update_drift_state(self, current_ece: float) -> bool:
        """Rolling-window drift state-machine with hysteresis.

        ON when ``ece >= mean + drift_stdev_mult_on * stdev`` AND
        ``ece > drift_ece_absolute_floor``.
        OFF after ``drift_off_consecutive_ticks`` ticks below
        ``mean + drift_stdev_mult_off * stdev``.
        """
        history = self._ece_history
        history.append(current_ece)
        if len(history) > self._cfg.drift_history_len:
            del history[: len(history) - self._cfg.drift_history_len]
        if len(history) < 3:
            return self._drift_on
        mean = statistics.fmean(history)
        stdev = statistics.pstdev(history)
        on_threshold = mean + self._cfg.drift_stdev_mult_on * stdev
        off_threshold = mean + self._cfg.drift_stdev_mult_off * stdev

        if not self._drift_on:
            if current_ece >= on_threshold and current_ece > self._cfg.drift_ece_absolute_floor:
                self._drift_on = True
                self._drift_off_streak = 0
                # Fire-and-forget alert (non-async wrapper).
                asyncio.get_event_loop().create_task(
                    self._record_alert("calibration_drift_on", {
                        "ece": current_ece, "mean": mean, "stdev": stdev,
                    })
                )
        else:
            if current_ece < off_threshold:
                self._drift_off_streak += 1
                if self._drift_off_streak >= self._cfg.drift_off_consecutive_ticks:
                    self._drift_on = False
                    self._drift_off_streak = 0
                    asyncio.get_event_loop().create_task(
                        self._record_alert("calibration_drift_off", {
                            "ece": current_ece, "mean": mean, "stdev": stdev,
                        })
                    )
            else:
                self._drift_off_streak = 0
        return self._drift_on

    async def _record_alert(self, category: str, payload: Dict[str, Any]) -> None:
        try:
            await self._alerts_coll.insert_one({
                "category": "calibration",
                "kind": category,
                "at": _now_iso(),
                "payload": payload,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("calibration alert write failed: %s", exc)
