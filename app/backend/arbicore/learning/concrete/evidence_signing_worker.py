"""Wave 5 · Evidence Signing Worker.

Independent from learning + scoring — a signer-worker failure can NEVER
break inference.  On each tick the worker:

    1. Reads the latest source rows (calibration active model, adaptive
       weights active recommendation).  Certification / decisions are
       optional sources — bundled by opportunistic polling when their
       fingerprint changes.
    2. For any source whose current fingerprint differs from the
       last-bundled fingerprint, builds a fresh evidence bundle, asks
       the signer to attach a signature (or mark unsigned), and
       persists it to ``db.evidence_bundles``.
    3. Updates internal counters + timestamps for the /status endpoint.

The worker is stateless across restarts — the "last-bundled fingerprint"
is recovered by reading the most recent bundle for each source at
warm-start.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ...config.signing_config import SigningConfig
from ...data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
from ...evidence.bundle import new_bundle
from ...evidence.signer import EvidenceSigner

logger = logging.getLogger("arbicore.evidence_signing_worker")


class EvidenceSigningWorker:
    def __init__(
        self,
        db,
        signer: EvidenceSigner,
        repo: EvidenceBundlesRepo,
        *,
        calibration_repo=None,
        adaptive_weights_repo=None,
        certification_provider=None,
        config: Optional[SigningConfig] = None,
        tick_interval_s: Optional[int] = None,
        alerts_collection: str = "alerts_log",
    ):
        self._db = db
        self._signer = signer
        self._repo = repo
        self._calibration_repo = calibration_repo
        self._adaptive_weights_repo = adaptive_weights_repo
        self._certification_provider = certification_provider
        self._cfg = config or SigningConfig()
        self._interval_s = int(tick_interval_s or self._cfg.tick_interval_s or 60)
        self._alerts_coll = db[alerts_collection]

        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._running = False
        self._iterations = 0
        self._last_run_at: float = 0.0
        self._last_error: Optional[str] = None
        self._consecutive_failures = 0
        # Per-source last-bundled fingerprint (source_model_id).
        self._last_fingerprints: Dict[str, Optional[str]] = {}
        self._last_bundles: Dict[str, Dict[str, Any]] = {}

    @property
    def running(self) -> bool:
        return self._running

    @property
    def status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "interval_s": self._interval_s,
            "iterations": self._iterations,
            "last_run_at": self._last_run_at,
            "last_error": self._last_error,
            "signer": self._signer.stats,
            "last_bundled_fingerprints": dict(self._last_fingerprints),
        }

    async def start(self) -> None:
        if self._running:
            return
        await self._repo.ensure_indexes()
        await self._warm_start()
        self._stop_event = asyncio.Event()
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="arbicore_evidence_signing_worker")
        logger.info("evidence_signing_worker started (interval=%ss)", self._interval_s)

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
        logger.info("evidence_signing_worker stopped (iterations=%s)", self._iterations)

    async def _warm_start(self) -> None:
        for source in ("calibration", "adaptive_weights", "certification"):
            try:
                latest = await self._repo.get_latest(source)
            except Exception:
                latest = None
            if latest:
                self._last_fingerprints[source] = latest.get("source_model_id")
                self._last_bundles[source] = latest

    async def _loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            wait_s = self._interval_s
            try:
                await self.tick_once()
                self._consecutive_failures = 0
            except Exception as exc:  # noqa: BLE001
                self._last_error = str(exc)
                self._consecutive_failures += 1
                logger.exception("evidence_signing_worker tick failed: %s", exc)
                wait_s = self._backoff_seconds(self._consecutive_failures)
                await self._record_alert("evidence_signing_tick_failed", {"error": str(exc)})
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait_s)
            except asyncio.TimeoutError:
                pass

    def _backoff_seconds(self, failure_count: int) -> int:
        ladder = self._cfg.backoff_ladder_s or (60,)
        idx = min(failure_count - 1, len(ladder) - 1)
        return int(ladder[idx])

    async def tick_once(self) -> Dict[str, Any]:
        """Bundle any sources whose fingerprint has changed since last tick."""
        t0 = time.time()
        self._last_run_at = t0
        emitted: List[str] = []

        # --- Confidence Calibration ---
        if self._calibration_repo is not None:
            active = await self._safe(self._calibration_repo.get_active, "confidence")
            emitted += await self._maybe_emit(
                source="calibration",
                source_row=active,
                payload_builder=self._payload_from_calibration,
                calibrator_version=(active or {}).get("calibrator_version"),
            )

        # --- Adaptive Weights (OBSERVE) ---
        if self._adaptive_weights_repo is not None:
            active = await self._safe(self._adaptive_weights_repo.get_active, "adaptive_weights")
            emitted += await self._maybe_emit(
                source="adaptive_weights",
                source_row=active,
                payload_builder=self._payload_from_adaptive_weights,
                provider_version=(active or {}).get("provider_version"),
            )

        # --- Certification ---
        if self._certification_provider is not None:
            cert_row = await self._safe(self._certification_provider)
            emitted += await self._maybe_emit(
                source="certification",
                source_row=cert_row,
                payload_builder=self._payload_from_certification,
                fingerprint_key="fingerprint",
            )

        result = {
            "emitted": emitted,
            "took_ms": int((time.time() - t0) * 1000),
        }
        self._iterations += 1
        self._last_error = None
        return result

    # --- source-specific helpers ---

    async def _safe(self, fn, *args):
        try:
            return await fn(*args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("evidence source read failed for %s: %s", fn, exc)
            return None

    async def _maybe_emit(
        self,
        *,
        source: str,
        source_row: Optional[Dict[str, Any]],
        payload_builder,
        provider_version: Optional[str] = None,
        calibrator_version: Optional[str] = None,
        fingerprint_key: str = "id",
    ) -> List[str]:
        if not source_row:
            return []
        fingerprint = source_row.get(fingerprint_key) or source_row.get("id")
        if fingerprint is None:
            return []
        if self._last_fingerprints.get(source) == fingerprint:
            return []
        payload = payload_builder(source_row)
        bundle = new_bundle(
            source_component=source,
            source_model_id=fingerprint,
            payload=payload,
            bundle_version=self._cfg.bundle_version,
            provider_version=provider_version,
            calibrator_version=calibrator_version,
        )
        signed = self._signer.sign_bundle(bundle)
        stored = await self._repo.insert(signed)
        self._last_fingerprints[source] = fingerprint
        self._last_bundles[source] = stored
        return [stored["bundle_id"]]

    @staticmethod
    def _payload_from_calibration(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "algorithm": row.get("algorithm"),
            "window_start": row.get("window_start"),
            "window_end": row.get("window_end"),
            "n_samples": row.get("n_samples"),
            "brier_score": row.get("brier_score"),
            "ece": row.get("ece"),
            "drift_alert": row.get("drift_alert"),
            "buckets": row.get("buckets"),
            "curve": row.get("curve"),
            "supersedes": row.get("supersedes"),
        }

    @staticmethod
    def _payload_from_adaptive_weights(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "mode": row.get("mode"),
            "n_signals": row.get("n_signals"),
            "aggregate_confidence": row.get("aggregate_confidence"),
            "recommendations": row.get("recommendations"),
            "supersedes": row.get("supersedes"),
        }

    @staticmethod
    def _payload_from_certification(row: Dict[str, Any]) -> Dict[str, Any]:
        # Whatever the certification provider returned — bundle verbatim.
        return dict(row or {})

    async def _record_alert(self, category: str, payload: Dict[str, Any]) -> None:
        try:
            await self._alerts_coll.insert_one({
                "category": "evidence_signing",
                "kind": category,
                "at": _iso_now(),
                "payload": payload,
            })
        except Exception as exc:  # noqa: BLE001
            logger.warning("evidence_signing alert write failed: %s", exc)


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
