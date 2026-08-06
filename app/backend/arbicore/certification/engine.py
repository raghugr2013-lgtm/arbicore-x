"""Shadow Certification engine (v2.11.9).

Turns raw Paper Validation state into immutable
:class:`ShadowCertificationCycle` snapshots and grades the run against
the canonical :class:`CertificationThresholds`.

Design notes
------------

* **Cycle window** — the engine keeps a *delta-baseline* of the runner's
  cumulative counters and the EvidenceBundle repo's cumulative
  histogram.  Every tick computes what changed since the last cycle
  boundary and records that as the new cycle.  This yields honest
  per-cycle rates rather than reporting the same cumulative rate on
  every tick.

* **Stage-p95 attribution** — computed from the last N EvidenceBundles
  emitted in the cycle window (bounded so the engine never scans the
  whole collection).

* **Fail-open** — any per-tick exception is recorded on the cycle as an
  infra-health failure, the cycle is graded FAIL for that dimension,
  and the engine continues.

* **Termination** — the engine does not autonomously start the runner;
  the caller decides when to call :meth:`start_run` / :meth:`stop`.
  Once ``target_cycles`` cycles have been recorded, :meth:`tick` will
  auto-finalise on the next invocation.

The engine is deliberately stateless-per-run: everything durable lives
in the repo.  The engine holds only an in-memory baseline of runner
counters + repo counts for delta arithmetic (nothing persisted).
"""

from __future__ import annotations

import logging
import math
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    ShadowCertificationCycle,
    ShadowCertificationRun,
    new_cycle_id,
)
from .thresholds import (
    CertificationStatus,
    CertificationThresholds,
    CycleStatus,
    load_thresholds_from_env,
)

logger = logging.getLogger(__name__)


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _p95(values: List[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    xs = sorted(float(v) for v in values)
    # nearest-rank p95
    idx = max(0, math.ceil(0.95 * len(xs)) - 1)
    return float(xs[idx])


class ShadowCertificationEngine:
    """Orchestrates one Shadow Certification run at a time."""

    #: Bound on how many EvidenceBundle rows a single cycle scans for
    #: stage-p95 computation.  Prevents unbounded reads under load.
    DEFAULT_EVIDENCE_SAMPLE = 200

    def __init__(
        self,
        *,
        cert_repo,
        evidence_repo,
        paper_runner=None,
        db=None,
        thresholds: Optional[CertificationThresholds] = None,
        evidence_sample: int = DEFAULT_EVIDENCE_SAMPLE,
    ) -> None:
        self._cert_repo = cert_repo
        self._evidence_repo = evidence_repo
        self._paper_runner = paper_runner
        self._db = db
        self._thresholds = thresholds or load_thresholds_from_env()
        self._evidence_sample = int(evidence_sample)

        # Baselines captured at cycle boundary — every tick diffs these
        # against the current counters to produce the delta cycle.
        self._baseline: Dict[str, Any] = {
            "evidence_total": 0,
            "outcome_counts": {},
            "runner_seen": 0,
            "runner_processed": 0,
            "runner_exceptions": 0,
            "last_boundary_ts": time.monotonic(),
            "last_evidence_created_at": None,
        }
        self._current_run_id: Optional[str] = None

    @property
    def thresholds(self) -> CertificationThresholds:
        return self._thresholds

    def set_thresholds(self, thresholds: CertificationThresholds) -> None:
        self._thresholds = thresholds

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start_run(
        self, *, thresholds: Optional[CertificationThresholds] = None
    ) -> ShadowCertificationRun:
        """Create + persist a fresh RUNNING certification run.

        Refuses if another run is already RUNNING (one at a time).
        """
        current = await self._cert_repo.current_running()
        if current is not None:
            raise RuntimeError(
                f"a Shadow Certification run is already active: {current.run_id}"
            )
        th = thresholds or self._thresholds
        run = ShadowCertificationRun.start(thresholds=th)
        await self._cert_repo.upsert(run)
        self._current_run_id = run.run_id
        await self._reset_baseline()
        return run

    async def stop_run(
        self, *, reason: str = "operator abort"
    ) -> Optional[ShadowCertificationRun]:
        run = await self.current_run()
        if run is None:
            return None
        if run.is_terminal:
            return run
        aborted = run.abort(reason=reason)
        await self._cert_repo.upsert(aborted)
        self._current_run_id = None
        return aborted

    async def current_run(self) -> Optional[ShadowCertificationRun]:
        return await self._cert_repo.current_running()

    # ------------------------------------------------------------------
    # Per-cycle tick
    # ------------------------------------------------------------------
    async def tick(self) -> Optional[ShadowCertificationRun]:
        """Record one certification cycle if a run is active.

        Returns the up-to-date run (possibly finalised).  Returns
        ``None`` if no run is active.  Never raises: infra failure
        gracefully records the cycle as FAIL and continues.
        """
        run = await self.current_run()
        if run is None:
            return None
        if run.is_terminal:
            return run

        start_wall = _iso_now()
        start_mono = time.monotonic()
        infra_health: Dict[str, Any] = {"mongo_ok": True, "runner_ok": True}
        infra_errors: List[str] = []
        outcome_delta: Dict[str, int] = {}
        seen_delta = processed_delta = exec_delta = 0
        runner_exc_delta = 0
        validation_ids: List[str] = []
        stage_p95: Dict[str, float] = {}

        # ---- Sample runner counters --------------------------------------
        try:
            runner_seen, runner_processed, runner_exc = self._sample_runner()
            seen_delta = max(0, runner_seen - int(self._baseline.get("runner_seen", 0)))
            processed_delta = max(
                0, runner_processed - int(self._baseline.get("runner_processed", 0))
            )
            runner_exc_delta = max(
                0, runner_exc - int(self._baseline.get("runner_exceptions", 0))
            )
        except Exception as exc:  # noqa: BLE001
            infra_health["runner_ok"] = False
            infra_errors.append(f"runner_sample_failed: {exc}")

        # ---- Sample evidence delta ---------------------------------------
        try:
            (
                outcome_delta,
                exec_delta,
                validation_ids,
                stage_p95,
                new_boundary_ts,
            ) = await self._sample_evidence_delta()
            self._baseline["last_evidence_created_at"] = new_boundary_ts
        except Exception as exc:  # noqa: BLE001
            infra_health["mongo_ok"] = False
            infra_errors.append(f"evidence_sample_failed: {exc}")

        # If runner reported processed but evidence delta smaller, we
        # trust evidence for `executable` (immutable canonical source).
        # `processed_delta` may double-count re-scanned opps; we clamp
        # it to at least the evidence delta count to keep ratios sane.
        ev_delta_total = sum(outcome_delta.values()) if outcome_delta else 0
        if processed_delta < ev_delta_total:
            processed_delta = ev_delta_total

        duration_ms = (time.monotonic() - start_mono) * 1000.0
        completed_at = _iso_now()

        # ---- Grade the cycle ---------------------------------------------
        cycle_status, cycle_reasons, flags = self._grade_cycle(
            processed=processed_delta,
            executable=exec_delta,
            stage_p95=stage_p95,
            runner_exceptions=runner_exc_delta,
            infra_ok=(infra_health["mongo_ok"] and infra_health["runner_ok"]),
        )
        cycle_reasons.extend(infra_errors)

        cycle = ShadowCertificationCycle(
            cycle_id=new_cycle_id(),
            cycle_index=run.cycles_completed,
            started_at=start_wall,
            completed_at=completed_at,
            duration_ms=duration_ms,
            validation_ids=validation_ids,
            opportunities_seen=seen_delta,
            opportunities_processed=processed_delta,
            executable_count=exec_delta,
            outcome_counts=outcome_delta,
            stage_p95_ms=stage_p95,
            infra_health=infra_health,
            runner_exceptions=runner_exc_delta,
            cycle_status=cycle_status.value,
            cycle_reasons=cycle_reasons,
            flags=flags,
        )

        # ---- Append + persist --------------------------------------------
        run = run.with_cycle(cycle)
        await self._cert_repo.upsert(run)
        await self._advance_baseline()

        # ---- Finalise if target reached ----------------------------------
        if run.cycles_completed >= run.target_cycles:
            run = await self._finalise(run)
        return run

    # ------------------------------------------------------------------
    # Finalise
    # ------------------------------------------------------------------
    async def finalise_now(self) -> Optional[ShadowCertificationRun]:
        """Grade + close the currently RUNNING run immediately."""
        run = await self.current_run()
        if run is None or run.is_terminal:
            return run
        finalised = await self._finalise(run)
        return finalised

    async def _finalise(
        self, run: ShadowCertificationRun
    ) -> ShadowCertificationRun:
        status, summary, pass_r, warn_r, fail_r = self._grade_run(run)
        final = run.finalise(
            status=status,
            summary=summary,
            pass_reasons=pass_r,
            warning_reasons=warn_r,
            fail_reasons=fail_r,
        )
        await self._cert_repo.upsert(final)
        self._current_run_id = None
        return final

    # ------------------------------------------------------------------
    # Grading
    # ------------------------------------------------------------------
    def _grade_cycle(
        self,
        *,
        processed: int,
        executable: int,
        stage_p95: Dict[str, float],
        runner_exceptions: int,
        infra_ok: bool,
    ) -> Tuple[CycleStatus, List[str], List[str]]:
        reasons: List[str] = []
        flags: List[str] = []
        th = self._thresholds

        # Low-volume flag: signals the cycle is statistically thin.
        if processed < th.min_opps_per_cycle:
            flags.append("low_volume")

        infra_fail = not infra_ok
        exception_rate = (
            runner_exceptions / float(max(1, processed)) if processed else 0.0
        )
        if exception_rate > th.max_infra_exception_rate:
            reasons.append(
                f"infra_exception_rate={exception_rate:.4f} exceeds "
                f"cap {th.max_infra_exception_rate}"
            )
            infra_fail = True

        p95_fail = False
        if stage_p95:
            worst_stage, worst_val = max(stage_p95.items(), key=lambda kv: kv[1])
            if worst_val > th.max_stage_p95_ms:
                reasons.append(
                    f"stage_p95:{worst_stage}={worst_val:.1f}ms exceeds cap "
                    f"{th.max_stage_p95_ms:.0f}ms"
                )
                p95_fail = True

        exec_rate = (executable / float(processed)) if processed else 0.0

        # Grading precedence: infra FAIL > p95 FAIL > exec-rate check.
        if infra_fail:
            return CycleStatus.FAIL, reasons or ["infra_failure"], flags
        if p95_fail:
            return CycleStatus.FAIL, reasons, flags
        if "low_volume" in flags:
            # Low-volume cycles don't grade against executable_rate.
            return CycleStatus.PASS, reasons or ["ok_low_volume"], flags
        if exec_rate >= th.min_executable_rate_pass:
            return CycleStatus.PASS, [f"executable_rate={exec_rate:.4f}"], flags
        if exec_rate >= th.min_executable_rate_warn:
            return CycleStatus.WARNING, [
                f"executable_rate={exec_rate:.4f} below pass threshold "
                f"{th.min_executable_rate_pass}"
            ], flags
        return CycleStatus.FAIL, [
            f"executable_rate={exec_rate:.4f} below warn threshold "
            f"{th.min_executable_rate_warn}"
        ], flags

    def _grade_run(
        self, run: ShadowCertificationRun
    ) -> Tuple[
        CertificationStatus, Dict[str, Any], List[str], List[str], List[str]
    ]:
        th = self._thresholds
        s, p, e = run.cumulative_totals()
        exec_rate = (e / float(p)) if p > 0 else 0.0
        outcome_counts = run.cumulative_outcome_counts()
        fail_cycles = sum(
            1 for c in run.cycles if c.cycle_status == CycleStatus.FAIL.value
        )
        warn_cycles = sum(
            1 for c in run.cycles if c.cycle_status == CycleStatus.WARNING.value
        )
        # Aggregate worst-stage p95 (max of per-cycle worsts).
        worst_p95 = 0.0
        for c in run.cycles:
            if c.stage_p95_ms:
                worst_p95 = max(worst_p95, max(c.stage_p95_ms.values()))
        # Aggregate exception rate.
        total_exc = sum(c.runner_exceptions for c in run.cycles)
        exception_rate = (total_exc / float(p)) if p > 0 else 0.0

        infra_healthy = all(
            c.infra_health.get("mongo_ok", True)
            and c.infra_health.get("runner_ok", True)
            for c in run.cycles
        )

        pass_reasons: List[str] = []
        warn_reasons: List[str] = []
        fail_reasons: List[str] = []

        # FAIL triggers
        if not infra_healthy:
            fail_reasons.append("infra_failure in ≥1 cycle")
        if exception_rate > th.max_infra_exception_rate:
            fail_reasons.append(
                f"cumulative_exception_rate={exception_rate:.4f} > cap "
                f"{th.max_infra_exception_rate}"
            )
        if fail_cycles > th.max_fail_cycles:
            fail_reasons.append(
                f"fail_cycles={fail_cycles} > cap {th.max_fail_cycles}"
            )
        if worst_p95 > th.max_stage_p95_ms:
            fail_reasons.append(
                f"worst_stage_p95={worst_p95:.1f}ms > cap {th.max_stage_p95_ms:.0f}ms"
            )
        if run.cycles_completed < run.target_cycles:
            fail_reasons.append(
                f"cycles_completed={run.cycles_completed} < target "
                f"{run.target_cycles}"
            )

        # WARNING (only applies if not FAIL)
        if warn_cycles > th.max_warn_cycles:
            warn_reasons.append(
                f"warn_cycles={warn_cycles} > cap {th.max_warn_cycles}"
            )
        if exec_rate < th.min_executable_rate_pass and p > 0:
            warn_reasons.append(
                f"executable_rate={exec_rate:.4f} < pass threshold "
                f"{th.min_executable_rate_pass}"
            )
            if exec_rate < th.min_executable_rate_warn:
                fail_reasons.append(
                    f"executable_rate={exec_rate:.4f} < warn threshold "
                    f"{th.min_executable_rate_warn}"
                )

        # Determine terminal status
        if fail_reasons:
            status = CertificationStatus.FAIL
        elif warn_reasons:
            status = CertificationStatus.WARNING
        else:
            status = CertificationStatus.PASS
            pass_reasons.append(
                f"executable_rate={exec_rate:.4f} ≥ "
                f"{th.min_executable_rate_pass}"
            )
            pass_reasons.append(
                f"{run.cycles_completed}/{run.target_cycles} cycles PASS"
            )
            pass_reasons.append(
                f"worst_stage_p95={worst_p95:.1f}ms ≤ {th.max_stage_p95_ms:.0f}ms"
            )

        summary = {
            "opportunities_seen":       s,
            "opportunities_processed":  p,
            "executable_count":         e,
            "executable_rate":          exec_rate,
            "outcome_counts":           outcome_counts,
            "worst_stage_p95_ms":       worst_p95,
            "total_runner_exceptions":  total_exc,
            "exception_rate":           exception_rate,
            "cycles_pass":              run.cycles_completed
                                        - fail_cycles - warn_cycles,
            "cycles_warn":              warn_cycles,
            "cycles_fail":              fail_cycles,
            "infra_healthy":            infra_healthy,
        }
        return status, summary, pass_reasons, warn_reasons, fail_reasons

    # ------------------------------------------------------------------
    # Sampling helpers
    # ------------------------------------------------------------------
    def _sample_runner(self) -> Tuple[int, int, int]:
        """Return current cumulative (seen, processed, exceptions)."""
        if self._paper_runner is None:
            return (0, 0, 0)
        m = getattr(self._paper_runner, "metrics", None)
        if m is None:
            return (0, 0, 0)
        return (
            int(getattr(m, "opportunities_seen", 0) or 0),
            int(getattr(m, "opportunities_processed", 0) or 0),
            int(getattr(m, "exceptions", 0) or 0),
        )

    async def _sample_evidence_delta(
        self,
    ) -> Tuple[
        Dict[str, int],       # outcome delta counts
        int,                  # executable delta count
        List[str],            # validation_ids in delta
        Dict[str, float],     # stage p95 in delta
        Optional[str],        # new "last created_at" boundary
    ]:
        """Query the evidence repo for docs created since the last boundary."""
        outcome_delta: Dict[str, int] = {}
        exec_delta = 0
        validation_ids: List[str] = []
        stage_durations: Dict[str, List[float]] = {}

        last_boundary = self._baseline.get("last_evidence_created_at")

        # Prefer bounded direct-collection scan for delta.
        docs: List[Dict[str, Any]] = []
        try:
            col = getattr(self._evidence_repo, "_col", None)
            if col is not None:
                q: Dict[str, Any] = {}
                if last_boundary:
                    q["created_at"] = {"$gt": last_boundary}
                cur = col.find(q, sort=[("created_at", 1)]).limit(
                    self._evidence_sample
                )
                async for doc in cur:
                    docs.append(doc)
            else:
                # Fallback via public repo surface (in-memory / stub).
                items = await self._evidence_repo.list_recent(
                    limit=self._evidence_sample
                )
                docs = [
                    (i.to_mongo() if hasattr(i, "to_mongo") else i)
                    for i in items
                ]
        except Exception:
            raise

        new_boundary = last_boundary
        for doc in docs:
            outcome = str(doc.get("outcome") or "UNKNOWN")
            outcome_delta[outcome] = outcome_delta.get(outcome, 0) + 1
            if outcome == "EXECUTABLE":
                exec_delta += 1
            vid = doc.get("validation_id")
            if vid:
                validation_ids.append(str(vid))
            created_at = doc.get("created_at")
            if isinstance(created_at, str):
                if new_boundary is None or created_at > new_boundary:
                    new_boundary = created_at
            # Stage durations for p95 computation
            for stage in (doc.get("stages") or []):
                name = str(stage.get("stage") or stage.get("name") or "").strip()
                if not name:
                    continue
                dur = stage.get("duration_ms")
                if dur is None:
                    continue
                stage_durations.setdefault(name, []).append(float(dur))

        stage_p95 = {name: _p95(vals) for name, vals in stage_durations.items()}
        return outcome_delta, exec_delta, validation_ids, stage_p95, new_boundary

    async def _reset_baseline(self) -> None:
        """Set baseline to the current world state so cycle #0 is a
        clean delta (i.e. only records what happens AFTER start_run)."""
        try:
            evidence_total = await self._evidence_repo.count()
        except Exception:  # noqa: BLE001
            evidence_total = 0
        try:
            outcome_counts = await self._evidence_repo.outcome_histogram()
        except Exception:  # noqa: BLE001
            outcome_counts = {}
        seen, processed, exc = self._sample_runner()
        # Baseline last_created_at = the most recent EvidenceBundle
        # already present so cycle #0 only picks up new ones.
        last_created_at = None
        try:
            recent = await self._evidence_repo.list_recent(limit=1)
            if recent:
                first = recent[0]
                d = first.to_mongo() if hasattr(first, "to_mongo") else first
                last_created_at = d.get("created_at")
        except Exception:  # noqa: BLE001
            last_created_at = None
        self._baseline = {
            "evidence_total": evidence_total,
            "outcome_counts": dict(outcome_counts),
            "runner_seen": seen,
            "runner_processed": processed,
            "runner_exceptions": exc,
            "last_boundary_ts": time.monotonic(),
            "last_evidence_created_at": last_created_at,
        }

    async def _advance_baseline(self) -> None:
        seen, processed, exc = self._sample_runner()
        try:
            evidence_total = await self._evidence_repo.count()
        except Exception:  # noqa: BLE001
            evidence_total = int(self._baseline.get("evidence_total", 0))
        self._baseline["runner_seen"] = seen
        self._baseline["runner_processed"] = processed
        self._baseline["runner_exceptions"] = exc
        self._baseline["evidence_total"] = evidence_total
        self._baseline["last_boundary_ts"] = time.monotonic()
