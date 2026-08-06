"""v2.11.8 · Paper Validation Framework — Slice A unit tests.

Covers the immutable evidence + outcome vocabulary + classifier +
pipeline integration.  Every assertion pins a contract the downstream
slices (B: simulate/liquidity, C: runner + API) will rely on.
"""
from __future__ import annotations

import asyncio
import re

import pytest

from arbicore.paper import (
    EvidenceBundle,
    InMemoryPaperEvidenceRepository,
    PaperOutcome,
    StageMetric,
    StageRecorder,
    TERMINAL_REASON_TO_OUTCOME,
    classify_outcome,
    new_validation_id,
)
from arbicore.execution.pipeline import OpportunityPipeline, PipelineResult


class _NoopJournal:
    async def record_discovery(self, *a, **k): pass
    async def record_event(self, *a, **k): pass


# ---------------------------------------------------------------------------
# 1. PaperOutcome vocabulary is closed at exactly 8 values
# ---------------------------------------------------------------------------
class TestOutcomeVocabulary:
    def test_exactly_eight_outcomes(self):
        assert set(PaperOutcome.all_values()) == {
            "EXECUTABLE", "REJECTED", "UNPROFITABLE",
            "LIQUIDITY_FAILURE", "GAS_FAILURE", "ROUTE_FAILURE",
            "RISK_FAILURE", "SIMULATION_FAILURE",
        }

    def test_outcome_is_string_enum(self):
        # Str-Enum semantics — Mongo can persist the raw .value directly.
        assert PaperOutcome.EXECUTABLE.value == "EXECUTABLE"
        assert str(PaperOutcome.EXECUTABLE) == "PaperOutcome.EXECUTABLE"


# ---------------------------------------------------------------------------
# 2. Validation ID + StageMetric contracts
# ---------------------------------------------------------------------------
class TestValidationId:
    _UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")

    def test_new_validation_id_is_uuid4(self):
        vid = new_validation_id()
        assert self._UUID_RE.match(vid), f"not a UUIDv4: {vid!r}"

    def test_new_validation_id_is_unique(self):
        ids = {new_validation_id() for _ in range(64)}
        assert len(ids) == 64


class TestStageMetric:
    def test_is_frozen(self):
        m = StageMetric(stage="quote", started_at="a", ended_at="b",
                         duration_ms=1.5, ok=True)
        with pytest.raises(Exception):
            m.stage = "gas"  # type: ignore[misc]

    def test_serialisation_shape(self):
        m = StageMetric(stage="quote", started_at="a", ended_at="b",
                         duration_ms=2.5, ok=False,
                         detail="no hops", failure_reason="no hops")
        d = m.to_dict()
        assert d == {
            "stage": "quote", "started_at": "a", "ended_at": "b",
            "duration_ms": 2.5, "ok": False, "detail": "no hops",
            "failure_reason": "no hops", "payload": {},
        }


# ---------------------------------------------------------------------------
# 3. EvidenceBundle is immutable + round-trips through Mongo dict
# ---------------------------------------------------------------------------
class TestEvidenceBundle:
    def _make(self, **overrides):
        base = dict(
            validation_id=new_validation_id(),
            opportunity_id="opp-1",
            strategy="flash_loan_arbitrage",
            mode="SHADOW",
            outcome=PaperOutcome.EXECUTABLE,
            outcome_reason="all stages passed",
        )
        base.update(overrides)
        return EvidenceBundle(**base)

    def test_frozen(self):
        b = self._make()
        with pytest.raises(Exception):
            b.outcome = PaperOutcome.REJECTED  # type: ignore[misc]

    def test_to_mongo_serialises_enum(self):
        b = self._make()
        m = b.to_mongo()
        assert m["outcome"] == "EXECUTABLE"

    def test_from_mongo_roundtrip(self):
        b = self._make(scanner_family="CEX_ARBITRAGE",
                        simulation_backend="heuristic")
        m = b.to_mongo()
        b2 = EvidenceBundle.from_mongo(m)
        assert b2.outcome is PaperOutcome.EXECUTABLE
        assert b2.scanner_family == "CEX_ARBITRAGE"
        assert b2.simulation_backend == "heuristic"
        assert b2.validation_id == b.validation_id


# ---------------------------------------------------------------------------
# 4. StageRecorder captures start/end/duration and exception paths
# ---------------------------------------------------------------------------
class TestStageRecorder:
    async def _run_ok(self):
        metrics = []
        async with StageRecorder("quote", metrics) as rec:
            rec.set_result(ok=True, detail="ok", payload={"x": 1})
        return metrics

    async def _run_exc(self):
        metrics = []
        try:
            async with StageRecorder("gas", metrics) as rec:
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        return metrics

    def test_records_success(self):
        m = asyncio.run(self._run_ok())
        assert len(m) == 1
        assert m[0]["stage"] == "quote"
        assert m[0]["ok"] is True
        assert m[0]["duration_ms"] >= 0
        assert m[0]["failure_reason"] is None
        assert m[0]["payload"] == {"x": 1}
        assert m[0]["started_at"] and m[0]["ended_at"]

    def test_records_exception(self):
        m = asyncio.run(self._run_exc())
        assert len(m) == 1
        assert m[0]["ok"] is False
        assert "RuntimeError" in (m[0]["failure_reason"] or "")


# ---------------------------------------------------------------------------
# 5. Classifier — every failed stage maps to the correct outcome
# ---------------------------------------------------------------------------
class TestClassifier:
    def _stage(self, name, ok, reason=""):
        return {"stage": name, "ok": ok, "failure_reason": reason,
                "detail": reason}

    def test_all_ok_shadow_is_executable(self):
        stages = [self._stage("quote", True), self._stage("gas", True),
                   self._stage("profit", True)]
        o, _ = classify_outcome(action="shadow", stages=stages)
        assert o is PaperOutcome.EXECUTABLE

    def test_all_ok_broadcast_is_executable(self):
        o, _ = classify_outcome(action="broadcast", stages=[])
        assert o is PaperOutcome.EXECUTABLE

    def test_observe_is_rejected(self):
        o, _ = classify_outcome(action="observe", stages=[])
        assert o is PaperOutcome.REJECTED

    def test_stage_failures_route_correctly(self):
        cases = [
            ("quote",          PaperOutcome.ROUTE_FAILURE),
            ("gas",            PaperOutcome.GAS_FAILURE),
            ("profit",         PaperOutcome.UNPROFITABLE),
            ("policy",         PaperOutcome.RISK_FAILURE),
            ("certification",  PaperOutcome.RISK_FAILURE),
            ("liquidity",      PaperOutcome.LIQUIDITY_FAILURE),
            ("simulate",       PaperOutcome.SIMULATION_FAILURE),
            ("broadcast",      PaperOutcome.SIMULATION_FAILURE),
        ]
        for stage_name, expected in cases:
            stages = [self._stage(stage_name, False, "boom")]
            o, r = classify_outcome(action="reject", stages=stages)
            assert o is expected, (
                f"stage {stage_name!r} → expected {expected} got {o}"
            )
            assert r == "boom"

    def test_first_failure_wins(self):
        # Two failures — the first (route) wins over the second (gas).
        stages = [
            self._stage("quote", False, "no hops"),
            self._stage("gas",   False, "rpc down"),
        ]
        o, _ = classify_outcome(action="reject", stages=stages)
        assert o is PaperOutcome.ROUTE_FAILURE


# ---------------------------------------------------------------------------
# 6. InMemory repo enforces immutability
# ---------------------------------------------------------------------------
class TestInMemoryRepo:
    async def _bundle(self, **k):
        return EvidenceBundle(
            validation_id=k.get("vid") or new_validation_id(),
            opportunity_id=k.get("opp") or "opp-1",
            strategy="flash_loan_arbitrage", mode="SHADOW",
            outcome=k.get("outcome", PaperOutcome.EXECUTABLE),
            outcome_reason="",
        )

    async def _run(self, coro):
        return await coro

    def test_double_insert_rejected(self):
        async def _run():
            repo = InMemoryPaperEvidenceRepository()
            b = await self._bundle()
            await repo.insert(b)
            with pytest.raises(ValueError):
                await repo.insert(b)
        asyncio.run(_run())

    def test_get_by_validation_id_roundtrip(self):
        async def _run():
            repo = InMemoryPaperEvidenceRepository()
            b = await self._bundle()
            await repo.insert(b)
            got = await repo.get_by_validation_id(b.validation_id)
            assert got is not None
            assert got.opportunity_id == b.opportunity_id
        asyncio.run(_run())

    def test_outcome_histogram(self):
        async def _run():
            repo = InMemoryPaperEvidenceRepository()
            await repo.insert(await self._bundle(outcome=PaperOutcome.EXECUTABLE))
            await repo.insert(await self._bundle(outcome=PaperOutcome.EXECUTABLE, vid=new_validation_id(), opp="opp-2"))
            await repo.insert(await self._bundle(outcome=PaperOutcome.REJECTED,   vid=new_validation_id(), opp="opp-3"))
            hist = await repo.outcome_histogram()
            assert hist == {"EXECUTABLE": 2, "REJECTED": 1}
        asyncio.run(_run())

    def test_list_recent_filter_by_outcome(self):
        async def _run():
            repo = InMemoryPaperEvidenceRepository()
            await repo.insert(await self._bundle(outcome=PaperOutcome.EXECUTABLE))
            await repo.insert(await self._bundle(outcome=PaperOutcome.REJECTED,   vid=new_validation_id(), opp="opp-2"))
            rows = await repo.list_recent(outcome="REJECTED")
            assert len(rows) == 1
            assert rows[0].outcome is PaperOutcome.REJECTED
        asyncio.run(_run())


# ---------------------------------------------------------------------------
# 7. OpportunityPipeline classifies + persists exactly once
# ---------------------------------------------------------------------------
class TestPipelineIntegration:
    def _pipeline(self, repo):
        return OpportunityPipeline(journal=_NoopJournal(),
                                   evidence_repo=repo)

    def _run(self, coro):
        return asyncio.run(coro)

    def test_missing_opportunity_id_is_rejected(self):
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo)
            r = await p.evaluate({})
            assert r.outcome == "REJECTED"
            assert r.validation_id
            # Bundle is persisted even when opp_id was missing.
            assert await repo.count() == 1
        self._run(_r())

    def test_route_failure_classified(self):
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo)
            r = await p.evaluate({"opportunity_id": "opp-r",
                                   "expected_profit_usd": 1.0})
            assert r.outcome == "ROUTE_FAILURE"
        self._run(_r())

    def test_unprofitable_classified(self):
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo)
            r = await p.evaluate({"opportunity_id": "opp-u",
                                   "swap_hops": [{"dex": "uni-v3"}]})
            assert r.outcome == "UNPROFITABLE"
        self._run(_r())

    def test_executable_classified_and_persisted(self):
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo)
            r = await p.evaluate({
                "opportunity_id": "opp-e",
                "swap_hops": [{"dex": "uni-v3"}, {"dex": "sushi"}],
                "expected_profit_usd": 50.0,
                "borrow_amount_usd": 1000.0,
                "strategy": "flash_loan_arbitrage",
            })
            assert r.outcome == "EXECUTABLE"
            assert r.validation_id
            b = await repo.get_by_validation_id(r.validation_id)
            assert b is not None
            assert b.outcome is PaperOutcome.EXECUTABLE
            # Stage timing was captured for every stage.
            assert b.stages, "stages persisted"
            for s in b.stages:
                assert "started_at" in s
                assert "ended_at" in s
                assert "duration_ms" in s
                assert s["duration_ms"] >= 0
        self._run(_r())

    def test_reuses_upstream_validation_id(self):
        async def _r():
            repo = InMemoryPaperEvidenceRepository()
            p = self._pipeline(repo)
            given = new_validation_id()
            r = await p.evaluate({
                "opportunity_id": "opp-vid",
                "swap_hops": [{"dex": "uni-v3"}],
                "expected_profit_usd": 10.0,
                "validation_id": given,
            })
            assert r.validation_id == given
        self._run(_r())

    def test_pipeline_works_without_evidence_repo(self):
        """Backward compatibility — evidence_repo is optional."""
        async def _r():
            p = OpportunityPipeline(journal=_NoopJournal())  # no evidence_repo
            r = await p.evaluate({"opportunity_id": "opp-noevi",
                                   "swap_hops": [{"dex": "uni-v3"}],
                                   "expected_profit_usd": 10.0})
            # Still classifies, still returns outcome on PipelineResult.
            assert r.outcome == "EXECUTABLE"
            assert r.validation_id
        self._run(_r())
