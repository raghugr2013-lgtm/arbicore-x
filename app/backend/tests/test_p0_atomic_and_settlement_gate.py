"""P0 — Atomic executor sim gating + mandatory settlement gate wiring."""
import asyncio
import types

import pytest

from arbicore.execution.atomic_executor_sim import AtomicExecutorSimulator
from arbicore.economics.opportunity_engine import OpportunityEngine


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _FakeQuoter:
    def _rpc_url(self):
        return None


# --------------------------------------------------- atomic sim gating
def test_atomic_sim_gated_without_executor():
    s = AtomicExecutorSimulator(rpc_url="http://x", executor_address=None,
                                executor_bytecode=None)
    out = _run(s.simulate_atomic(entry_calldata="0x1234"))
    assert out["available"] is False and out["passed"] is False
    assert "EXECUTOR" in out["reason"] or "executor" in out["reason"]


def test_atomic_sim_gated_without_bytecode():
    s = AtomicExecutorSimulator(rpc_url="http://x",
                                executor_address="0x00000000000000000000000000000000000000aa",
                                executor_bytecode=None)
    out = _run(s.simulate_atomic(entry_calldata="0x1234"))
    assert out["available"] is False
    assert "bytecode" in out["reason"].lower()


def test_atomic_sim_no_rpc():
    s = AtomicExecutorSimulator(rpc_url="", executor_address="0xaa", executor_bytecode="0x60")
    out = _run(s.simulate_atomic(entry_calldata="0x00"))
    assert out["available"] is False and "RPC" in out["reason"]


def test_atomic_readiness_flags():
    rd = AtomicExecutorSimulator(rpc_url="http://x").readiness()
    assert rd["rpc_configured"] is True
    assert rd["executor_address_set"] is False
    assert rd["executor_bytecode_available"] is False


# --------------------------------------- mandatory settlement gate wiring
class _FakeSim:
    def __init__(self, passed):
        self._passed = passed
        self.called = False

    async def simulate(self, **kwargs):
        self.called = True
        return {"passed": self._passed, "reason": "ok" if self._passed else "no repay"}


def _stub_route(dexes):
    """Minimal RouteCycle-like object. pool_address absent from engine specs
    means the venue spec resolves empty (dex None) → non-Aerodrome path."""
    pools = [types.SimpleNamespace(pool_address=f"missing:{i}", dex_protocol=d)
             for i, d in enumerate(dexes)]
    return types.SimpleNamespace(
        route_id="r1", pools=pools, borrow_token="WETH",
        token_path=["WETH", "USDC", "WETH"], hop_count=len(dexes))


def test_settlement_not_applicable_for_non_aerodrome_route():
    eng = OpportunityEngine(quoter_registry=_FakeQuoter(),
                            settlement_simulator=_FakeSim(True))
    out = _run(eng._run_settlement(_stub_route(["uniswap_v3", "uniswap_v3"]),
                                   2500.0, 1.0))
    assert out["passed"] is False and out.get("applicable") is False


def test_settlement_gate_runs_for_aerodrome_route():
    eng = OpportunityEngine(quoter_registry=_FakeQuoter(),
                            settlement_simulator=_FakeSim(True))
    # inject aerodrome specs so the route is settlement-eligible
    r = _stub_route(["aerodrome", "aerodrome"])
    for p in r.pools:
        eng._specs[p.pool_address] = {"dex": "aerodrome", "stable": False}
    out = _run(eng._run_settlement(r, 2500.0, 1.0))
    assert out["passed"] is True


def test_settlement_gate_rejects_when_sim_fails():
    fake = _FakeSim(False)
    eng = OpportunityEngine(quoter_registry=_FakeQuoter(), settlement_simulator=fake)
    r = _stub_route(["aerodrome", "aerodrome"])
    for p in r.pools:
        eng._specs[p.pool_address] = {"dex": "aerodrome", "stable": True}
    out = _run(eng._run_settlement(r, 2500.0, 1.0))
    assert out["passed"] is False and fake.called is True
