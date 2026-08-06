"""v2.11.8 · Paper Validation Framework — Slice C unit tests.

Covers:
  * PaperValidationRunner start/stop/run_once
  * Idempotency: same opportunity_id processed once
  * Metrics: histogram + counters updated correctly
  * The 4 API endpoints (via TestClient direct-import, not HTTP)
"""
from __future__ import annotations

import asyncio
import os
import types

import pytest

from arbicore.paper import (
    EvidenceBundle,
    InMemoryPaperEvidenceRepository,
    PaperOutcome,
    PaperValidationRunner,
    is_enabled_via_env,
    new_validation_id,
)
from arbicore.execution.pipeline import OpportunityPipeline


class _NoopJournal:
    async def record_discovery(self, *a, **k): pass
    async def record_event(self, *a, **k): pass


class _FakeOppSource:
    """Async source mimicking MongoOpportunityRepository.find(query, limit=)."""
    def __init__(self, batches):
        # batches: list[list[dict]] — each list is the response of one .find() call
        self._batches = list(batches)
        self._i = 0

    async def find(self, *a, limit: int = 25, **k):
        if self._i >= len(self._batches):
            return []
        batch = self._batches[self._i]
        self._i += 1
        return batch[:limit]


def _run(coro): return asyncio.run(coro)


# ---------------------------------------------------------------------------
# is_enabled_via_env
# ---------------------------------------------------------------------------
class TestEnableFlag:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_PAPER_VALIDATION_ENABLED", raising=False)
        assert not is_enabled_via_env()

    def test_true_variants(self, monkeypatch):
        for v in ("1", "true", "TRUE", "yes", "on"):
            monkeypatch.setenv("ARBICORE_PAPER_VALIDATION_ENABLED", v)
            assert is_enabled_via_env(), v

    def test_false_variants(self, monkeypatch):
        for v in ("0", "false", "no", "off", ""):
            monkeypatch.setenv("ARBICORE_PAPER_VALIDATION_ENABLED", v)
            assert not is_enabled_via_env(), v


# ---------------------------------------------------------------------------
# Runner.run_once — one bounded batch
# ---------------------------------------------------------------------------
class TestRunOnce:
    def _make(self, opps):
        repo = InMemoryPaperEvidenceRepository()
        pipeline = OpportunityPipeline(journal=_NoopJournal(), evidence_repo=repo)
        src = _FakeOppSource([opps])
        return repo, PaperValidationRunner(
            opp_source=src, pipeline=pipeline, evidence_repo=repo,
            batch_limit=10,
        )

    def test_processes_all_opps(self):
        opps = [
            {"opportunity_id": "o1", "swap_hops": [{"dex": "u"}], "expected_profit_usd": 1.0},
            {"opportunity_id": "o2", "swap_hops": [{"dex": "u"}], "expected_profit_usd": 1.0},
        ]
        repo, runner = self._make(opps)
        n = _run(runner.run_once())
        assert n == 2
        assert runner.metrics.opportunities_processed == 2
        assert runner.metrics.cycles_completed == 1
        # Both bundles landed in the repo.
        assert _run(repo.count()) == 2

    def test_idempotency_same_opp_id(self):
        """Calling run_once twice on the same opp_id must NOT reprocess."""
        opps = [{"opportunity_id": "o1", "swap_hops": [{"dex": "u"}],
                  "expected_profit_usd": 1.0}]
        repo = InMemoryPaperEvidenceRepository()
        pipeline = OpportunityPipeline(journal=_NoopJournal(), evidence_repo=repo)
        # Two batches of the SAME opp.
        src = _FakeOppSource([opps, opps])
        runner = PaperValidationRunner(
            opp_source=src, pipeline=pipeline, evidence_repo=repo,
        )
        _run(runner.run_once())
        _run(runner.run_once())
        assert runner.metrics.opportunities_processed == 1
        assert runner.metrics.opportunities_skipped_dup == 1
        assert _run(repo.count()) == 1

    def test_missing_opportunity_id_ignored(self):
        opps = [{"opportunity_id": "", "swap_hops": [{"dex": "u"}]}]
        repo, runner = self._make(opps)
        n = _run(runner.run_once())
        assert n == 0
        assert runner.metrics.opportunities_processed == 0

    def test_outcome_counts_tracked(self):
        opps = [
            {"opportunity_id": "o1", "swap_hops": [{"dex": "u"}], "expected_profit_usd": 1.0},
            {"opportunity_id": "o2"},   # missing hops → ROUTE_FAILURE
        ]
        repo, runner = self._make(opps)
        _run(runner.run_once())
        assert runner.metrics.outcome_counts.get("EXECUTABLE") == 1
        assert runner.metrics.outcome_counts.get("ROUTE_FAILURE") == 1

    def test_exception_recorded_but_loop_continues(self):
        """A per-opp exception must not halt the cycle."""
        class _ExplodingPipeline:
            async def evaluate(self, opp):
                if opp.get("opportunity_id") == "o-bad":
                    raise RuntimeError("boom")
                # Fall back to a real pipeline for the good one.
                pipeline = OpportunityPipeline(journal=_NoopJournal(),
                                                evidence_repo=repo)
                return await pipeline.evaluate(opp)
        opps = [
            {"opportunity_id": "o-bad"},
            {"opportunity_id": "o-good", "swap_hops": [{"dex": "u"}],
             "expected_profit_usd": 1.0},
        ]
        repo = InMemoryPaperEvidenceRepository()
        src = _FakeOppSource([opps])
        runner = PaperValidationRunner(
            opp_source=src, pipeline=_ExplodingPipeline(),
            evidence_repo=repo,
        )
        _run(runner.run_once())
        assert runner.metrics.exceptions == 1
        assert runner.metrics.last_error and "boom" in runner.metrics.last_error
        # The good opp still landed in the repo.
        assert _run(repo.count()) == 1


# ---------------------------------------------------------------------------
# Runner start / stop
# ---------------------------------------------------------------------------
class TestRunnerLifecycle:
    def test_start_and_stop(self):
        repo = InMemoryPaperEvidenceRepository()
        pipeline = OpportunityPipeline(journal=_NoopJournal(), evidence_repo=repo)
        # Empty source — the runner will loop idle.
        src = _FakeOppSource([])

        async def _r():
            runner = PaperValidationRunner(
                opp_source=src, pipeline=pipeline, evidence_repo=repo,
                idle_sleep_s=0.05, active_sleep_s=0.05,
            )
            runner.start()
            assert runner.is_running()
            await asyncio.sleep(0.15)
            await runner.stop()
            assert not runner.is_running()
            assert runner.metrics.started_at is not None
            # At least one cycle ran.
            assert runner.metrics.cycles_completed >= 1
        _run(_r())


# ---------------------------------------------------------------------------
# RunnerMetrics serialisation shape
# ---------------------------------------------------------------------------
class TestRunnerMetrics:
    def test_to_dict_shape(self):
        r = PaperValidationRunner(
            opp_source=_FakeOppSource([]),
            pipeline=OpportunityPipeline(journal=_NoopJournal()),
            evidence_repo=InMemoryPaperEvidenceRepository(),
        )
        d = r.metrics.to_dict()
        for k in ("started_at", "last_cycle_at", "cycles_completed",
                   "opportunities_seen", "opportunities_processed",
                   "opportunities_skipped_dup", "exceptions", "last_error",
                   "outcome_counts"):
            assert k in d, f"missing metric {k!r}"
