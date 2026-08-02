"""ArbiCore X — Phase D D-2.0 Funding Economics Assessor tests.

Six operator-requested evidence categories + INV-2/INV-3 guards.
"""
from __future__ import annotations

import asyncio
import inspect
import math
import time
from typing import Optional

import pytest

from arbicore.scanners.funding_arbitrage.economics import (
    DEFAULT_VENUE_FEES_PCT,
    EconomicAssessment,
    FundingEconomicsAssessor,
)
from arbicore.scanners.funding_arbitrage.verifier import (
    FundingDifferential, VenueFundingRead,
)


def _read(venue, apr, interval_h=8, provenance=None):
    return VenueFundingRead(
        venue=venue, venue_symbol=f"{venue.upper()}-SYM",
        subject_id="BTC", canonical_asset="BTC-PERP",
        funding_rate_pct_per_interval=apr / ((24.0/interval_h) * 365.0),
        funding_interval_h=interval_h, funding_apr_pct=apr,
        next_funding_ts=time.time()+3600, next_funding_iso=None,
        mark_price=65000.0, index_price=None, open_interest_usd=None,
        venue_observed_at_ts=time.time(), age_s=0.5, freshness_ok=True,
        venue_provenance_id=provenance or f"{venue}_futures_public",
        normalization_notes=[], raw={},
    )


def _diff(long_v, long_apr, short_v, short_apr,
          long_h=8, short_h=8, asset_base="BTC"):
    lr, sr = (_read(long_v, long_apr, long_h),
              _read(short_v, short_apr, short_h))
    return FundingDifferential(
        asset_base=asset_base, canonical_asset=f"{asset_base}-PERP",
        long_venue=long_v, long_funding_apr_pct=long_apr,
        short_venue=short_v, short_funding_apr_pct=short_apr,
        differential_apr_pct=short_apr - long_apr,
        captured_at_ts=time.time(),
        long_read=lr, short_read=sr,
    )


def _cfg(**overrides):
    base = {}
    base.update(overrides)
    return lambda: base


# ============================================================================
# Category 1: Differential vs realistic execution cost
# ============================================================================

def test_total_round_trip_cost_is_two_taker_each_leg():
    """Default fees: ok=0.05+0.05+0.05+0.05=0.20%. Verified explicit."""
    a = FundingEconomicsAssessor(config_loader=_cfg())
    d = _diff("okx", 1.0, "gate", 11.0)   # both default fees 0.05/0.05
    ea = a.assess(d)
    assert ea.long_round_trip_cost_pct == pytest.approx(0.10)
    assert ea.short_round_trip_cost_pct == pytest.approx(0.10)
    assert ea.total_round_trip_cost_pct == pytest.approx(0.20)


def test_break_even_hours_inverse_of_apr():
    """10 % APR diff → revenue 10/8760 %/h = 0.0011415 %/h. Cost 0.20 %.
    break-even = 0.20 / 0.0011415 ≈ 175.2 h."""
    a = FundingEconomicsAssessor(config_loader=_cfg())
    d = _diff("okx", 0.0, "gate", 10.0)
    ea = a.assess(d)
    assert ea.break_even_hours == pytest.approx(175.2, rel=1e-3)


def test_break_even_inf_when_apr_zero_or_negative():
    a = FundingEconomicsAssessor(config_loader=_cfg())
    ea_zero = a.assess(_diff("okx", 5.0, "gate", 5.0))
    assert ea_zero.break_even_hours == math.inf
    # Note: differential by construction is >= 0, this is purely defensive


# ============================================================================
# Category 2: Exchange fee impact (per-venue)
# ============================================================================

def test_hyperliquid_lower_fees_shorten_break_even():
    a = FundingEconomicsAssessor(config_loader=_cfg())
    # 10% APR diff. Compare okx<->gate (0.05/0.05) vs okx<->hyperliquid (0.05/0.025)
    high_fee = a.assess(_diff("okx", 0.0, "gate", 10.0)).break_even_hours
    low_fee  = a.assess(_diff("okx", 0.0, "hyperliquid", 10.0, short_h=1)).break_even_hours
    assert low_fee < high_fee


def test_operator_can_override_venue_fees():
    a = FundingEconomicsAssessor(config_loader=_cfg(
        venue_fees={"okx": {"taker": 0.0, "maker": 0.0},
                    "gate": {"taker": 0.0, "maker": 0.0}}))
    ea = a.assess(_diff("okx", 0.0, "gate", 10.0))
    assert ea.total_round_trip_cost_pct == 0.0
    assert ea.break_even_hours == 0.0


def test_default_venue_fees_table_includes_all_d2_venues():
    for v in ("bybit","okx","gate","bitget","mexc","kucoin","hyperliquid"):
        assert v in DEFAULT_VENUE_FEES_PCT


# ============================================================================
# Category 3: Liquidity requirements
# ============================================================================

def test_liquidity_inconclusive_when_no_depth_provided():
    a = FundingEconomicsAssessor(config_loader=_cfg())
    ea = a.assess(_diff("okx", 0.0, "gate", 12.0))
    assert ea.meets_liquidity_threshold is None
    assert ea.is_economically_actionable is None
    assert any("liquidity_unknown" in n for n in ea.economics_notes)


def test_liquidity_passes_when_depth_above_safety_factor_times_notional():
    a = FundingEconomicsAssessor(config_loader=_cfg(
        default_notional_usd=1000.0, depth_safety_factor=5.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 12.0),
                  long_leg_depth_usd=20_000.0,    # 20000 / 5 = 4000 max pos
                  short_leg_depth_usd=15_000.0)   # 15000 / 5 = 3000 max pos
    assert ea.max_position_usd_by_liquidity == pytest.approx(3000.0)
    assert ea.meets_liquidity_threshold is True


def test_liquidity_fails_when_depth_below_min_position():
    a = FundingEconomicsAssessor(config_loader=_cfg(min_position_usd=100.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 12.0),
                  long_leg_depth_usd=200.0, short_leg_depth_usd=500.0)
    assert ea.max_position_usd_by_liquidity == pytest.approx(40.0)
    assert ea.meets_liquidity_threshold is False
    assert any("insufficient_liquidity" in n for n in ea.economics_notes)


def test_liquidity_fails_when_depth_below_requested_notional():
    a = FundingEconomicsAssessor(config_loader=_cfg(
        default_notional_usd=5000.0, depth_safety_factor=5.0,
        min_position_usd=100.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 12.0),
                  long_leg_depth_usd=10_000.0,    # 10000/5 = 2000 < 5000
                  short_leg_depth_usd=12_000.0)
    assert ea.meets_liquidity_threshold is False
    assert any("depth_below_requested_notional" in n
                for n in ea.economics_notes)


def test_partial_depth_inputs_inconclusive():
    a = FundingEconomicsAssessor(config_loader=_cfg())
    ea = a.assess(_diff("okx", 0.0, "gate", 12.0),
                  long_leg_depth_usd=10_000.0)   # no short depth
    assert ea.meets_liquidity_threshold is None
    assert any("partial_depth_provided" in n for n in ea.economics_notes)


# ============================================================================
# Category 4: Minimum viable differential thresholds
# ============================================================================

def test_min_diff_threshold_fail_for_small_apr():
    a = FundingEconomicsAssessor(config_loader=_cfg(min_diff_apr_pct=5.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 3.0))
    assert ea.meets_min_diff_threshold is False
    assert any("min_diff_threshold" in n for n in ea.economics_notes)


def test_min_diff_threshold_pass_for_large_apr():
    a = FundingEconomicsAssessor(config_loader=_cfg(min_diff_apr_pct=5.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 10.0))
    assert ea.meets_min_diff_threshold is True


# ============================================================================
# Category 5: Large differential that is NOT actionable
# ============================================================================

def test_large_diff_but_break_even_too_long_is_not_actionable():
    """20% APR diff with default 0.20% round-trip → break-even 87.6 h.
    With max_break_even_hours=24, the differential alone is large but
    economically NOT actionable on a 1-day holding horizon."""
    a = FundingEconomicsAssessor(config_loader=_cfg(
        min_diff_apr_pct=5.0, max_break_even_hours=24.0,
        min_position_usd=100.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 20.0),
                  long_leg_depth_usd=100_000.0,
                  short_leg_depth_usd=100_000.0)
    assert ea.meets_min_diff_threshold is True
    assert ea.meets_break_even_horizon is False
    assert ea.is_economically_actionable is False
    assert any("break_even_too_long" in n for n in ea.economics_notes)


def test_large_diff_but_insufficient_liquidity_is_not_actionable():
    a = FundingEconomicsAssessor(config_loader=_cfg(
        min_diff_apr_pct=5.0, max_break_even_hours=1000.0,
        default_notional_usd=5000.0, depth_safety_factor=5.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 50.0),
                  long_leg_depth_usd=500.0, short_leg_depth_usd=600.0)
    assert ea.meets_min_diff_threshold is True
    assert ea.meets_break_even_horizon is True
    assert ea.meets_liquidity_threshold is False
    assert ea.is_economically_actionable is False


def test_fully_actionable_triple_pass():
    """Large diff + acceptable break-even + sufficient depth ⇒ actionable."""
    a = FundingEconomicsAssessor(config_loader=_cfg(
        min_diff_apr_pct=5.0, max_break_even_hours=200.0,
        default_notional_usd=1000.0, depth_safety_factor=5.0,
        min_position_usd=100.0))
    ea = a.assess(_diff("okx", 0.0, "gate", 12.0),
                  long_leg_depth_usd=50_000.0, short_leg_depth_usd=50_000.0)
    assert ea.meets_min_diff_threshold is True
    assert ea.meets_break_even_horizon is True
    assert ea.meets_liquidity_threshold is True
    assert ea.is_economically_actionable is True
    assert ea.economics_notes == []


# ============================================================================
# Category 6: Live differential → economic assessment (no decision, evidence)
# ============================================================================

def test_live_btc_assessment_evidence_shape():
    from arbicore.scanners.funding_arbitrage.sources import build_all_funding_sources
    from arbicore.scanners.funding_arbitrage.verifier import (
        FundingDifferentialVerifier,
    )
    sources = build_all_funding_sources(
        config_loader=lambda: {"discovery_sources": {}})
    v = FundingDifferentialVerifier(sources=sources,
                                     config_loader=lambda: {"max_funding_age_s": 180.0})
    try:
        ev = asyncio.run(v.compute_differential("BTC"))
    finally:
        for s in sources:
            try: asyncio.run(s.close())
            except Exception: pass
    if ev.differential is None:
        pytest.skip(f"insufficient venues: {ev.verifier_notes}")
    a = FundingEconomicsAssessor(config_loader=_cfg(
        min_diff_apr_pct=5.0, max_break_even_hours=24.0,
        default_notional_usd=1000.0))
    ea = a.assess(ev.differential)
    # Evidence shape — assertions don't care about WHICH path failed
    assert ea.asset_base == "BTC"
    assert ea.long_venue != ea.short_venue
    assert ea.total_round_trip_cost_pct > 0
    assert ea.funding_revenue_apr_pct == pytest.approx(
        ev.differential.differential_apr_pct)
    if ea.differential_apr_pct > 0:
        assert ea.break_even_hours > 0
    # No depth provided ⇒ inconclusive overall
    assert ea.meets_liquidity_threshold is None
    assert ea.is_economically_actionable is None


# ============================================================================
# INV-2 / INV-3 static guards (AST-stripped)
# ============================================================================

def _strip(mod) -> str:
    import ast, io, tokenize
    src = inspect.getsource(mod)
    tree = ast.parse(src); drop = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef,
                           ast.AsyncFunctionDef, ast.ClassDef)):
            b = getattr(n, "body", None)
            if b and isinstance(b[0], ast.Expr) and \
               isinstance(b[0].value, ast.Constant) and \
               isinstance(b[0].value.value, str):
                drop.append((b[0].lineno, b[0].end_lineno))
    lines = src.splitlines(keepends=True)
    keep = [True]*len(lines)
    for lo, hi in drop:
        for i in range(lo-1, hi):
            if 0 <= i < len(keep): keep[i] = False
    stripped = "".join(l for l, k in zip(lines, keep) if k)
    toks = [t for t in tokenize.generate_tokens(io.StringIO(stripped).readline)
            if t.type != tokenize.COMMENT]
    return tokenize.untokenize(toks)


def test_inv2_assessor_does_not_construct_canonical_opportunity():
    import arbicore.scanners.funding_arbitrage.economics as mod
    code = _strip(mod)
    for forbidden in ("CanonicalOpportunity", "EmissionBus", "emission_bus"):
        assert forbidden not in code, f"INV violated: {forbidden}"


def test_inv3_assessor_does_not_touch_source_data_quality():
    import arbicore.scanners.funding_arbitrage.economics as mod
    code = _strip(mod)
    assert "source_data_quality" not in code
