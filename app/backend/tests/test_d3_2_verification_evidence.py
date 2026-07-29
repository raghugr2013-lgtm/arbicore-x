"""Tests for D-3.2 — universal VerificationEvidence substrate.

Verifies the protocol-agnostic vocabulary + builder consumed by every
opportunity family's verifier (D-3 / D-4 / D-5 / D-6).

Covers:
  - EvidenceLegRole vocabulary spans all planned families
  - LegEvidence + VerificationEvidence shape
  - derive_provenance picks the MIN-trust leg classification
  - DEAD / CONTAMINATED leg → ValueError (verifier translates to DENIED)
  - build_canonical_from_evidence is opportunity-type-agnostic:
      * works for DEX_ARBITRAGE, FUNDING_ARBITRAGE, LAUNCH_ARBITRAGE,
        CROSS_CHAIN_ARBITRAGE, FLASH_LOAN_ARBITRAGE
  - Metadata trail records candidate_id + leg source_ids (INV-3 audit)
  - INV-1/INV-2 not violated (module doesn't import EmissionBus, doesn't
    consume DiscoveryCandidate at all)
"""
from __future__ import annotations

import ast
import inspect

import pytest

from arbicore.scanners.verification_evidence import (
    EvidenceLegRole, LegEvidence, VerificationEvidence,
    derive_provenance, build_canonical_from_evidence,
)
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.enums import (
    DataProvenance, OpportunityStatus, OpportunityType,
)


# ----- vocabulary ----------------------------------------------------------

def test_leg_role_vocabulary_covers_planned_families():
    """Vocabulary must span D-3/D-4/D-5/D-6 use cases."""
    must_have = {
        EvidenceLegRole.BUY, EvidenceLegRole.SELL,           # D-3 / CEX arb
        EvidenceLegRole.LONG, EvidenceLegRole.SHORT,         # D-2 funding
        EvidenceLegRole.BRIDGE_IN, EvidenceLegRole.BRIDGE_OUT,   # D-5
        EvidenceLegRole.LAUNCH_PRIMARY, EvidenceLegRole.LAUNCH_SECONDARY,  # D-4
        EvidenceLegRole.BORROW, EvidenceLegRole.REPAY,
        EvidenceLegRole.HOP,                                 # D-6
    }
    assert must_have.issubset(EvidenceLegRole.KNOWN)


# ----- derive_provenance ---------------------------------------------------

def _leg(role, source_id, **kw):
    return LegEvidence(leg_role=role, venue_id=f"venue:{source_id}",
                       source_id=source_id, **kw)


def test_derive_provenance_picks_min_trust():
    """REAL + SIMULATED legs → SIMULATED (the weaker)."""
    legs = [
        _leg(EvidenceLegRole.BUY, "uniswap_v3_quoter_ethereum", price=2000.0),
        _leg(EvidenceLegRole.SELL, "simulated", price=2010.0),  # SIMULATED
    ]
    assert derive_provenance(legs) == DataProvenance.SIMULATED


def test_derive_provenance_all_real_returns_real():
    legs = [
        _leg(EvidenceLegRole.BUY, "uniswap_v3_quoter_ethereum", price=2000.0),
        _leg(EvidenceLegRole.SELL, "pancake_v3_quoter_bnb", price=2010.0),
    ]
    assert derive_provenance(legs) == DataProvenance.REAL


def test_derive_provenance_contaminated_raises():
    """`1inch` is CONTAMINATED in SOURCE_REGISTRY."""
    legs = [
        _leg(EvidenceLegRole.BUY, "uniswap_v3_quoter_ethereum", price=2000.0),
        _leg(EvidenceLegRole.SELL, "oneinch", price=2050.0),
    ]
    with pytest.raises(ValueError, match="CONTAMINATED"):
        derive_provenance(legs)


def test_derive_provenance_dead_raises():
    legs = [
        _leg(EvidenceLegRole.BUY, "uniswap_v3_quoter_ethereum", price=2000.0),
        _leg(EvidenceLegRole.SELL, "sushiswap", price=2050.0),  # DEAD
    ]
    with pytest.raises(ValueError, match="DEAD"):
        derive_provenance(legs)


def test_derive_provenance_empty_raises():
    with pytest.raises(ValueError):
        derive_provenance([])


# ----- build_canonical_from_evidence: protocol-agnostic --------------------

def _dex_evidence():
    return VerificationEvidence(
        verifier_id="dex_quote_verifier",
        candidate_id="cand_xyz",
        discovery_source="venue_dex_pool:uniswap_v3:ethereum",
        subject_id="WETH/USDC@ethereum",
        asset="WETH",
        chain="ethereum",
        legs=[
            _leg(EvidenceLegRole.BUY, "uniswap_v3_quoter_ethereum",
                 price=2000.0, size_usd=1000.0, depth_usd=10_000_000.0,
                 chain="ethereum"),
            _leg(EvidenceLegRole.SELL, "pancake_v3_quoter_bnb",
                 price=2020.0, size_usd=1000.0, depth_usd=8_000_000.0,
                 chain="ethereum"),
        ],
        gross_spread_pct=1.0,
        notional_usd=1000.0,
    )


def test_builder_dex_arb_happy_path():
    ev = _dex_evidence()
    opp = build_canonical_from_evidence(
        ev,
        opportunity_type=OpportunityType.DEX_ARBITRAGE,
        opportunity_id="opp_test",
    )
    assert isinstance(opp, CanonicalOpportunity)
    assert opp.opportunity_type == OpportunityType.DEX_ARBITRAGE
    assert opp.opportunity_id == "opp_test"
    assert opp.subject_id == "WETH/USDC@ethereum"
    assert opp.asset == "WETH"
    assert opp.chain == "ethereum"
    assert opp.buy_venue == "venue:uniswap_v3_quoter_ethereum"
    assert opp.sell_venue == "venue:pancake_v3_quoter_bnb"
    assert opp.buy_price == 2000.0
    assert opp.sell_price == 2020.0
    assert opp.spread_pct == 1.0
    assert opp.expected_profit_usd == 10.0  # 1000 * 1% = 10
    assert opp.source_data_quality == DataProvenance.REAL   # INV-3
    assert opp.status == OpportunityStatus.CANDIDATE
    # Audit trail
    assert opp.metadata["discovery_candidate_id"] == "cand_xyz"
    assert opp.metadata["verifier_id"] == "dex_quote_verifier"
    assert opp.metadata["leg_count"] == 2
    assert "uniswap_v3_quoter_ethereum" in opp.metadata["leg_source_ids"]
    assert "pancake_v3_quoter_bnb" in opp.metadata["leg_source_ids"]


def test_builder_works_for_funding_arb():
    """LONG/SHORT roles map to buy/sell venue automatically."""
    ev = VerificationEvidence(
        verifier_id="funding_arb_verifier",
        candidate_id="cand_f",
        discovery_source="venue_funding:bybit",
        subject_id="BTCUSDT",
        asset="BTC",
        legs=[
            _leg(EvidenceLegRole.LONG, "bybit_public", price=60000.0),
            _leg(EvidenceLegRole.SHORT, "okx_public", price=60100.0),
        ],
        gross_spread_pct=0.1,
        notional_usd=1000.0,
    )
    opp = build_canonical_from_evidence(
        ev, opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        opportunity_id="opp_funding",
    )
    assert opp.opportunity_type == OpportunityType.FUNDING_ARBITRAGE
    assert opp.buy_venue == "venue:bybit_public"
    assert opp.sell_venue == "venue:okx_public"


def test_builder_works_for_launch_arb():
    """LAUNCH_PRIMARY/LAUNCH_SECONDARY roles map automatically."""
    ev = VerificationEvidence(
        verifier_id="launch_verifier",
        candidate_id="cand_l", discovery_source="solana_rpc_primary",
        subject_id="SOLANA_TOKEN_MINT_XYZ",
        asset="XYZ",
        legs=[
            _leg(EvidenceLegRole.LAUNCH_PRIMARY, "raydium_quoter_solana",
                 price=0.10),
            _leg(EvidenceLegRole.LAUNCH_SECONDARY, "raydium_quoter_solana",
                 price=0.15),
        ],
        gross_spread_pct=50.0, notional_usd=1000.0,
    )
    opp = build_canonical_from_evidence(
        ev, opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        opportunity_id="opp_launch",
    )
    assert opp.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE
    assert opp.buy_venue == "venue:raydium_quoter_solana"
    assert opp.sell_venue == "venue:raydium_quoter_solana"


def test_builder_works_for_cross_chain():
    ev = VerificationEvidence(
        verifier_id="cross_chain_verifier",
        candidate_id="cand_x", discovery_source="bridge_intel",
        subject_id="USDC@ethereum->arbitrum",
        asset="USDC",
        legs=[
            _leg(EvidenceLegRole.BRIDGE_OUT, "uniswap_v3_quoter_ethereum",
                 price=1.0),
            _leg(EvidenceLegRole.BRIDGE_IN, "uniswap_v3_quoter_arbitrum",
                 price=1.002),
        ],
        gross_spread_pct=0.2, notional_usd=1000.0,
    )
    opp = build_canonical_from_evidence(
        ev, opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        opportunity_id="opp_xchain",
    )
    assert opp.buy_venue == "venue:uniswap_v3_quoter_ethereum"
    assert opp.sell_venue == "venue:uniswap_v3_quoter_arbitrum"


def test_builder_works_for_flash_loan():
    """Flash-loan: BORROW + ordered HOP legs + REPAY → buy/sell override."""
    ev = VerificationEvidence(
        verifier_id="flash_loan_verifier",
        candidate_id="cand_fl", discovery_source="cycle_miner",
        subject_id="USDC->WETH->WBTC->USDC@ethereum",
        asset="USDC",
        legs=[
            _leg(EvidenceLegRole.BORROW, "uniswap_v3_quoter_ethereum",
                 price=1.0),
            _leg(EvidenceLegRole.HOP, "uniswap_v3_quoter_ethereum", price=2000.0),
            _leg(EvidenceLegRole.HOP, "uniswap_v3_quoter_ethereum", price=30.0),
            _leg(EvidenceLegRole.REPAY, "uniswap_v3_quoter_ethereum",
                 price=1.005),
        ],
        gross_spread_pct=0.5, notional_usd=10_000.0,
    )
    opp = build_canonical_from_evidence(
        ev, opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        opportunity_id="opp_fl",
        buy_venue_override="aave_v3:ethereum",
        sell_venue_override="aave_v3:ethereum",
    )
    assert opp.opportunity_type == OpportunityType.FLASH_LOAN_ARBITRAGE
    assert opp.buy_venue == "aave_v3:ethereum"
    assert opp.sell_venue == "aave_v3:ethereum"
    assert opp.metadata["leg_count"] == 4
    assert opp.metadata["leg_roles"] == [
        "borrow", "hop", "hop", "repay",
    ]


def test_builder_propagates_inv3_provenance():
    """SIMULATED leg → opp.source_data_quality = SIMULATED."""
    ev = _dex_evidence()
    ev.legs[1].source_id = "simulated"  # SIMULATED
    opp = build_canonical_from_evidence(
        ev, opportunity_type=OpportunityType.DEX_ARBITRAGE,
        opportunity_id="opp_inv3",
    )
    assert opp.source_data_quality == DataProvenance.SIMULATED


def test_builder_refuses_contaminated():
    ev = _dex_evidence()
    ev.legs[1].source_id = "oneinch"
    with pytest.raises(ValueError):
        build_canonical_from_evidence(
            ev, opportunity_type=OpportunityType.DEX_ARBITRAGE,
            opportunity_id="opp_bad",
        )


# ----- INV-1 / INV-2 module-level checks -----------------------------------

def test_inv1_module_does_not_consume_discovery_candidate():
    """The universal substrate must not see DiscoveryCandidate."""
    import arbicore.scanners.verification_evidence as mod
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            assert "DiscoveryCandidate" not in (
                (n.name for n in node.names) if node.names else []
            )
        if isinstance(node, ast.Name) and node.id == "DiscoveryCandidate":
            raise AssertionError(
                "verification_evidence must not reference DiscoveryCandidate"
            )


def test_inv2_module_does_not_call_emission_bus():
    import arbicore.scanners.verification_evidence as mod
    tree = ast.parse(inspect.getsource(mod))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            raise AssertionError("verification_evidence imports EmissionBus")
        if isinstance(node, ast.Attribute) and node.attr == "emit":
            raise AssertionError("verification_evidence uses .emit attribute")
