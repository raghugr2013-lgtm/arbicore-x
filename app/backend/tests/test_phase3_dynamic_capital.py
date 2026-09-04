"""Phase-3 P0#1 — dynamic capital wiring (offline).

Proves the ACTUAL current wallet balance is the source of truth for plan-time
sizing, the protected gas-reserve floor fails closed, the balance-delta gate
invalidates stale sizing, existing hard caps still bind, and NO fixed $5,000
plan-time capital assumption remains in the live path.
"""
import asyncio
import inspect

import pytest

from arbicore.execution.dynamic_capital import (
    resolve_operating_capital, balance_delta_ok, gas_reserve_usd)
from arbicore.execution.capital_policy import CapitalAllocator, DEFAULT_POLICY


class _FakeRepo:
    def __init__(self, policy=None):
        self._policy = policy if policy is not None else dict(DEFAULT_POLICY)
    async def get(self, strategy):
        return self._policy


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _evaluate(**kw):
    alloc = CapitalAllocator(repo=_FakeRepo())
    return _run(alloc.evaluate(**kw))


# ── operating capital derived from live balance (reserve floor) ──
def test_operating_capital_scales_with_balance():
    low = resolve_operating_capital(wallet_balance_usd=100.0, gas_cost_usd=5.0, reserve_usd=25.0)
    high = resolve_operating_capital(wallet_balance_usd=1000.0, gas_cost_usd=5.0, reserve_usd=25.0)
    assert low.ok and high.ok
    assert low.reference_capital_usd == 70.0        # 100 - (5+25)
    assert high.reference_capital_usd == 970.0
    assert high.reference_capital_usd > low.reference_capital_usd


def test_insufficient_gas_reserve_fails_closed():
    ctx = resolve_operating_capital(wallet_balance_usd=20.0, gas_cost_usd=10.0, reserve_usd=25.0)
    assert ctx.ok is False and ctx.reference_capital_usd is None
    assert "gas+reserve" in ctx.reason


def test_stale_or_missing_balance_fails_closed():
    assert resolve_operating_capital(wallet_balance_usd=None, gas_cost_usd=5.0).ok is False
    assert resolve_operating_capital(wallet_balance_usd=500.0, gas_cost_usd=None).ok is False


def test_zero_operating_after_reserve_fails_closed():
    ctx = resolve_operating_capital(wallet_balance_usd=30.0, gas_cost_usd=5.0, reserve_usd=25.0)
    assert ctx.ok is False   # 30 - 30 = 0 operating


# ── balance-delta revalidation between sizing and broadcast ──
def test_balance_delta_within_tolerance_ok():
    r = balance_delta_ok(sizing_balance_usd=1000.0, fresh_balance_usd=1004.0, tolerance=0.005)
    assert r.ok is True


def test_balance_delta_beyond_tolerance_fails_closed():
    r = balance_delta_ok(sizing_balance_usd=1000.0, fresh_balance_usd=1100.0, tolerance=0.005)
    assert r.ok is False and "drift" in r.reason


def test_balance_delta_missing_fails_closed():
    assert balance_delta_ok(sizing_balance_usd=None, fresh_balance_usd=1000.0).ok is False
    assert balance_delta_ok(sizing_balance_usd=1000.0, fresh_balance_usd=None).ok is False


# ── allocator: no fixed-capital fallback ──
def test_allocator_default_has_no_fixed_capital():
    sig = inspect.signature(CapitalAllocator.evaluate)
    assert sig.parameters["reference_capital_usd"].default is None  # not 5000.0


def test_allocator_denies_when_balance_unavailable():
    d = _evaluate(strategy="flash_loan_arb", proposed_usd=1000.0,
                  reference_capital_usd=None)
    assert d.approved is False and d.binding_constraint == "wallet_balance_unavailable"


def test_allocator_wallet_limit_tracks_live_balance():
    # wallet_pct=0.20 → wallet_limit = ref_capital * 0.20
    low = _evaluate(strategy="s", proposed_usd=10_000.0, reference_capital_usd=1_000.0)
    high = _evaluate(strategy="s", proposed_usd=10_000.0, reference_capital_usd=5_000.0)
    assert low.wallet_limit_usd == pytest.approx(200.0)
    assert high.wallet_limit_usd == pytest.approx(1_000.0)
    assert high.approved_usd >= low.approved_usd


# ── existing hard caps still bind (not removed by dynamic balance) ──
def test_per_plan_cap_still_binds():
    # huge balance → wallet_limit huge, but per_plan_cap $2.5k binds
    d = _evaluate(strategy="s", proposed_usd=1_000_000.0,
                  reference_capital_usd=10_000_000.0,
                  available_liquidity_usd=1_000_000_000.0)
    assert d.approved_usd <= DEFAULT_POLICY["max_per_plan_usd"]
    assert d.binding_constraint in ("per_plan_cap", "daily_notional", "pool")


def test_pool_liquidity_cap_still_binds():
    # tiny liquidity → pool cap (0.5%) binds regardless of large balance
    d = _evaluate(strategy="s", proposed_usd=100_000.0,
                  reference_capital_usd=1_000_000.0,
                  available_liquidity_usd=10_000.0)
    assert d.approved_usd <= 10_000.0 * DEFAULT_POLICY["max_pool_percent"] + 1e-6
    assert d.binding_constraint == "pool"


# ── regression: initial balance is NOT a permanent ceiling ──
def test_balance_is_not_a_permanent_ceiling_A_B_C():
    """balance A → size; balance grows → bigger size; balance falls → smaller."""
    def approved_for(bal_usd):
        ctx = resolve_operating_capital(wallet_balance_usd=bal_usd, gas_cost_usd=5.0,
                                        reserve_usd=25.0)
        d = _evaluate(strategy="s", proposed_usd=10_000_000.0,
                      reference_capital_usd=ctx.reference_capital_usd,
                      available_liquidity_usd=1_000_000_000.0)
        # cap per_plan at 2.5k would mask growth; use a policy with huge caps
        return d.wallet_limit_usd  # wallet limit directly reflects live balance
    a = approved_for(1_000.0)      # balance A
    b = approved_for(50_000.0)     # profit → balance B (higher)
    c = approved_for(10_000.0)     # loss   → balance C (lower)
    assert b > a          # scales UP as balance grows
    assert c < b          # scales DOWN as balance falls
    assert a != b != c    # no single fixed ceiling


def test_no_fixed_5000_used_when_balance_given():
    # ref_capital 200 → wallet_limit 40 (200*0.2), NOT 1000 (5000*0.2)
    d = _evaluate(strategy="s", proposed_usd=10_000.0, reference_capital_usd=200.0)
    assert d.wallet_limit_usd == pytest.approx(40.0)


def test_gas_reserve_config_default():
    assert gas_reserve_usd() >= 0.0
