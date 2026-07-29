"""Tests for validators (liquidity, slippage, mev risk, whitelist) and capital."""
import pytest

from arbicore.intelligence import (
    CapitalSizer,
    LiquidityValidator,
    MevRiskClassifier,
    PairWhitelist,
    SlippageValidator,
)
from arbicore.models import MevRiskLevel


# ---- Liquidity ----
def test_liquidity_floor():
    v = LiquidityValidator(min_liquidity_usd=100_000)
    assert v.validate(liquidity_usd=150_000, trade_amount=10_000).passed is True
    assert v.validate(liquidity_usd=50_000).passed is False


def test_liquidity_depth_check():
    v = LiquidityValidator(min_liquidity_usd=100_000, depth_multiplier=2.0)
    # passes floor but fails depth (needs 2x of 60k = 120k)
    assert v.validate(liquidity_usd=110_000, trade_amount=60_000).passed is False


# ---- Slippage (deterministic) ----
def test_slippage_deterministic_pass():
    v = SlippageValidator()
    r = v.validate(net_profit=100, gas_cost=10, slippage_estimate=0.004)
    assert r.passed is True
    assert r.details["deterministic"] is True


def test_slippage_fail_when_profit_too_low():
    v = SlippageValidator(profit_gas_multiplier=2.0)
    r = v.validate(net_profit=15, gas_cost=10, slippage_estimate=0.005)
    assert r.passed is False


def test_slippage_default_estimate_is_midpoint():
    v = SlippageValidator(min_slippage=0.003, max_slippage=0.006)
    assert v.default_estimate() == pytest.approx(0.0045)


# ---- MEV risk ----
def test_mev_low_risk():
    c = MevRiskClassifier()
    assert c.classify(liquidity_usd=800_000, volatility=0.01).level == MevRiskLevel.LOW


def test_mev_high_risk_low_liquidity():
    c = MevRiskClassifier()
    assert c.classify(liquidity_usd=5_000, volatility=0.5).level == MevRiskLevel.HIGH


def test_mev_medium_risk():
    c = MevRiskClassifier()
    assert c.classify(liquidity_usd=150_000, volatility=0.03).level == MevRiskLevel.MEDIUM


# ---- Whitelist ----
def test_whitelist_bidirectional():
    wl = PairWhitelist.default()
    assert wl.is_allowed("WETH/USDC") is True
    assert wl.is_allowed("USDC/WETH") is True
    assert wl.is_allowed("DOGE/PEPE") is False


def test_whitelist_inactive_allows_all():
    wl = PairWhitelist(["WETH/USDC"], active=False)
    assert wl.is_allowed("ANYTHING/ELSE") is True


# ---- Capital sizing ----
def test_capital_pool_binding():
    s = CapitalSizer().size(available_liquidity=1_000_000, reference_capital_usd=40_000)
    # pool=8000, wallet=10000, cap=10000 -> pool binds
    assert s.suggested_trade_size_usd == 8000.0
    assert s.binding_constraint == "pool"


def test_capital_cap_binding():
    s = CapitalSizer().size(available_liquidity=10_000_000, reference_capital_usd=1_000_000)
    assert s.suggested_trade_size_usd == 10_000.0
    assert s.binding_constraint == "per_trade_cap"
