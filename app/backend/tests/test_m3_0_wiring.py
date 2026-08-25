"""M3.0 wiring — prove the controlled-live broadcaster is fail-closed and that
the safety builder reuses the real M2 data path.
"""
from __future__ import annotations

import asyncio

from arbicore.execution.broadcast import LimitedLiveBroadcaster
from arbicore.execution.pre_broadcast import (
    PreBroadcastValidator, CircuitBreaker, RevalidationInputs)
from arbicore.runtime.composition import build_controlled_live_safety


def _run(c):
    return asyncio.new_event_loop().run_until_complete(c)


class _Kill:
    async def guard(self):
        return None


class _Mode:
    async def get(self, s):
        return {"mode": "LIMITED_LIVE"}


class _Alloc:
    async def evaluate(self, **kw):
        class _R:
            approved = True
            binding_constraint = ""
        return _R()


def _plan():
    return {"strategy": "flash_loan_arbitrage", "chain": "base",
            "opportunity_id": "op-1"}


def _bcaster(**kw):
    return LimitedLiveBroadcaster(
        kill_switch=_Kill(), mode_repo=_Mode(), wallet_registry=None,
        secret_registry=None, capital_allocator=_Alloc(),
        require_revalidation=True, **kw)


def test_preview_builder_is_fail_closed_none():
    # No Base RPC in preview → (None, None) → require_revalidation denies.
    v, b = build_controlled_live_safety(None)
    assert v is None and b is None


def test_missing_validator_blocks_broadcast():
    rc = _run(_bcaster().broadcast_plan(_plan(), confirm=True))
    assert rc.broadcast_sent is False
    assert rc.gate_ladder.get("pre_broadcast_revalidation") == "DENIED" or \
        any("secret_resolution" in r or "preflight" in r for r in rc.denied_reasons)


def _good(**o):
    base = dict(block_number=1000, quoted_block=999, now_ts=1.0, deadline_ts=1e12,
                net_profit_usd=40.0, min_tvl_usd=500_000.0, quote_ok=True,
                price_ok=True, mev_ok=True, flashloan_available=True,
                opp_fingerprint="op-1")
    base.update(o)
    return RevalidationInputs(**base)


def _validator(inp):
    async def fresh(plan):
        return inp
    return PreBroadcastValidator(fresh_fn=fresh)


def test_stale_opportunity_blocks_broadcast():
    rc = _run(_bcaster(pre_broadcast_validator=_validator(
        _good(block_number=2000, quoted_block=999))).broadcast_plan(
        _plan(), confirm=True))
    assert rc.broadcast_sent is False


def test_unprofitable_opportunity_blocks_broadcast():
    rc = _run(_bcaster(pre_broadcast_validator=_validator(
        _good(net_profit_usd=1.0))).broadcast_plan(_plan(), confirm=True))
    assert rc.broadcast_sent is False


def test_tripped_circuit_breaker_blocks_broadcast():
    cb = CircuitBreaker(max_daily_loss_usd=10.0)
    cb.record_outcome(realized_pnl_usd=-50.0, success=False)   # trips daily
    rc = _run(_bcaster(pre_broadcast_validator=_validator(_good()),
                       circuit_breaker=cb).broadcast_plan(_plan(), confirm=True))
    assert rc.broadcast_sent is False
    assert rc.gate_ladder.get("circuit_breaker") == "DENIED"


def test_flashloan_unavailable_blocks_broadcast():
    rc = _run(_bcaster(pre_broadcast_validator=_validator(
        _good(flashloan_available=None))).broadcast_plan(_plan(), confirm=True))
    assert rc.broadcast_sent is False
