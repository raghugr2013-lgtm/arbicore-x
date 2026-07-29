"""Deterministic unit tests for the Historical Drift Analyzer compute layer.

These tests use synthetic price series (no network) to verify the pure-compute
helpers in drift_engine return the schema-mandated shapes and correct values
for known inputs.
"""
from __future__ import annotations

import pytest

from services.execution import drift_engine as de


def _series(start_ts: float, prices: list[float], interval_s: int) -> list[tuple[float, float]]:
    """Build a (ts, price) series at uniform interval."""
    return [(start_ts + i * interval_s, p) for i, p in enumerate(prices)]


def test_drift_stats_empty_returns_zeros():
    out = de._drift_stats([], horizon_s=60)
    assert out["samples"] == 0
    assert out["avg_pct"] is None
    assert out["p95_adverse_pct"] is None


def test_drift_stats_flat_series_zero_drift():
    series = _series(0.0, [100.0] * 30, interval_s=30)  # flat
    out = de._drift_stats(series, horizon_s=60)
    assert out["samples"] >= 5
    assert out["avg_pct"] == 0.0
    assert out["worst_pct"] == 0.0
    assert out["stdev_pct"] == 0.0


def test_drift_stats_known_drop():
    # 10 prices, each dropping 1% per step over 60-s windows
    # Start at 100, drop by 1 each: 100, 99, 98, 97, ...
    prices = [100.0 - i for i in range(10)]
    series = _series(0.0, prices, interval_s=60)
    out = de._drift_stats(series, horizon_s=60)
    assert out["samples"] >= 5
    # Each step is ~ -1.01 % change
    assert -1.5 < out["avg_pct"] < -0.5
    # Worst should be at most the largest one-step drop
    assert out["worst_pct"] < 0


def test_survivability_matrix_perfect_when_no_adverse():
    # All-positive returns → every spread survives every horizon
    series = _series(0.0, [100.0 + i * 0.5 for i in range(30)], interval_s=30)
    series_per = {30: series, 60: series, 120: series,
                  300: series, 600: series, 900: series}
    out = de._survivability(series_per)
    assert "spreads_pct" in out and out["spreads_pct"] == de.SPREADS_PCT
    # Spread 2% at horizon 60: all returns positive → survival_prob = 1.0
    cell = out["matrix"]["2"]["60"]
    assert cell["survival_prob"] == 1.0
    assert cell["disappearance_prob"] == 0.0


def test_opportunity_capacity_empty_book_infeasible():
    out = de._opportunity_capacity(None, entry_price=3.8e-5,
                                   entry_price_source="portal",
                                   min_buy_usd=50.0,
                                   profitable_target_pct=8.0)
    assert out["feasible"] is False
    assert out["max_executable_size_usd"] is None


def test_opportunity_capacity_walks_bid_book():
    # entry 100.0, buyers at 110, 108, 105, 102. Threshold 5% → cutoff 105.
    # Capacity at 5% = qty above 105 priced * sum (price*qty).
    live_book = {
        "bids": [[110.0, 1.0], [108.0, 2.0], [105.0, 3.0], [102.0, 5.0]],
        "asks": [],
        "created_at": "2026-06-15T10:00:00Z",
    }
    out = de._opportunity_capacity(live_book, entry_price=100.0,
                                   entry_price_source="portal",
                                   min_buy_usd=50.0,
                                   profitable_target_pct=5.0)
    assert out["feasible"] is True
    # Capacity at 5% (floor=105.0) includes 110×1 + 108×2 + 105×3 = 641
    assert pytest.approx(out["capacity_by_threshold"]["5"]["max_size_usd"], rel=1e-3) == 641.0
    # 3 levels consumed
    assert out["capacity_by_threshold"]["5"]["buyers_consumed"] == 3


def test_classify_regime_stable():
    out = de._classify_regime(realized_vol_1h_pct=0.5,
                              drift_p95_at_5min=-0.3,
                              liquidity_stability=0.9)
    assert out["label"] == "Stable"


def test_classify_regime_extremely_volatile():
    out = de._classify_regime(realized_vol_1h_pct=5.0,
                              drift_p95_at_5min=-4.0,
                              liquidity_stability=0.1)
    assert out["label"] == "Extremely Volatile"


def test_split_symbol_known_quotes():
    assert de._split_symbol("BDAGUSDT") == ("BDAG", "USDT")
    assert de._split_symbol("BTCUSDC") == ("BTC", "USDC")
    assert de._split_symbol("ETHUSD") == ("ETH", "USD")
    assert de._split_symbol("WEIRDSYMBOL") == ("", "")


def test_horizons_are_well_formed():
    assert de.HORIZONS_PRIMARY_S == [30, 60, 120, 300, 600, 900]
    assert de.HORIZONS_SECONDARY_S == [1800, 3600, 7200]
    assert set(de.HORIZONS_ALL_S) == set(de.HORIZONS_PRIMARY_S + de.HORIZONS_SECONDARY_S)


def test_risk_score_returns_valid_label():
    rs = de._risk_score(current_spread_pct=8.0,
                        drift_by_horizon={"600": {"avg_pct": -0.1,
                                                  "p95_adverse_pct": -0.5,
                                                  "samples": 50}},
                        liquidity_factor=0.9, duration_factor=0.8,
                        regime_label="Stable",
                        recommended_size_usd=100.0,
                        expected_cycle_s=600)
    assert rs["label"] in ("LOW", "MEDIUM", "HIGH", "VERY_HIGH")
    assert 0 <= rs["score_0_100"] <= 100
    assert rs["risk_adjusted_profit_pct"] is not None
