"""D-5.1 — BridgeEconomicsAssessor tests."""
from __future__ import annotations

from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.enums import MevRiskLevel
from arbicore.scanners.cross_chain_arbitrage.economics import (
    BridgeEconomicsAssessor,
)


def _build():
    return BridgeEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=2, winsorize_pct=0.05),
        default_notional_usd=1000.0,
    )


def test_assess_returns_economics_with_costs():
    a = _build()
    out = a.assess(
        bridge="lifi", source_chain="ethereum", destination_chain="arbitrum",
        primary_venue_id="lifi:ethereum:USDC",
        secondary_venue_id="lifi:arbitrum:USDC",
        primary_fee_bps=5, secondary_fee_bps=5,
        slippage_bridge_pct=0.5, total_bridge_fee_usd=2.0,
        signal_categories=["lifi"], real_outcomes=[], synthetic_outcomes=None,
        notional_usd=1000.0, mev_risk_level=MevRiskLevel.LOW,
    )
    assert out.bridge == "lifi"
    assert out.notional_usd == 1000.0
    assert out.total_bridge_fee_usd == 2.0
    assert out.economics.total_slippage_pct >= 0.0
    assert out.gas_source_chain_usd > 0.0
    assert out.gas_destination_chain_usd > 0.0


def test_to_metadata_emits_required_keys():
    a = _build()
    out = a.assess(
        bridge="stargate", source_chain="base",
        destination_chain="optimism",
        primary_venue_id="x", secondary_venue_id="y",
        primary_fee_bps=10, secondary_fee_bps=10,
        slippage_bridge_pct=0.2, total_bridge_fee_usd=0.5,
        signal_categories=[], real_outcomes=[],
    )
    md = out.to_metadata()
    for k in ("source_chain", "destination_chain", "bridge_provider",
              "total_bridge_fee_usd", "total_round_trip_cost_pct",
              "gas_source_chain_usd", "gas_destination_chain_usd"):
        assert k in md


def test_uses_override_gas_when_provided():
    a = _build()
    out = a.assess(
        bridge="lifi", source_chain="ethereum",
        destination_chain="arbitrum",
        primary_venue_id="x", secondary_venue_id="y",
        primary_fee_bps=5, secondary_fee_bps=5,
        slippage_bridge_pct=0.0, total_bridge_fee_usd=0.0,
        signal_categories=[], real_outcomes=[],
        gas_source_chain_usd=12.34, gas_destination_chain_usd=0.42,
    )
    assert out.gas_source_chain_usd == 12.34
    assert out.gas_destination_chain_usd == 0.42


def test_mev_penalty_propagates_via_aggregate():
    a = _build()
    low = a.assess(
        bridge="lifi", source_chain="ethereum",
        destination_chain="arbitrum",
        primary_venue_id="x", secondary_venue_id="y",
        primary_fee_bps=5, secondary_fee_bps=5,
        slippage_bridge_pct=0.0, total_bridge_fee_usd=0.0,
        signal_categories=[], real_outcomes=[],
        mev_risk_level=MevRiskLevel.LOW,
    )
    hi = a.assess(
        bridge="lifi", source_chain="ethereum",
        destination_chain="arbitrum",
        primary_venue_id="x", secondary_venue_id="y",
        primary_fee_bps=5, secondary_fee_bps=5,
        slippage_bridge_pct=0.0, total_bridge_fee_usd=0.0,
        signal_categories=[], real_outcomes=[],
        mev_risk_level=MevRiskLevel.HIGH,
    )
    assert hi.economics.mev_penalty_pct >= low.economics.mev_penalty_pct


def test_inv2_economics_does_not_import_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.economics as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text


def test_rationale_lines_present():
    a = _build()
    out = a.assess(
        bridge="lifi", source_chain="ethereum",
        destination_chain="base",
        primary_venue_id="x", secondary_venue_id="y",
        primary_fee_bps=5, secondary_fee_bps=5,
        slippage_bridge_pct=0.3, total_bridge_fee_usd=1.0,
        signal_categories=[], real_outcomes=[],
    )
    assert out.rationale
    assert any("gas" in r for r in out.rationale)
