"""Bounded shared verification worker pool for flash-loan candidates.

Design (B2-preserving):
  B2 fair ``claim_batch`` selects chain-balanced jobs FIRST.
  This module only executes verification of already-claimed candidates
  with bounded concurrency (shared across all chains).

Does NOT:
  - select/claim candidates (B2 remains authoritative)
  - alter H05 sizing or Gate-7 thresholds
  - enable LIVE / signing / broadcast
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, TypeVar

T = TypeVar("T")

# Hard ceiling for a single scanner process. Benchmarks use 6/12/24/36.
MAX_VERIFICATION_WORKERS = 36
DEFAULT_VERIFICATION_WORKERS = 2
MAX_CLAIM_BATCH_SIZE = 256
DEFAULT_CLAIM_BATCH_FLOOR = 32

ENV_WORKERS = "ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS"
ENV_CLAIM_BATCH = "ARBICORE_FLASH_LOAN_CLAIM_BATCH_SIZE"


def resolve_verification_workers(cfg: Optional[Dict[str, Any]] = None) -> int:
    """Resolve worker count: env override → scanner config → default.

    Caps at ``MAX_VERIFICATION_WORKERS``. Never returns < 1.
    """
    raw: Any = None
    env = os.environ.get(ENV_WORKERS)
    if env is not None and str(env).strip() != "":
        raw = env
    elif isinstance(cfg, dict) and cfg.get("verifier_concurrency") is not None:
        raw = cfg.get("verifier_concurrency")
    else:
        raw = DEFAULT_VERIFICATION_WORKERS
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_VERIFICATION_WORKERS
    return max(1, min(MAX_VERIFICATION_WORKERS, n))


def resolve_claim_batch_size(
    cfg: Optional[Dict[str, Any]] = None,
    *,
    workers: Optional[int] = None,
) -> int:
    """Claim size after B2 fairness: keep workers busy without unbounded grabs.

    Default: ``max(32, workers)`` so a 36-worker pool claims 36 fair jobs/tick
    rather than starving capacity behind a hard 32 ceiling.
    """
    w = workers if workers is not None else resolve_verification_workers(cfg)
    env = os.environ.get(ENV_CLAIM_BATCH)
    if env is not None and str(env).strip() != "":
        try:
            return max(1, min(MAX_CLAIM_BATCH_SIZE, int(env)))
        except (TypeError, ValueError):
            pass
    if isinstance(cfg, dict) and cfg.get("claim_batch_size") is not None:
        try:
            return max(1, min(MAX_CLAIM_BATCH_SIZE, int(cfg["claim_batch_size"])))
        except (TypeError, ValueError):
            pass
    return max(DEFAULT_CLAIM_BATCH_FLOOR, int(w))


def resolve_claim_ttl_s(
    *,
    batch_size: int,
    workers: int,
    base_ttl_s: float = 60.0,
) -> float:
    """Extend claim lock so parallel verify can finish before TTL steal.

    Rough bound: wall ≈ (batch/workers) * ~5s per verify, plus margin.
    """
    w = max(1, int(workers))
    b = max(1, int(batch_size))
    estimated = (b / w) * 5.0 + 30.0
    return float(max(base_ttl_s, estimated, 120.0))


class VerificationPoolStats:
    """In-process instrumentation for worker-pool benchmarks."""

    def __init__(self) -> None:
        self.workers_configured: int = 0
        self.workers_active_peak: int = 0
        self._active: int = 0
        self.jobs_started: int = 0
        self.jobs_completed: int = 0
        self.jobs_failed: int = 0
        self.jobs_cancelled: int = 0
        self.verify_durations_s: List[float] = []
        self.last_batch_size: int = 0
        self.last_batch_wall_s: Optional[float] = None

    def begin(self, workers: int, batch_size: int) -> None:
        self.workers_configured = int(workers)
        self.last_batch_size = int(batch_size)

    def enter_job(self) -> None:
        self._active += 1
        self.jobs_started += 1
        if self._active > self.workers_active_peak:
            self.workers_active_peak = self._active

    def leave_job(self, *, ok: bool, duration_s: float,
                  cancelled: bool = False) -> None:
        self._active = max(0, self._active - 1)
        if cancelled:
            self.jobs_cancelled += 1
        elif ok:
            self.jobs_completed += 1
        else:
            self.jobs_failed += 1
        self.verify_durations_s.append(float(duration_s))

    def snapshot(self) -> Dict[str, Any]:
        xs = list(self.verify_durations_s)
        xs_sorted = sorted(xs)
        med = xs_sorted[len(xs_sorted) // 2] if xs_sorted else None
        return {
            "workers_configured": self.workers_configured,
            "workers_active_peak": self.workers_active_peak,
            "workers_active_now": self._active,
            "jobs_started": self.jobs_started,
            "jobs_completed": self.jobs_completed,
            "jobs_failed": self.jobs_failed,
            "jobs_cancelled": self.jobs_cancelled,
            "last_batch_size": self.last_batch_size,
            "last_batch_wall_s": self.last_batch_wall_s,
            "verify_duration_n": len(xs),
            "verify_duration_min_s": min(xs) if xs else None,
            "verify_duration_max_s": max(xs) if xs else None,
            "verify_duration_mean_s": (sum(xs) / len(xs)) if xs else None,
            "verify_duration_median_s": med,
            "max_workers_ceiling": MAX_VERIFICATION_WORKERS,
        }


async def run_bounded(
    items: Sequence[T],
    worker_fn: Callable[[T], Awaitable[Any]],
    *,
    workers: int,
    stop_event: Optional[asyncio.Event] = None,
    stats: Optional[VerificationPoolStats] = None,
    on_item_error: Optional[Callable[[T, BaseException], Awaitable[None]]] = None,
) -> List[Any]:
    """Run ``worker_fn`` over ``items`` with at most ``workers`` in flight.

    - Bounded by ``asyncio.Semaphore`` (no unbounded task fan-out beyond
      ``len(items)``, and never more than ``workers`` concurrent).
    - One item failure does not cancel siblings.
    - If ``stop_event`` is set before an item starts, that item is skipped
      (cancelled) and remaining queued items are skipped.
    """
    n = max(1, min(MAX_VERIFICATION_WORKERS, int(workers)))
    sem = asyncio.Semaphore(n)
    if stats is not None:
        stats.begin(n, len(items))

    async def _one(item: T) -> Any:
        if stop_event is not None and stop_event.is_set():
            if stats is not None:
                stats.enter_job()
                stats.leave_job(ok=False, duration_s=0.0, cancelled=True)
            return None
        async with sem:
            if stop_event is not None and stop_event.is_set():
                if stats is not None:
                    stats.enter_job()
                    stats.leave_job(ok=False, duration_s=0.0, cancelled=True)
                return None
            t0 = time.perf_counter()
            if stats is not None:
                stats.enter_job()
            try:
                result = await worker_fn(item)
                if stats is not None:
                    stats.leave_job(ok=True, duration_s=time.perf_counter() - t0)
                return result
            except asyncio.CancelledError:
                if stats is not None:
                    stats.leave_job(
                        ok=False,
                        duration_s=time.perf_counter() - t0,
                        cancelled=True,
                    )
                raise
            except Exception as exc:  # noqa: BLE001 — isolate per job
                if stats is not None:
                    stats.leave_job(ok=False, duration_s=time.perf_counter() - t0)
                if on_item_error is not None:
                    try:
                        await on_item_error(item, exc)
                    except Exception:  # noqa: BLE001
                        pass
                return exc

    t_batch = time.perf_counter()
    results = await asyncio.gather(*[_one(it) for it in items], return_exceptions=False)
    if stats is not None:
        stats.last_batch_wall_s = time.perf_counter() - t_batch
    return list(results)
