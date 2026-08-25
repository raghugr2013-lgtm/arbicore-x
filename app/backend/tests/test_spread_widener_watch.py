"""Spread Widener Watch — flag correctness (offline, read-only, no RPC).

Locks in the fix where partial/anomalous quotes must NEVER be flagged as
"worth M3 validation" (a false-flag would send garbage into M3). Only fully
priced ("ok") routes with a plausible spread and a computed net qualify.
"""
from types import SimpleNamespace

import pytest

from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    MevRiskScorer)
from scripts.m3_0_spread_widener_watch import (
    _worth_m3, _evaluate, _net_gap, _near_threshold)


# ---- flag predicate --------------------------------------------------------

def test_worth_m3_flags_profitable():
    assert _worth_m3(net=50.0, min_net=35.0) is True


def test_worth_m3_below_floor_not_flagged():
    # positive gross but net below floor → NOT a full-M3 trigger (only edge_positive)
    assert _worth_m3(net=10.0, min_net=35.0) is False


def test_worth_m3_negative_net_not_flagged():
    assert _worth_m3(net=-50.0, min_net=35.0) is False


def test_worth_m3_none_net_never_flagged():
    # partial/anomalous quote → net is None → must NOT flag
    assert _worth_m3(net=None, min_net=35.0) is False


# ---- _evaluate refuses partial / anomalous quotes --------------------------

class _FakeEcon:
    def assess(self, **kw):
        # net scales with gross so tests are deterministic
        return SimpleNamespace(atomic_profit_usd=float(kw["gross_profit_pct"]) * 100.0)


def _facts_for(pool0):
    table = {
        "P_OKP": {"route_quote_status": "ok", "gross_profit_pct": 1.0,
                  "hop_legs": [{"h": 1}], "min_pool_tvl_usd_in_route": 1e6},
        "P_OKL": {"route_quote_status": "ok", "gross_profit_pct": -0.5,
                  "hop_legs": [{"h": 1}], "min_pool_tvl_usd_in_route": 1e6},
        "P_PARTIAL": {"route_quote_status": "partial", "gross_profit_pct": 40000.0,
                      "hop_legs": [{"h": 1}], "min_pool_tvl_usd_in_route": 0},
        "P_ANOM": {"route_quote_status": "ok", "gross_profit_pct": 999.0,
                   "hop_legs": [{"h": 1}], "min_pool_tvl_usd_in_route": 1e6},
    }
    return table.get(pool0)


async def _fake_quote_provider(hm, borrow_usd):
    return _facts_for(hm["route_pools"][0])


@pytest.mark.asyncio
async def test_evaluate_only_prices_ok_plausible_routes():
    cycles = [
        {"name": "ok_profit", "borrow_token": "WETH",
         "route_pools": ["P_OKP", "x"], "cycle_token_path": ["WETH", "USDC", "WETH"]},
        {"name": "ok_loss", "borrow_token": "WETH",
         "route_pools": ["P_OKL", "x"], "cycle_token_path": ["WETH", "USDC", "WETH"]},
        {"name": "partial", "borrow_token": "WETH",
         "route_pools": ["P_PARTIAL", "x"], "cycle_token_path": ["WETH", "USDC", "WETH"]},
        {"name": "anomaly", "borrow_token": "WETH",
         "route_pools": ["P_ANOM", "x"], "cycle_token_path": ["WETH", "USDC", "WETH"]},
    ]
    rows = await _evaluate(cycles, _fake_quote_provider, _FakeEcon(),
                           congestion_pct=10.0, mev=MevRiskScorer(),
                           borrow_usd=10000.0)
    by = {r["name"]: r for r in rows}
    # ok routes get a computed net
    assert by["ok_profit"]["est_net_usd"] == pytest.approx(100.0)
    assert by["ok_loss"]["est_net_usd"] == pytest.approx(-50.0)
    # partial + anomaly are refused (net stays None → cannot be flagged)
    assert by["partial"]["est_net_usd"] is None
    assert by["anomaly"]["est_net_usd"] is None

    # end-to-end flag decision
    assert _worth_m3(by["ok_profit"]["est_net_usd"], 35.0) is True
    assert _worth_m3(by["ok_loss"]["est_net_usd"], 35.0) is False
    assert _worth_m3(by["partial"]["est_net_usd"], 35.0) is False
    assert _worth_m3(by["anomaly"]["est_net_usd"], 35.0) is False


# ---- near-threshold signal (read-only) -------------------------------------

def test_net_gap_semantics():
    assert _net_gap(None, 35.0) is None
    assert _net_gap(-50.0, 35.0) == pytest.approx(85.0)   # $85 below threshold
    assert _net_gap(20.0, 35.0) == pytest.approx(15.0)    # $15 below (near)
    assert _net_gap(40.0, 35.0) == pytest.approx(-5.0)    # above ⇒ negative gap


def test_near_threshold_selects_and_ranks_within_band():
    rows = [
        {"name": "far_below", "est_net_usd": -50.0},   # gap 85 → excluded
        {"name": "near_a", "est_net_usd": 20.0},       # gap 15 → in band
        {"name": "near_b", "est_net_usd": 30.0},       # gap 5  → in band (nearest)
        {"name": "above", "est_net_usd": 40.0},        # gap -5 → excluded (already worth_m3)
        {"name": "unpriced", "est_net_usd": None},     # gap None → excluded
    ]
    near = _near_threshold(rows, min_net=35.0, band=25.0, top=10)
    assert [r["name"] for r in near] == ["near_b", "near_a"]   # nearest first
    assert all(r.get("near_threshold") for r in near)
    # band respected: nothing beyond $25 gap
    assert all(0.0 < r["net_gap_usd"] <= 25.0 for r in near)


def test_near_threshold_top_limit():
    rows = [{"name": f"r{i}", "est_net_usd": 34.0 - i} for i in range(20)]
    near = _near_threshold(rows, min_net=35.0, band=100.0, top=3)
    assert len(near) == 3
    assert near[0]["name"] == "r0"    # smallest gap first
