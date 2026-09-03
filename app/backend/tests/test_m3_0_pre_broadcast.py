"""M3.0 — atomic pre-broadcast revalidation + circuit breakers (offline).

Proves every new fail-closed safety invariant with deterministic doubles, and
that the broadcaster refuses to sign/broadcast when fresh final validation is
required but missing/failing.
"""
from __future__ import annotations

import asyncio

from arbicore.execution.pre_broadcast import (
    RevalidationInputs, PreBroadcastValidator, SeenOpportunityGuard,
    CircuitBreaker,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _good(**over):
    base = dict(block_number=1000, quoted_block=998, now_ts=100.0,
                deadline_ts=200.0, net_profit_usd=40.0, min_tvl_usd=500_000.0,
                quote_ok=True, price_ok=True, mev_ok=True,
                flashloan_available=True, opp_fingerprint="fp-1")
    base.update(over)
    return RevalidationInputs(**base)


def _validator(inputs, **kw):
    async def fresh(plan):
        return inputs
    kw.setdefault("min_net_profit_usd", 25.0)
    kw.setdefault("safety_buffer_usd", 10.0)
    kw.setdefault("max_block_lag", 5)
    return PreBroadcastValidator(fresh_fn=fresh, **kw)


# ── happy path ───────────────────────────────────────────────────────────────
def test_all_green_passes():
    d = _run(_validator(_good()).validate({}))
    assert d.ok is True
    assert all(v == "PASS" for v in d.gate.values())


# ── each fail-closed branch ──────────────────────────────────────────────────
def test_fresh_read_unavailable_fails_closed():
    async def fresh(plan):
        return None
    v = PreBroadcastValidator(fresh_fn=fresh)
    assert _run(v.validate({})).ok is False


def test_fresh_read_exception_fails_closed():
    async def fresh(plan):
        raise RuntimeError("rpc down")
    v = PreBroadcastValidator(fresh_fn=fresh)
    d = _run(v.validate({}))
    assert d.ok is False and "revalidation" in d.gate


def test_reorg_head_below_quoted_fails_closed():
    d = _run(_validator(_good(block_number=997, quoted_block=998)).validate({}))
    assert d.ok is False and d.gate["reorg_protection"] == "DENIED"


def test_stale_block_lag_fails_closed():
    d = _run(_validator(_good(block_number=1010, quoted_block=1000)).validate({}))
    assert d.ok is False and d.gate["block_freshness"] == "DENIED"


def test_deadline_passed_fails_closed():
    d = _run(_validator(_good(now_ts=300.0, deadline_ts=200.0)).validate({}))
    assert d.ok is False and d.gate["deadline"] == "DENIED"


def test_stale_quote_fails_closed():
    d = _run(_validator(_good(quote_ok=False)).validate({}))
    assert d.ok is False and d.gate["fresh_quote"] == "DENIED"


def test_stale_price_fails_closed():
    d = _run(_validator(_good(price_ok=False)).validate({}))
    assert d.ok is False and d.gate["fresh_price"] == "DENIED"


def test_mev_over_cap_fails_closed():
    d = _run(_validator(_good(mev_ok=False)).validate({}))
    assert d.ok is False and d.gate["mev_risk"] == "DENIED"


def test_flashloan_unavailable_fails_closed():
    for val in (False, None):
        d = _run(_validator(_good(flashloan_available=val)).validate({}))
        assert d.ok is False and d.gate["flashloan_availability"] == "DENIED"


def test_tvl_unverifiable_fails_closed():
    for val in (None, 0.0):
        d = _run(_validator(_good(min_tvl_usd=val)).validate({}))
        assert d.ok is False and d.gate["liquidity_tvl"] == "DENIED"


def test_profit_below_floor_plus_buffer_fails_closed():
    # floor 25 + buffer 10 = 35 required
    d = _run(_validator(_good(net_profit_usd=34.99)).validate({}))
    assert d.ok is False and d.gate["profit_buffer"] == "DENIED"
    d2 = _run(_validator(_good(net_profit_usd=35.0)).validate({}))
    assert d2.ok is True


def test_profit_none_fails_closed():
    d = _run(_validator(_good(net_profit_usd=None)).validate({}))
    assert d.ok is False and d.gate["profit_buffer"] == "DENIED"


# ── duplicate-opportunity ────────────────────────────────────────────────────
def test_duplicate_opportunity_blocked_second_time():
    v = _validator(_good())
    assert _run(v.validate({})).ok is True         # first claims fp
    # a fresh validator sharing the same dedupe guard sees it as in-flight
    guard = v._dedupe
    v2 = _validator(_good())
    v2._dedupe = guard
    d = _run(v2.validate({}))
    assert d.ok is False and d.gate["duplicate_opportunity"] == "DENIED"


def test_dedupe_ttl_expiry():
    clk = {"t": 0.0}
    g = SeenOpportunityGuard(ttl_s=10.0, clock=lambda: clk["t"])
    g.claim("x")
    assert g.seen("x") is True
    clk["t"] = 11.0
    assert g.seen("x") is False


# ── circuit breaker ──────────────────────────────────────────────────────────
def test_breaker_daily_loss_trips():
    cb = CircuitBreaker(max_daily_loss_usd=100.0, max_hourly_loss_usd=1e9,
                        max_consecutive_failures=1_000)
    cb.record_outcome(realized_pnl_usd=-120.0, success=False)
    assert cb.status()["tripped"] is True


def test_breaker_hourly_loss_trips():
    cb = CircuitBreaker(max_daily_loss_usd=1e9, max_hourly_loss_usd=50.0,
                        max_consecutive_failures=1_000)
    cb.record_outcome(realized_pnl_usd=-60.0, success=False)
    assert cb.status()["tripped"] is True


def test_breaker_consecutive_failures_trips_and_resets():
    cb = CircuitBreaker(max_daily_loss_usd=1e9, max_hourly_loss_usd=1e9,
                        max_consecutive_failures=3)
    for _ in range(3):
        cb.record_outcome(realized_pnl_usd=0.0, success=False)
    assert cb.status()["tripped"] is True
    cb.record_outcome(realized_pnl_usd=5.0, success=True)   # reset
    assert cb.status()["tripped"] is False


def test_breaker_health_flag_trips():
    cb = CircuitBreaker(max_daily_loss_usd=1e9, max_hourly_loss_usd=1e9,
                        max_consecutive_failures=1_000)
    cb.set_health("rpc", False)
    assert cb.status()["tripped"] is True


def test_breaker_on_trip_fires_once():
    fired = []

    async def on_trip(reason):
        fired.append(reason)

    cb = CircuitBreaker(max_daily_loss_usd=10.0, on_trip=on_trip)
    cb.record_outcome(realized_pnl_usd=-20.0, success=False)
    _run(cb.guard())
    _run(cb.guard())
    assert len(fired) == 1   # only on transition into tripped


# ── broadcaster wiring: no broadcast without fresh validation ────────────────
def test_broadcaster_require_revalidation_missing_blocks_broadcast():
    from arbicore.execution.broadcast import LimitedLiveBroadcaster

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

    b = LimitedLiveBroadcaster(
        kill_switch=_Kill(), mode_repo=_Mode(), wallet_registry=None,
        secret_registry=None, capital_allocator=_Alloc(),
        require_revalidation=True)   # no validator wired
    rc = _run(b.broadcast_plan({"strategy": "flash_loan_arbitrage",
                                "chain": "base"}, confirm=True))
    assert rc.broadcast_sent is False
    assert any("pre_broadcast_revalidation" in r or "secret_resolution" in r
               or "preflight" in r for r in rc.denied_reasons)


def test_broadcaster_denying_validator_blocks_broadcast():
    from arbicore.execution.broadcast import LimitedLiveBroadcaster

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

    async def fresh(plan):
        return _good(net_profit_usd=1.0)   # below floor+buffer → deny

    val = PreBroadcastValidator(fresh_fn=fresh)
    b = LimitedLiveBroadcaster(
        kill_switch=_Kill(), mode_repo=_Mode(), wallet_registry=None,
        secret_registry=None, capital_allocator=_Alloc(),
        pre_broadcast_validator=val, require_revalidation=True)
    rc = _run(b.broadcast_plan({"strategy": "flash_loan_arbitrage",
                                "chain": "base"}, confirm=True))
    assert rc.broadcast_sent is False
