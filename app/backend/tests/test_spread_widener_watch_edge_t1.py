"""T1 edge-case coverage for the Spread Widener Watch (offline, read-only).

Covers: plausibility clamp override via env, missing hop_legs, quote-provider
exception, economics exception, and the negative-net + zero-gross flag boundary.
All rows produced by these paths must be non-flaggable (est_net_usd None) or
correctly flagged by _worth_m3 only.
"""
import os
from types import SimpleNamespace

import pytest

from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    MevRiskScorer)
from scripts.m3_0_spread_widener_watch import _worth_m3, _evaluate


class _FakeEcon:
    def assess(self, **kw):
        return SimpleNamespace(atomic_profit_usd=float(kw["gross_profit_pct"]) * 100.0)


class _BoomEcon:
    def assess(self, **kw):
        raise RuntimeError("econ down")


def _cycle(name, pool0):
    return {"name": name, "borrow_token": "WETH",
            "route_pools": [pool0, "x"],
            "cycle_token_path": ["WETH", "USDC", "WETH"]}


# ---- flag predicate boundaries --------------------------------------------

def test_worth_m3_exact_min_net_boundary():
    assert _worth_m3(net=35.0, gross=-1.0, min_net=35.0, min_gross=0.0) is True
    assert _worth_m3(net=34.99, gross=-1.0, min_net=35.0, min_gross=0.0) is False


def test_worth_m3_gross_none_uses_net_only():
    assert _worth_m3(net=100.0, gross=None, min_net=35.0, min_gross=0.0) is True
    assert _worth_m3(net=1.0, gross=None, min_net=35.0, min_gross=0.0) is False


def test_worth_m3_respects_raised_min_gross():
    # never "lowers" a threshold: raising min_gross must reduce flagging
    assert _worth_m3(net=1.0, gross=0.1, min_net=35.0, min_gross=0.5) is False


# ---- _evaluate degraded paths ---------------------------------------------

@pytest.mark.asyncio
async def test_evaluate_no_hop_legs_and_provider_exception_never_flaggable():
    async def provider(hm, borrow_usd):
        p = hm["route_pools"][0]
        if p == "BOOM":
            raise ValueError("rpc rate limited")
        if p == "EMPTY":
            return {"route_quote_status": "ok", "gross_profit_pct": 5.0,
                    "hop_legs": []}
        return None

    rows = await _evaluate([_cycle("boom", "BOOM"), _cycle("empty", "EMPTY"),
                            _cycle("none", "NADA")],
                           provider, _FakeEcon(), congestion_pct=None,
                           mev=MevRiskScorer(), borrow_usd=10000.0)
    by = {r["name"]: r for r in rows}
    assert "error" in by["boom"]
    for name in ("boom", "empty", "none"):
        assert by[name].get("est_net_usd") is None
        assert _worth_m3(by[name].get("est_net_usd"),
                         by[name].get("gross_profit_pct"), 35.0, 0.0) is False


@pytest.mark.asyncio
async def test_evaluate_econ_failure_leaves_net_none():
    async def provider(hm, borrow_usd):
        return {"route_quote_status": "ok", "gross_profit_pct": 1.0,
                "hop_legs": [{"h": 1}]}

    rows = await _evaluate([_cycle("okp", "P")], provider, _BoomEcon(),
                           congestion_pct=5.0, mev=MevRiskScorer(),
                           borrow_usd=10000.0)
    assert rows[0]["est_net_usd"] is None
    assert rows[0]["worth_m3_validation"] is False
    assert _worth_m3(rows[0].get("est_net_usd"),
                     rows[0].get("gross_profit_pct"), 35.0, 0.0) is False


@pytest.mark.asyncio
async def test_evaluate_plausibility_clamp_is_env_tightenable(monkeypatch):
    async def provider(hm, borrow_usd):
        return {"route_quote_status": "ok", "gross_profit_pct": 5.0,
                "hop_legs": [{"h": 1}]}

    monkeypatch.setenv("ARBICORE_SPREAD_WATCH_MAX_GROSS_PCT", "1.0")
    rows = await _evaluate([_cycle("tight", "P")], provider, _FakeEcon(),
                           congestion_pct=5.0, mev=MevRiskScorer(),
                           borrow_usd=10000.0)
    assert rows[0]["est_net_usd"] is None
    monkeypatch.delenv("ARBICORE_SPREAD_WATCH_MAX_GROSS_PCT")
    rows = await _evaluate([_cycle("loose", "P")], provider, _FakeEcon(),
                           congestion_pct=5.0, mev=MevRiskScorer(),
                           borrow_usd=10000.0)
    assert rows[0]["est_net_usd"] == pytest.approx(500.0)
