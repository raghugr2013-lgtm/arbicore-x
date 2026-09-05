"""Regression: m3_0_real_candidate_scan must run through the REAL validation
path and fail closed (never crash) when controlled-live deps are unavailable.

Reproduces the AttributeError ('NoneType' has no attribute 'validate') that hit
`await validator.validate(plan)` when build_controlled_live_safety returned
(None, None), and proves the fix keeps the genuine validator path intact.

Deterministic + offline. No RPC, no signing/broadcast, no fabricated candidate.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

from scripts.m3_0_real_candidate_scan import (
    _controlled_live_unavailable_reason, validate_candidate,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeValidator:
    """Minimal PreBroadcastValidator-shaped double (async validate → decision).
    Used ONLY to prove validate_candidate INVOKES the real validator and passes
    its verdict through unchanged — it never fabricates a PASS."""

    def __init__(self, *, ok, gate, reasons):
        self._decision = SimpleNamespace(ok=ok, gate=gate, reasons=reasons)
        self.called_with = None

    async def validate(self, plan):
        self.called_with = plan
        return self._decision


def test_validate_candidate_failclosed_when_validator_none():
    # The exact crash site: validator is None. Must DENY, not raise.
    reason = "controlled_live_unavailable: no Base RPC — FAIL-CLOSED"
    out = _run(validate_candidate(None, {"opportunity_id": "x"}, reason))
    assert out["ok"] is False
    assert out["gates"] == {}
    assert out["reasons"] == [reason]


def test_validate_candidate_invokes_real_validator_pass_through():
    plan = {"opportunity_id": "cand-1"}
    v_ok = _FakeValidator(ok=True, gate={"g1": "PASS"}, reasons=["ok"])
    out = _run(validate_candidate(v_ok, plan, None))
    assert v_ok.called_with is plan            # real validator actually invoked
    assert out == {"ok": True, "gates": {"g1": "PASS"}, "reasons": ["ok"]}

    # A denying decision must pass through faithfully (no unconditional accept).
    v_deny = _FakeValidator(ok=False, gate={"g1": "FAIL"}, reasons=["gate_7"])
    out2 = _run(validate_candidate(v_deny, plan, None))
    assert out2["ok"] is False and out2["reasons"] == ["gate_7"]


def test_unavailable_reason_is_explicit_and_never_raises():
    from arbicore.execution.quoter import QuoterRegistry
    reason = _controlled_live_unavailable_reason(QuoterRegistry())
    assert isinstance(reason, str) and reason
    assert "FAIL-CLOSED" in reason or "probe_error" in reason


def test_build_controlled_live_safety_returns_pair_and_failcloses():
    # Without an operator Base RPC / USD price feed (CI default), the real
    # constructor returns a (None, None) fail-closed pair — never a half-built
    # validator. When it IS built, it is a PreBroadcastValidator (non-None).
    from arbicore.execution.quoter import QuoterRegistry
    from arbicore.runtime.composition import build_controlled_live_safety
    from arbicore.execution.pre_broadcast import PreBroadcastValidator, CircuitBreaker
    validator, breaker = build_controlled_live_safety(QuoterRegistry())
    if validator is None:
        assert breaker is None                 # fail-closed pair, no crash
    else:
        assert isinstance(validator, PreBroadcastValidator)
        assert isinstance(breaker, CircuitBreaker)
