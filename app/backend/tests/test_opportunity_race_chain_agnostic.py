"""Opportunity Race — chain-agnostic first-qualifying-edge selection (fail-closed).

Proves: no hardcoded chain preference; only ECONOMICS-PASS candidates that clear
the UNCHANGED Gate-7 profit floor qualify; below-floor / not-ready candidates are
skipped; no signing/broadcast/execution side effects; deterministic ordering.
"""
from __future__ import annotations

import pytest

from arbicore.control.opportunity_race import run_opportunity_race
from arbicore.control.chain_execution_readiness import PASS, BLOCKED, STAGE_ORDER


def _readiness(chain, *, econ_pass, net_profit=None, reached="ECONOMICS"):
    stages = {}
    for s in STAGE_ORDER:
        stages[s] = {"status": PASS, "reason": "ok", "evidence": {}}
    if econ_pass:
        stages["ECONOMICS"] = {"status": PASS, "reason": "economically_evaluated_all_in",
                               "evidence": {"net_profit_usd": net_profit}}
    else:
        stages["ECONOMICS"] = {"status": BLOCKED, "reason": "all_in_cost_evidence_unavailable",
                               "evidence": {}}
    # Stages after ECONOMICS left PASS is fine; qualifying_stage=ECONOMICS.
    return {"chain": chain, "stages": stages, "reached_stage": reached,
            "terminal_blocker": None}


def _fake_evaluate(table):
    async def _ev(chain, *, candidate=None, **kw):
        return table[chain]
    return _ev


@pytest.mark.asyncio
async def test_first_qualifying_edge_no_chain_preference():
    # polygon submitted FIRST and qualifies ⇒ it wins over arbitrum/base.
    table = {
        "polygon": _readiness("polygon", econ_pass=True, net_profit=120.0),
        "arbitrum": _readiness("arbitrum", econ_pass=True, net_profit=500.0),
        "base": _readiness("base", econ_pass=True, net_profit=999.0),
    }
    cands = [{"chain": "polygon", "candidate": {"borrow_amount_usd": 10_000}},
             {"chain": "arbitrum", "candidate": {"borrow_amount_usd": 10_000}},
             {"chain": "base", "candidate": {"borrow_amount_usd": 10_000}}]
    res = await run_opportunity_race(cands, evaluate_fn=_fake_evaluate(table))
    assert res["winner"]["chain"] == "polygon"       # first submitted qualifier
    assert res["entrants"] == 3
    assert res["signed"] is False and res["broadcast"] is False and res["executed"] is False


@pytest.mark.asyncio
async def test_below_floor_candidate_skipped():
    # arbitrum below the $25 Gate-7 floor ⇒ skipped; ethereum wins.
    table = {
        "arbitrum": _readiness("arbitrum", econ_pass=True, net_profit=5.0),
        "ethereum": _readiness("ethereum", econ_pass=True, net_profit=40.0),
    }
    cands = [{"chain": "arbitrum", "candidate": {"borrow_amount_usd": 10_000}},
             {"chain": "ethereum", "candidate": {"borrow_amount_usd": 10_000}}]
    res = await run_opportunity_race(cands, evaluate_fn=_fake_evaluate(table))
    assert res["winner"]["chain"] == "ethereum"
    assert res["evaluated"][0]["qualified"] is False   # arbitrum skipped (below floor)


@pytest.mark.asyncio
async def test_not_economics_ready_does_not_qualify():
    table = {
        "optimism": _readiness("optimism", econ_pass=False),
        "bnb": _readiness("bnb", econ_pass=False),
    }
    cands = [{"chain": "optimism", "candidate": {"borrow_amount_usd": 10_000}},
             {"chain": "bnb", "candidate": {"borrow_amount_usd": 10_000}}]
    res = await run_opportunity_race(cands, evaluate_fn=_fake_evaluate(table))
    assert res["winner"] is None
    assert res["entrants"] == 0


@pytest.mark.asyncio
async def test_race_offline_all_six_chains_no_winner():
    # Real evaluator, offline (no RPC) ⇒ nothing qualifies, no winner, no side effects.
    cands = [{"chain": c, "candidate": {"borrow_amount_usd": 10_000}}
             for c in ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")]
    res = await run_opportunity_race(cands)
    assert res["winner"] is None
    assert res["entrants"] == 0
    assert res["signed"] is False and res["broadcast"] is False and res["executed"] is False
