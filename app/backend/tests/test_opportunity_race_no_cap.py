"""Regression: the default Opportunity Race must NOT truncate the per-chain
universe (no hidden cap=10). An explicit operator/test cap still works.

Proves the fix for the VPS truncation (arbitrum 10/15, polygon 10/12, bnb 10/20,
total 50 instead of 62). Deterministic: spies capture the ``cap`` the race
forwards to the canonical certifier, cross-checked against the REAL per-chain
probe universe sizes.
"""
from __future__ import annotations

import asyncio

from arbicore.runtime.opportunity_race import (
    SixChainOpportunityRace, _default_chain_evaluator, _default_base_evaluator,
)
from scripts.vps_multichain_preflight import _build_probe_tasks

SIX_CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]
# The previously verified FULL non-Base probe universe (authoritative).
FULL_UNIVERSE = {"ethereum": 9, "arbitrum": 15, "optimism": 6,
                 "polygon": 12, "bnb": 20}


def _spy_evaluator(caps: dict):
    """Records the cap forwarded per chain, and returns rows sized to the REAL
    probe universe honouring that cap (None ⇒ full, int ⇒ truncated)."""
    async def _ev(chain, cap):
        caps[chain] = cap
        universe = len(_build_probe_tasks(chain))
        n = universe if cap is None else min(universe, int(cap))
        rows = [{"quotable": True, "liquidity_verified": True} for _ in range(n)]
        return {"skipped": None, "head": {"block": 1, "error": None},
                "rows": rows, "candidates": []}
    return _ev


# ── Default race forwards NO cap (None) to every chain ───────────────────────
def test_default_race_forwards_no_cap():
    caps: dict = {}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_spy_evaluator(caps),
                                   base_evaluator=_spy_evaluator(caps))
    asyncio.run(race.scan_once())
    assert all(caps[c] is None for c in SIX_CHAINS), caps


def test_default_pairs_cap_is_none():
    assert SixChainOpportunityRace()._pairs_cap is None


# ── Full per-chain universe is evaluated (no truncation to 10) ───────────────
def test_arbitrum_evaluates_all_15():
    caps: dict = {}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_spy_evaluator(caps),
                                   base_evaluator=_spy_evaluator(caps))
    result = asyncio.run(race.scan_once())
    assert FULL_UNIVERSE["arbitrum"] == 15
    assert result.per_chain["arbitrum"].candidates_seen == 15


def test_polygon_evaluates_all_12():
    caps: dict = {}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_spy_evaluator(caps),
                                   base_evaluator=_spy_evaluator(caps))
    result = asyncio.run(race.scan_once())
    assert result.per_chain["polygon"].candidates_seen == 12


def test_bnb_evaluates_all_20():
    caps: dict = {}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_spy_evaluator(caps),
                                   base_evaluator=_spy_evaluator(caps))
    result = asyncio.run(race.scan_once())
    assert result.per_chain["bnb"].candidates_seen == 20


def test_full_non_base_universe_is_62():
    caps: dict = {}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_spy_evaluator(caps),
                                   base_evaluator=_spy_evaluator(caps))
    result = asyncio.run(race.scan_once())
    non_base = sum(result.per_chain[c].candidates_seen
                   for c in FULL_UNIVERSE)
    assert non_base == 62
    assert sum(FULL_UNIVERSE.values()) == 62


# ── An explicit cap still works when deliberately supplied ───────────────────
def test_explicit_cap_still_truncates():
    caps: dict = {}
    race = SixChainOpportunityRace(networks=SIX_CHAINS, pairs_cap=3,
                                   chain_evaluator=_spy_evaluator(caps),
                                   base_evaluator=_spy_evaluator(caps))
    result = asyncio.run(race.scan_once())
    assert all(caps[c] == 3 for c in SIX_CHAINS)
    assert result.per_chain["bnb"].candidates_seen == 3
    assert result.per_chain["arbitrum"].candidates_seen == 3


def test_default_certifier_forwards_none_cap(monkeypatch):
    captured = {}

    async def _fake_certify(chain, cap):
        captured["cap"] = cap
        return {"skipped": None, "head": {"block": 1}, "rows": [], "candidates": []}

    monkeypatch.setattr("scripts.vps_runtime_certify._certify_chain", _fake_certify)
    asyncio.run(_default_chain_evaluator("arbitrum", None))
    assert captured["cap"] is None


# ── Base canonical M3 still composed via the existing evaluator ──────────────
def test_base_still_uses_canonical_default_evaluator():
    assert SixChainOpportunityRace()._base_eval is _default_base_evaluator


def test_base_evaluator_ignores_cap_uses_full_canonical(monkeypatch):
    # Base composes the fixed canonical CANDIDATES set (not probe-capped).
    monkeypatch.setattr(
        "arbicore.config.persistent.resolve_rpc_url_from_env", lambda chain: None)
    res = asyncio.run(_default_base_evaluator("base", None))
    assert res["skipped"] == "no_operator_configured_rpc"  # honest, fail-closed


# ── Six-chain orchestration + safety unchanged by the cap fix ────────────────
def test_six_chain_coverage_and_safety_preserved():
    caps: dict = {}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_spy_evaluator(caps),
                                   base_evaluator=_spy_evaluator(caps))
    result = asyncio.run(race.scan_once())
    assert set(result.per_chain.keys()) == set(SIX_CHAINS)
    for k in ("signing", "broadcast", "auto_execution", "full_live", "withdrawals"):
        assert result.safety_posture[k] is False
