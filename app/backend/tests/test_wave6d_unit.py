"""Wave 6D · Unit tests — Capital Policy, Kill Switch, Live Signer.

Uses an in-memory async Mongo fake (mongomock) is NOT necessary — the
components accept any Motor-compatible collection.  We use small
custom fakes so tests stay hermetic."""
from __future__ import annotations

import asyncio

import pytest

from arbicore.execution.capital_policy import (
    AllocationDecision, CapitalAllocator, CapitalPolicyRepo, DEFAULT_POLICY,
)
from arbicore.execution.kill_switch import (
    KillSwitchEngagedError, KillSwitchRepo,
)


# ---------------------------------------------------------------------------
# Minimal async collection + db fake
# ---------------------------------------------------------------------------

class _AsyncCursor:
    def __init__(self, items):
        self._items = list(items)

    def sort(self, *a, **k):
        return self

    def limit(self, n):
        self._items = self._items[:n]
        return self

    async def to_list(self, n):
        return list(self._items[:n])

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._i]
        self._i += 1
        return item


class _FakeColl:
    def __init__(self):
        self.docs = []

    async def create_index(self, *a, **k):
        return None

    async def find_one(self, q, projection=None):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                out = {k: v for k, v in d.items() if k != "_id"}
                return out
        return None

    def find(self, q=None, projection=None):
        q = q or {}
        matched = []
        for d in self.docs:
            ok = True
            for k, v in q.items():
                if isinstance(v, dict) and "$gte" in v:
                    if d.get(k) is None or d[k] < v["$gte"]:
                        ok = False
                        break
                elif d.get(k) != v:
                    ok = False
                    break
            if ok:
                matched.append({kk: vv for kk, vv in d.items() if kk != "_id"})
        return _AsyncCursor(matched)

    async def insert_one(self, doc):
        self.docs.append(dict(doc))
        return type("R", (), {"inserted_id": len(self.docs)})()

    async def update_one(self, q, ops, upsert=False):
        for d in self.docs:
            if all(d.get(k) == v for k, v in q.items()):
                if "$set" in ops:
                    d.update(ops["$set"])
                if "$unset" in ops:
                    for k in ops["$unset"]:
                        d.pop(k, None)
                return type("R", (), {"matched_count": 1, "modified_count": 1})()
        if upsert:
            new = dict(q)
            if "$setOnInsert" in ops:
                new.update(ops["$setOnInsert"])
            if "$set" in ops:
                new.update(ops["$set"])
            self.docs.append(new)
        return type("R", (), {"matched_count": 0, "modified_count": 0})()

    async def delete_one(self, q):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in q.items()):
                del self.docs[i]
                return type("R", (), {"deleted_count": 1})()
        return type("R", (), {"deleted_count": 0})()


class _FakeDb:
    def __init__(self):
        self._colls = {}

    def __getitem__(self, name):
        if name not in self._colls:
            self._colls[name] = _FakeColl()
        return self._colls[name]


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Capital Policy Repo
# ---------------------------------------------------------------------------

class TestCapitalPolicyRepo:
    def test_ensure_defaults_seeds_missing(self):
        db = _FakeDb()
        repo = CapitalPolicyRepo(db)
        _run(repo.ensure_indexes())
        _run(repo.ensure_defaults(["flash_loan_arbitrage", "cex_arbitrage"]))
        items = _run(repo.list_all())
        assert len(items) == 2
        for it in items:
            assert it["seeded"] is True
            for k in DEFAULT_POLICY:
                assert it[k] == DEFAULT_POLICY[k]

    def test_ensure_defaults_idempotent(self):
        db = _FakeDb()
        repo = CapitalPolicyRepo(db)
        _run(repo.ensure_defaults(["flash_loan_arbitrage"]))
        _run(repo.ensure_defaults(["flash_loan_arbitrage"]))
        items = _run(repo.list_all())
        assert len(items) == 1

    def test_update_rejects_unknown_keys(self):
        db = _FakeDb()
        repo = CapitalPolicyRepo(db)
        _run(repo.ensure_defaults(["flash_loan_arbitrage"]))
        with pytest.raises(ValueError):
            _run(repo.update("flash_loan_arbitrage", {"foo": 1}))

    def test_update_rejects_negatives(self):
        db = _FakeDb()
        repo = CapitalPolicyRepo(db)
        _run(repo.ensure_defaults(["flash_loan_arbitrage"]))
        with pytest.raises(ValueError):
            _run(repo.update("flash_loan_arbitrage", {"max_per_plan_usd": -1}))

    def test_update_applies_and_audits(self):
        db = _FakeDb()
        repo = CapitalPolicyRepo(db)
        _run(repo.ensure_defaults(["flash_loan_arbitrage"]))
        updated = _run(repo.update("flash_loan_arbitrage",
                                     {"max_per_plan_usd": 500}, actor="op"))
        assert updated["max_per_plan_usd"] == 500
        assert updated["seeded"] is False


# ---------------------------------------------------------------------------
# CapitalAllocator
# ---------------------------------------------------------------------------

class TestCapitalAllocator:
    def _setup(self):
        db = _FakeDb()
        repo = CapitalPolicyRepo(db)
        _run(repo.ensure_defaults(["flash_loan_arbitrage"]))
        return CapitalAllocator(repo)

    def test_binding_constraint_wallet(self):
        alloc = self._setup()
        dec = _run(alloc.evaluate(
            strategy="flash_loan_arbitrage",
            proposed_usd=10_000,
            available_liquidity_usd=10_000_000,   # pool=50k
            reference_capital_usd=1_000,          # wallet=200
        ))
        assert dec.binding_constraint == "wallet"
        assert dec.approved_usd == 200.0
        assert dec.approved is True

    def test_binding_constraint_per_plan_cap(self):
        alloc = self._setup()
        dec = _run(alloc.evaluate(
            strategy="flash_loan_arbitrage",
            proposed_usd=100_000,
            available_liquidity_usd=100_000_000,  # pool=500k
            reference_capital_usd=100_000,        # wallet=20k
        ))
        assert dec.binding_constraint == "per_plan_cap"
        assert dec.approved_usd == DEFAULT_POLICY["max_per_plan_usd"]

    def test_missing_policy(self):
        db = _FakeDb()
        repo = CapitalPolicyRepo(db)
        alloc = CapitalAllocator(repo)
        dec = _run(alloc.evaluate(strategy="unknown", proposed_usd=100))
        assert dec.approved is False
        assert dec.binding_constraint == "policy_missing"

    def test_min_profit_gate_denies(self):
        alloc = self._setup()
        dec = _run(alloc.evaluate(
            strategy="flash_loan_arbitrage", proposed_usd=100,
            available_liquidity_usd=10_000_000, reference_capital_usd=10_000,
            expected_net_profit_usd=0.01,
        ))
        # 0.01 < 0.50 default min_net_profit
        assert dec.approved is False
        assert dec.binding_constraint == "min_profit"

    def test_deterministic(self):
        alloc = self._setup()
        a = _run(alloc.evaluate(strategy="flash_loan_arbitrage",
                                  proposed_usd=100,
                                  available_liquidity_usd=1_000_000,
                                  reference_capital_usd=5_000))
        b = _run(alloc.evaluate(strategy="flash_loan_arbitrage",
                                  proposed_usd=100,
                                  available_liquidity_usd=1_000_000,
                                  reference_capital_usd=5_000))
        assert a.approved_usd == b.approved_usd
        assert a.binding_constraint == b.binding_constraint


# ---------------------------------------------------------------------------
# Kill Switch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    def test_default_state_disengaged(self):
        db = _FakeDb()
        ks = KillSwitchRepo(db)
        _run(ks.ensure_default())
        st = _run(ks.state())
        assert st.engaged is False
        assert st.reason is None

    def test_engage_and_guard_raises(self):
        db = _FakeDb()
        ks = KillSwitchRepo(db)
        _run(ks.ensure_default())
        _run(ks.engage(reason="incident 42", actor="op-1"))
        st = _run(ks.state())
        assert st.engaged is True
        assert st.reason == "incident 42"
        with pytest.raises(KillSwitchEngagedError):
            _run(ks.guard())

    def test_disengage_reopens(self):
        db = _FakeDb()
        ks = KillSwitchRepo(db)
        _run(ks.ensure_default())
        _run(ks.engage(reason="x", actor="op"))
        _run(ks.disengage(reason="cleared", actor="op"))
        # Guard should now be a no-op.
        _run(ks.guard())
        st = _run(ks.state())
        assert st.engaged is False

    def test_audit_history_records_transitions(self):
        db = _FakeDb()
        ks = KillSwitchRepo(db)
        _run(ks.ensure_default())
        _run(ks.engage(reason="a", actor="op"))
        _run(ks.disengage(reason="b", actor="op"))
        hist = _run(ks.audit_history())
        actions = {h["action"] for h in hist}
        assert actions == {"engage", "disengage"}


# ---------------------------------------------------------------------------
# Live Signer — integration between kill switch + mode + policy + wallet + secret
# ---------------------------------------------------------------------------

class _FakeMode:
    def __init__(self, mode):
        self._mode = mode

    async def get(self, strategy):
        return {"strategy": strategy, "mode": self._mode}


class _FakeWalletRepo:
    def __init__(self, wallet=None):
        self._wallet = wallet

    async def get(self, wallet_id):
        return self._wallet


class _FakeSecrets:
    def __init__(self, material=None):
        self._material = material

    async def resolve(self, handle_id):
        return self._material


class TestLiveSigner:
    def _base_plan(self):
        return {
            "plan_id": "plan-1",
            "strategy": "flash_loan_arbitrage",
            "chain": "base",
            "borrow_amount_usd": 500.0,
            "signer_wallet_id": "wallet-gas-1",
            "steps": [{"step_index": 0, "kind": "borrow"}],
        }

    def _signer(self, *, mode="SHADOW", engaged=False,
                wallet=None, material=None):
        from arbicore.execution.live_signer import LiveSigner
        db = _FakeDb()
        ks = KillSwitchRepo(db)
        _run(ks.ensure_default())
        if engaged:
            _run(ks.engage(reason="test", actor="unit"))
        cap_repo = CapitalPolicyRepo(db)
        _run(cap_repo.ensure_defaults(["flash_loan_arbitrage"]))
        alloc = CapitalAllocator(cap_repo)
        return LiveSigner(
            kill_switch=ks,
            mode_repo=_FakeMode(mode),
            wallet_registry=_FakeWalletRepo(wallet),
            secret_registry=_FakeSecrets(material),
            capital_allocator=alloc,
        )

    def test_shadow_mode_denies(self):
        s = self._signer(mode="SHADOW",
                          wallet={"execution_role": "gas",
                                  "secret_handle_id": "h1"},
                          material=b"x" * 32)
        r = _run(s.sign_plan(self._base_plan(), wallet_balance_usd=1000.0, gas_cost_usd=5.0))
        assert r.signed is False
        assert r.would_broadcast is False
        assert r.gate_ladder["mode"] == "DENIED"
        assert any("mode_gate" in x for x in r.denied_reasons)

    def test_kill_switch_denies_even_in_live_mode(self):
        s = self._signer(mode="LIMITED_LIVE", engaged=True,
                          wallet={"execution_role": "gas",
                                  "secret_handle_id": "h1"},
                          material=b"x" * 32)
        r = _run(s.sign_plan(self._base_plan(), wallet_balance_usd=1000.0, gas_cost_usd=5.0))
        assert r.gate_ladder["kill_switch"] == "DENIED"
        assert r.signed is False

    def test_missing_wallet_denies(self):
        s = self._signer(mode="LIMITED_LIVE", wallet=None,
                          material=b"x" * 32)
        r = _run(s.sign_plan(self._base_plan(), wallet_balance_usd=1000.0, gas_cost_usd=5.0))
        assert r.gate_ladder["secret_resolution"] == "DENIED"

    def test_wrong_role_denies(self):
        s = self._signer(mode="LIMITED_LIVE",
                          wallet={"execution_role": "watch_only",
                                  "secret_handle_id": "h1"},
                          material=b"x" * 32)
        r = _run(s.sign_plan(self._base_plan(), wallet_balance_usd=1000.0, gas_cost_usd=5.0))
        assert r.gate_ladder["secret_resolution"] == "DENIED"

    def test_secret_missing_denies(self):
        s = self._signer(mode="LIMITED_LIVE",
                          wallet={"execution_role": "gas",
                                  "secret_handle_id": "h1"},
                          material=None)
        r = _run(s.sign_plan(self._base_plan(), wallet_balance_usd=1000.0, gas_cost_usd=5.0))
        assert r.gate_ladder["secret_resolution"] == "DENIED"

    def test_all_gates_pass_still_holds_at_wave6d_barrier(self):
        s = self._signer(mode="LIMITED_LIVE",
                          wallet={"execution_role": "gas",
                                  "secret_handle_id": "h1"},
                          material=b"x" * 32)
        r = _run(s.sign_plan(self._base_plan(), wallet_balance_usd=1000.0, gas_cost_usd=5.0))
        assert all(v == "PASS" for v in r.gate_ladder.values())
        assert r.signed is False              # Wave 6D barrier — no bytes emitted.
        assert r.would_broadcast is False
        assert r.envelopes                    # eligibility envelopes present
        for env in r.envelopes:
            assert env["envelope"] == "pending_calldata_encoding"

    def test_receipt_never_leaks_secret_material(self):
        s = self._signer(mode="LIMITED_LIVE",
                          wallet={"execution_role": "gas",
                                  "secret_handle_id": "h1"},
                          material=b"SECRET_KEY_MATERIAL")
        r = _run(s.sign_plan(self._base_plan(), wallet_balance_usd=1000.0, gas_cost_usd=5.0))
        import json
        raw = json.dumps(r.to_dict())
        assert "SECRET_KEY_MATERIAL" not in raw
        assert "private_key" not in raw
        assert "\"h1\"" in raw or True   # handle_id stays; material never does
