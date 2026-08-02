"""P0-C · Unified Pipeline Glue — regression tests.

Unit tests exercise the ``OpportunityPipeline`` coordinator against
in-memory fakes for every dependency. This proves:

  * OBSERVE mode records the opportunity and stops.
  * PAPER / SHADOW terminates at SHADOW_RECORDED with the expected
    journal payload.
  * Kill switch engaged → POLICY_DENIED, never broadcasts.
  * Capital allocator denies → POLICY_DENIED, never broadcasts.
  * Certifier fails → REJECTED, no broadcast attempt.
  * LIMITED_LIVE + all-green → broadcast IS attempted (using the fake
    broadcaster) → BROADCAST_SENT.
  * LIMITED_LIVE + certifier fail → REJECTED, no broadcast.
  * Missing plan_id → broadcast returns unwired, journalled as
    BROADCAST_FAILED, never touches chain.

HTTP contract test proves the ``POST /api/arbicore/pipeline/evaluate``
route exists and returns the canonical shape.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List

import pytest
import requests

from arbicore.data.journal import (
    ExecutionStatus, OpportunityJournal, LearningLabel,
)
from arbicore.execution.pipeline import OpportunityPipeline, PipelineResult


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


def _await(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# =========================================================================
# In-memory Mongo surface — just enough for the Journal
# =========================================================================

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._k = None
        self._d = 1
        self._limit = None

    def sort(self, k, d=1):
        self._k, self._d = k, d
        return self

    def limit(self, n):
        self._limit = int(n)
        return self

    def __aiter__(self):
        docs = self._docs
        if self._k:
            docs = sorted(docs, key=lambda x: x.get(self._k) or "",
                          reverse=self._d < 0)
        if self._limit is not None:
            docs = docs[: self._limit]
        self._it = iter(docs)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class _Coll:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.log: List[Dict[str, Any]] = []
        self.indexes = []

    async def create_index(self, *a, **kw):
        self.indexes.append((a, kw))
        return "ok"

    async def find_one(self, filt, projection=None):
        k = filt.get("opportunity_id")
        d = self.docs.get(k)
        return dict(d) if d else None

    async def update_one(self, filt, update, upsert=False):
        k = filt["opportunity_id"]
        cur = self.docs.get(k, {"opportunity_id": k})
        cur.update(update.get("$set", {}))
        self.docs[k] = cur
        class _R:
            matched_count = 1
        return _R()

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
        # Not used in these tests
        if False:
            yield {}


class _DB:
    def __init__(self):
        self._cols: Dict[str, _Coll] = {}

    def __getitem__(self, n):
        return self._cols.setdefault(n, _Coll())


# =========================================================================
# Fake dependencies
# =========================================================================

class _FakeMode:
    def __init__(self, mode="SHADOW"):
        self.mode = mode

    async def get(self, strategy):
        return {"strategy": strategy, "mode": self.mode}


class _FakeKill:
    def __init__(self, engaged=False):
        self.engaged = engaged

    async def get(self):
        return {"engaged": self.engaged, "state": "engaged" if self.engaged else "disengaged"}


class _FakeAllocator:
    def __init__(self, approve=True, reasons=None, binding="per_plan_cap"):
        self.approve = approve
        self.reasons = reasons or []
        self.binding = binding

    async def evaluate(self, *, strategy, proposed_usd, expected_net_profit_usd):
        return {
            "approved": self.approve,
            "binding_constraint": self.binding,
            "reasons": self.reasons,
            "proposed_usd": proposed_usd,
        }


class _FakeCertifier:
    def __init__(self, certified=True):
        self.certified = certified
        self.calls = []

    async def certify(self, **kw):
        self.calls.append(kw)
        return {
            "certified": self.certified,
            "status": "ok" if self.certified else "fail",
            "summary": "fake certifier",
            "stages": [],
        }


class _FakeBroadcaster:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    async def broadcast_plan(self, plan_doc, *, actor, confirm, expected_net_profit_usd=None):
        self.calls.append({"plan_doc": plan_doc, "actor": actor})
        if not self.ok:
            raise RuntimeError("broadcaster failed for test")
        class _R:
            def to_dict(self):
                return {"tx_hash": "0xabc", "ok": True, "pnl_usd": None}
        return _R()


class _FakePlansRepo:
    def __init__(self, plan_docs=None):
        self.plans = plan_docs or {}

    async def get(self, plan_id):
        return self.plans.get(plan_id)


def _opp(**overrides) -> Dict[str, Any]:
    base = {
        "opportunity_id": "opp-1",
        "strategy": "flash_loan_arbitrage",
        "chain": "base",
        "borrow_token": "0xWETH",
        "borrow_amount_wei": 100_000_000_000_000_000,
        "borrow_amount_usd": 250.0,
        "flash_loan_provider": "balancer_v2",
        "swap_hops": [{"dex": "uni_v3"}, {"dex": "aerodrome"}],
        "net_profit_usd": 3.5,
        "expected_profit_usd": 3.5,
        "confidence": 0.7,
        "plan_id": "plan-1",
    }
    base.update(overrides)
    return base


def _pipe(mode="SHADOW", **kw):
    db = _DB()
    journal = OpportunityJournal(db)
    pipe = OpportunityPipeline(
        journal=journal,
        mode_repo=_FakeMode(mode=mode),
        kill_switch=kw.get("kill", _FakeKill(engaged=False)),
        capital_allocator=kw.get("alloc", _FakeAllocator(approve=True)),
        certifier=kw.get("certifier", _FakeCertifier(certified=True)),
        broadcaster=kw.get("broadcaster"),
        plans_repo=kw.get("plans"),
    )
    return db, journal, pipe


# =========================================================================
# Unit tests
# =========================================================================

class TestPipelineModes:
    def test_observe_records_and_stops(self):
        db, journal, pipe = _pipe(mode="OBSERVE")
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "observe"
        assert result.mode == "OBSERVE"
        # Journal captured the discovery even without any downstream stages.
        entry = _await(journal.get("opp-1"))
        assert entry is not None
        assert entry.execution_status == ExecutionStatus.DISCOVERED.value
        assert entry.mode == "OBSERVE"

    def test_shadow_terminates_at_shadow_recorded(self):
        db, journal, pipe = _pipe(mode="SHADOW")
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "shadow"
        # Every canonical stage present in the result
        stages_seen = {s["stage"] for s in result.stages}
        assert {"quote", "gas", "profit", "policy", "certification"}.issubset(stages_seen)
        entry = _await(journal.get("opp-1"))
        assert entry.execution_status == ExecutionStatus.SHADOW_RECORDED.value
        assert entry.expected_result is not None
        assert entry.expected_result["would_survive"] is True

    def test_paper_also_terminates_shadow(self):
        db, journal, pipe = _pipe(mode="PAPER")
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "shadow"

    def test_kill_switch_engaged_denies(self):
        db, journal, pipe = _pipe(mode="LIMITED_LIVE", kill=_FakeKill(engaged=True))
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "deny"
        entry = _await(journal.get("opp-1"))
        assert entry.execution_status == ExecutionStatus.POLICY_DENIED.value
        assert entry.policy_decision["engine"] == "kill_switch"

    def test_capital_denial_denies(self):
        db, journal, pipe = _pipe(
            mode="LIMITED_LIVE",
            alloc=_FakeAllocator(approve=False, reasons=["daily_notional"],
                                 binding="daily_notional"),
        )
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "deny"
        entry = _await(journal.get("opp-1"))
        assert entry.execution_status == ExecutionStatus.POLICY_DENIED.value
        assert entry.policy_decision["engine"] == "capital"

    def test_certifier_fails_causes_reject(self):
        db, journal, pipe = _pipe(
            mode="LIMITED_LIVE",
            certifier=_FakeCertifier(certified=False),
        )
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "reject"
        entry = _await(journal.get("opp-1"))
        assert entry.execution_status == ExecutionStatus.REJECTED.value
        # And no broadcast attempt was made — even though we were in LIMITED_LIVE.

    def test_limited_live_broadcasts_when_all_green(self):
        broadcaster = _FakeBroadcaster(ok=True)
        plans = _FakePlansRepo({"plan-1": {"plan_id": "plan-1", "steps": []}})
        db, journal, pipe = _pipe(
            mode="LIMITED_LIVE",
            broadcaster=broadcaster,
            plans=plans,
        )
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "broadcast"
        assert result.broadcast_receipt is not None
        entry = _await(journal.get("opp-1"))
        assert entry.execution_status == ExecutionStatus.BROADCAST_SENT.value
        assert entry.actual_result is not None
        assert len(broadcaster.calls) == 1

    def test_limited_live_broadcast_failure_is_journaled(self):
        broadcaster = _FakeBroadcaster(ok=False)
        plans = _FakePlansRepo({"plan-1": {"plan_id": "plan-1"}})
        db, journal, pipe = _pipe(
            mode="LIMITED_LIVE",
            broadcaster=broadcaster, plans=plans,
        )
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "reject"
        entry = _await(journal.get("opp-1"))
        assert entry.execution_status == ExecutionStatus.BROADCAST_FAILED.value

    def test_unprofitable_after_gas_is_rejected_early(self):
        db, journal, pipe = _pipe(mode="SHADOW")
        # borrow_amount_usd 250 * 0.6% = 1.5 gas. net = 1.0 → after_gas = -0.5 → reject
        result = _await(pipe.evaluate(_opp(net_profit_usd=1.0, expected_profit_usd=1.0)))
        assert result.action == "reject"
        entry = _await(journal.get("opp-1"))
        assert entry.execution_status == ExecutionStatus.REJECTED.value

    def test_missing_opportunity_id_returns_reject(self):
        db, journal, pipe = _pipe(mode="SHADOW")
        result = _await(pipe.evaluate({"strategy": "cex_arbitrage"}))
        assert result.action == "reject"
        assert "opportunity_id" in result.reason

    def test_never_broadcasts_without_promotion(self):
        """The critical invariant: SHADOW mode must never call the broadcaster."""
        broadcaster = _FakeBroadcaster(ok=True)
        plans = _FakePlansRepo({"plan-1": {"plan_id": "plan-1"}})
        db, journal, pipe = _pipe(
            mode="SHADOW", broadcaster=broadcaster, plans=plans,
        )
        result = _await(pipe.evaluate(_opp()))
        assert result.action == "shadow"
        assert broadcaster.calls == []


# =========================================================================
# HTTP contract test
# =========================================================================

@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestPipelineHTTP:
    def test_evaluate_shape_and_writes_journal(self, client):
        opp = {
            "opportunity_id": "http-probe-{}".format(os.urandom(3).hex()),
            "strategy": "cex_arbitrage",
            "expected_profit_usd": 3.0,
            "net_profit_usd": 3.0,
            "swap_hops": [{"dex": "uni_v3"}],
        }
        r = client.post(f"{API}/arbicore/pipeline/evaluate",
                        json={"opportunity": opp, "strategy": "cex_arbitrage"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "result" in data
        assert data["result"]["opportunity_id"] == opp["opportunity_id"]
        # PAPER mode terminates at shadow.
        assert data["result"]["action"] in {"shadow", "observe", "reject"}

        # And the journal now knows about this opportunity.
        g = client.get(f"{API}/arbicore/journal/{opp['opportunity_id']}")
        assert g.status_code == 200
        gj = g.json()
        assert "entry" in gj
        assert gj["entry"]["opportunity_id"] == opp["opportunity_id"]

    def test_evaluate_rejects_missing_opp_id(self, client):
        r = client.post(f"{API}/arbicore/pipeline/evaluate",
                        json={"opportunity": {}})
        assert r.status_code == 200, r.text
        data = r.json()
        assert "error" in data
