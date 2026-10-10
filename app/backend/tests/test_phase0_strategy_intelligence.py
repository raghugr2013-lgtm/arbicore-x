"""Phase 0 strategy intelligence + economics observability.

Classifies stored m2.3 bundles and discovery candidates. Does not recompute
economics and does not change Gate 7 / Gate 8.
"""
from __future__ import annotations

import asyncio
import copy
import inspect
import json

from arbicore.discovery import base_pool_registry as reg
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.discovery import DiscoveryCandidate, VerifiedOutcome
from arbicore.models.enums import OpportunityType
from arbicore.observability import observe_strategy_intelligence
from arbicore.observability import economics_observation as econ_mod
from arbicore.observability import record as record_mod
from arbicore.observability import taxonomy as tax_mod
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
from arbicore.scanners.flash_loan_arbitrage.economics import FlashLoanEconomicsAssessor
from arbicore.scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit,
    FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)
from arbicore.scanners.flash_loan_arbitrage.verifier import FlashLoanOpportunityVerifier


def _leg(protocol: str, venue: str, fee_bps: int = 5) -> dict:
    return {
        "venue_id": venue,
        "source_id": f"{protocol}_quoter",
        "dex_protocol": protocol,
        "fee_bps": fee_bps,
        "status": "ok",
        "block_number": 100,
        "depth_usd": 500_000.0,
        "amount_in_wei": 1000,
        "amount_out_wei": 990,
        "token_in": "0x" + "11" * 20,
        "token_out": "0x" + "22" * 20,
    }


def _bundle(
    *,
    path,
    protocols,
    pools=None,
    hop_count=None,
    chain="base",
    provider="balancer_v2",
    economics=None,
    fees=None,
    gas=None,
    include_protocols=True,
    include_dex_on_legs=True,
    venues=None,
):
    hop_count = len(path) - 1 if hop_count is None else hop_count
    pools = list(pools or [f"pool-{i}" for i in range(hop_count)])
    addresses = [f"0x{(i + 1):040x}" for i in range(hop_count)]
    legs = []
    for i in range(hop_count):
        protocol = protocols[i] if i < len(protocols) else protocols[-1]
        venue = venues[i] if venues else f"{protocol}:{chain}:{i}"
        leg = _leg(protocol, venue, fee_bps=5 if i == 0 else 30)
        if not include_dex_on_legs:
            leg.pop("dex_protocol", None)
        legs.append(leg)
    route = {
        "route_pools": pools,
        "route_pool_addresses": addresses,
        "cycle_token_path": list(path),
        "hop_count": hop_count,
    }
    if include_protocols:
        route["route_dex_protocols"] = list(protocols)
    return {
        "bundle_id": "flarb:phase0:1",
        "schema_version": "m2.3",
        "source_component": "flash_loan_arb_verifier",
        "created_at": "2026-10-04T09:09:29.105057Z",
        "chain": chain,
        "flash_loan_provider": provider,
        "outcome_tag": (
            "denied:gate_rejection:gate_7:atomic_profit $-83.69 < floor $25.00"
        ),
        "route": route,
        "quotes": {
            "hop_legs": legs,
            "gross_profit_pct": -0.335908,
            "quote_notional_usd": 10000.0,
        },
        "economics": economics if economics is not None else {
            "gross_spread_pct": -0.335908,
            "atomic_profit_usd": -83.691492,
            "expected_net_after_costs_usd": -83.691492,
            "borrow_amount_usd": 10000.0,
        },
        "fees": fees if fees is not None else {
            "flash_loan_fee_bps": 0,
            "flash_loan_fee_usd": 0.0,
            "total_swap_fee_pct": 0.35,
            "total_slippage_pct": 0.0,
        },
        "gas": gas if gas is not None else {
            "tx_gas_units": 167820,
            "gas_cost_usd": 0.100692,
        },
        "gates": {
            "gate_7": {
                "status": "FAIL",
                "reason": "atomic_profit $-83.69 < floor $25.00",
            },
        },
        "block_context": {
            "verified_at_ts": 1791104969.105057,
            "block_number": 1,
        },
    }


def _family(bundle, candidate=None):
    recorded = observe_strategy_intelligence(bundle, candidate)
    return recorded["strategy"]["primary_family"], recorded


def test_fixture_a_dex_to_dex():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "sushiswap_v3"],
    )
    primary, rec = _family(bundle)
    assert primary == "DEX_TO_DEX"
    assert rec["strategy"]["secondary_tags"] == ["CROSS_POOL", "CROSS_PROTOCOL"]
    assert rec["strategy"]["classification_state"] == "COMPLETE"
    assert rec["strategy"]["confidence"] == "HIGH"
    assert rec["strategy"]["strategy_completeness"] == "FULLY_CLASSIFIED"
    assert "distinct per-leg protocols" in " ".join(rec["strategy"]["evidence"])
    assert rec["economics"]["completeness"] == "PARTIAL"
    assert rec["economics"]["fields"]["true_net_usd"]["value"] == -83.691492
    assert rec["economics"]["fields"]["decision_net_usd"]["value"] == -83.69
    assert rec["economics"]["fields"]["flash_loan_fee_usd"]["value"] == 0.0
    assert rec["economics"]["fields"]["flash_loan_fee_pct"]["value"] is None
    assert rec["economics"]["fields"]["flash_loan_fee_pct"]["status"] == "AVAILABLE_NOT_PERSISTED"
    assert len(rec["legs"]) == 2
    assert rec["legs"][0]["protocol"]["value"] == "uniswap_v3"
    assert rec["legs"][1]["protocol"]["value"] == "sushiswap_v3"
    assert "not a route protocol" in " ".join(rec["strategy"]["evidence"])


def test_fixture_b_triangular():
    bundle = _bundle(
        path=["USDC", "WETH", "AERO", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3", "uniswap_v3"],
    )
    primary, rec = _family(bundle)
    assert primary == "TRIANGULAR"
    assert rec["strategy"]["secondary_tags"] == ["CROSS_POOL"]
    assert "CROSS_PROTOCOL" not in rec["strategy"]["secondary_tags"]


def test_fixture_c_multi_hop():
    bundle = _bundle(
        path=["USDC", "WETH", "WBTC", "ARB", "USDC"],
        protocols=["uniswap_v3"] * 4,
    )
    primary, rec = _family(bundle)
    assert primary == "MULTI_HOP"
    assert "MULTI_DEX" not in rec["strategy"]["secondary_tags"]
    assert "CROSS_PROTOCOL" not in rec["strategy"]["secondary_tags"]


def test_fixture_d_multi_dex():
    bundle = _bundle(
        path=["USDC", "WETH", "WBTC", "ARB", "USDC"],
        protocols=["uniswap_v3", "sushiswap_v3", "uniswap_v3", "aerodrome"],
    )
    primary, rec = _family(bundle)
    assert primary == "MULTI_DEX"
    assert rec["strategy"]["secondary_tags"] == [
        "MULTI_HOP", "CROSS_POOL", "CROSS_PROTOCOL",
    ]


def test_fixture_e_cross_pool():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3"],
        venues=["venue-fee-500", "venue-fee-3000"],
        pools=["uniswap_v3:USDC:WETH:500", "uniswap_v3:USDC:WETH:3000"],
    )
    primary, rec = _family(bundle)
    assert primary == "CROSS_POOL"
    assert rec["strategy"]["secondary_tags"] == []
    assert rec["legs"][0]["venue"]["value"] == "venue-fee-500"
    assert rec["legs"][1]["venue"]["value"] == "venue-fee-3000"


def test_fixture_f_cross_protocol():
    bundle = _bundle(
        path=["USDC", "WETH", "AERO", "USDC"],
        protocols=["uniswap_v3", "aerodrome", "uniswap_v3"],
    )
    primary, rec = _family(bundle)
    assert primary == "CROSS_PROTOCOL"
    assert "TRIANGULAR" in rec["strategy"]["secondary_tags"]
    assert "DEX_TO_DEX" not in rec["strategy"]["secondary_tags"]


def test_fixture_g_stablecoin_cross_protocol():
    bundle = _bundle(
        path=["USDC", "USDT", "USDC"],
        protocols=["uniswap_v3", "curve_stable"],
    )
    primary, rec = _family(bundle)
    assert primary == "STABLECOIN_CROSS_PROTOCOL"
    assert "DEX_TO_DEX" in rec["strategy"]["secondary_tags"]
    assert "CROSS_PROTOCOL" in rec["strategy"]["secondary_tags"]


def test_fixture_h_lst_lrt_cross_protocol():
    bundle = _bundle(
        path=["USDC", "WSTETH", "USDC"],
        protocols=["uniswap_v3", "curve_stable"],
    )
    primary, rec = _family(bundle)
    assert primary == "LST_LRT_CROSS_PROTOCOL"
    assert "STABLECOIN_CROSS_PROTOCOL" not in rec["strategy"]["secondary_tags"]
    assert "CROSS_PROTOCOL" in rec["strategy"]["secondary_tags"]


def test_complex_triangular_cross_protocol_and_same_protocol_stays_triangular():
    complex_route = _bundle(
        path=["USDC", "WETH", "AERO", "WETH", "USDC"],
        protocols=["uniswap_v3", "aerodrome", "uniswap_v3", "aerodrome"],
    )
    primary, rec = _family(complex_route)
    assert primary == "COMPLEX_TRIANGULAR_CROSS_PROTOCOL"
    assert "TRIANGULAR" in rec["strategy"]["secondary_tags"]
    assert "MULTI_HOP" not in rec["strategy"]["secondary_tags"]

    same = _bundle(
        path=["USDC", "WETH", "AERO", "WETH", "USDC"],
        protocols=["uniswap_v3"] * 4,
    )
    primary_same, rec_same = _family(same)
    assert primary_same == "TRIANGULAR"
    assert "MULTI_HOP" not in rec_same["strategy"]["secondary_tags"]
    assert any("MULTI_HOP is not assigned" in line for line in rec_same["strategy"]["evidence"])


def test_fixture_i_incomplete_evidence_is_not_forced():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "sushiswap_v3"],
        include_protocols=False,
        include_dex_on_legs=False,
        venues=["uniswap_v3:base", "sushiswap_v3:base"],
    )
    primary, rec = _family(bundle)
    assert primary == "UNCLASSIFIED"
    assert rec["strategy"]["classification_state"] == "INCOMPLETE"
    assert rec["strategy"]["strategy_completeness"] == "PARTIALLY_CLASSIFIED"
    assert rec["strategy"]["secondary_tags"] == []
    assert "CROSS_PROTOCOL" not in rec["strategy"]["secondary_tags"]
    assert any("No family was forced" in line for line in rec["strategy"]["evidence"])
    assert "legs[0].protocol" in rec["strategy"]["unresolved_fields"]


def test_fixture_j_economics_bundle_missing_persisted_fields():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3"],
    )
    del bundle["fees"]
    del bundle["gas"]["tx_gas_units"]
    del bundle["quotes"]["gross_profit_pct"]
    primary, rec = _family(bundle)
    assert primary == "CROSS_POOL"
    assert rec["bundle_presence"] == "PARTIAL_BUNDLE"
    assert rec["economics"]["completeness"] == "PARTIAL"
    assert rec["economics"]["fields"]["atomic_profit_usd"]["value"] == -83.691492
    assert rec["economics"]["fields"]["gross_profit_usd"]["value"] is None
    assert rec["economics"]["fields"]["dex_fee_usd"]["status"] == "unavailable"
    assert rec["economics"]["fields"]["gas_units"]["value"] is None
    assert rec["economics"]["fields"]["mev_penalty"]["status"] == "AVAILABLE_NOT_PERSISTED"
    assert rec["economics"]["fields"]["mev_penalty"]["value"] is None
    assert rec["economics"]["fields"]["mev_adjusted_net_pct"]["value"] is None


def test_fixture_k_no_evidence_bundle():
    rec = observe_strategy_intelligence(None)
    assert rec["bundle_presence"] == "NO_BUNDLE"
    assert rec["evidence_schema_version"] is None
    assert rec["strategy"]["primary_family"] == "UNKNOWN"
    assert rec["strategy"]["classification_state"] == "UNKNOWN"
    assert rec["strategy"]["strategy_completeness"] == "UNKNOWN"
    assert rec["strategy"]["confidence"] == "NONE"
    assert rec["economics"]["completeness"] == "UNAVAILABLE"
    for field in rec["economics"]["fields"].values():
        assert field["value"] is None
        assert field["status"] != "available"
    assert rec["economics"]["fields"]["mev_penalty"]["status"] == "unavailable"
    assert rec["legs"] == []


def test_different_venues_do_not_prove_cross_protocol():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "sushiswap_v3"],
        include_protocols=False,
        include_dex_on_legs=False,
        venues=["uniswap_v3:base", "sushiswap_v3:base"],
        pools=["uniswap_v3:USDC:WETH:500", "sushiswap_v3:USDC:WETH:3000"],
    )
    bundle["route"]["route_pool_addresses"] = ["0x" + "ab" * 20, "0x" + "cd" * 20]
    primary, rec = _family(bundle)
    assert primary == "UNCLASSIFIED"
    blob = json.dumps(rec["strategy"])
    assert "CROSS_PROTOCOL" not in rec["strategy"]["secondary_tags"]
    assert primary != "CROSS_PROTOCOL"
    assert "were not parsed as protocols" in " ".join(rec["strategy"]["evidence"])
    assert "CROSS_PROTOCOL" not in blob or "not proven" in blob

    same = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["Uniswap_V3", "uniswap_v3"],
        venues=["venue-a", "venue-b"],
    )
    primary_same, rec_same = _family(same)
    assert primary_same == "CROSS_POOL"
    assert "CROSS_PROTOCOL" not in rec_same["strategy"]["secondary_tags"]


def test_missing_economics_field_remains_missing_not_zero():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3"],
    )
    del bundle["fees"]["total_slippage_pct"]
    del bundle["gas"]["tx_gas_units"]
    rec = observe_strategy_intelligence(bundle)
    slippage = rec["economics"]["fields"]["slippage_pct"]
    gross_usd = rec["economics"]["fields"]["gross_profit_usd"]
    gas_units = rec["economics"]["fields"]["gas_units"]
    assert slippage["value"] is None and slippage["value"] != 0
    assert slippage["status"] == "unavailable"
    assert gross_usd["value"] is None and gross_usd["status"] == "unavailable"
    assert gas_units["value"] is None and gas_units["status"] == "unavailable"
    # A stored zero is a real zero. The coerced fee bps is not the applied rate.
    stored = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3"],
    )
    kept = observe_strategy_intelligence(stored)
    assert kept["economics"]["fields"]["slippage_pct"]["status"] == "available"
    assert kept["economics"]["fields"]["slippage_pct"]["value"] == 0.0
    assert kept["economics"]["fields"]["flash_loan_fee_usd"]["value"] == 0.0
    assert kept["economics"]["fields"]["flash_loan_fee_pct"]["value"] is None
    assert kept["economics"]["fields"]["flash_loan_fee_bps_stored"]["value"] == 0
    assert "not the applied" in kept["economics"]["fields"]["flash_loan_fee_bps_stored"]["note"].lower() or \
        "Not the applied" in kept["economics"]["fields"]["flash_loan_fee_bps_stored"]["note"]


def test_candidate_without_bundle_uses_persisted_route_and_decision_net():
    candidate = {
        "candidate_id": "7e45d1eea1f28e2ef915",
        "verified_at": "2026-10-04T09:09:29.105057Z",
        "verified_outcome": (
            "denied:gate_rejection:gate_7:atomic_profit $-83.69 < floor $25.00"
        ),
        "hint_metric": {
            "chain": "base",
            "provider": "balancer_v2",
            "borrow_token": "USDC",
            "cycle_token_path": ["USDC", "WETH", "USDC"],
            "hop_count": 2,
            "route_pools": [
                "uniswap_v3:USDC:WETH:500",
                "uniswap_v3:USDC:WETH:3000",
            ],
            "route_dex_protocols": ["uniswap_v3", "uniswap_v3"],
        },
    }
    rec = observe_strategy_intelligence(None, candidate)
    assert rec["bundle_presence"] == "NO_BUNDLE"
    assert rec["strategy"]["primary_family"] == "CROSS_POOL"
    assert rec["strategy"]["classification_state"] == "COMPLETE"
    decision = rec["economics"]["fields"]["decision_net_usd"]
    assert decision["value"] == -83.69
    assert decision["status"] == "available"
    assert decision["provenance_kind"] == "persisted_decision"
    assert decision["timestamp"] == "2026-10-04T09:09:29.105057Z"
    assert rec["economics"]["fields"]["gross_profit_pct"]["value"] is None
    assert rec["economics"]["fields"]["true_net_usd"]["value"] is None
    assert rec["economics"]["completeness"] == "PARTIAL"
    assert rec["economics"]["fields"]["gate_7"]["status"] == "unavailable"


def test_best_stored_shape_reads_numbers_without_recomputing():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3"],
        pools=["uniswap_v3:USDC:WETH:500", "uniswap_v3:USDC:WETH:3000"],
        provider="balancer_v2",
    )
    rec = observe_strategy_intelligence(bundle)
    assert rec["strategy"]["primary_family"] == "CROSS_POOL"
    assert rec["economics"]["fields"]["gross_profit_pct"]["value"] == -0.335908
    assert rec["economics"]["fields"]["true_net_usd"]["value"] == -83.691492
    assert rec["economics"]["fields"]["decision_net_usd"]["value"] == -83.69
    assert rec["economics"]["fields"]["gas_cost_usd"]["value"] == 0.100692
    assert rec["economics"]["fields"]["dex_fee_pct"]["value"] == 0.35
    assert rec["economics"]["fields"]["quote_notional_usd"]["value"] == 10000.0
    # -0.335908% of 10000 is about -33.59, not the stored decision net.
    assert rec["economics"]["fields"]["true_net_usd"]["value"] != round(
        10000.0 * -0.335908 / 100.0, 2
    )
    assert rec["economics"]["fields"]["gate_7"]["value"]["status"] == "FAIL"
    assert rec["economics"]["fields"]["gate_7"]["value"]["floor_usd"] == 25.0
    assert rec["legs"][0]["quote"]["path_symbol_in"]["value"] == "USDC"
    assert rec["legs"][0]["quote"]["fee_bps"]["value"] == 5


def test_observation_is_deterministic_json_and_does_not_mutate():
    bundle = _bundle(
        path=["USDC", "WETH", "AERO", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3", "uniswap_v3"],
    )
    original = copy.deepcopy(bundle)
    first = observe_strategy_intelligence(bundle)
    second = observe_strategy_intelligence(bundle)
    assert first == second
    assert bundle == original
    json.dumps(first)


def test_gross_percent_conflict_is_not_averaged():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3"],
    )
    bundle["economics"]["gross_spread_pct"] = 1.0
    bundle["quotes"]["gross_profit_pct"] = 9.0
    rec = observe_strategy_intelligence(bundle)
    gross = rec["economics"]["fields"]["gross_profit_pct"]
    assert gross["status"] == "unavailable"
    assert gross["value"] is None
    assert "gross_profit_pct" in rec["economics"]["unresolved_fields"]


def test_observer_does_not_invoke_the_economics_formula():
    blob = (
        inspect.getsource(tax_mod)
        + inspect.getsource(econ_mod)
        + inspect.getsource(record_mod)
    )
    assert "aggregate_economics(" not in blob
    assert "min_atomic_profit_usd" not in blob
    assert "100_000" not in blob
    assert "100000" not in blob


def test_gate7_dynamic_and_gate8_thresholds():
    from arbicore.scanners.flash_loan_arbitrage.filter import (
        REPORTING_ATOMIC_PROFIT_FLOOR_USD,
    )
    gate7 = FlashLoanGate7AtomicProfit({})
    # Dynamic floor: sub-$25 positive passes; non-positive rejects.
    assert gate7.evaluate(atomic_profit_usd=-1.0, borrow_amount_usd=10_000.0).passed is False
    assert gate7.evaluate(atomic_profit_usd=24.99, borrow_amount_usd=10_000.0).passed is True
    assert gate7.evaluate(atomic_profit_usd=25.0, borrow_amount_usd=10_000.0).passed is True
    assert REPORTING_ATOMIC_PROFIT_FLOOR_USD == 25.0
    gate8 = FlashLoanGate8LiquidityDepth({})
    assert gate8.evaluate(min_pool_tvl_usd_in_route=99_999.99).passed is False
    assert gate8.evaluate(min_pool_tvl_usd_in_route=100_000.0).passed is True


def test_fully_stored_economics_can_be_complete():
    bundle = _bundle(
        path=["USDC", "WETH", "USDC"],
        protocols=["uniswap_v3", "uniswap_v3"],
    )
    bundle["economics"].update({
        "gross_profit_usd": -33.59,
        "mev_penalty_pct": 0.5,
        "mev_adjusted_net_pct": -0.8369,
        "true_net_pct": -0.8369,
        "flash_loan_fee_pct": 0.0,
    })
    bundle["fees"].update({
        "total_swap_fee_usd": 35.0,
        "total_slippage_usd": 0.0,
        "flash_loan_fee_pct": 0.0,
    })
    bundle["gas"]["gas_price"] = 1_000_000_000
    bundle["outcome_tag"] = (
        "denied:gate_rejection:gate_7:atomic_profit $-83.69 < floor $25.00"
    )
    rec = observe_strategy_intelligence(bundle)
    assert rec["economics"]["completeness"] == "COMPLETE"
    assert rec["economics"]["fields"]["gross_profit_usd"]["value"] == -33.59
    assert rec["economics"]["fields"]["gas_price"]["value"] == 1_000_000_000
    assert rec["economics"]["fields"]["slippage_usd"]["value"] == 0.0
    assert rec["economics"]["calculator_version"] is None


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _real_pool_ids():
    ids = [p.canonical_id for p in reg.get_canonical_pools()
           if p.address_resolution == reg.DETERMINISTIC_VERIFIED
           and p.dex == "uniswap_v3"
           and {"WETH", "USDC"} == {p.token0_symbol, p.token1_symbol}]
    return ids[:2]


def test_real_m23_verifier_bundle_is_observed_not_recomputed():
    pools = _real_pool_ids()
    assert len(pools) >= 2

    async def _qp(_hm, _borrow):
        legs = [{
            "venue_id": "uniswap_v3:base",
            "source_id": "uniswap_v3_quoter_base",
            "fee_bps": 5,
            "depth_usd": 500_000.0,
            "dex_protocol": "uniswap_v3",
        } for _ in range(2)]
        return {
            "hop_legs": legs,
            "gross_profit_pct": 3.0,
            "tx_gas_units": 250_000,
            "min_pool_tvl_usd_in_route": 500_000.0,
            "tvl_provenance": "onchain_reserves",
            "route_quote_status": "ok",
            "verified_at_ts": 123.0,
            "quote_block": 999,
        }

    captured = []

    async def sink(bundle):
        captured.append(bundle)

    verifier = FlashLoanOpportunityVerifier(
        quote_provider=_qp,
        economics_assessor=FlashLoanEconomicsAssessor(
            roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05),
            default_borrow_amount_usd=10_000.0,
        ),
        mev_scorer=MevRiskScorer(),
        gate_7=FlashLoanGate7AtomicProfit({}),
        gate_8=FlashLoanGate8LiquidityDepth({}),
        gate_9=FlashLoanGate9FlashLoanMev({}),
        default_borrow_amount_usd=10_000.0,
        evidence_sink=sink,
    )
    candidate = DiscoveryCandidate(
        candidate_id="cand-m23",
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source="test_source",
        subject_id="WETH-USDC",
        asset="WETH",
        hint_metric={
            "chain": "base",
            "provider": "balancer_v2",
            "borrow_token": "WETH",
            "borrow_amount_usd": 10_000.0,
            "route_pools": pools,
            "cycle_token_path": ["WETH", "USDC", "WETH"],
            "route_dex_protocols": ["uniswap_v3", "uniswap_v3"],
            "hop_count": 2,
        },
    )
    _opp, outcome = _run(verifier.verify(candidate))
    assert outcome.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    assert len(captured) == 1
    bundle = captured[0]
    assert bundle["schema_version"] == "m2.3"
    frozen = copy.deepcopy(bundle)
    rec = observe_strategy_intelligence(bundle)
    assert bundle == frozen
    assert rec["evidence_schema_version"] == "m2.3"
    assert rec["bundle_presence"] == "COMPLETE_BUNDLE"
    assert rec["strategy"]["primary_family"] == "CROSS_POOL"
    assert "CROSS_PROTOCOL" not in rec["strategy"]["secondary_tags"]
    atomic = rec["economics"]["fields"]["atomic_profit_usd"]
    assert atomic["status"] == "available"
    assert atomic["value"] == bundle["economics"]["atomic_profit_usd"]
    assert atomic["source"] == "verifier_bundle.economics.atomic_profit_usd"
    assert rec["economics"]["fields"]["gross_profit_usd"]["value"] is None
    assert rec["economics"]["fields"]["mev_penalty"]["status"] == "AVAILABLE_NOT_PERSISTED"
    assert rec["economics"]["fields"]["mev_penalty"]["value"] is None
    assert rec["economics"]["fields"]["gate_7"]["value"]["status"] == "PASS"
    assert rec["economics"]["fields"]["quote_notional_usd"]["status"] == "unavailable"
    assert rec["legs"][0]["protocol"]["value"] == "uniswap_v3"
    assert rec["legs"][0]["chain"]["value"] == "base"
    assert rec["legs"][0]["pool"]["status"] == "available"
    assert rec["economics"]["calculator_version"] is None
