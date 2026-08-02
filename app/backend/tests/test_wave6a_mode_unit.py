"""Wave 6A · Execution mode ladder — unit tests."""
from __future__ import annotations

import pytest

from arbicore.execution.mode import (
    MODES, TRADING_STRATEGIES, ExecutionModeRepo,
    default_mode_map, is_broadcast_allowed, validate_transition,
)


class TestLadder:
    def test_modes_are_exact(self):
        assert MODES == ("OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE")

    def test_broadcast_allowed_only_for_live_modes(self):
        assert is_broadcast_allowed("OBSERVE") is False
        assert is_broadcast_allowed("PAPER") is False
        assert is_broadcast_allowed("SHADOW") is False
        assert is_broadcast_allowed("LIMITED_LIVE") is True
        assert is_broadcast_allowed("FULL_LIVE") is True

    def test_default_map_matches_approved_posture(self):
        d = default_mode_map()
        assert d["flash_loan_arbitrage"] == "SHADOW"
        for s in ("cex_arbitrage", "dex_capital_arbitrage",
                  "cross_chain_arbitrage", "portfolio_rebalance",
                  "treasury_movement", "position_management"):
            assert d[s] == "PAPER"

    def test_all_trading_strategies_have_defaults(self):
        d = default_mode_map()
        for s in TRADING_STRATEGIES:
            assert s in d


class TestTransitionValidator:
    def test_forward_one_step_allowed(self):
        for i in range(len(MODES) - 1):
            validate_transition(MODES[i], MODES[i + 1])  # must not raise

    def test_forward_two_step_rejected(self):
        with pytest.raises(ValueError, match="skips the ladder"):
            validate_transition("SHADOW", "FULL_LIVE")

    def test_direct_observe_to_limited_live_rejected(self):
        with pytest.raises(ValueError):
            validate_transition("OBSERVE", "LIMITED_LIVE")

    def test_backward_rollback_any_distance_allowed(self):
        validate_transition("FULL_LIVE", "OBSERVE")
        validate_transition("LIMITED_LIVE", "PAPER")
        validate_transition("SHADOW", "OBSERVE")

    def test_noop_transition_allowed(self):
        validate_transition("PAPER", "PAPER")

    def test_unknown_mode_rejected(self):
        with pytest.raises(ValueError):
            validate_transition("PAPER", "TURBO")
        with pytest.raises(ValueError):
            validate_transition("MYSTERY", "PAPER")


# ------- ExecutionModeRepo (async) -------

class _AsyncCursor:
    def __init__(self, docs): self._docs = list(docs); self._i = 0
    def sort(self, key, direction=1):
        if isinstance(key, str):
            self._docs.sort(key=lambda d: d.get(key), reverse=(direction == -1))
        elif isinstance(key, list):
            for k, dir_ in reversed(key):
                self._docs.sort(key=lambda x: x.get(k), reverse=(dir_ == -1))
        return self
    def limit(self, n): self._docs = self._docs[:n]; return self
    async def to_list(self, n): return list(self._docs[:n])

class _MemColl:
    def __init__(self): self._docs = []
    async def create_index(self, *a, **k): return None
    async def insert_one(self, doc): self._docs.append(dict(doc)); return type("R",(),{})()
    async def find_one(self, q, p=None):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()): return dict(d)
        return None
    def find(self, q=None, p=None):
        q = q or {}
        return _AsyncCursor([dict(d) for d in self._docs
                             if all(d.get(k) == v for k, v in q.items())])
    async def update_one(self, q, u, upsert=False):
        for d in self._docs:
            if all(d.get(k) == v for k, v in q.items()):
                for k, v in u.get("$set", {}).items(): d[k] = v
                return type("R",(),{"modified_count":1})()
        if upsert:
            d = {}
            for k, v in q.items(): d[k] = v
            for k, v in u.get("$set", {}).items(): d[k] = v
            for k, v in u.get("$setOnInsert", {}).items(): d.setdefault(k, v)
            self._docs.append(d)
            return type("R",(),{"upserted_id":1})()
        return type("R",(),{"modified_count":0})()

class _MemDB:
    def __init__(self): self._c = {}
    def __getitem__(self, n): return self._c.setdefault(n, _MemColl())


@pytest.mark.asyncio
async def test_ensure_defaults_is_idempotent():
    db = _MemDB()
    repo = ExecutionModeRepo(db)
    await repo.ensure_indexes()
    await repo.ensure_defaults()
    first = await repo.list_all()
    await repo.ensure_defaults()  # second call — must not duplicate
    second = await repo.list_all()
    assert len(first) == len(second) == len(TRADING_STRATEGIES)


@pytest.mark.asyncio
async def test_transition_records_audit():
    db = _MemDB()
    repo = ExecutionModeRepo(db)
    await repo.ensure_defaults()
    row = await repo.transition("cex_arbitrage", "SHADOW",
                                reason="canary review complete",
                                actor="alice")
    assert row["mode"] == "SHADOW"
    audit = await repo.audit_history("cex_arbitrage")
    # Bootstrap seed + transition = 2 audit rows.
    assert len(audit) == 2
    assert audit[0]["to_mode"] == "SHADOW"
    assert audit[0]["actor"] == "alice"


@pytest.mark.asyncio
async def test_transition_rejects_skips_and_unknown_strategies():
    db = _MemDB()
    repo = ExecutionModeRepo(db)
    await repo.ensure_defaults()
    with pytest.raises(ValueError):
        await repo.transition("flash_loan_arbitrage", "FULL_LIVE", reason="skip")
    with pytest.raises(ValueError):
        await repo.transition("mystery_strategy", "PAPER", reason="whatever")


@pytest.mark.asyncio
async def test_rollback_always_allowed():
    db = _MemDB()
    repo = ExecutionModeRepo(db)
    await repo.ensure_defaults()
    # SHADOW is the default for flash_loan_arbitrage — roll back straight to OBSERVE.
    row = await repo.transition("flash_loan_arbitrage", "OBSERVE",
                                reason="rollback drill")
    assert row["mode"] == "OBSERVE"
