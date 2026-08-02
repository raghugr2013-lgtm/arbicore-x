"""P0-D · Autonomous Executor — regression tests.

Unit tests drive the executor with a fake DiscoveryRepo + a stub
pipeline that records the calls. The critical safety invariants are
tested explicitly:

    * Default configuration starts in SHADOW/PAPER (via the pipeline's
      mode gate) → the fake broadcaster is NEVER called even when we
      feed it a fully-shaped flash-loan opportunity.
    * Terminal + consumed rows in the journal are skipped on subsequent
      ticks (no double-processing).
    * The learning ledger is invoked every N ticks and its errors do
      not crash the loop.
    * start/stop/tick_once are all idempotent.

HTTP contract tests exercise the four new routes.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import pytest
import requests

from arbicore.data.journal import (
    ExecutionStatus, LearningLabel, OpportunityJournal,
)
from arbicore.execution.auto_executor import AutoExecutor
from arbicore.execution.pipeline import OpportunityPipeline


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


def _await(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# =========================================================================
# In-memory Mongo (same shape as prior tests)
# =========================================================================

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs); self._k = None; self._d = 1; self._limit = None
    def sort(self, k, d=1):
        self._k, self._d = k, d; return self
    def limit(self, n):
        self._limit = int(n); return self
    def __aiter__(self):
        docs = self._docs
        if self._k:
            docs = sorted(docs, key=lambda x: x.get(self._k) or "", reverse=self._d < 0)
        if self._limit is not None:
            docs = docs[: self._limit]
        self._it = iter(docs); return self
    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.indexes = []
    async def create_index(self, *a, **kw):
        self.indexes.append((a, kw)); return "ok"
    async def find_one(self, filt, projection=None):
        k = filt.get("opportunity_id"); d = self.docs.get(k)
        return dict(d) if d else None
    async def update_one(self, filt, update, upsert=False):
        k = filt["opportunity_id"]
        cur = self.docs.get(k, {"opportunity_id": k})
        cur.update(update.get("$set", {}))
        self.docs[k] = cur
        return type("R", (), {"matched_count": 1})
    def find(self, filt=None, projection=None):
        docs = list(self.docs.values())
        if filt:
            def m(d):
                for kk, vv in filt.items():
                    if d.get(kk) != vv:
                        return False
                return True
            docs = [d for d in docs if m(d)]
        return _Cursor(docs)
    async def aggregate(self, pipeline):
        if False:
            yield {}


class _DB:
    def __init__(self):
        self._c: Dict[str, _Coll] = {}
    def __getitem__(self, n):
        return self._c.setdefault(n, _Coll())


# =========================================================================
# Fakes
# =========================================================================

class _FakeDiscoveryRepo:
    def __init__(self, rows):
        self.rows = list(rows)

    async def list_recent(self, *, status=None, chain=None, limit=50):
        return list(self.rows)[: int(limit)]


class _RecordingPipeline:
    """Journals the discovery event but does no downstream work — the
    executor's job is only to invoke it. What the pipeline does with
    each opportunity is exhaustively covered in test_p0c_pipeline_glue.
    """

    def __init__(self, journal, action="shadow"):
        self._journal = journal
        self._action = action
        self.calls: List[str] = []

    async def evaluate(self, opp, *, strategy=None, scanner_family=None):
        opp_id = opp.get("opportunity_id")
        self.calls.append(opp_id)
        await self._journal.record_discovery(
            opp, mode="SHADOW", scanner_family=scanner_family,
        )
        class _R:
            action = self._action
            def to_dict(inner_self):
                return {"opportunity_id": opp_id, "action": inner_self.action}
        r = _R()
        r.action = self._action
        return r


class _FakeLedger:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    async def emit_from_journal(self, *, batch=100):
        self.calls += 1
        if self.fail:
            raise RuntimeError("ledger boom")
        return {"processed": 0, "emitted_samples": 0,
                "touched_signals": 0, "neutrals": 0, "as_of": "now"}


def _rows(n):
    return [{"opportunity_id": f"opp-{i}", "confidence": 0.7,
             "strategy": "flash_loan_arbitrage"} for i in range(n)]


# =========================================================================
# Unit tests
# =========================================================================

class TestAutoExecutorTick:
    def test_tick_evaluates_each_row(self):
        db = _DB()
        journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal)
        exe = AutoExecutor(
            pipeline=pipe,
            discovery_repo=_FakeDiscoveryRepo(_rows(3)),
            journal=journal,
            interval_s=1.0, batch_size=10,
        )
        summary = _await(exe.tick_once())
        assert summary["evaluated"] == 3
        assert summary["skipped"] == 0
        assert set(pipe.calls) == {"opp-0", "opp-1", "opp-2"}
        assert summary["actions"] == {"shadow": 3}

    def test_min_confidence_filters(self):
        db = _DB(); journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal)
        rows = [
            {"opportunity_id": "hi", "confidence": 0.9},
            {"opportunity_id": "lo", "confidence": 0.2},
        ]
        exe = AutoExecutor(
            pipeline=pipe, discovery_repo=_FakeDiscoveryRepo(rows),
            journal=journal, min_confidence=0.5,
        )
        summary = _await(exe.tick_once())
        assert summary["evaluated"] == 1
        assert summary["skipped"] == 1
        assert pipe.calls == ["hi"]

    def test_terminal_and_consumed_rows_are_skipped(self):
        db = _DB(); journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal)
        # Pre-populate journal with an already-consumed terminal row.
        _await(journal.record_discovery({"opportunity_id": "done"}, mode="SHADOW"))
        _await(journal.record_event(
            "done", kind="shadow_recorded",
            status=ExecutionStatus.SHADOW_RECORDED.value,
        ))
        _await(journal.set_learning_label(
            "done", LearningLabel.NEUTRAL.value, consumed=True,
        ))
        exe = AutoExecutor(
            pipeline=pipe,
            discovery_repo=_FakeDiscoveryRepo([
                {"opportunity_id": "done", "confidence": 0.9},
                {"opportunity_id": "fresh", "confidence": 0.9},
            ]),
            journal=journal,
        )
        summary = _await(exe.tick_once())
        assert summary["evaluated"] == 1  # only "fresh"
        assert summary["skipped"] == 1
        assert pipe.calls == ["fresh"]

    def test_learning_ledger_fires_every_n_ticks(self):
        db = _DB(); journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal)
        ledger = _FakeLedger()
        exe = AutoExecutor(
            pipeline=pipe,
            discovery_repo=_FakeDiscoveryRepo(_rows(1)),
            journal=journal,
            learning_ledger=ledger,
            learning_every_n_ticks=2,
        )
        _await(exe.tick_once())  # tick 1 — no ledger
        assert ledger.calls == 0
        _await(exe.tick_once())  # tick 2 — ledger fires
        assert ledger.calls == 1
        _await(exe.tick_once())  # tick 3 — no ledger
        assert ledger.calls == 1
        _await(exe.tick_once())  # tick 4 — ledger fires
        assert ledger.calls == 2

    def test_ledger_error_does_not_crash_tick(self):
        db = _DB(); journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal)
        ledger = _FakeLedger(fail=True)
        exe = AutoExecutor(
            pipeline=pipe, discovery_repo=_FakeDiscoveryRepo(_rows(1)),
            journal=journal, learning_ledger=ledger,
            learning_every_n_ticks=1,
        )
        summary = _await(exe.tick_once())
        # Tick still returns a summary; error is captured but not raised.
        assert summary["evaluated"] == 1
        assert any("learning_ledger" in e for e in summary["errors"])

    def test_totals_accumulate(self):
        db = _DB(); journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal, action="reject")
        exe = AutoExecutor(
            pipeline=pipe, discovery_repo=_FakeDiscoveryRepo(_rows(2)),
            journal=journal,
        )
        _await(exe.tick_once())
        _await(exe.tick_once())
        status = exe.status()
        assert status["total_ticks"] == 2
        assert status["total_evaluated"] == 4
        assert status["total_actions"]["reject"] == 4

    def test_default_shadow_never_broadcasts(self):
        """The safety invariant: with the real pipeline in SHADOW/PAPER mode,
        the executor must never invoke the broadcaster — even when handed
        a fully-shaped flash-loan opportunity with a plan_id.
        """
        db = _DB(); journal = OpportunityJournal(db)

        class _NeverBroadcaster:
            def __init__(self):
                self.calls = []
            async def broadcast_plan(self, *a, **kw):
                self.calls.append(kw); raise AssertionError(
                    "SHADOW mode must never call the broadcaster")

        class _ShadowMode:
            async def get(self, s):
                return {"strategy": s, "mode": "SHADOW"}

        class _NoKill:
            async def get(self):
                return {"engaged": False}

        broadcaster = _NeverBroadcaster()
        pipeline = OpportunityPipeline(
            journal=journal,
            mode_repo=_ShadowMode(),
            kill_switch=_NoKill(),
            capital_allocator=None,
            certifier=None,
            broadcaster=broadcaster,
            plans_repo={},
        )
        opp = {
            "opportunity_id": "sensitive-1",
            "strategy": "flash_loan_arbitrage",
            "chain": "base",
            "borrow_token": "0xWETH",
            "borrow_amount_wei": 100_000_000_000_000_000,
            "borrow_amount_usd": 250.0,
            "flash_loan_provider": "balancer_v2",
            "swap_hops": [{"dex": "uni_v3"}],
            "net_profit_usd": 5.0,
            "plan_id": "plan-1",
        }
        exe = AutoExecutor(
            pipeline=pipeline,
            discovery_repo=_FakeDiscoveryRepo([opp]),
            journal=journal,
        )
        _await(exe.tick_once())
        assert broadcaster.calls == []


class TestAutoExecutorLifecycle:
    def test_start_then_stop(self):
        db = _DB(); journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal)
        exe = AutoExecutor(
            pipeline=pipe, discovery_repo=_FakeDiscoveryRepo([]),
            journal=journal, interval_s=0.05,
        )

        async def _cycle():
            await exe.start()
            assert exe.running is True
            # Let the loop run a couple of ticks then stop.
            await asyncio.sleep(0.15)
            await exe.stop()
            assert exe.running is False
            # total_ticks should be >= 1
            assert exe.status()["total_ticks"] >= 1

        asyncio.new_event_loop().run_until_complete(_cycle())

    def test_start_is_idempotent(self):
        db = _DB(); journal = OpportunityJournal(db)
        pipe = _RecordingPipeline(journal)
        exe = AutoExecutor(
            pipeline=pipe, discovery_repo=_FakeDiscoveryRepo([]),
            journal=journal, interval_s=1.0,
        )

        async def _cycle():
            await exe.start()
            first_task = exe._task
            await exe.start()  # second call is a no-op
            assert exe._task is first_task
            await exe.stop()

        asyncio.new_event_loop().run_until_complete(_cycle())


# =========================================================================
# HTTP contract tests
# =========================================================================

@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestAutoExecutorHTTP:
    def test_status_shape(self, client):
        r = client.get(f"{API}/arbicore/auto-executor/status")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("running", "interval_s", "batch_size", "min_confidence",
                  "learning_every_n_ticks", "last_run_at",
                  "total_ticks", "total_evaluated", "total_actions"):
            assert k in d

    def test_tick_returns_summary(self, client):
        r = client.post(f"{API}/arbicore/auto-executor/tick")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "summary" in d
        for k in ("ran_at", "batch_size", "evaluated", "skipped",
                  "actions", "errors"):
            assert k in d["summary"]

    def test_stop_then_start_round_trip(self, client):
        r_stop = client.post(f"{API}/arbicore/auto-executor/stop")
        assert r_stop.status_code == 200, r_stop.text
        assert r_stop.json()["stopped"] is True
        assert r_stop.json()["running"] is False

        r_start = client.post(f"{API}/arbicore/auto-executor/start")
        assert r_start.status_code == 200, r_start.text
        assert r_start.json()["started"] is True
        assert r_start.json()["running"] is True
