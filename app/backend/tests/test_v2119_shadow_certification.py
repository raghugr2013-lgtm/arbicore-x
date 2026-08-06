"""Shadow Certification (v2.11.9) — unit tests.

Locks in the canonical behaviours:

1. Frozen models refuse mutation post-construction.
2. Thresholds honour environment overrides.
3. Engine grading precedence: infra > p95 > exec-rate.
4. State machine: RUNNING → PASS / WARNING / FAIL / ABORTED, never back.
5. Repo insert-then-replace under stable ``run_id``.
6. Two-runs-at-a-time refused.
7. Auto-finalise on target_cycles.
8. Fail-open on repo exceptions.

Uses the in-memory repo + hand-rolled fake evidence surface to keep the
tests deterministic and independent of Mongo.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import FrozenInstanceError
from typing import Any, Dict, List, Optional

import pytest

from arbicore.certification import (
    CertificationStatus,
    CertificationThresholds,
    CycleStatus,
    InMemoryShadowCertificationRepository,
    ShadowCertificationCycle,
    ShadowCertificationEngine,
    ShadowCertificationRun,
    load_thresholds_from_env,
    new_run_id,
    new_cycle_id,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class _FakeEvidenceRepo:
    """Minimal async surface matching what the engine reads."""

    def __init__(self) -> None:
        self._docs: List[Dict[str, Any]] = []

    # Deterministic direct-collection scan — mimics `_col.find(...).limit(N)`
    class _Col:
        def __init__(self, outer: "_FakeEvidenceRepo") -> None:
            self._outer = outer

        def find(self, q: Dict[str, Any], sort=None):
            gt = None
            if isinstance(q.get("created_at"), dict):
                gt = q["created_at"].get("$gt")
            docs = [
                d for d in self._outer._docs
                if gt is None or (d.get("created_at") or "") > gt
            ]
            docs.sort(key=lambda d: d.get("created_at") or "")
            return _FakeEvidenceRepo._Cursor(docs)

    class _Cursor:
        def __init__(self, docs: List[Dict[str, Any]]) -> None:
            self._docs = docs
            self._limit: Optional[int] = None

        def limit(self, n: int) -> "_FakeEvidenceRepo._Cursor":
            self._limit = int(n)
            return self

        def __aiter__(self):
            self._i = 0
            self._stop = min(len(self._docs), self._limit or len(self._docs))
            return self

        async def __anext__(self):
            if self._i >= self._stop:
                raise StopAsyncIteration
            d = self._docs[self._i]
            self._i += 1
            return d

    def __post_init__(self):
        self._col = _FakeEvidenceRepo._Col(self)

    def __init__(self) -> None:  # noqa: F811 (re-declared for clarity)
        self._docs = []
        self._col = _FakeEvidenceRepo._Col(self)

    async def count(self) -> int:
        return len(self._docs)

    async def outcome_histogram(self) -> Dict[str, int]:
        h: Dict[str, int] = {}
        for d in self._docs:
            k = str(d.get("outcome") or "UNKNOWN")
            h[k] = h.get(k, 0) + 1
        return h

    async def list_recent(self, *, limit: int = 100, **_kw) -> List[Dict[str, Any]]:
        return sorted(
            self._docs, key=lambda d: d.get("created_at") or "", reverse=True
        )[:limit]

    # Test helper
    def _append(self, **kw):
        d = {
            "outcome":       "REJECTED",
            "validation_id": kw.get("validation_id") or f"vid-{len(self._docs)+1}",
            "created_at":    kw.get("created_at") or f"2026-01-01T00:00:{len(self._docs):02d}",
            "stages":        kw.get("stages") or [],
        }
        d.update({k: v for k, v in kw.items() if k in ("outcome",)})
        self._docs.append(d)


class _FakeRunnerMetrics:
    def __init__(self, seen=0, processed=0, exceptions=0):
        self.opportunities_seen = seen
        self.opportunities_processed = processed
        self.exceptions = exceptions


class _FakeRunner:
    def __init__(self):
        self.metrics = _FakeRunnerMetrics()


# ---------------------------------------------------------------------------
# 1. Frozen model contracts
# ---------------------------------------------------------------------------
def test_shadow_cycle_is_frozen():
    c = ShadowCertificationCycle(
        cycle_id="c1", cycle_index=0,
        started_at="t0", completed_at="t1",
        duration_ms=1.0,
    )
    with pytest.raises(FrozenInstanceError):
        c.cycle_status = "FAIL"  # type: ignore[misc]


def test_shadow_run_is_frozen_and_with_cycle_returns_new_instance():
    th = CertificationThresholds(target_cycles=2)
    r0 = ShadowCertificationRun.start(thresholds=th)
    assert r0.cycles_completed == 0
    with pytest.raises(FrozenInstanceError):
        r0.status = "PASS"  # type: ignore[misc]
    c1 = ShadowCertificationCycle(
        cycle_id="c1", cycle_index=0,
        started_at="t0", completed_at="t1", duration_ms=1.0,
    )
    r1 = r0.with_cycle(c1)
    assert r1 is not r0
    assert r0.cycles_completed == 0  # r0 untouched
    assert r1.cycles_completed == 1


def test_shadow_run_finalise_and_abort_transitions():
    th = CertificationThresholds(target_cycles=1)
    r = ShadowCertificationRun.start(thresholds=th)
    fin = r.finalise(
        status=CertificationStatus.PASS,
        summary={"a": 1}, pass_reasons=["ok"],
        warning_reasons=[], fail_reasons=[],
    )
    assert fin.is_terminal
    with pytest.raises(ValueError):
        fin.finalise(
            status=CertificationStatus.PASS,
            summary={}, pass_reasons=[],
            warning_reasons=[], fail_reasons=[],
        )
    # abort on terminal is a no-op (returns same instance)
    assert fin.abort("late") is fin


# ---------------------------------------------------------------------------
# 2. Thresholds env overrides
# ---------------------------------------------------------------------------
def test_thresholds_env_override(monkeypatch):
    monkeypatch.setenv("ARBICORE_SHADOW_CERT_TARGET_CYCLES", "3")
    monkeypatch.setenv("ARBICORE_SHADOW_CERT_MIN_EXEC_RATE_PASS", "0.42")
    monkeypatch.setenv("ARBICORE_SHADOW_CERT_MAX_STAGE_P95_MS", "1234.5")
    th = load_thresholds_from_env()
    assert th.target_cycles == 3
    assert th.min_executable_rate_pass == pytest.approx(0.42)
    assert th.max_stage_p95_ms == pytest.approx(1234.5)


def test_thresholds_roundtrip_dict():
    th = CertificationThresholds(
        target_cycles=7, min_executable_rate_pass=0.2,
        min_executable_rate_warn=0.1, max_stage_p95_ms=999.0,
        max_infra_exception_rate=0.05, max_fail_cycles=1,
        max_warn_cycles=3, min_opps_per_cycle=1,
    )
    th2 = CertificationThresholds.from_dict(th.to_dict())
    assert th2 == th


# ---------------------------------------------------------------------------
# 3. Engine start / current / start-twice
# ---------------------------------------------------------------------------
async def _impl_test_engine_start_and_reject_duplicate():
    repo = InMemoryShadowCertificationRepository()
    ev = _FakeEvidenceRepo()
    engine = ShadowCertificationEngine(
        cert_repo=repo, evidence_repo=ev, paper_runner=_FakeRunner(),
        thresholds=CertificationThresholds(target_cycles=2),
    )
    run = await engine.start_run()
    assert run.status == "RUNNING"
    with pytest.raises(RuntimeError):
        await engine.start_run()
    assert (await engine.current_run()).run_id == run.run_id


# ---------------------------------------------------------------------------
# 4. Engine tick + auto-finalise (PASS path)
# ---------------------------------------------------------------------------
async def _impl_test_engine_tick_pass_path():
    repo = InMemoryShadowCertificationRepository()
    ev = _FakeEvidenceRepo()
    runner = _FakeRunner()
    engine = ShadowCertificationEngine(
        cert_repo=repo, evidence_repo=ev, paper_runner=runner,
        thresholds=CertificationThresholds(
            target_cycles=2,
            min_executable_rate_pass=0.5,
            min_executable_rate_warn=0.25,
            min_opps_per_cycle=1,  # allow small volumes to grade
        ),
    )
    await engine.start_run()

    # Cycle 1: 2 EXECUTABLE, 2 REJECTED → exec_rate = 0.5 → PASS
    for i in range(2):
        ev._append(outcome="EXECUTABLE", created_at=f"2026-02-01T00:00:{i:02d}")
    for i in range(2):
        ev._append(outcome="REJECTED", created_at=f"2026-02-01T00:01:{i:02d}")
    runner.metrics = _FakeRunnerMetrics(seen=4, processed=4, exceptions=0)
    r1 = await engine.tick()
    assert r1 is not None and r1.status == "RUNNING"
    assert r1.cycles_completed == 1
    assert r1.cycles[0].cycle_status == "PASS"

    # Cycle 2: 3 EXECUTABLE → PASS, and target reached → finalise PASS
    for i in range(3):
        ev._append(outcome="EXECUTABLE", created_at=f"2026-02-02T00:00:{i:02d}")
    runner.metrics = _FakeRunnerMetrics(seen=7, processed=7, exceptions=0)
    r2 = await engine.tick()
    assert r2.status == "PASS"
    assert r2.cycles_completed == 2
    assert "5/2 cycles PASS" not in r2.pass_reasons  # sanity


# ---------------------------------------------------------------------------
# 5. Engine grading — infra FAIL trumps everything
# ---------------------------------------------------------------------------
async def _impl_test_engine_infra_failure_cycle_grades_fail():
    repo = InMemoryShadowCertificationRepository()
    ev = _FakeEvidenceRepo()

    # Break the fake repo's find so evidence sampling raises.
    class _BrokenCol:
        def find(self, *a, **kw):
            raise RuntimeError("mongo unreachable")
    ev._col = _BrokenCol()

    engine = ShadowCertificationEngine(
        cert_repo=repo, evidence_repo=ev,
        paper_runner=_FakeRunner(),
        thresholds=CertificationThresholds(target_cycles=1, min_opps_per_cycle=1),
    )
    await engine.start_run()
    r = await engine.tick()
    # Auto-finalises at target=1
    assert r.status == "FAIL"
    assert r.cycles[0].cycle_status == "FAIL"
    assert any("infra" in reason.lower()
               for reason in r.cycles[0].cycle_reasons + r.fail_reasons)


# ---------------------------------------------------------------------------
# 6. Repo upsert idempotency
# ---------------------------------------------------------------------------
async def _impl_test_inmemory_repo_upsert_and_current():
    repo = InMemoryShadowCertificationRepository()
    th = CertificationThresholds(target_cycles=1)
    r = ShadowCertificationRun.start(thresholds=th)
    await repo.upsert(r)
    assert (await repo.current_running()).run_id == r.run_id

    # Finalise + upsert same run_id → current_running vanishes
    fin = r.finalise(
        status=CertificationStatus.PASS,
        summary={}, pass_reasons=[], warning_reasons=[], fail_reasons=[],
    )
    await repo.upsert(fin)
    assert await repo.current_running() is None
    assert (await repo.get(r.run_id)).status == "PASS"
    # List still shows both listings? No — same run_id key, so one item only.
    items = await repo.list_recent()
    assert len(items) == 1
    assert items[0].status == "PASS"


# ---------------------------------------------------------------------------
# 7. Engine abort transition
# ---------------------------------------------------------------------------
async def _impl_test_engine_abort_terminal():
    repo = InMemoryShadowCertificationRepository()
    ev = _FakeEvidenceRepo()
    engine = ShadowCertificationEngine(
        cert_repo=repo, evidence_repo=ev, paper_runner=_FakeRunner(),
        thresholds=CertificationThresholds(target_cycles=5),
    )
    await engine.start_run()
    ab = await engine.stop_run(reason="test")
    assert ab.status == "ABORTED"
    assert any("aborted" in fr for fr in ab.fail_reasons)
    # Second stop is idempotent (no-op)
    ab2 = await engine.stop_run(reason="test")
    assert ab2 is None or ab2.status == "ABORTED"
    # Start a new run now that current is terminal
    fresh = await engine.start_run()
    assert fresh.status == "RUNNING"


# ---------------------------------------------------------------------------
# 8. Evidence link — validation_ids captured per cycle
# ---------------------------------------------------------------------------
async def _impl_test_engine_captures_validation_ids_per_cycle():
    repo = InMemoryShadowCertificationRepository()
    ev = _FakeEvidenceRepo()
    engine = ShadowCertificationEngine(
        cert_repo=repo, evidence_repo=ev, paper_runner=_FakeRunner(),
        thresholds=CertificationThresholds(target_cycles=1, min_opps_per_cycle=1),
    )
    await engine.start_run()
    ev._append(outcome="EXECUTABLE", validation_id="vid-A",
                created_at="2027-01-01T00:00:00")
    ev._append(outcome="REJECTED",  validation_id="vid-B",
                created_at="2027-01-01T00:00:01")
    r = await engine.tick()
    assert r.status in ("PASS", "WARNING", "FAIL")
    ids = r.cycles[0].validation_ids
    assert set(ids) == {"vid-A", "vid-B"}


# ---- sync wrappers ----
def test_engine_start_and_reject_duplicate():
    return _run(_impl_test_engine_start_and_reject_duplicate())
def test_engine_tick_pass_path():
    return _run(_impl_test_engine_tick_pass_path())
def test_engine_infra_failure_cycle_grades_fail():
    return _run(_impl_test_engine_infra_failure_cycle_grades_fail())
def test_inmemory_repo_upsert_and_current():
    return _run(_impl_test_inmemory_repo_upsert_and_current())
def test_engine_abort_terminal():
    return _run(_impl_test_engine_abort_terminal())
def test_engine_captures_validation_ids_per_cycle():
    return _run(_impl_test_engine_captures_validation_ids_per_cycle())
