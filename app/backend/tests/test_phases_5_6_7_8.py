"""Phases 5-8 backbone regression tests."""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Phase 5 — ProviderRegistry
# ---------------------------------------------------------------------------

class _FakeRPC:
    kind = None
    def __init__(self, provider_id, chain="base", fail=False,
                  slow=False):
        from arbicore.providers.base import ProviderKind
        self.provider_id = provider_id
        self.kind = ProviderKind.RPC
        self.chain = chain
        self._fail = fail
        self._slow = slow

    async def eth_get_block_number(self):
        if self._slow:
            await asyncio.sleep(0.02)
        if self._fail:
            raise RuntimeError("boom")
        return 42

    async def eth_call(self, *a, **k): return "0x"
    async def eth_get_gas_price(self): return 1
    async def health_probe(self): return {"ok": True}


async def test_registry_prefers_healthy_and_fails_over():
    from arbicore.providers import ProviderRegistry
    from arbicore.providers.base import ProviderKind
    r = ProviderRegistry()
    r.register(_FakeRPC("bad", fail=True), priority=10)
    r.register(_FakeRPC("good"), priority=20)

    # first call routes to 'bad' (priority=10 → higher precedence
    # before health data exists) → fails → registry fails over to 'good'
    result = await r.call(
        ProviderKind.RPC, lambda p: p.eth_get_block_number(),
        chain="base")
    assert result == 42
    snap = r.snapshot()
    ids = {row["provider_id"]: row
           for row in snap["by_kind"]["rpc"]}
    assert ids["bad"]["failures"] == 1
    assert ids["good"]["successes"] == 1


async def test_registry_breaker_trips_after_consecutive_failures():
    from arbicore.providers import ProviderRegistry, CircuitBreaker
    from arbicore.providers.base import ProviderKind, ProviderError
    r = ProviderRegistry(breaker=CircuitBreaker(
        consecutive_failure_threshold=3,
        open_duration_seconds=60))
    r.register(_FakeRPC("only", fail=True))
    for _ in range(3):
        try:
            await r.call(ProviderKind.RPC,
                          lambda p: p.eth_get_block_number(),
                          chain="base")
        except ProviderError:
            pass
    snap = r.snapshot()
    only = snap["by_kind"]["rpc"][0]
    assert only["status"] == "TRIPPED"


# ---------------------------------------------------------------------------
# Phase 8 — Kill Switch + Capital Policy
# ---------------------------------------------------------------------------

async def test_kill_switch_default_engaged_boot_safe(monkeypatch):
    for k in list(os.environ):
        if k.startswith("ARBICORE_SAFETY_"):
            monkeypatch.delenv(k, raising=False)
    from arbicore.safety import load_policy_from_env, KillSwitch
    cfg = load_policy_from_env()
    k = KillSwitch(cfg)
    assert k.is_engaged() is True
    assert k.reason() == "boot_default"


async def test_kill_switch_engage_disengage(monkeypatch):
    monkeypatch.setenv("ARBICORE_SAFETY_KILL_DEFAULT", "0")
    from arbicore.safety import load_policy_from_env, KillSwitch
    k = KillSwitch(load_policy_from_env())
    assert k.is_engaged() is False
    k.engage(by="op", reason="test")
    assert k.is_engaged() is True
    k.disengage(by="admin", reason="clear")
    assert k.is_engaged() is False


async def test_capital_policy_clips(monkeypatch):
    monkeypatch.setenv("ARBICORE_SAFETY_MAX_PER_TRADE_USD", "500")
    monkeypatch.setenv("ARBICORE_SAFETY_PER_TYPE_CAPS_USD",
                        "dex_arbitrage:250,flash_loan_arbitrage:1000")
    from arbicore.safety import load_policy_from_env, CapitalAllocationPolicy
    p = CapitalAllocationPolicy(load_policy_from_env())
    assert p.clip_capital(requested_usd=100.0) == 100.0
    assert p.clip_capital(requested_usd=10_000.0) == 500.0
    assert p.clip_capital(requested_usd=10_000.0,
                          opportunity_type="dex_arbitrage") == 250.0


async def test_approval_gate_denies_when_kill_engaged(monkeypatch):
    monkeypatch.setenv("ARBICORE_SAFETY_KILL_DEFAULT", "1")
    monkeypatch.setenv("ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED", "1")
    from arbicore.safety import (
        load_policy_from_env, KillSwitch, ApprovalGate)
    cfg = load_policy_from_env()
    k = KillSwitch(cfg)
    g = ApprovalGate(cfg, k)
    v = g.evaluate({"capital_required_usd": 100})
    assert v.approved is False
    assert "kill_switch_engaged" in v.reason


async def test_approval_gate_denies_when_live_execution_disabled(monkeypatch):
    monkeypatch.setenv("ARBICORE_SAFETY_KILL_DEFAULT", "0")
    monkeypatch.setenv("ARBICORE_SAFETY_LIVE_EXECUTION_ENABLED", "0")
    from arbicore.safety import (
        load_policy_from_env, KillSwitch, ApprovalGate)
    cfg = load_policy_from_env()
    v = ApprovalGate(cfg, KillSwitch(cfg)).evaluate({})
    assert v.approved is False
    assert "live_execution_disabled" in v.reason


# ---------------------------------------------------------------------------
# Phase 6 — Paper Engine
# ---------------------------------------------------------------------------

@pytest.fixture()
async def paper_stack():
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mid import MidWriter
    from arbicore.paper import PaperEngine
    from arbicore.safety import (
        KillSwitch, CapitalAllocationPolicy, PolicyConfig)

    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = f"paper_test_{uuid.uuid4().hex[:8]}"
    db = client[db_name]
    writer = MidWriter(db)
    cfg = PolicyConfig(kill_engaged_by_default=False,
                       max_per_trade_usd=1000.0,
                       live_execution_enabled=False)
    kill = KillSwitch(cfg)
    cap  = CapitalAllocationPolicy(cfg)
    engine = PaperEngine(writer, kill_switch=kill, capital_policy=cap)
    try:
        yield engine, kill, cap, db
    finally:
        await client.drop_database(db_name)
        client.close()


async def test_paper_engine_produces_analysis(paper_stack):
    engine, _, _, db = paper_stack
    a = await engine.analyse({
        "opp_id": "p1", "opportunity_type": "dex_arbitrage",
        "chain": "base",
        "expected_profit_usd": 50, "expected_gas_usd": 8,
        "capital_required_usd": 500, "flash_loan_fee_bps": 9,
        "slippage_bps": 10, "confidence": 0.8, "risk_score": 0.2,
    })
    assert a.policy_blocked is False
    assert a.net_profit_usd < a.expected_profit_usd    # gas + fl + slip deducted
    assert 0.0 <= a.execution_probability <= 1.0
    assert a.expected_value_usd == pytest.approx(
        a.net_profit_usd * a.execution_probability, rel=1e-6)
    # MID persistence
    ev = await db.mid_opportunities.find_one(
        {"opp_id": "p1", "event_type": "paper.engine.analysed"})
    assert ev is not None
    dec = await db.mid_decisions.find_one(
        {"opp_id": "p1", "gate": "paper_engine"})
    assert dec is not None


async def test_paper_engine_blocks_when_kill_engaged(paper_stack):
    engine, kill, _, db = paper_stack
    kill.engage(by="test", reason="unit-test")
    a = await engine.analyse({
        "opp_id": "p2", "opportunity_type": "dex_arbitrage",
        "chain": "base", "capital_required_usd": 100})
    assert a.policy_blocked is True
    assert "kill_switch_engaged" in a.reason
    assert engine.stats.policy_blocked == 1


async def test_paper_engine_clips_capital(paper_stack):
    engine, _, _, _ = paper_stack
    a = await engine.analyse({
        "opp_id": "p3", "opportunity_type": "dex_arbitrage",
        "chain": "base",
        "capital_required_usd": 999_999.0,
        "expected_profit_usd": 20, "expected_gas_usd": 5,
        "flash_loan_fee_bps": 9, "confidence": 0.5, "risk_score": 0.5,
    })
    assert a.capital_required_usd == 1000.0        # policy max


# ---------------------------------------------------------------------------
# Phase 7 — Wallet + Secret provider stubs
# ---------------------------------------------------------------------------

async def test_wallet_noop_refuses_to_sign():
    from arbicore.wallets import NoOpWalletProvider
    from arbicore.providers.base import ProviderError
    w = NoOpWalletProvider()
    assert await w.list_addresses("base") == []
    with pytest.raises(ProviderError):
        await w.sign_transaction("base", "0x0", {})


async def test_env_secret_provider(monkeypatch):
    from arbicore.wallets import EnvSecretProvider
    monkeypatch.setenv("ARBICORE_ALPHA", "hello")
    monkeypatch.setenv("SOME_OTHER_VAR", "leak")
    s = EnvSecretProvider()
    assert await s.get("ARBICORE_ALPHA") == "hello"
    assert await s.get("SOME_OTHER_VAR") is None
    keys = await s.list_keys("ARBICORE_")
    assert "ARBICORE_ALPHA" in keys
