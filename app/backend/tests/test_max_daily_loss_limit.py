"""Additive tests for the operator STOP-LOSS (max_daily_loss_usd) enforced by
the execution-side CapitalAllocator — the binding sizing authority consumed by
live_signer / broadcast / pipeline / certification.

Proves it is a HARD SAFETY STOP (not a notional cap): normal sizing is
unaffected while cumulative realized loss is below the cap; once the cap is
reached the plan is blocked (approved_usd=0, binding='daily_loss_limit'); and an
unreadable loss ledger fails CLOSED. No signing, no broadcast, no funds move.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from arbicore.execution.capital_policy import (
    CapitalAllocator, CapitalPolicyRepo, DEFAULT_POLICY,
)

STRAT = "flash_loan_arbitrage"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ── minimal async Mongo fakes ───────────────────────────────────────────────
class _Cursor:
    def __init__(self, items): self._items = list(items)
    def __aiter__(self): self._i = 0; return self
    async def __anext__(self):
        if self._i >= len(self._items):
            raise StopAsyncIteration
        it = self._items[self._i]; self._i += 1; return it


class _Coll:
    def __init__(self): self.docs = []
    async def create_index(self, *a, **k): return None
    async def find_one(self, q, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                return {k: v for k, v in d.items() if k != "_id"}
        return None
    async def insert_one(self, doc): self.docs.append(dict(doc))
    async def update_one(self, q, update, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                d.update(update.get("$set", {})); return
        if upsert:
            nd = {}; nd.update(update.get("$setOnInsert", {}))
            nd.update(update.get("$set", {})); self.docs.append(nd)
    def find(self, q, projection=None): return _Cursor(list(self.docs))


class _DB:
    def __init__(self): self._c = {}
    def __getitem__(self, name): return self._c.setdefault(name, _Coll())


class _PlansRepo:
    """Exposes ._coll.find like the real plans repo. ``raise_on_find`` models
    an unreadable ledger (fail-closed path)."""
    def __init__(self, docs, raise_on_find=False):
        self._coll = _Coll(); self._coll.docs = list(docs)
        if raise_on_find:
            def _boom(*a, **k): raise RuntimeError("db down")
            self._coll.find = _boom  # type: ignore


def _seeded_allocator(plans_repo=None):
    repo = CapitalPolicyRepo(_DB())
    _run(repo.ensure_defaults([STRAT]))
    return CapitalAllocator(repo, plans_repo=plans_repo)


# ── config presence + validation ───────────────────────────────────────────
def test_default_policy_has_stop_loss():
    assert DEFAULT_POLICY["max_daily_loss_usd"] == 100.0


def test_seed_includes_stop_loss():
    repo = CapitalPolicyRepo(_DB())
    _run(repo.ensure_defaults([STRAT]))
    doc = _run(repo.get(STRAT))
    assert doc["max_daily_loss_usd"] == 100.0


def test_update_accepts_valid_and_rejects_negative():
    repo = CapitalPolicyRepo(_DB())
    _run(repo.ensure_defaults([STRAT]))
    updated = _run(repo.update(STRAT, {"max_daily_loss_usd": 50}, actor="op"))
    assert updated["max_daily_loss_usd"] == 50
    with pytest.raises(ValueError):
        _run(repo.update(STRAT, {"max_daily_loss_usd": -1}))


# ── enforcement semantics ───────────────────────────────────────────────────
def test_no_plans_repo_not_tripped():
    dec = _run(_seeded_allocator().evaluate(strategy=STRAT, proposed_usd=1_000))
    assert dec.binding_constraint != "daily_loss_limit"   # normal sizing intact
    assert dec.approved is True
    assert dec.daily_loss_used_usd == 0.0
    assert dec.max_daily_loss_usd == 100.0


def test_loss_below_cap_allows():
    pr = _PlansRepo([{"strategy": STRAT, "created_at": "9999",
                      "realized_loss_usd": 30.0}])
    dec = _run(_seeded_allocator(pr).evaluate(strategy=STRAT, proposed_usd=1_000))
    assert dec.approved is True
    assert dec.binding_constraint != "daily_loss_limit"
    assert dec.daily_loss_used_usd == 30.0
    assert dec.daily_loss_remaining_usd == 70.0


def test_loss_at_or_above_cap_halts():
    pr = _PlansRepo([{"strategy": STRAT, "created_at": "9999",
                      "realized_loss_usd": 120.0}])
    dec = _run(_seeded_allocator(pr).evaluate(strategy=STRAT, proposed_usd=1_000))
    assert dec.approved is False
    assert dec.approved_usd == 0.0
    assert dec.binding_constraint == "daily_loss_limit"
    assert any("stop-loss" in r for r in dec.reasons)


def test_unreadable_ledger_fails_closed():
    pr = _PlansRepo([], raise_on_find=True)
    dec = _run(_seeded_allocator(pr).evaluate(strategy=STRAT, proposed_usd=1_000))
    assert dec.approved is False
    assert dec.binding_constraint == "daily_loss_limit"
    assert any("fail-closed" in r for r in dec.reasons)


def test_decision_json_serializable_with_new_fields():
    dec = _run(_seeded_allocator().evaluate(strategy=STRAT, proposed_usd=100))
    d = json.loads(json.dumps(dec.to_dict()))
    for k in ("max_daily_loss_usd", "daily_loss_used_usd",
              "daily_loss_remaining_usd"):
        assert k in d
