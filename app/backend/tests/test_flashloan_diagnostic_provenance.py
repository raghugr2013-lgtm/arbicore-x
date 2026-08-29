"""Diagnostic provenance is stamped onto every flash-loan evidence bundle and
is STRICTLY observability — it never influences the verifier verdict.

The provenance mechanism adds, per persisted bundle:
    audit_run_id, scanner_tick_id, worker_id, candidate_id, claim identity

These fields let an operator trace a persisted bundle back to the exact scan
that produced it. This suite proves the bundle carries them, that a failing /
absent provenance source can NEVER break verification or change the verdict,
and that the default (unwired) diagnostics still identify the candidate.

Offline / deterministic. No RPC, no Mongo, no signing, no broadcast.
"""
from __future__ import annotations

import asyncio

from arbicore.discovery import base_pool_registry as reg
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    MevRiskScorer,
)
from arbicore.scanners.flash_loan_arbitrage.economics import (
    FlashLoanEconomicsAssessor,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)
from arbicore.scanners.flash_loan_arbitrage.verifier import (
    FlashLoanOpportunityVerifier,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _real_pool_ids():
    ids = [p.canonical_id for p in reg.get_canonical_pools()
           if p.address_resolution == reg.DETERMINISTIC_VERIFIED
           and p.dex == "uniswap_v3"
           and {"WETH", "USDC"} == {p.token0_symbol, p.token1_symbol}]
    return ids[:2]


def _hm():
    return {"chain": "base", "provider": "balancer_v2", "borrow_token": "WETH",
            "borrow_amount_usd": 10_000.0, "route_pools": _real_pool_ids(),
            "cycle_token_path": ["WETH", "USDC", "WETH"],
            "route_dex_protocols": ["uniswap_v3", "uniswap_v3"], "hop_count": 2}


def _facts(gross_pct=3.0):
    leg = {"venue_id": "uniswap_v3:base", "source_id": "uniswap_v3_quoter_base",
           "fee_bps": 5, "depth_usd": 500_000.0, "dex_protocol": "uniswap_v3"}
    return {"hop_legs": [dict(leg), dict(leg)], "gross_profit_pct": gross_pct,
            "tx_gas_units": 250_000, "min_pool_tvl_usd_in_route": 500_000.0,
            "tvl_provenance": "onchain_reserves", "route_quote_status": "ok",
            "verified_at_ts": 123.0, "quote_block": 999}


def _mk_verifier(*, diag_fn=None, gross_pct=3.0):
    async def _qp(hm, borrow):
        return _facts(gross_pct)

    return FlashLoanOpportunityVerifier(
        quote_provider=_qp,
        economics_assessor=FlashLoanEconomicsAssessor(
            roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05),
            default_borrow_amount_usd=10_000.0),
        mev_scorer=MevRiskScorer(),
        gate_7=FlashLoanGate7AtomicProfit({}),
        gate_8=FlashLoanGate8LiquidityDepth({}),
        gate_9=FlashLoanGate9FlashLoanMev({}),
        default_borrow_amount_usd=10_000.0,
        diagnostic_provenance_fn=diag_fn)


def _candidate():
    return DiscoveryCandidate(
        candidate_id="cand-diag", hint_source="test_source",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id="WETH-USDC", asset="WETH", hint_metric=_hm())


def _verify_capture(v):
    captured = []

    async def sink(b):
        captured.append(b)

    v.evidence_sink = sink
    opp, outcome = _run(v.verify(_candidate()))
    return opp, outcome, captured[0]


def _stamp(cand):
    return {"audit_run_id": "flarb_audit:deadbeef", "scanner_tick_id": 7,
            "worker_id": "flash_loan_arb:abc123",
            "candidate_id": cand.candidate_id, "claimed_by": "worker-x"}


def test_bundle_carries_full_diagnostic_provenance():
    _opp, outcome, b = _verify_capture(_mk_verifier(diag_fn=_stamp))
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    d = b["diagnostics"]
    assert d["audit_run_id"] == "flarb_audit:deadbeef"
    assert d["scanner_tick_id"] == 7
    assert d["worker_id"] == "flash_loan_arb:abc123"
    assert d["candidate_id"] == "cand-diag"
    assert d["claimed_by"] == "worker-x"


def test_default_diagnostics_has_candidate_id_when_unwired():
    _opp, _outcome, b = _verify_capture(_mk_verifier(diag_fn=None))
    assert b["diagnostics"] == {"candidate_id": "cand-diag"}


def test_diagnostics_failure_never_breaks_verify():
    def _boom(_cand):
        raise RuntimeError("provenance source down")

    opp, outcome, b = _verify_capture(_mk_verifier(diag_fn=_boom))
    # Verdict must be unaffected by a raising provenance source.
    assert opp is not None
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    # And the diagnostics block still identifies the candidate.
    assert b["diagnostics"] == {"candidate_id": "cand-diag"}


def test_diagnostics_isolated_from_verdict():
    # The same inputs must yield the identical verdict with or without a
    # diagnostic provenance source wired in.
    _o1, out_with, _b1 = _verify_capture(_mk_verifier(diag_fn=_stamp))
    _o2, out_without, _b2 = _verify_capture(_mk_verifier(diag_fn=None))
    assert out_with.split(":")[0] == out_without.split(":")[0] == "confirmed_canonical"


def test_diagnostics_present_on_denied_bundles_too():
    # A denied candidate still gets a traceable diagnostics block.
    _opp, outcome, b = _verify_capture(_mk_verifier(diag_fn=_stamp, gross_pct=0.0))
    assert not outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    assert b["verification_status"] == "DENIED"
    assert b["diagnostics"]["audit_run_id"] == "flarb_audit:deadbeef"
