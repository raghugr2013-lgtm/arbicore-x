"""Paper Validation Runner (v2.11.8 · Slice C).

Continuously drains newly-discovered opportunities from the canonical
opportunity repo, drives each through the OpportunityPipeline in
PAPER/SHADOW mode, and persists an immutable :class:`EvidenceBundle`
per opportunity.

The runner is deliberately *conservative*:

* **Idempotent** — it tracks the last-processed `opportunity_id` so a
  restart does not reprocess or duplicate evidence.
* **Fail-open** — a per-opportunity exception does NOT halt the loop;
  the runner logs and continues to the next opp.
* **Off by default** — the boot sequence only starts the runner when
  ``ARBICORE_PAPER_VALIDATION_ENABLED=true`` is set (avoids surprising
  test / preview environments).
* **Bounded** — one cycle processes at most ``batch_limit`` opps to
  keep the coroutine responsive to a ``stop()`` signal.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence_age_s(existing: Any, now_ts: float) -> float:
    """Return the age (seconds) of an existing evidence record.

    Accepts either a raw Mongo doc (``dict``) or an object with a
    ``created_at`` attribute (:class:`EvidenceBundle`).  Best-effort:
    an unparsable / missing timestamp returns 0.0 which keeps the
    default "skip as duplicate" behaviour.
    """
    if existing is None:
        return 0.0
    ca = None
    if isinstance(existing, dict):
        ca = existing.get("created_at")
    else:
        ca = getattr(existing, "created_at", None)
    if isinstance(ca, str) and ca:
        try:
            dt = datetime.fromisoformat(ca.replace("Z", "+00:00"))
            return max(0.0, now_ts - dt.timestamp())
        except ValueError:
            return 0.0
    return 0.0


@dataclass
class RunnerMetrics:
    """Lightweight in-memory metrics for the /validation/metrics endpoint."""

    started_at:            Optional[str] = None
    last_cycle_at:         Optional[str] = None
    cycles_completed:      int = 0
    opportunities_seen:    int = 0
    opportunities_processed: int = 0
    opportunities_skipped_dup: int = 0
    exceptions:            int = 0
    last_error:            Optional[str] = None
    #: histogram-of-outcomes for THIS process's uptime (repo has the
    #: absolute all-time histogram).
    outcome_counts:        Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "started_at":                self.started_at,
            "last_cycle_at":             self.last_cycle_at,
            "cycles_completed":          self.cycles_completed,
            "opportunities_seen":        self.opportunities_seen,
            "opportunities_processed":   self.opportunities_processed,
            "opportunities_skipped_dup": self.opportunities_skipped_dup,
            "exceptions":                self.exceptions,
            "last_error":                self.last_error,
            "outcome_counts":            dict(self.outcome_counts),
        }


class PaperValidationRunner:
    """Continuous Paper Validation driver.

    Wire it once at boot with (a) the canonical opportunity source
    (something with ``.find(query, limit=...)``), (b) the
    OpportunityPipeline, and (c) an evidence repo — then call
    ``start()``.
    """

    #: How many opportunities to process per cycle.  Kept small so a
    #: stop() request lands promptly.
    DEFAULT_BATCH_LIMIT = 25
    #: Sleep between cycles when no new opps landed.
    DEFAULT_IDLE_SLEEP_S = 5.0
    #: Minimum sleep between cycles even when opps are flowing.  Keeps
    #: the loop from monopolising the event loop on a busy scanner.
    DEFAULT_ACTIVE_SLEEP_S = 0.5

    def __init__(
        self,
        *,
        opp_source,
        pipeline,
        evidence_repo,
        batch_limit: int = DEFAULT_BATCH_LIMIT,
        idle_sleep_s: float = DEFAULT_IDLE_SLEEP_S,
        active_sleep_s: float = DEFAULT_ACTIVE_SLEEP_S,
        reprocess_stale_after_s: float = 0.0,
    ) -> None:
        self._opp_source = opp_source
        self._pipeline = pipeline
        self._evidence = evidence_repo
        self._batch_limit = int(batch_limit)
        self._idle_sleep_s = float(idle_sleep_s)
        self._active_sleep_s = float(active_sleep_s)

        # v2.11.9 — allow the runner to *re-evaluate* an opportunity when
        # its most recent EvidenceBundle is older than this threshold.
        # Zero disables the behaviour (strictly one-evidence-per-opp).
        # Env override: ``ARBICORE_PAPER_RUNNER_REPROCESS_STALE_MIN`` in
        # minutes. Used during live Shadow Certification so long-lived
        # scanner emissions (deterministic route-hash IDs re-upserted
        # every tick) continue to exercise the pipeline instead of
        # becoming permanent dedup skips.
        env_min = os.environ.get("ARBICORE_PAPER_RUNNER_REPROCESS_STALE_MIN")
        if env_min:
            try:
                reprocess_stale_after_s = max(
                    float(reprocess_stale_after_s),
                    float(env_min) * 60.0,
                )
            except ValueError:
                pass
        self._reprocess_stale_after_s = float(reprocess_stale_after_s)

        # Idempotency memory — the set of opportunity_ids we've already
        # emitted an EvidenceBundle for during this process.
        self._processed_ids: set[str] = set()

        self._task: Optional[asyncio.Task] = None
        self._stop_flag: bool = False
        self.metrics = RunnerMetrics()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Kick off the coroutine.  No-op if already running."""
        if self.is_running():
            return
        self._stop_flag = False
        self.metrics.started_at = _iso_now()
        self._task = asyncio.create_task(self._run_forever(),
                                          name="paper-validation-runner")
        logger.info("PaperValidationRunner started")

    async def stop(self) -> None:
        """Request graceful shutdown and await the coroutine."""
        self._stop_flag = True
        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=10.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                logger.warning("PaperValidationRunner did not stop within 10s; cancelled")

    # ------------------------------------------------------------------
    # Core loop
    # ------------------------------------------------------------------
    async def _run_forever(self) -> None:
        while not self._stop_flag:
            try:
                processed = await self.run_once()
                await asyncio.sleep(
                    self._active_sleep_s if processed else self._idle_sleep_s
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:  # noqa: BLE001
                self.metrics.exceptions += 1
                self.metrics.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception("PaperValidationRunner cycle failed")
                await asyncio.sleep(self._idle_sleep_s)

    async def run_once(self) -> int:
        """Process one bounded batch. Returns the number of opps
        actually processed (not the batch size).  Public so tests can
        drive the runner deterministically."""
        self.metrics.cycles_completed += 1
        self.metrics.last_cycle_at = _iso_now()

        opps: List[Any] = await self._fetch_opps()
        self.metrics.opportunities_seen += len(opps)

        processed = 0
        _now_ts = time.time()
        for opp in opps:
            opp_id = self._opp_id(opp)
            if not opp_id:
                continue
            if opp_id in self._processed_ids and self._reprocess_stale_after_s <= 0:
                self.metrics.opportunities_skipped_dup += 1
                continue
            # If evidence already exists for this opp (from a previous
            # process), don't reprocess UNLESS the stored evidence has
            # aged past the configured stale threshold — this is the
            # "re-evaluate live opps" mode enabled during Shadow
            # Certification.
            try:
                existing = await self._evidence.get_by_opportunity_id(opp_id)
            except Exception:  # noqa: BLE001
                existing = None
            if existing is not None:
                age_s = _evidence_age_s(existing, _now_ts)
                if (self._reprocess_stale_after_s <= 0
                        or age_s < self._reprocess_stale_after_s):
                    self._processed_ids.add(opp_id)
                    self.metrics.opportunities_skipped_dup += 1
                    continue
                # else: fall through and re-evaluate (stale evidence).
            try:
                r = await self._pipeline.evaluate(self._opp_as_dict(opp))
                self.metrics.opportunities_processed += 1
                self._processed_ids.add(opp_id)
                oc = r.outcome or "UNKNOWN"
                self.metrics.outcome_counts[oc] = (
                    self.metrics.outcome_counts.get(oc, 0) + 1
                )
                processed += 1
            except Exception as exc:  # noqa: BLE001
                self.metrics.exceptions += 1
                self.metrics.last_error = f"{type(exc).__name__}: {exc}"
                logger.exception(
                    "PaperValidationRunner opp %s failed", opp_id
                )
        return processed

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    async def _fetch_opps(self) -> List[Any]:
        """Ask the opp source for a bounded window of newest opps.

        T0-2: restrict to REAL / VERIFIED_REAL provenance so SIMULATED /
        synthetic (thin_activator) rows can never be paper/shadow-analyzed as
        executable. Legitimate REAL opps in any mode (PAPER/SHADOW/LIVE) are
        unaffected — ``mode`` is orthogonal to ``source_data_quality``.
        """
        from ..models.enums import LEARNING_ELIGIBLE_PROVENANCE as _REAL_PROV
        try:
            rows = await self._opp_source.find(
                {}, limit=self._batch_limit, provenance_filter=_REAL_PROV)
        except TypeError:
            try:
                rows = await self._opp_source.find(
                    limit=self._batch_limit, provenance_filter=_REAL_PROV)
            except TypeError:
                # Source without provenance support — fall back (tests).
                rows = await self._opp_source.find({}, limit=self._batch_limit)
        except Exception as exc:  # noqa: BLE001
            self.metrics.exceptions += 1
            self.metrics.last_error = f"opp source: {exc}"
            return []
        return list(rows or [])

    @staticmethod
    def _opp_id(opp: Any) -> str:
        if isinstance(opp, dict):
            return str(opp.get("opportunity_id") or "")
        return str(getattr(opp, "opportunity_id", "") or "")

    @staticmethod
    def _opp_as_dict(opp: Any) -> Dict[str, Any]:
        if isinstance(opp, dict):
            return dict(opp)
        for method_name in ("to_dict", "model_dump"):
            fn = getattr(opp, method_name, None)
            if callable(fn):
                d = fn()
                if isinstance(d, dict):
                    return d
        return {"opportunity_id": PaperValidationRunner._opp_id(opp)}


def is_enabled_via_env() -> bool:
    """Read the runner-enabled flag from the process env."""
    raw = (os.environ.get("ARBICORE_PAPER_VALIDATION_ENABLED") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")
