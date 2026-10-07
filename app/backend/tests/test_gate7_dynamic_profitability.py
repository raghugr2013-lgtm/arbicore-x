"""Gate 7 dynamic profitability — $25 is reporting-only, not a hard reject."""
from __future__ import annotations

from arbicore.scanners.flash_loan_arbitrage.filter import (
    DEFAULT_MIN_ATOMIC_PROFIT_USD,
    REPORTING_ATOMIC_PROFIT_FLOOR_USD,
    FlashLoanGate7AtomicProfit,
    Gate7ProfitMetrics,
    empty_gate7_profit_metrics,
    profit_band_key,
)
from arbicore.scanners.generic_dex_route_engine import MIN_ATOMIC_PROFIT_USD


def _g7(thresholds=None):
    return FlashLoanGate7AtomicProfit(thresholds=thresholds or {})


# ---- TEST 1: negative rejects ------------------------------------------------
def test_1_negative_net_rejected():
    r = _g7().evaluate(atomic_profit_usd=-1.0, borrow_amount_usd=10_000.0)
    assert r.passed is False
    assert "atomic_profit" in r.reason


# ---- TEST 2–4: sub-$25 positives are NOT rejected for being below $25 -------
def test_2_ten_cents_not_rejected_for_below_25():
    r = _g7().evaluate(atomic_profit_usd=0.10, borrow_amount_usd=10_000.0)
    assert r.passed is True
    assert r.metric_snapshot["reporting_ge_25"] is False


def test_3_one_dollar_not_rejected_for_below_25():
    r = _g7().evaluate(atomic_profit_usd=1.0, borrow_amount_usd=10_000.0)
    assert r.passed is True
    assert r.metric_snapshot["reporting_ge_25"] is False


def test_4_ten_dollars_not_rejected_for_below_25():
    r = _g7().evaluate(atomic_profit_usd=10.0, borrow_amount_usd=10_000.0)
    assert r.passed is True
    assert r.metric_snapshot["reporting_ge_25"] is False


# ---- TEST 5–7: larger profits remain eligible --------------------------------
def test_5_twenty_five_eligible():
    r = _g7().evaluate(atomic_profit_usd=25.0, borrow_amount_usd=10_000.0)
    assert r.passed is True
    assert r.metric_snapshot["reporting_ge_25"] is True


def test_6_one_hundred_eligible():
    r = _g7().evaluate(atomic_profit_usd=100.0, borrow_amount_usd=10_000.0)
    assert r.passed is True
    assert r.metric_snapshot["reporting_ge_100"] is True


def test_7_ten_thousand_eligible():
    r = _g7().evaluate(atomic_profit_usd=10_000.0, borrow_amount_usd=10_000.0)
    assert r.passed is True
    assert r.metric_snapshot["max_net_profit_cap"] is None


# ---- TEST 8: no artificial MAX_NET_PROFIT ceiling ----------------------------
def test_8_no_max_net_profit_ceiling():
    g = _g7()
    for profit in (0.10, 0.50, 1.0, 5.0, 10.0, 25.0, 100.0, 1_000.0, 10_000.0):
        r = g.evaluate(atomic_profit_usd=profit, borrow_amount_usd=50_000.0)
        assert r.passed is True, f"unexpected reject at ${profit}"
        assert r.metric_snapshot["max_net_profit_cap"] is None
    # Zero and negative still rejected
    assert _g7().evaluate(atomic_profit_usd=0.0, borrow_amount_usd=1.0).passed is False
    assert _g7().evaluate(atomic_profit_usd=-0.01, borrow_amount_usd=1.0).passed is False


# ---- TEST 9: $25 remains reporting / statistical only ------------------------
def test_9_twenty_five_is_reporting_bucket_not_hard_reject():
    assert REPORTING_ATOMIC_PROFIT_FLOOR_USD == 25.0
    assert DEFAULT_MIN_ATOMIC_PROFIT_USD == 0.0
    assert MIN_ATOMIC_PROFIT_USD == 0.0

    g = _g7()
    below = g.evaluate(atomic_profit_usd=24.99, borrow_amount_usd=10_000.0)
    assert below.passed is True  # NOT rejected for being below $25
    assert below.metric_snapshot["reporting_floor_usd"] == 25.0
    assert below.metric_snapshot["reporting_ge_25"] is False
    assert below.metric_snapshot["profit_band"] == "profit_10_to_25"

    at = g.evaluate(atomic_profit_usd=25.0, borrow_amount_usd=10_000.0)
    assert at.passed is True
    assert at.metric_snapshot["reporting_ge_25"] is True

    # Operator may still raise a fixed floor via config
    raised = FlashLoanGate7AtomicProfit(
        thresholds={"min_atomic_profit_usd": 25.0})
    assert raised.evaluate(
        atomic_profit_usd=24.99, borrow_amount_usd=10_000.0).passed is False
    assert raised.evaluate(
        atomic_profit_usd=25.0, borrow_amount_usd=10_000.0).passed is True


def test_profit_bands_and_metrics_accumulator():
    m = Gate7ProfitMetrics()
    samples = [-1.0, 0.0, 0.05, 0.25, 0.75, 2.0, 7.0, 15.0, 40.0, 150.0]
    for p in samples:
        m.record(p)
    snap = m.snapshot()
    assert snap["total_gate7_evaluations"] == len(samples)
    assert snap["negative_net_count"] == 1
    assert snap["zero_net_count"] == 1
    assert snap["positive_net_count"] == 8
    assert snap["profit_0_to_0_10"] == 1
    assert snap["profit_0_10_to_0_50"] == 1
    assert snap["profit_0_50_to_1"] == 1
    assert snap["profit_1_to_5"] == 1
    assert snap["profit_5_to_10"] == 1
    assert snap["profit_10_to_25"] == 1
    assert snap["profit_25_to_100"] == 1
    assert snap["profit_100_plus"] == 1
    assert snap["count_ge_25"] == 2
    assert snap["count_ge_100"] == 1
    assert snap["count_net_profit_ge_25"] == 2
    assert snap["count_net_profit_ge_100"] == 1
    assert snap["best_net_profit"] == 150.0
    assert snap["worst_net_profit"] == -1.0
    assert snap["max_net_profit_cap"] is None
    assert empty_gate7_profit_metrics()["total_gate7_evaluations"] == 0
    assert profit_band_key(0.05) == "profit_0_to_0_10"
    assert profit_band_key(-1.0) is None
