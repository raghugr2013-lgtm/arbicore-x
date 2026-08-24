"""M2.3 — auditable evidence for EVERY verified candidate (CONFIRMED + DENIED),
with explicit per-gate outcomes (offline, deterministic).

Uses the REAL economics assessor + REAL Gates 7/8/9 + REAL MevRiskScorer with a
fake (in-process) quote provider double. No RPC, no broadcast.
"""
from __future__ import annotations

import asyncio

from arbicore.discovery import base_pool_registry as reg
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
from arbicore.scanners.flash_loan_arbitrage.economics import FlashLoanEconomicsAssessor
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


def _hm(**over):
    hm = {
        "chain": "base", "provider": "balancer_v2", "borrow_token": "WETH",
        "borrow_amount_usd": 10_000.0,
        "route_pools": _real_pool_ids(),
        "cycle_token_path": ["WETH", "USDC", "WETH"],
        "route_dex_protocols": ["uniswap_v3", "uniswap_v3"], "hop_count": 2,
    }
    hm.update(over)
    return hm


def _facts(*, gross_pct, min_tvl):
    legs = [{"venue_id": "uniswap_v3:base", "source_id": "uniswap_v3_quoter_base",
             "fee_bps": 5, "depth_usd": min_tvl, "dex_protocol": "uniswap_v3"}
            for _ in range(2)]
    return {"hop_legs": legs, "gross_profit_pct": gross_pct,
            "tx_gas_units": 250_000, "min_pool_tvl_usd_in_route": min_tvl,
            "tvl_provenance": "onchain_reserves", "route_quote_status": "ok",
            "verified_at_ts": 123.0}


def _mk_verifier(facts_or_none, *, sink=None, shadow=None):
    async def _qp(hm, borrow):
        return facts_or_none

    econ = FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05),
        default_borrow_amount_usd=10_000.0)
    return FlashLoanOpportunityVerifier(
        quote_provider=_qp, economics_assessor=econ, mev_scorer=MevRiskScorer(),
        gate_7=FlashLoanGate7AtomicProfit({}),
        gate_8=FlashLoanGate8LiquidityDepth({}),
        gate_9=FlashLoanGate9FlashLoanMev({}),
        default_borrow_amount_usd=10_000.0,
        evidence_sink=sink, shadow_sink=shadow)


def _candidate():
    return DiscoveryCandidate(
        candidate_id="cand-1", opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="test_source", subject_id="WETH-USDC", asset="WETH",
        hint_metric=_hm())


def _verify_capture(facts_or_none):
    captured = []

    async def sink(b):
        captured.append(b)

    v = _mk_verifier(facts_or_none, sink=sink)
    opp, outcome = _run(v.verify(_candidate()))
    assert len(captured) == 1, "exactly one evidence bundle per verified candidate"
    return opp, outcome, captured[0]


def test_confirmed_bundle_all_gates_pass():
    opp, outcome, b = _verify_capture(_facts(gross_pct=3.0, min_tvl=500_000.0))
    assert opp is not None
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    assert b["verification_status"] == "CONFIRMED"
    assert b["gates"]["gate_7"]["status"] == "PASS"
    assert b["gates"]["gate_8"]["status"] == "PASS"
    assert b["gates"]["gate_9"]["status"] == "PASS"
    assert b["opportunity_id"] == opp.opportunity_id
    assert b["broadcast"] is False
    # real audit: pool addresses resolved from the canonical registry
    assert all(a for a in b["route"]["route_pool_addresses"])
    assert b["liquidity"]["min_pool_tvl_usd_in_route"] == 500_000.0
    assert b["economics"]["atomic_profit_usd"] > 0


def test_denied_gate8_records_per_gate_outcomes():
    # profitable (Gate 7 passes) but TVL unverifiable → Gate 8 fails closed,
    # Gate 9 never evaluated.
    opp, outcome, b = _verify_capture(_facts(gross_pct=3.0, min_tvl=0.0))
    assert opp is None
    assert outcome.startswith(VerifiedOutcome.DENIED_GATE_PREFIX + "gate_8")
    assert b["verification_status"] == "DENIED"
    assert b["gates"]["gate_7"]["status"] == "PASS"
    assert b["gates"]["gate_8"]["status"] == "FAIL"
    assert "unverifiable" in (b["gates"]["gate_8"]["reason"] or "")
    assert b["gates"]["gate_9"]["status"] == "NOT_EVALUATED"


def test_denied_gate7_records_per_gate_outcomes():
    # unprofitable → Gate 7 fails; Gates 8 & 9 not evaluated.
    opp, outcome, b = _verify_capture(_facts(gross_pct=-1.0, min_tvl=500_000.0))
    assert opp is None
    assert outcome.startswith(VerifiedOutcome.DENIED_GATE_PREFIX + "gate_7")
    assert b["gates"]["gate_7"]["status"] == "FAIL"
    assert b["gates"]["gate_8"]["status"] == "NOT_EVALUATED"
    assert b["gates"]["gate_9"]["status"] == "NOT_EVALUATED"


def test_denied_venue_unreadable_all_gates_not_evaluated():
    opp, outcome, b = _verify_capture(None)  # quote provider returns None
    assert opp is None
    assert outcome == VerifiedOutcome.DENIED_VENUE_UNREADABLE
    assert b["verification_status"] == "DENIED"
    for g in ("gate_7", "gate_8", "gate_9"):
        assert b["gates"][g]["status"] == "NOT_EVALUATED"
    assert b["broadcast"] is False


def test_evidence_sink_failure_never_breaks_verification():
    async def boom(_b):
        raise RuntimeError("mongo down")

    v = _mk_verifier(_facts(gross_pct=3.0, min_tvl=500_000.0), sink=boom)
    opp, outcome = _run(v.verify(_candidate()))
    assert opp is not None  # verdict unaffected by audit-sink failure
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)


def test_bundle_shape_for_repo_insert():
    _opp, _outcome, b = _verify_capture(_facts(gross_pct=3.0, min_tvl=500_000.0))
    # EvidenceBundlesRepo required identity fields present + Mongo-safe.
    for k in ("bundle_id", "source_component", "source_model_id", "created_at"):
        assert b.get(k)
    import json
    json.dumps(b)  # must be JSON/BSON-serialisable (no ObjectId/datetime objs)
