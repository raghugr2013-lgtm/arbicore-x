"""Phase 0 Security Fixes S2–S6 focused tests.

Covers:
  * S2 kill-switch policy gate  (OpportunityPipeline._policy_check)
  * S3 auto-confirm default-off (OpportunityPipeline._broadcast passes confirm=False)
  * S4 technical-validation endpoint auth + execute-path safety gates
  * S5 broadcaster constructs with new balance_reader kwarg (no regression)
  * S6 slippage guard in LimitedLiveBroadcaster.broadcast_plan
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any, Dict, List, Optional

import pytest
import requests

# ensure the backend package root is importable
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


BASE_URL = "http://localhost:8001"


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) \
        if False else asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Fakes shared by S2 / S3 / S6 tests
# ---------------------------------------------------------------------------
class _FakeKSState:
    def __init__(self, engaged: bool):
        self.engaged = engaged


class _FakeKSRepo:
    """Mimics KillSwitchRepo — only exposes state() and guard()."""

    def __init__(self, engaged: bool = False):
        self._engaged = engaged

    async def state(self):
        return _FakeKSState(self._engaged)

    async def guard(self):
        if self._engaged:
            raise RuntimeError("kill switch engaged")


class _FakeModeRepo:
    def __init__(self, mode: str = "SHADOW"):
        self._mode = mode

    async def get(self, strategy: str):
        return {"mode": self._mode}


class _FakeWallets:
    def __init__(self, w=None):
        self._w = w

    async def get(self, wid):
        return self._w


class _FakeSecrets:
    def __init__(self, m=None):
        self._m = m

    async def resolve(self, h):
        return self._m


class _FakeAlloc:
    """Broadcaster capital allocator fake (evaluate returns object)."""

    def __init__(self, approved: bool = True):
        self._approved = approved

    async def evaluate(self, **kw):
        class D:
            approved = self._approved
            approved_usd = 100.0
            binding_constraint = "per_plan_cap" if self._approved else "min_profit"
            reasons = ["ok"]
        d = D()
        d.approved = self._approved
        return d


class _FakePipelineAlloc:
    """Pipeline capital allocator fake (evaluate returns dict)."""

    async def evaluate(self, **kw):
        return {"approved": True, "binding_constraint": "per_plan_cap",
                "reasons": []}


class _CaptureBroadcaster:
    """Captures kwargs passed to broadcast_plan without side effects."""

    def __init__(self):
        self.calls: List[Dict[str, Any]] = []

    async def broadcast_plan(self, plan_doc, **kwargs):
        self.calls.append({"plan_doc": plan_doc, "kwargs": kwargs})

        class R:
            def to_dict(self):
                return {"broadcast_sent": False, "confirm_seen": kwargs.get("confirm")}
        return R()


class _FakePlansRepo:
    def __init__(self, doc):
        self._doc = doc

    async def get(self, plan_id):
        return self._doc


class _FakeJournal:
    """Minimal OpportunityJournal stub — records nothing, methods no-op."""

    async def record(self, *a, **kw):
        return None

    async def append(self, *a, **kw):
        return None

    async def create(self, *a, **kw):
        return None

    async def update(self, *a, **kw):
        return None

    def __getattr__(self, name):
        async def _noop(*a, **kw):
            return None
        return _noop


# ===========================================================================
# S2 · Kill switch policy gate
# ===========================================================================
class TestS2KillSwitchPolicyGate:
    def _pipeline(self, engaged: bool):
        from arbicore.execution.pipeline import OpportunityPipeline
        return OpportunityPipeline(
            journal=_FakeJournal(),
            kill_switch=_FakeKSRepo(engaged=engaged),
            capital_allocator=_FakePipelineAlloc(),
        )

    def test_engaged_kill_switch_denies(self):
        p = self._pipeline(engaged=True)
        outcome = _run(p._policy_check("flash_loan_arbitrage", "LIMITED_LIVE",
                                        {"gross_profit_usd": 10.0,
                                         "net_profit_usd": 5.0}))
        assert outcome.ok is False
        assert outcome.stage == "policy"
        assert "kill" in (outcome.detail or "").lower()
        assert outcome.payload.get("decision") == "deny"
        assert outcome.payload.get("engine") == "kill_switch"

    def test_disengaged_kill_switch_passes(self):
        p = self._pipeline(engaged=False)
        outcome = _run(p._policy_check("flash_loan_arbitrage", "LIMITED_LIVE",
                                        {"gross_profit_usd": 10.0,
                                         "net_profit_usd": 5.0}))
        assert outcome.ok is True
        assert outcome.payload.get("decision") == "allow"


# ===========================================================================
# S3 · auto_confirm default-off
# ===========================================================================
class TestS3AutoConfirmDefaultOff:
    def test_default_auto_confirm_is_false(self):
        from arbicore.execution.pipeline import OpportunityPipeline
        p = OpportunityPipeline(journal=_FakeJournal())
        assert p._auto_confirm is False

    def test_broadcast_passes_confirm_false_by_default(self):
        from arbicore.execution.pipeline import (
            OpportunityPipeline, PipelineResult,
        )
        plan_doc = {"plan_id": "plan-x", "strategy": "flash_loan_arbitrage"}
        cap = _CaptureBroadcaster()
        p = OpportunityPipeline(
            journal=_FakeJournal(),
            broadcaster=cap,
            plans_repo=_FakePlansRepo(plan_doc),
        )
        opp = {"plan_id": "plan-x", "net_profit_usd": 1.0}
        result = PipelineResult(
            opportunity_id="opp-1", strategy="flash_loan_arbitrage",
            mode="LIMITED_LIVE", action="broadcast", reason="test",
        )
        outcome = _run(p._broadcast(opp, "flash_loan_arbitrage", result))
        assert outcome.ok is True
        assert len(cap.calls) == 1
        assert cap.calls[0]["kwargs"].get("confirm") is False

    def test_broadcast_passes_confirm_true_when_enabled(self):
        from arbicore.execution.pipeline import (
            OpportunityPipeline, PipelineResult,
        )
        plan_doc = {"plan_id": "plan-x", "strategy": "flash_loan_arbitrage"}
        cap = _CaptureBroadcaster()
        p = OpportunityPipeline(
            journal=_FakeJournal(),
            broadcaster=cap,
            plans_repo=_FakePlansRepo(plan_doc),
            auto_confirm=True,
        )
        opp = {"plan_id": "plan-x", "net_profit_usd": 1.0}
        result = PipelineResult(
            opportunity_id="opp-1", strategy="flash_loan_arbitrage",
            mode="LIMITED_LIVE", action="broadcast", reason="test",
        )
        _run(p._broadcast(opp, "flash_loan_arbitrage", result))
        assert cap.calls[0]["kwargs"].get("confirm") is True


# ===========================================================================
# S4 · technical-validation endpoint auth + execute gates
# ===========================================================================
class TestS4TechnicalValidationEndpoint:
    URL = f"{BASE_URL}/api/arbicore/wizard/technical-validation"

    def _login(self) -> requests.Session:
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/auth/login", json={
            "username": "operator", "password": "ShadowOperator!2026",
        }, timeout=10)
        assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
        return s

    def test_no_auth_returns_401(self):
        r = requests.post(self.URL, json={"execute": False}, timeout=10)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_auth_execute_false_graceful(self):
        s = self._login()
        r = s.post(self.URL, json={"execute": False}, timeout=30)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:400]}"
        data = r.json()
        # Either a real result or a graceful {"ok": false, "error": ...}
        assert isinstance(data, dict)
        assert ("result" in data) or (data.get("ok") is False and "error" in data)

    def test_auth_execute_true_refused_gracefully(self):
        s = self._login()
        r = s.post(self.URL, json={"execute": True}, timeout=30)
        assert r.status_code == 200, f"status={r.status_code} body={r.text[:400]}"
        data = r.json()
        # Must NOT crash. Must be refused with a helpful error about
        # missing executor / signer / chain allowlist.
        assert data.get("ok") is False, f"expected refusal, got {data}"
        err = (data.get("error") or "").lower()
        assert any(k in err for k in ("executor", "signer", "chain",
                                        "kill", "allowlist")), \
            f"unexpected error message: {err!r}"


# ===========================================================================
# S5 · broadcaster constructs with balance_reader (no regression)
# ===========================================================================
class TestS5BalanceReaderConstruct:
    def test_constructs_with_balance_reader(self):
        from arbicore.execution.broadcast import LimitedLiveBroadcaster

        class _BR:
            async def read(self, chain, address):
                class B:
                    ok = True
                    balance_usd = 500.0
                return B()

        b = LimitedLiveBroadcaster(
            kill_switch=_FakeKSRepo(),
            mode_repo=_FakeModeRepo("SHADOW"),
            wallet_registry=_FakeWallets(),
            secret_registry=_FakeSecrets(),
            capital_allocator=_FakeAlloc(),
            balance_reader=_BR(),
        )
        # Attribute must be stored
        assert b._balance_reader is not None

    def test_minimal_broadcast_returns_receipt_no_regression(self):
        from arbicore.execution.broadcast import LimitedLiveBroadcaster
        b = LimitedLiveBroadcaster(
            kill_switch=_FakeKSRepo(),
            mode_repo=_FakeModeRepo("SHADOW"),
            wallet_registry=_FakeWallets(),
            secret_registry=_FakeSecrets(),
            capital_allocator=_FakeAlloc(),
        )
        plan = {"plan_id": "plan-x", "strategy": "flash_loan_arbitrage",
                "chain": "base"}
        r = _run(b.broadcast_plan(plan, confirm=False))
        # No exception, we get a receipt with gate_ladder populated.
        assert hasattr(r, "gate_ladder")
        assert isinstance(r.gate_ladder, dict)
        assert r.broadcast_sent is False


# ===========================================================================
# S6 · slippage guard
# ===========================================================================
TOKEN_WETH_BASE = "0x4200000000000000000000000000000000000006"
DEV_PRIV = "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d"
DEV_ADDR = "0x70997970c51812dc3a010c7d01b50e0d17dc79c8"
RECIPIENT = "0x0000000000000000000000000000000000000abc"


def _base_plan(hops):
    return {
        "plan_id": "plan-slip",
        "strategy": "flash_loan_arbitrage",
        "chain": "base",
        "flash_loan_provider": "balancer_v2",
        "borrow_token": TOKEN_WETH_BASE,
        "borrow_amount_wei": 10 ** 17,
        "borrow_amount_usd": 250.0,
        "recipient": RECIPIENT,
        "signer_wallet_id": "wallet-gas-1",
        "hops": hops,
        "steps": [{"kind": "borrow", "token": TOKEN_WETH_BASE,
                    "amount_wei": 10 ** 17, "recipient": RECIPIENT}],
    }


class TestS6SlippageGuard:
    def _bcast(self, mode="LIMITED_LIVE"):
        from arbicore.execution.broadcast import LimitedLiveBroadcaster
        return LimitedLiveBroadcaster(
            kill_switch=_FakeKSRepo(),
            mode_repo=_FakeModeRepo(mode),
            wallet_registry=_FakeWallets({
                "execution_role": "gas",
                "secret_handle_id": "h1",
                "address": DEV_ADDR,
            }),
            secret_registry=_FakeSecrets(DEV_PRIV),
            capital_allocator=_FakeAlloc(approved=True),
        )

    def test_zero_min_out_denied(self):
        b = self._bcast()
        r = _run(b.broadcast_plan(_base_plan([{"amount_out_min_wei": 0}]),
                                    confirm=True))
        assert r.gate_ladder.get("slippage_guard") == "DENIED"
        assert any("amountoutminimum" in d.lower() or "slippage_guard" in d
                     for d in r.denied_reasons)
        assert r.broadcast_sent is False

    def test_missing_min_out_denied(self):
        b = self._bcast()
        r = _run(b.broadcast_plan(_base_plan([{}]), confirm=True))
        assert r.gate_ladder.get("slippage_guard") == "DENIED"

    def test_positive_min_out_passes_slippage(self):
        b = self._bcast()
        r = _run(b.broadcast_plan(_base_plan([{"amount_out_min_wei": 1000}]),
                                    confirm=True))
        assert r.gate_ladder.get("slippage_guard") == "PASS"

    def test_extract_plan_hops_top_level(self):
        from arbicore.execution.broadcast import _extract_plan_hops
        hops = _extract_plan_hops(_base_plan([{"amount_out_min_wei": 42}]))
        assert len(hops) == 1
        assert int(hops[0]["amount_out_min_wei"]) == 42

    def test_extract_plan_hops_from_swap_steps(self):
        from arbicore.execution.broadcast import _extract_plan_hops
        plan = {
            "steps": [
                {"kind": "borrow", "token": TOKEN_WETH_BASE},
                {"kind": "swap", "args": [{"amountOutMinimum": 999}]},
                {"kind": "swap", "args": [{"amountOutMinimum": 0}]},
            ],
        }
        hops = _extract_plan_hops(plan)
        assert len(hops) == 2
        assert int(hops[0]["amount_out_min_wei"]) == 999
        assert int(hops[1]["amount_out_min_wei"]) == 0
