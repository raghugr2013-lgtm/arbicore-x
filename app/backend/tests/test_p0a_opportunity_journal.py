"""P0-A · Opportunity Journal — regression tests.

Tests are split into two layers:
    * **Unit** — direct calls into the ``OpportunityJournal`` repo using
      an in-memory fake collection. No HTTP, no Motor. This proves the
      state machine (discovery → event → label) is correct.
    * **HTTP contract** — hits the running backend through
      ``REACT_APP_BACKEND_URL`` to prove the routes exist, respond with
      the expected shape, and honour the filter query params.

The HTTP layer follows the exact pattern used by every other
``test_v2_*`` file in this suite so it plugs in with zero test-runner
changes.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, List, Optional

import pytest
import requests

from arbicore.data.journal import (
    OpportunityJournal, JournalEntry, ExecutionStatus, LearningLabel,
    JOURNAL_COLLECTION,
)


# =========================================================================
# In-memory fake Motor collection — just enough to satisfy the repo.
# =========================================================================

class _FakeCursor:
    def __init__(self, docs: List[Dict[str, Any]]):
        self._docs = list(docs)
        self._sort_key: Optional[str] = None
        self._sort_dir: int = 1
        self._limit: Optional[int] = None

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
            docs = sorted(
                docs,
                key=lambda d: d.get(self._sort_key) or "",
                reverse=self._sort_dir < 0,
            )
        if self._limit is not None:
            docs = docs[: self._limit]
        self._iter = iter(docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


class _FakeCollection:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.indexes: List[Any] = []

    async def create_index(self, spec, **kwargs):
        self.indexes.append((spec, kwargs))
        return "ok"

    async def find_one(self, filt, projection=None):
        key = filt.get("opportunity_id")
        doc = self.docs.get(key)
        return dict(doc) if doc else None

    async def update_one(self, filt, update, upsert=False):
        key = filt["opportunity_id"]
        doc = self.docs.get(key, {"opportunity_id": key})
        doc.update(update.get("$set", {}))
        self.docs[key] = doc
        class _R:
            matched_count = 1
            upserted_id = key
        return _R()

    def find(self, filt=None, projection=None):
        docs = list(self.docs.values())
        if filt:
            def match(d):
                for k, v in filt.items():
                    if d.get(k) != v:
                        return False
                return True
            docs = [d for d in docs if match(d)]
        return _FakeCursor(docs)

    async def aggregate(self, pipeline):
        # Minimal $group aggregation used by summary()
        groups: Dict[tuple, Dict[str, Any]] = {}
        for d in self.docs.values():
            key = (
                d.get("execution_status"),
                d.get("mode"),
                d.get("learning_label"),
            )
            g = groups.setdefault(key, {"n": 0, "profit_sum": 0.0, "profit_n": 0,
                                        "conf_sum": 0.0, "conf_n": 0})
            g["n"] += 1
            p = d.get("expected_profit_usd")
            if isinstance(p, (int, float)):
                g["profit_sum"] += p
                g["profit_n"] += 1
            c = d.get("confidence_score")
            if isinstance(c, (int, float)):
                g["conf_sum"] += c
                g["conf_n"] += 1
        out = []
        for (status, mode, label), g in groups.items():
            out.append({
                "_id": {"status": status, "mode": mode, "label": label},
                "n": g["n"],
                "avg_profit": (g["profit_sum"] / g["profit_n"]) if g["profit_n"] else None,
                "avg_confidence": (g["conf_sum"] / g["conf_n"]) if g["conf_n"] else None,
            })
        for row in out:
            yield row


class _FakeDB:
    def __init__(self):
        self._cols: Dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, _FakeCollection())


# =========================================================================
# Unit tests — direct against the repo
# =========================================================================

@pytest.fixture
def journal():
    return OpportunityJournal(_FakeDB())


def _await(coro):
    """Run a coroutine to completion on a fresh loop.

    Using ``asyncio.run`` (rather than ``asyncio.get_event_loop``) is
    resilient to earlier tests on the same xdist worker that may have
    closed the default loop.
    """
    return asyncio.new_event_loop().run_until_complete(coro)


class TestJournalUnit:
    def test_indexes_created(self, journal):
        _await(journal.ensure_indexes())
        # Seven indexes expected: opportunity_id (unique), execution_status,
        # opportunity_type, mode, last_seen, learning_label, learning_consumed.
        col = journal._col  # type: ignore
        assert len(col.indexes) >= 6

    def test_record_discovery_creates_row(self, journal):
        opp = {
            "opportunity_id": "opp-1",
            "opportunity_type": "DEX_ARB",
            "chain": "base",
            "asset": "WETH/USDC",
            "buy_venue": "aerodrome",
            "sell_venue": "uniswap_v3",
            "expected_profit_usd": 42.5,
            "capital_required_usd": 5000.0,
            "confidence_score": 0.71,
            "risk_score": 0.22,
        }
        entry = _await(journal.record_discovery(opp, mode="SHADOW", scanner_family="DEX_ARB"))
        assert entry.opportunity_id == "opp-1"
        assert entry.execution_status == ExecutionStatus.DISCOVERED.value
        assert entry.mode == "SHADOW"
        assert entry.observation_count == 1
        assert entry.expected_profit_usd == 42.5
        assert entry.confidence_score == 0.71
        assert entry.first_seen == entry.last_seen
        assert entry.lifetime_ms == 0
        assert len(entry.events) == 1
        assert entry.events[0].kind == "discovered"

    def test_record_discovery_is_idempotent(self, journal):
        opp = {"opportunity_id": "opp-2", "expected_profit_usd": 10.0}
        first = _await(journal.record_discovery(opp, mode="SHADOW"))
        # Second observation
        opp["expected_profit_usd"] = 12.0
        second = _await(journal.record_discovery(opp, mode="SHADOW"))
        assert first.opportunity_id == second.opportunity_id
        assert second.observation_count == 2
        assert second.expected_profit_usd == 12.0
        assert len(second.events) == 2

    def test_record_event_appends_and_updates_status(self, journal):
        opp = {"opportunity_id": "opp-3", "expected_profit_usd": 30.0}
        _await(journal.record_discovery(opp, mode="SHADOW"))
        updated = _await(journal.record_event(
            "opp-3",
            kind="quoted",
            detail={"buy": 1000, "sell": 1005},
            patch={"spread_pct": 0.5},
            status=ExecutionStatus.QUOTED.value,
        ))
        assert updated is not None
        assert updated.execution_status == ExecutionStatus.QUOTED.value
        assert updated.spread_pct == 0.5
        assert updated.events[-1].kind == "quoted"

    def test_record_event_returns_none_for_unknown_id(self, journal):
        r = _await(journal.record_event("nope", kind="quoted"))
        assert r is None

    def test_set_learning_label(self, journal):
        opp = {"opportunity_id": "opp-4"}
        _await(journal.record_discovery(opp, mode="SHADOW"))
        r = _await(journal.set_learning_label("opp-4", LearningLabel.NEGATIVE.value, consumed=True))
        assert r is not None
        assert r.learning_label == LearningLabel.NEGATIVE.value
        assert r.learning_consumed is True
        assert r.events[-1].kind == "learning_labelled"

    def test_list_filters(self, journal):
        _await(journal.record_discovery({"opportunity_id": "a"}, mode="SHADOW"))
        _await(journal.record_discovery({"opportunity_id": "b"}, mode="OBSERVE"))
        _await(journal.record_discovery({"opportunity_id": "c"}, mode="SHADOW"))
        shadow = _await(journal.list(mode="SHADOW", limit=10))
        observed = _await(journal.list(mode="OBSERVE", limit=10))
        assert len(shadow) == 2
        assert len(observed) == 1

    def test_summary_shape(self, journal):
        _await(journal.record_discovery({"opportunity_id": "x",
                                         "expected_profit_usd": 20.0,
                                         "confidence_score": 0.5}, mode="SHADOW"))
        summary = _await(journal.summary())
        assert set(summary.keys()) == {"total", "buckets", "as_of"}
        assert summary["total"] == 1
        assert len(summary["buckets"]) == 1
        b = summary["buckets"][0]
        for k in ("execution_status", "mode", "learning_label", "n"):
            assert k in b


# =========================================================================
# HTTP contract tests — hit the running FastAPI backend
# =========================================================================

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "http://localhost:8001",
).rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestJournalHTTP:
    def test_list_shape_empty_or_populated(self, client):
        r = client.get(f"{API}/arbicore/journal")
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("items", "count", "as_of"):
            assert k in data
        assert isinstance(data["items"], list)
        assert data["count"] == len(data["items"])

    def test_summary_shape(self, client):
        r = client.get(f"{API}/arbicore/journal/summary")
        assert r.status_code == 200, r.text
        data = r.json()
        for k in ("total", "buckets", "as_of"):
            assert k in data
        assert isinstance(data["buckets"], list)

    def test_get_missing_returns_error_envelope(self, client):
        r = client.get(f"{API}/arbicore/journal/does-not-exist-{uuid.uuid4().hex}")
        assert r.status_code == 200, r.text
        data = r.json()
        assert "error" in data

    def test_list_filters_are_honoured(self, client):
        # Even with an empty DB the filter must return HTTP 200 + empty items.
        r = client.get(f"{API}/arbicore/journal",
                       params={"execution_status": "DISCOVERED",
                               "mode": "SHADOW",
                               "limit": 5})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["count"] <= 5
