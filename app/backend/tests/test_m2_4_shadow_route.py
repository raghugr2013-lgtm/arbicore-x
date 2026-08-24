"""M2.4 — CONFIRMED candidates route into the existing paper/SHADOW pipeline;
NEVER broadcast (offline, deterministic).

Wires the verifier's shadow_sink to the REAL OpportunityPipeline (SHADOW: no
mode_repo, no broadcaster) with a fake journal + in-memory paper evidence repo.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from arbicore.discovery import base_pool_registry as reg
from arbicore.execution.pipeline import OpportunityPipeline
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType
from arbicore.paper import InMemoryPaperEvidenceRepository
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
from arbicore.scanners.flash_loan_arbitrage.economics import FlashLoanEconomicsAssessor
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)
from arbicore.scanners.flash_loan_arbitrage.shadow_route import (
    canonical_to_pipeline_opp, route_to_shadow,
)
from arbicore.scanners.flash_loan_arbitrage.verifier import (
    FlashLoanOpportunityVerifier,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeJournal:
    """Minimal in-memory journal double exposing the two methods the
    OpportunityPipeline calls."""

    def __init__(self):
        self.discoveries: List[Dict[str, Any]] = []
        self.events: List[Dict[str, Any]] = []

    async def record_discovery(self, opp, *, mode, scanner_family=None,
                               detail=None):
        self.discoveries.append({"opp": opp, "mode": mode})
        return None

    async def record_event(self, opportunity_id, kind, *, detail=None,
                           patch=None, status=None):
        self.events.append({"id": opportunity_id, "kind": kind,
                            "status": status})
        return None


def _real_pool_ids():
    ids = [p.canonical_id for p in reg.get_canonical_pools()
           if p.address_resolution == reg.DETERMINISTIC_VERIFIED
           and p.dex == "uniswap_v3"
           and {"WETH", "USDC"} == {p.token0_symbol, p.token1_symbol}]
    return ids[:2]


def _facts():
    legs = [{"venue_id": "uniswap_v3:base", "source_id": "uniswap_v3_quoter_base",
             "fee_bps": 5, "depth_usd": 500_000.0, "dex_protocol": "uniswap_v3"}
            for _ in range(2)]
    return {"hop_legs": legs, "gross_profit_pct": 3.0, "tx_gas_units": 250_000,
            "min_pool_tvl_usd_in_route": 500_000.0,
            "tvl_provenance": "onchain_reserves", "route_quote_status": "ok",
            "verified_at_ts": 123.0}


def _candidate():
    hm = {"chain": "base", "provider": "balancer_v2", "borrow_token": "WETH",
          "borrow_amount_usd": 10_000.0, "route_pools": _real_pool_ids(),
          "cycle_token_path": ["WETH", "USDC", "WETH"],
          "route_dex_protocols": ["uniswap_v3", "uniswap_v3"], "hop_count": 2}
    return DiscoveryCandidate(
        candidate_id="cand-shadow-1",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="test_source", subject_id="WETH-USDC", asset="WETH",
        hint_metric=hm)


def _mk_verifier(shadow_sink):
    async def _qp(hm, borrow):
        return _facts()

    econ = FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05),
        default_borrow_amount_usd=10_000.0)
    return FlashLoanOpportunityVerifier(
        quote_provider=_qp, economics_assessor=econ, mev_scorer=MevRiskScorer(),
        gate_7=FlashLoanGate7AtomicProfit({}),
        gate_8=FlashLoanGate8LiquidityDepth({}),
        gate_9=FlashLoanGate9FlashLoanMev({}),
        default_borrow_amount_usd=10_000.0, shadow_sink=shadow_sink)


def test_confirmed_candidate_routes_to_shadow_no_broadcast():
    journal = _FakeJournal()
    evidence_repo = InMemoryPaperEvidenceRepository()
    pipeline = OpportunityPipeline(journal=journal, evidence_repo=evidence_repo)
    results = []

    async def shadow_sink(canonical, evidence):
        results.append(await route_to_shadow(pipeline, canonical, evidence))

    v = _mk_verifier(shadow_sink)
    opp, outcome = _run(v.verify(_candidate()))
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    assert len(results) == 1
    res = results[0]
    # SHADOW mode (no mode_repo) → analysis, never broadcast.
    assert res.mode == "SHADOW"
    assert res.action != "broadcast"
    assert res.action == "shadow"
    # paper evidence persisted for the routed opportunity.
    stored = _run(evidence_repo.get_by_opportunity_id(opp.opportunity_id))
    assert stored is not None
    assert stored.mode == "SHADOW"


def test_pipeline_opp_projection_uses_only_verified_values():
    class _C:
        opportunity_id = "flash_loan_arb:WETH-USDC:123"
        chain = "base"
        expected_profit_usd = 150.0
        confidence_score = 70.0

    ev = {"chain": "base", "borrow_token": "WETH", "input_amount_usd": 10_000.0,
          "flash_loan_provider": "balancer_v2",
          "economics": {"atomic_profit_usd": 142.0},
          "liquidity": {"min_pool_tvl_usd_in_route": 500_000.0},
          "quotes": {"hop_legs": [{"dex_protocol": "uniswap_v3", "fee_bps": 5,
                                   "depth_usd": 500_000.0}]},
          "bundle_id": "flarb:cand:123"}
    opp = canonical_to_pipeline_opp(_C(), ev)
    assert opp["opportunity_type"] == "FLASH_LOAN_ARBITRAGE"
    assert opp["net_profit_usd"] == 142.0
    assert opp["borrow_amount_usd"] == 10_000.0
    assert opp["source_data_quality"] == "REAL"
    assert opp["swap_hops"][0]["pool_liquidity_usd"] == 500_000.0


def test_shadow_route_asserts_no_broadcast_action():
    """route_to_shadow must trip if a pipeline ever returns broadcast."""
    class _BroadcastPipeline:
        async def evaluate(self, opp, *, strategy=None, scanner_family=None):
            class _R:
                action = "broadcast"
                mode = "FULL_LIVE"
            return _R()

    class _C:
        opportunity_id = "x"
        chain = "base"
        expected_profit_usd = 1.0

    raised = False
    try:
        _run(route_to_shadow(_BroadcastPipeline(), _C(), {"chain": "base"}))
    except AssertionError:
        raised = True
    assert raised, "route_to_shadow must reject a broadcast action"
