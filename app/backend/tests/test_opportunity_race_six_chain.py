"""Six-Chain READ-ONLY Opportunity Race — deterministic unit tests.

All tests use INJECTED fake per-chain evaluators (no network / no RPC) so they
are deterministic and offline. They assert coverage, isolation, fail-closed
economics, positive-NET surfacing, safety invariants, lifecycle, provenance and
that the Base canonical path / E1-E2 executor capability are untouched.
"""
from __future__ import annotations

import asyncio

import pytest

from arbicore.runtime.opportunity_race import (
    SixChainOpportunityRace, SAFETY_POSTURE,
    STATUS_EVALUATED, STATUS_SKIPPED, STATUS_TIMEOUT, STATUS_ERROR,
)

SIX_CHAINS = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]


def _row(quotable=True, liq=True):
    return {"quotable": quotable, "liquidity_verified": liq}


def _cand(chain, net, *, econ=True, block=100, eid=None):
    return {
        "chain": chain, "block": block,
        "stages": {"ECONOMICALLY_VALID": econ},
        "all_in_net_usd": net,
        "evidence_id": eid or f"cand:{chain}:{net}",
        "eliminated_at": None, "reason": None,
    }


def _chain_res(chain, *, rows=None, candidates=None, skipped=None, block=100, error=None):
    return {"skipped": skipped, "head": {"block": block, "error": error},
            "rows": rows or [], "candidates": candidates or []}


def _fake_evaluator(mapping):
    async def _ev(chain, cap):
        val = mapping.get(chain)
        if callable(val):
            return await val(chain, cap)
        return val if val is not None else _chain_res(chain, skipped="no_operator_configured_rpc")
    return _ev


# ── Coverage: all six chains included AND evaluated ─────────────────────────
def test_all_six_chains_in_universe():
    race = SixChainOpportunityRace(networks=SIX_CHAINS)
    assert race.networks() == SIX_CHAINS
    assert len(race.networks()) == 6


def test_all_six_chains_evaluated():
    mapping = {c: _chain_res(c, rows=[_row()]) for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert set(result.per_chain.keys()) == set(SIX_CHAINS)
    assert all(r.status == STATUS_EVALUATED for r in result.per_chain.values())


def test_no_implicit_cap_truncates_universe():
    # 6 chains in, 6 chains out — nothing silently dropped.
    mapping = {c: _chain_res(c, rows=[_row(), _row()]) for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS, max_chain_concurrency=2,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert len(result.per_chain) == 6
    assert result.candidates_seen == 12


# ── Isolation: one chain cannot suppress the others ─────────────────────────
def test_chain_exception_isolated():
    async def _boom(chain, cap):
        raise RuntimeError("rpc exploded")
    mapping = {c: _chain_res(c, rows=[_row()]) for c in SIX_CHAINS}
    mapping["arbitrum"] = _boom
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.per_chain["arbitrum"].status == STATUS_ERROR
    assert "rpc exploded" in (result.per_chain["arbitrum"].last_error or "")
    # The other five still evaluated.
    for c in SIX_CHAINS:
        if c != "arbitrum":
            assert result.per_chain[c].status == STATUS_EVALUATED


def test_rpc_timeout_isolated():
    async def _hang(chain, cap):
        await asyncio.sleep(5)
        return _chain_res(chain, rows=[_row()])
    mapping = {c: _chain_res(c, rows=[_row()]) for c in SIX_CHAINS}
    mapping["polygon"] = _hang
    race = SixChainOpportunityRace(networks=SIX_CHAINS, per_chain_timeout_s=0.2,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.per_chain["polygon"].status == STATUS_TIMEOUT
    for c in SIX_CHAINS:
        if c != "polygon":
            assert result.per_chain[c].status == STATUS_EVALUATED


# ── Economics: fail-closed / net semantics ───────────────────────────────────
def test_negative_economics_not_positive():
    mapping = {c: _chain_res(c, rows=[_row()],
                             candidates=[_cand(c, -1.5)]) for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.positive_net_count == 0
    assert result.operator_action_required is False
    assert result.best_candidate is None


def test_zero_net_is_not_positive():
    mapping = {c: _chain_res(c, candidates=[_cand(c, 0.0)]) for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.positive_net_count == 0


def test_missing_economics_fail_closed():
    # econ flag False AND net None → never positive.
    mapping = {c: _chain_res(c, candidates=[_cand(c, None, econ=False)])
               for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.positive_net_count == 0
    assert result.economically_valid == 0


def test_econ_valid_flag_without_positive_net_not_surfaced():
    # ECONOMICALLY_VALID True but net not > 0 → not surfaced.
    mapping = {c: _chain_res(c, candidates=[_cand(c, -0.01, econ=True)])
               for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.economically_valid == 6
    assert result.positive_net_count == 0


def test_positive_net_candidate_surfaced():
    mapping = {c: _chain_res(c, rows=[_row()]) for c in SIX_CHAINS}
    mapping["optimism"] = _chain_res("optimism", rows=[_row()],
                                     candidates=[_cand("optimism", 12.34)])
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.positive_net_count == 1
    assert result.operator_action_required is True
    assert result.best_candidate["chain"] == "optimism"
    assert result.best_candidate["all_in_net_usd"] == 12.34
    assert result.best_candidate["operator_action_required"] is True


def test_stale_quote_rejected():
    # positive net but quote block far behind head → stale → not surfaced.
    mapping = {c: _chain_res(c, block=1000) for c in SIX_CHAINS}
    mapping["ethereum"] = _chain_res("ethereum", block=1000,
                                     candidates=[_cand("ethereum", 9.9, block=100)])
    race = SixChainOpportunityRace(networks=SIX_CHAINS, max_block_lag=5,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.positive_net_count == 0
    assert result.best_candidate is None


def test_fresh_quote_within_lag_surfaced():
    mapping = {c: _chain_res(c, block=1000) for c in SIX_CHAINS}
    mapping["ethereum"] = _chain_res("ethereum", block=1000,
                                     candidates=[_cand("ethereum", 9.9, block=998)])
    race = SixChainOpportunityRace(networks=SIX_CHAINS, max_block_lag=5,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert result.positive_net_count == 1


# ── Deterministic best-candidate selection ──────────────────────────────────
def test_best_candidate_deterministic():
    mapping = {
        "base": _chain_res("base", candidates=[_cand("base", 5.0, eid="b")]),
        "ethereum": _chain_res("ethereum", candidates=[_cand("ethereum", 9.0, eid="e")]),
        "arbitrum": _chain_res("arbitrum", candidates=[_cand("arbitrum", 9.0, eid="a")]),
        "optimism": _chain_res("optimism"),
        "polygon": _chain_res("polygon"),
        "bnb": _chain_res("bnb"),
    }
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    r1 = asyncio.run(race.scan_once())
    r2 = asyncio.run(race.scan_once())
    # Highest net = 9.0 tie between arbitrum & ethereum → tie-break by chain asc.
    assert r1.best_candidate["chain"] == "arbitrum"
    assert r1.best_candidate["chain"] == r2.best_candidate["chain"]
    assert r1.positive_net_count == 3


# ── Safety invariants ────────────────────────────────────────────────────────
def test_safety_invariant_always_false():
    for k in ("signing", "broadcast", "auto_execution", "full_live"):
        assert SAFETY_POSTURE[k] is False
    mapping = {c: _chain_res(c, candidates=[_cand(c, 100.0)]) for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    for k in ("signing", "broadcast", "auto_execution", "full_live"):
        assert result.safety_posture[k] is False
    assert result.to_dict()["safety_posture"]["broadcast"] is False


def test_no_execution_symbols_imported():
    import arbicore.runtime.opportunity_race as mod
    for banned in ("LiveSigner", "AutoExecutor", "LimitedLiveBroadcaster",
                   "broadcast_tx", "sign_and_send"):
        assert not hasattr(mod, banned)


# ── Lifecycle + repeated scans ───────────────────────────────────────────────
def test_start_stop_lifecycle():
    async def _run():
        mapping = {c: _chain_res(c, rows=[_row()]) for c in SIX_CHAINS}
        race = SixChainOpportunityRace(networks=SIX_CHAINS, interval_s=1,
                                       chain_evaluator=_fake_evaluator(mapping),
                                       base_evaluator=_fake_evaluator(mapping))
        assert race.status()["state"] == "STOPPED"
        await race.start()
        assert race.status()["state"] == "RUNNING"
        await asyncio.sleep(0.2)
        st = await race.stop()
        assert st["state"] == "STOPPED"
        return race
    race = asyncio.run(_run())
    assert race.status()["scan_count"] >= 1


def test_repeated_scans_accumulate_history():
    mapping = {c: _chain_res(c, rows=[_row()]) for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    asyncio.run(race.scan_once())
    asyncio.run(race.scan_once())
    asyncio.run(race.scan_once())
    assert len(race.history()) == 3
    assert race.status()["scan_count"] == 3


# ── Provenance / evidence preservation ───────────────────────────────────────
def test_evidence_provenance_preserved():
    mapping = {c: _chain_res(c) for c in SIX_CHAINS}
    mapping["polygon"] = _chain_res(
        "polygon", candidates=[_cand("polygon", 3.0, eid="cand:polygon:evi42")])
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert "cand:polygon:evi42" in result.to_dict()["evidence_ids"]
    assert result.best_candidate["evidence_id"] == "cand:polygon:evi42"


# ── Skipped chains reported honestly (fail-closed, not fabricated) ───────────
def test_unconfigured_chain_skipped_not_positive():
    mapping = {c: _chain_res(c, skipped="no_operator_configured_rpc")
               for c in SIX_CHAINS}
    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_fake_evaluator(mapping),
                                   base_evaluator=_fake_evaluator(mapping))
    result = asyncio.run(race.scan_once())
    assert all(r.status == STATUS_SKIPPED for r in result.per_chain.values())
    assert result.positive_net_count == 0
    assert result.operator_action_required is False


# ── Base canonical path is composed via injection, not rewritten ─────────────
def test_base_uses_injected_evaluator():
    seen = {}

    async def _base_ev(chain, cap):
        seen["base_called"] = chain
        return _chain_res(chain, skipped="base_canonical_use_m3_0_real_candidate_scan")

    async def _other_ev(chain, cap):
        return _chain_res(chain, rows=[_row()])

    race = SixChainOpportunityRace(networks=SIX_CHAINS,
                                   chain_evaluator=_other_ev,
                                   base_evaluator=_base_ev)
    result = asyncio.run(race.scan_once())
    assert seen.get("base_called") == "base"
    assert result.per_chain["base"].status == STATUS_SKIPPED
    assert result.per_chain["base"].reason == "base_canonical_use_m3_0_real_candidate_scan"


def test_default_networks_are_six_real_chains():
    # Without an override, the universe comes from supported_networks().
    race = SixChainOpportunityRace()
    nets = race.networks()
    assert nets[0] == "base"
    for c in ["ethereum", "arbitrum", "optimism", "polygon", "bnb"]:
        assert c in nets


# ── E1/E2 executor capability behaviour unchanged ────────────────────────────
def test_e1_e2_capability_unchanged():
    from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
        SUPPORTED_DEXES, SUPPORTED_FLASH_PROVIDERS)
    from arbicore.execution.settlement_dispatcher import evaluate_settlement, Verdict
    assert set(SUPPORTED_DEXES) == {"uniswap_v3"}
    assert set(SUPPORTED_FLASH_PROVIDERS) == {"balancer_v2", "aave_v3"}
    d = evaluate_settlement(flash_provider="balancer_v2",
                            swap_venues=["uniswap_v3"], chain="base",
                            executor_deployed=True)
    assert d.verdict is Verdict.EXECUTABLE
