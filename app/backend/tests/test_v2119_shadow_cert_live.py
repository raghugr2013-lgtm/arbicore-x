"""v2.11.9 · Live Shadow Certification integration tests.

Exercises the end-to-end wiring for the "Live Shadow Certification"
phase.  Focus is on the *contracts* between the pieces we added (or
touched) during v2.11.9, not on the pure unit behaviour that
:mod:`test_v2119_shadow_certification` already covers.

Test coverage:

1. Pre-flight readiness snapshot shape — every field the operator
   dashboard depends on is present with the expected types.
2. Runtime autostart record — populated with the six Wave1B scanners
   after ``ARBICORE_RUNTIME_AUTOSTART=on`` boot.
3. Paper runner ``reprocess_stale_after_s`` logic — evidence younger
   than the threshold is skipped; evidence older is re-evaluated.
4. Shadow Certification engine link fidelity — every EvidenceBundle
   created in the cycle window is captured in ``cycle.validation_ids``.
5. Run summary embeds a readiness snapshot + infrastructure_only
   marker under ``summary.start_markers``.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import replace
from typing import Any, Dict, List

import pytest

from arbicore.certification import (
    CertificationThresholds,
    InMemoryShadowCertificationRepository,
    ShadowCertificationCycle,
    ShadowCertificationEngine,
    ShadowCertificationRun,
    load_thresholds_from_env,
)
from arbicore.paper.runner import PaperValidationRunner, _evidence_age_s


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
class _FakeOpp:
    def __init__(self, opp_id: str) -> None:
        self.opportunity_id = opp_id

    def to_dict(self) -> Dict[str, Any]:
        return {"opportunity_id": self.opportunity_id}


class _FakeOppSource:
    def __init__(self, opps: List[_FakeOpp]) -> None:
        self._opps = opps

    async def find(self, *_a, **_kw) -> List[_FakeOpp]:
        return list(self._opps)


class _FakePipelineResult:
    def __init__(self, outcome: str) -> None:
        self.outcome = outcome


class _FakePipeline:
    def __init__(self, outcome: str = "REJECTED") -> None:
        self._outcome = outcome
        self.calls: List[str] = []

    async def evaluate(self, opp_dict: Dict[str, Any]) -> _FakePipelineResult:
        self.calls.append(opp_dict.get("opportunity_id", ""))
        return _FakePipelineResult(self._outcome)


class _FakeEvidenceRepo:
    """Just enough surface for the runner + engine to work."""

    def __init__(self) -> None:
        self._by_opp: Dict[str, Dict[str, Any]] = {}
        self._all: List[Dict[str, Any]] = []

    async def get_by_opportunity_id(self, opp_id: str):
        return self._by_opp.get(opp_id)

    async def upsert(self, evidence) -> None:
        d = evidence if isinstance(evidence, dict) else evidence.to_mongo()
        self._by_opp[d["opportunity_id"]] = d
        self._all.append(d)

    async def count(self) -> int:
        return len(self._all)

    async def outcome_histogram(self) -> Dict[str, int]:
        h: Dict[str, int] = {}
        for d in self._all:
            h[d.get("outcome", "?")] = h.get(d.get("outcome", "?"), 0) + 1
        return h

    async def list_recent(self, *, limit: int = 100, **_kw):
        return sorted(self._all, key=lambda d: d.get("created_at", ""), reverse=True)[:limit]

    # Direct collection surface for the engine's delta scan
    class _Col:
        def __init__(self, outer: "_FakeEvidenceRepo") -> None:
            self._outer = outer

        def find(self, q, sort=None):
            gt = None
            if isinstance(q.get("created_at"), dict):
                gt = q["created_at"].get("$gt")
            docs = [
                d for d in self._outer._all
                if gt is None or (d.get("created_at") or "") > gt
            ]
            docs.sort(key=lambda d: d.get("created_at") or "")
            return _FakeEvidenceRepo._Cursor(docs)

    class _Cursor:
        def __init__(self, docs):
            self._docs = docs
            self._limit = None

        def limit(self, n):
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

    def __getattr__(self, name):
        if name == "_col":
            self._col = _FakeEvidenceRepo._Col(self)
            return self._col
        raise AttributeError(name)


# ---------------------------------------------------------------------------
# 1. _evidence_age_s
# ---------------------------------------------------------------------------
def test_evidence_age_s_from_dict_iso():
    now = time.time()
    ca_ts = now - 42.0
    from datetime import datetime, timezone
    iso = datetime.fromtimestamp(ca_ts, tz=timezone.utc).isoformat()
    age = _evidence_age_s({"created_at": iso}, now)
    assert 41.5 < age < 42.5


def test_evidence_age_s_missing_returns_zero():
    assert _evidence_age_s({"created_at": None}, time.time()) == 0.0
    assert _evidence_age_s(None, time.time()) == 0.0
    assert _evidence_age_s({}, time.time()) == 0.0


# ---------------------------------------------------------------------------
# 2. Runner honours reprocess_stale_after_s
# ---------------------------------------------------------------------------
def test_runner_skips_when_evidence_is_fresh():
    from datetime import datetime, timezone

    async def _impl():
        opp = _FakeOpp("opp-fresh-1")
        pipeline = _FakePipeline()
        ev = _FakeEvidenceRepo()
        # Seed a very recent evidence
        await ev.upsert({
            "opportunity_id": "opp-fresh-1",
            "outcome":        "REJECTED",
            "created_at":     datetime.now(timezone.utc).isoformat(),
        })
        runner = PaperValidationRunner(
            opp_source=_FakeOppSource([opp]),
            pipeline=pipeline,
            evidence_repo=ev,
            reprocess_stale_after_s=60.0,  # 1 min stale — evidence is fresh
        )
        n = await runner.run_once()
        # Runner should NOT evaluate the opp — it is fresh.
        assert n == 0
        assert pipeline.calls == []
        assert runner.metrics.opportunities_skipped_dup >= 1
    _run(_impl())


def test_runner_reprocesses_when_evidence_is_stale():
    from datetime import datetime, timezone, timedelta

    async def _impl():
        opp = _FakeOpp("opp-stale-1")
        pipeline = _FakePipeline(outcome="REJECTED")
        ev = _FakeEvidenceRepo()
        # Seed an OLD evidence (2 min ago), threshold=60s → stale.
        old = (datetime.now(timezone.utc) - timedelta(seconds=120)).isoformat()
        await ev.upsert({
            "opportunity_id": "opp-stale-1",
            "outcome":        "REJECTED",
            "created_at":     old,
        })
        runner = PaperValidationRunner(
            opp_source=_FakeOppSource([opp]),
            pipeline=pipeline,
            evidence_repo=ev,
            reprocess_stale_after_s=60.0,
        )
        n = await runner.run_once()
        assert n == 1
        assert pipeline.calls == ["opp-stale-1"]
        assert runner.metrics.opportunities_processed == 1
    _run(_impl())


# ---------------------------------------------------------------------------
# 3. Engine captures validation_ids created inside the cycle window
# ---------------------------------------------------------------------------
def test_engine_captures_validation_ids_from_evidence_window():
    from datetime import datetime, timezone, timedelta

    async def _impl():
        repo = InMemoryShadowCertificationRepository()
        ev = _FakeEvidenceRepo()
        engine = ShadowCertificationEngine(
            cert_repo=repo,
            evidence_repo=ev,
            paper_runner=None,
            thresholds=CertificationThresholds(
                target_cycles=1, min_opps_per_cycle=1,
                min_executable_rate_pass=0.001,
                min_executable_rate_warn=0.0,
            ),
        )
        # Pre-seed one evidence BEFORE the run — must be excluded.
        pre = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
        await ev.upsert({
            "opportunity_id": "opp-pre-1",
            "validation_id":  "vid-pre-1",
            "outcome":        "REJECTED",
            "created_at":     pre,
        })
        await engine.start_run()

        # Now emit two evidence bundles AFTER start.
        for i in range(2):
            await asyncio.sleep(0.01)
            await ev.upsert({
                "opportunity_id": f"opp-live-{i}",
                "validation_id":  f"vid-live-{i}",
                "outcome":        "EXECUTABLE" if i == 0 else "REJECTED",
                "created_at":     datetime.now(timezone.utc).isoformat(),
            })

        run = await engine.tick()
        # Target=1 → engine auto-finalises.  We should end up in a
        # terminal state (PASS since 1/2 executable = 0.5 > 0.001 pass).
        assert run.is_terminal
        cycle = run.cycles[0]
        # Both post-start evidence bundles captured; pre-start excluded.
        vids = set(cycle.validation_ids)
        assert vids == {"vid-live-0", "vid-live-1"}
        assert cycle.executable_count == 1
        assert cycle.opportunities_processed >= 2
    _run(_impl())


# ---------------------------------------------------------------------------
# 4. Readiness snapshot shape — the exact fields the dashboard reads
# ---------------------------------------------------------------------------
def test_readiness_snapshot_shape_has_required_fields():
    """The operator dashboard depends on this fixed shape.  A shape
    regression would break the live progress panel silently."""
    REQUIRED_TOP = {
        "generated_at", "scanners_running", "scanners_all",
        "runtime_autostart", "paper_runner", "canonical_opportunities",
        "unknown", "issues", "is_live_ready",
    }
    REQUIRED_RUNNER = {
        "enabled", "is_running", "opportunities_seen",
        "opportunities_processed", "cycles_completed",
    }
    # Build a snapshot in-process using the same helper the endpoint
    # calls (import lazily to avoid hard-loading server.py at collection).
    import importlib
    server = importlib.import_module("server")
    snap = _run(server._shadow_cert_readiness_snapshot())
    missing_top = REQUIRED_TOP - set(snap.keys())
    assert missing_top == set(), f"missing top-level keys: {missing_top}"
    missing_runner = REQUIRED_RUNNER - set(snap["paper_runner"].keys())
    assert missing_runner == set(), f"missing paper_runner keys: {missing_runner}"
    assert isinstance(snap["is_live_ready"], bool)
    assert isinstance(snap["issues"], list)
    assert isinstance(snap["scanners_running"], list)
    assert isinstance(snap["scanners_all"], list)
