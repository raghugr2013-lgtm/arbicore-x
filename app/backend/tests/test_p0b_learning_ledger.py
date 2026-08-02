"""P0-B · Learning Ledger — regression tests.

Unit layer exercises the pure labelling function and the emit_from_journal
batch loop against in-memory fake collections. HTTP layer verifies the
two new routes are wired.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

import pytest
import requests

from arbicore.data.journal import (
    ExecutionStatus, JournalEntry, LearningLabel, OpportunityJournal,
)
from arbicore.learning.ledger import LearningLedger, label_entry


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


def _await(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# =========================================================================
# In-memory fakes — minimal Mongo surface.
# =========================================================================

class _Cursor:
    def __init__(self, docs):
        self._docs = list(docs)
        self._sort_key = None
        self._sort_dir = 1
        self._limit = None

    def sort(self, key, direction=1):
        self._sort_key = key
        self._sort_dir = direction
        return self

    def limit(self, n):
        self._limit = int(n)
        return self

    def __aiter__(self):
        docs = self._docs
        if self._sort_key:
            docs = sorted(docs, key=lambda d: d.get(self._sort_key) or "",
                          reverse=self._sort_dir < 0)
        if self._limit is not None:
            docs = docs[: self._limit]
        self._iter = iter(docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration

    async def to_list(self, n):
        # Consume the async iterator to a list
        out = []
        async for d in self:
            out.append(d)
        return out


class _Coll:
    def __init__(self):
        self.docs: List[Dict[str, Any]] = []
        self.indexes = []

    async def create_index(self, spec, **kwargs):
        self.indexes.append((spec, kwargs))
        return "ok"

    async def find_one(self, filt, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in filt.items()):
                return dict(d)
        return None

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": len(self.docs)})

    async def update_one(self, filt, update, upsert=False):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in filt.items()):
                new = {**d, **update.get("$set", {})}
                self.docs[i] = new
                return type("R", (), {"matched_count": 1, "upserted_id": None})
        if upsert:
            new = {**filt, **update.get("$set", {})}
            self.docs.append(new)
            return type("R", (), {"matched_count": 0, "upserted_id": len(self.docs)})
        return type("R", (), {"matched_count": 0, "upserted_id": None})

    def find(self, filt=None, projection=None):
        docs = list(self.docs)
        if filt:
            def match(d):
                for k, v in filt.items():
                    if d.get(k) != v:
                        return False
                return True
            docs = [d for d in docs if match(d)]
        return _Cursor(docs)

    async def aggregate(self, pipeline):
        groups: Dict[tuple, Dict[str, Any]] = {}
        for d in self.docs:
            key = (
                d.get("execution_status"),
                d.get("mode"),
                d.get("learning_label"),
            )
            g = groups.setdefault(key, {"n": 0})
            g["n"] += 1
        for (status, mode, label), g in groups.items():
            yield {
                "_id": {"status": status, "mode": mode, "label": label},
                "n": g["n"],
                "avg_profit": None,
                "avg_confidence": None,
            }


class _DB:
    def __init__(self):
        self.cols: Dict[str, _Coll] = {}

    def __getitem__(self, name):
        return self.cols.setdefault(name, _Coll())


# =========================================================================
# Unit tests — pure labelling
# =========================================================================

def _entry(**kw) -> JournalEntry:
    kw.setdefault("opportunity_id", "opp-x")
    return JournalEntry(**kw)


class TestLabelEntry:
    def test_completed_positive(self):
        e = _entry(
            execution_status=ExecutionStatus.COMPLETED.value,
            actual_result={"pnl_usd": 12.5},
        )
        label, survived = label_entry(e)
        assert label == LearningLabel.POSITIVE.value
        assert survived is True

    def test_completed_negative(self):
        e = _entry(
            execution_status=ExecutionStatus.COMPLETED.value,
            actual_result={"pnl_usd": -3.0},
        )
        label, survived = label_entry(e)
        assert label == LearningLabel.NEGATIVE.value
        assert survived is False

    def test_completed_missing_pnl_is_neutral(self):
        e = _entry(
            execution_status=ExecutionStatus.COMPLETED.value,
            actual_result={},
        )
        label, survived = label_entry(e)
        assert label == LearningLabel.NEUTRAL.value
        assert survived is None

    def test_broadcast_failed_is_negative(self):
        e = _entry(execution_status=ExecutionStatus.BROADCAST_FAILED.value)
        label, survived = label_entry(e)
        assert label == LearningLabel.NEGATIVE.value
        assert survived is False

    def test_shadow_explicit_would_survive_true(self):
        e = _entry(
            execution_status=ExecutionStatus.SHADOW_RECORDED.value,
            expected_result={"would_survive": True},
        )
        label, survived = label_entry(e)
        assert label == LearningLabel.POSITIVE.value
        assert survived is True

    def test_shadow_falls_back_to_cert_plus_policy(self):
        e = _entry(
            execution_status=ExecutionStatus.SHADOW_RECORDED.value,
            certification_result={"status": "ok"},
            policy_decision={"decision": "allow"},
        )
        label, survived = label_entry(e)
        assert label == LearningLabel.POSITIVE.value

        e2 = _entry(
            execution_status=ExecutionStatus.SHADOW_RECORDED.value,
            certification_result={"status": "fail"},
            policy_decision={"decision": "allow"},
        )
        label2, survived2 = label_entry(e2)
        assert label2 == LearningLabel.NEGATIVE.value
        assert survived2 is False

    def test_policy_denied_and_rejected_are_neutral(self):
        for s in (ExecutionStatus.POLICY_DENIED.value,
                  ExecutionStatus.REJECTED.value):
            e = _entry(execution_status=s)
            label, survived = label_entry(e)
            assert label == LearningLabel.NEUTRAL.value
            assert survived is None

    def test_non_terminal_is_pending(self):
        e = _entry(execution_status=ExecutionStatus.QUOTED.value)
        label, survived = label_entry(e)
        assert label == LearningLabel.PENDING.value
        assert survived is None


# =========================================================================
# Unit tests — emit_from_journal
# =========================================================================

@pytest.fixture
def stack():
    db = _DB()
    journal = OpportunityJournal(db)
    ledger = LearningLedger(db, journal)
    return db, journal, ledger


class TestLearningLedgerEmit:
    def test_ensure_indexes(self, stack):
        db, journal, ledger = stack
        _await(ledger.ensure_indexes())
        assert len(db["calibration_log"].indexes) >= 3
        assert len(db["arbicore_signal_metrics"].indexes) >= 1

    def test_emit_completed_row(self, stack):
        db, journal, ledger = stack
        opp = {
            "opportunity_id": "opp-1",
            "opportunity_type": "DEX_ARB",
            "chain": "base",
            "buy_venue": "aerodrome",
            "sell_venue": "uniswap_v3",
            "confidence_score": 0.62,
        }
        _await(journal.record_discovery(opp, mode="LIMITED_LIVE"))
        _await(journal.record_event(
            "opp-1", kind="broadcast_completed",
            patch={"actual_result": {"pnl_usd": 7.5}},
            status=ExecutionStatus.COMPLETED.value,
        ))
        result = _await(ledger.emit_from_journal(batch=10))
        assert result["processed"] == 1
        assert result["emitted_samples"] == 1
        assert result["touched_signals"] == 1
        assert result["neutrals"] == 0
        # Sample landed in calibration_log
        cl = db["calibration_log"].docs
        assert len(cl) == 1
        assert cl[0]["survived"] is True
        assert cl[0]["opportunity_id"] == "opp-1"
        assert cl[0]["status"] == "resolved"
        # Signal metric landed
        sm = db["arbicore_signal_metrics"].docs
        assert len(sm) == 1
        assert sm[0]["sample_count"] == 1
        assert sm[0]["win_rate"] == 1.0
        # Journal marked consumed with correct label
        entry = _await(journal.get("opp-1"))
        assert entry.learning_consumed is True
        assert entry.learning_label == LearningLabel.POSITIVE.value

    def test_emit_rejected_row_is_neutral_but_marked_consumed(self, stack):
        db, journal, ledger = stack
        _await(journal.record_discovery({"opportunity_id": "opp-2"}, mode="SHADOW"))
        _await(journal.record_event(
            "opp-2", kind="policy_denied",
            patch={"policy_decision": {"decision": "deny", "engine": "mode"}},
            status=ExecutionStatus.POLICY_DENIED.value,
        ))
        result = _await(ledger.emit_from_journal(batch=10))
        assert result["processed"] == 1
        assert result["emitted_samples"] == 0
        assert result["neutrals"] == 1
        assert db["calibration_log"].docs == []
        entry = _await(journal.get("opp-2"))
        assert entry.learning_consumed is True
        assert entry.learning_label == LearningLabel.NEUTRAL.value

    def test_emit_is_idempotent(self, stack):
        db, journal, ledger = stack
        _await(journal.record_discovery({"opportunity_id": "opp-3",
                                         "confidence_score": 0.5}, mode="LIMITED_LIVE"))
        _await(journal.record_event(
            "opp-3", kind="broadcast_completed",
            patch={"actual_result": {"pnl_usd": -1.0}},
            status=ExecutionStatus.COMPLETED.value,
        ))
        r1 = _await(ledger.emit_from_journal(batch=10))
        r2 = _await(ledger.emit_from_journal(batch=10))
        assert r1["processed"] == 1
        assert r2["processed"] == 0
        assert len(db["calibration_log"].docs) == 1  # not doubled

    def test_signal_metric_running_mean(self, stack):
        db, journal, ledger = stack
        # Two wins + one loss for the same signal → win_rate == 2/3
        for i, pnl in enumerate([5.0, 8.0, -2.0]):
            oid = f"opp-{i}"
            _await(journal.record_discovery({
                "opportunity_id": oid,
                "opportunity_type": "DEX_ARB",
                "chain": "base",
                "buy_venue": "aerodrome",
                "sell_venue": "uniswap_v3",
                "confidence_score": 0.5,
            }, mode="LIMITED_LIVE"))
            _await(journal.record_event(
                oid, kind="broadcast_completed",
                patch={"actual_result": {"pnl_usd": pnl}},
                status=ExecutionStatus.COMPLETED.value,
            ))
        _await(ledger.emit_from_journal(batch=10))
        sm = db["arbicore_signal_metrics"].docs
        assert len(sm) == 1
        assert sm[0]["sample_count"] == 3
        assert abs(sm[0]["win_rate"] - (2.0 / 3.0)) < 1e-6


# =========================================================================
# HTTP contract tests
# =========================================================================

@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestLedgerHTTP:
    def test_status_shape(self, client):
        r = client.get(f"{API}/arbicore/learning/ledger/status")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("pending", "consumed", "last_run_at", "last_batch", "as_of"):
            assert k in d
        assert isinstance(d["pending"], int)
        assert isinstance(d["consumed"], int)

    def test_emit_default(self, client):
        r = client.post(f"{API}/arbicore/learning/ledger/emit", json={})
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("processed", "emitted_samples", "touched_signals", "neutrals", "as_of"):
            assert k in d
        assert isinstance(d["processed"], int)

    def test_emit_honours_batch_param(self, client):
        r = client.post(f"{API}/arbicore/learning/ledger/emit", json={"batch": 3})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["processed"] <= 3
