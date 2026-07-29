"""D-5.1 — CrossChainOpportunityVerifier tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
)
from arbicore.models.enums import (
    DataProvenance, MevRiskLevel, OpportunityStatus, OpportunityType,
)
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    BridgeRouteCatalog, MevRiskScorer,
)
from arbicore.scanners.cross_chain_arbitrage.chain_liveness import (
    ChainLivenessRegistry,
)
from arbicore.scanners.cross_chain_arbitrage.economics import (
    BridgeEconomicsAssessor,
)
from arbicore.scanners.cross_chain_arbitrage.filter import (
    CrossChainGate7BridgeLiveness, CrossChainGate8ChainLiveness,
    CrossChainGate9CrossChainMev,
)
from arbicore.scanners.cross_chain_arbitrage.verifier import (
    CrossChainOpportunityVerifier,
)


_DEFAULT_GATE = {
    "min_bridge_health_score": 70.0,
    "min_bridge_liveness_score": 75.0,
    "min_bridge_inventory_pct": 30.0,
    "max_inbound_latency_p95_s": 1800.0,
    "max_chain_congestion_score": 80.0,
    "max_chain_finality_s": 1800.0,
    "max_cross_chain_mev_risk_class": "MEDIUM",
}


def _facts(*, src="ethereum", dst="arbitrum", asset="USDC",
            bridge="lifi", source_id="lifi_quote_real",
            out_amount=995.0, slippage_pct=0.3,
            bridge_fee=2.0, p50=180.0, p95=400.0) -> Dict[str, Any]:
    return {
        "bridge": bridge, "source_chain": src, "destination_chain": dst,
        "asset": asset,
        "primary_venue_id": f"{bridge}:{src}:{asset}",
        "secondary_venue_id": f"{bridge}:{dst}:{asset}",
        "source_id": source_id,
        "expected_out_amount": out_amount,
        "expected_out_amount_usd": out_amount,
        "slippage_bridge_pct": slippage_pct,
        "transfer_modelling_confidence": 0.85,
        "primary_fee_bps": 5, "secondary_fee_bps": 5,
        "total_bridge_fee_usd": bridge_fee,
        "inbound_latency_p50_s": p50,
        "inbound_latency_p95_s": p95,
        "verified_at_ts": 1234567890.0,
        "quote_source": "lifi:/quote",
        "notional_usd": 1000.0,
    }


def _candidate(**kw) -> DiscoveryCandidate:
    src = kw.get("src", "ethereum")
    dst = kw.get("dst", "arbitrum")
    asset = kw.get("asset", "USDC")
    bridge = kw.get("bridge", "lifi")
    subject = f"cross_chain:{bridge}:{src}→{dst}:{asset}"
    cid = make_candidate_id(
        hint_source="t",
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        subject_id=subject, asset=asset,
        candidate_venues=[f"{bridge}:{src}", f"{bridge}:{dst}"],
        hint_observed_at=1.0,
    )
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        hint_source="t", hint_observed_at=1.0, subject_id=subject,
        asset=asset,
        candidate_venues=[f"{bridge}:{src}", f"{bridge}:{dst}"],
        hint_metric={"bridge": bridge, "source_chain": src,
                      "destination_chain": dst},
        reason="t",
    )


def _build_verifier(*, provider) -> CrossChainOpportunityVerifier:
    cfg_loader = lambda: {  # noqa: E731
        "chains": {c: {"enabled": False, "gas_token": "ETH"}
                   for c in ("ethereum", "arbitrum", "base",
                              "optimism", "polygon", "solana")},
    }
    return CrossChainOpportunityVerifier(
        transfer_provider=provider,
        economics_assessor=BridgeEconomicsAssessor(
            roi_engine=ROIProbabilityEngine(min_sample=2),
            default_notional_usd=1000.0),
        chain_liveness=ChainLivenessRegistry(config_loader=cfg_loader),
        route_catalog=BridgeRouteCatalog(config_loader=cfg_loader),
        mev_scorer=MevRiskScorer(),
        gate_7=CrossChainGate7BridgeLiveness(thresholds=_DEFAULT_GATE),
        gate_8=CrossChainGate8ChainLiveness(thresholds=_DEFAULT_GATE),
        gate_9=CrossChainGate9CrossChainMev(thresholds=_DEFAULT_GATE),
        default_notional_usd=1000.0,
    )


def test_verifier_returns_none_when_provider_returns_none():
    async def provider(_):
        return None
    v = _build_verifier(provider=provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert tag == VerifiedOutcome.DENIED_VENUE_UNREADABLE


def test_verifier_returns_none_on_provider_exception():
    async def provider(_):
        raise RuntimeError("oops")
    v = _build_verifier(provider=provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert tag.startswith(VerifiedOutcome.DENIED_VENUE_UNREADABLE)


def test_verifier_emits_canonical_on_happy_path():
    async def provider(_):
        return _facts()
    v = _build_verifier(provider=provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is not None
    assert tag.startswith(VerifiedOutcome.CONFIRMED_PREFIX)
    assert out.opportunity_type == OpportunityType.CROSS_CHAIN_ARBITRAGE
    assert out.opportunity_id.startswith("cross_chain_arb:")
    assert out.status == OpportunityStatus.CANDIDATE


def test_inv3_canonical_provenance_is_real_from_legs():
    async def provider(_):
        return _facts(source_id="lifi_quote_real")
    v = _build_verifier(provider=provider)
    out, _ = asyncio.run(v.verify(_candidate()))
    assert out is not None
    assert out.source_data_quality == DataProvenance.REAL


def test_inv3_unknown_source_id_denies():
    async def provider(_):
        return _facts(source_id="some_unknown_source")
    v = _build_verifier(provider=provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert tag == VerifiedOutcome.DENIED_VENUE_UNREADABLE


def test_gate_7_rejects_high_latency():
    async def provider(_):
        return _facts(p95=99999.0)
    v = _build_verifier(provider=provider)
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert "gate_7" in tag


def test_gate_8_rejects_with_loaded_high_congestion():
    async def provider(_):
        return _facts()
    v = _build_verifier(provider=provider)

    async def loader():
        return {"ethereum": {"finality_s": 12, "congestion_score": 99,
                              "gas_token": "ETH"}}
    v.chain_liveness.set_loader(loader)
    asyncio.run(v.chain_liveness.refresh())
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert "gate_8" in tag


def test_gate_9_rejects_extreme_mev():
    async def provider(_):
        return _facts(asset="WETH")
    v = _build_verifier(provider=provider)

    async def loader():
        return {
            "ethereum": {"finality_s": 12, "congestion_score": 99,
                          "gas_token": "ETH"},
            "arbitrum": {"finality_s": 5, "congestion_score": 99,
                          "gas_token": "ETH"},
        }
    v.chain_liveness.set_loader(loader)
    asyncio.run(v.chain_liveness.refresh())
    v.gate_8 = None  # Isolate Gate 9.
    out, tag = asyncio.run(v.verify(_candidate()))
    assert out is None
    assert "gate_9" in tag


def test_category_metadata_keys_complete():
    from arbicore.models.category_metadata import (
        KNOWN_CATEGORY_METADATA_KEYS,
    )
    async def provider(_):
        return _facts()
    v = _build_verifier(provider=provider)
    out, _ = asyncio.run(v.verify(_candidate()))
    assert out is not None
    vocab = KNOWN_CATEGORY_METADATA_KEYS[OpportunityType.CROSS_CHAIN_ARBITRAGE]
    emitted = set(out.category_metadata.keys())
    unknown = emitted - vocab
    assert not unknown, f"verifier produced unknown vocab keys: {unknown}"
    assert {"bridge_route_id", "bridge_corridor_id",
             "total_round_trip_cost_pct",
             "cross_chain_mev_risk_class"} <= emitted


def test_inv2_verifier_module_no_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.verifier as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text
    assert "_bus.emit(" not in text


def test_inv1_verifier_uses_build_canonical_from_evidence():
    import arbicore.scanners.cross_chain_arbitrage.verifier as mod
    text = open(mod.__file__).read()
    assert "build_canonical_from_evidence" in text
    assert "CanonicalOpportunity(" not in text
