"""D-5.2 Completion — multi-bridge dispatch + outcome_history_loader tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
)
from arbicore.models.enums import OpportunityType
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
from arbicore.scanners.cross_chain_arbitrage.scanner import (
    CrossChainArbitrageScanner,
)
from arbicore.scanners.cross_chain_arbitrage.verifier import (
    CrossChainOpportunityVerifier,
)


_GATES = {
    "min_bridge_health_score": 70.0,
    "min_bridge_liveness_score": 75.0,
    "min_bridge_inventory_pct": 30.0,
    "max_inbound_latency_p95_s": 1800.0,
    "max_chain_congestion_score": 80.0,
    "max_chain_finality_s": 1800.0,
    "max_cross_chain_mev_risk_class": "MEDIUM",
}


def _facts(bridge: str, source_id: str) -> Dict[str, Any]:
    return {
        "bridge": bridge, "source_chain": "ethereum",
        "destination_chain": "arbitrum", "asset": "USDC",
        "primary_venue_id": f"{bridge}:ethereum:USDC",
        "secondary_venue_id": f"{bridge}:arbitrum:USDC",
        "source_id": source_id,
        "expected_out_amount": 995.0,
        "expected_out_amount_usd": 995.0,
        "slippage_bridge_pct": 0.3,
        "transfer_modelling_confidence": 0.85,
        "primary_fee_bps": 5, "secondary_fee_bps": 5,
        "total_bridge_fee_usd": 2.0,
        "inbound_latency_p50_s": 180.0,
        "inbound_latency_p95_s": 400.0,
        "verified_at_ts": 1.0, "quote_source": f"{bridge}:/quote",
        "notional_usd": 1000.0,
    }


def _make_cand(bridge: str) -> DiscoveryCandidate:
    subject = f"cross_chain:{bridge}:ethereum→arbitrum:USDC"
    cid = make_candidate_id(
        hint_source="t",
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        subject_id=subject, asset="USDC",
        candidate_venues=[f"{bridge}:ethereum", f"{bridge}:arbitrum"],
        hint_observed_at=1.0,
    )
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        hint_source="t", hint_observed_at=1.0, subject_id=subject,
        asset="USDC",
        candidate_venues=[f"{bridge}:ethereum", f"{bridge}:arbitrum"],
        hint_metric={"bridge": bridge, "source_chain": "ethereum",
                      "destination_chain": "arbitrum"},
        reason="t",
    )


def _scanner_cfg() -> Dict[str, Any]:
    return {
        "interval_s": 1, "default_notional_usd": 1000.0,
        "verifier_concurrency": 2,
        "bridges": {"lifi": {"enabled": False},
                     "stargate": {"enabled": False}},
        "chains": {c: {"enabled": False, "gas_token": "ETH"}
                   for c in ("ethereum", "arbitrum", "base",
                              "optimism", "polygon", "solana")},
        "gate_thresholds": {"default": _GATES},
        "roi_probability": {"min_sample_size": 2},
        "transfer_model": {"corridor_overrides": {}},
    }


def _make_scanner(*, enabled: bool):
    cfg = _scanner_cfg()
    state = {"enabled": enabled}
    queue = MagicMock()
    queue.upsert_many = AsyncMock(return_value=None)
    queue.claim_batch = AsyncMock(return_value=[])
    queue.mark_processed = AsyncMock(return_value=None)
    bus = MagicMock()
    bus.emit = AsyncMock(return_value=None)
    return CrossChainArbitrageScanner(
        emission_bus=bus, discovery_queue=queue,
        venue_capability_repo=MagicMock(),
        config_loader=lambda: cfg, state_loader=lambda: state,
    ), bus, queue


# ============================================================================
# Multi-bridge dispatch
# ============================================================================

def test_scanner_dispatches_to_lifi_provider():
    s, bus, queue = _make_scanner(enabled=True)

    async def lifi_provider(c):
        return _facts("lifi", "lifi_quote_real")
    s.register_transfer_provider("lifi", lifi_provider)
    queue.claim_batch = AsyncMock(return_value=[_make_cand("lifi")])
    asyncio.run(s._tick())
    bus.emit.assert_called_once()
    emitted = bus.emit.call_args.args[0]
    assert emitted.category_metadata["bridge_provider"] == "lifi"


def test_scanner_dispatches_to_stargate_provider():
    s, bus, queue = _make_scanner(enabled=True)

    async def stargate_provider(c):
        return _facts("stargate", "stargate_quote_real")
    s.register_transfer_provider("stargate", stargate_provider)
    queue.claim_batch = AsyncMock(return_value=[_make_cand("stargate")])
    asyncio.run(s._tick())
    bus.emit.assert_called_once()
    emitted = bus.emit.call_args.args[0]
    assert emitted.category_metadata["bridge_provider"] == "stargate"


def test_scanner_dispatches_correctly_with_both_providers():
    s, bus, queue = _make_scanner(enabled=True)
    seen: List[str] = []

    async def lifi_provider(c):
        seen.append("lifi")
        return _facts("lifi", "lifi_quote_real")

    async def stargate_provider(c):
        seen.append("stargate")
        return _facts("stargate", "stargate_quote_real")

    s.register_transfer_provider("lifi", lifi_provider)
    s.register_transfer_provider("stargate", stargate_provider)
    queue.claim_batch = AsyncMock(return_value=[
        _make_cand("lifi"), _make_cand("stargate"),
    ])
    asyncio.run(s._tick())
    assert sorted(seen) == ["lifi", "stargate"]
    assert bus.emit.call_count == 2


def test_scanner_default_provider_unattached_yields_denied():
    s, bus, queue = _make_scanner(enabled=True)
    queue.claim_batch = AsyncMock(return_value=[_make_cand("lifi")])
    asyncio.run(s._tick())
    bus.emit.assert_not_called()
    assert s.stats["denied_venue_unreadable"] == 1


def test_scanner_set_transfer_provider_back_compat():
    """D-5.1 single-provider API still works (registers as __default__)."""
    s, bus, queue = _make_scanner(enabled=True)

    async def default_provider(c):
        return _facts("lifi", "lifi_quote_real")
    s.set_transfer_provider(default_provider)
    queue.claim_batch = AsyncMock(return_value=[_make_cand("lifi")])
    asyncio.run(s._tick())
    bus.emit.assert_called_once()


def test_transfer_providers_accessor_returns_attached_bridges():
    s, *_ = _make_scanner(enabled=False)

    async def lifi(c):
        return None

    async def stg(c):
        return None
    s.register_transfer_provider("lifi", lifi)
    s.register_transfer_provider("stargate", stg)
    view = s.transfer_providers()
    assert set(view.keys()) == {"lifi", "stargate"}


def test_transfer_provider_is_default_property_reflects_attachment():
    s, *_ = _make_scanner(enabled=False)
    assert s.transfer_provider_is_default

    async def lifi(c):
        return None
    s.register_transfer_provider("lifi", lifi)
    assert not s.transfer_provider_is_default


# ============================================================================
# Outcome history loader hook
# ============================================================================

def _build_verifier(provider, outcome_loader=None):
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
        gate_7=CrossChainGate7BridgeLiveness(thresholds=_GATES),
        gate_8=CrossChainGate8ChainLiveness(thresholds=_GATES),
        gate_9=CrossChainGate9CrossChainMev(thresholds=_GATES),
        outcome_history_loader=outcome_loader,
        default_notional_usd=1000.0,
    )


def test_outcome_history_loader_is_called():
    captured = {"called_with": None}

    async def loader(corridor: Dict[str, Any]) -> List[Dict[str, Any]]:
        captured["called_with"] = corridor
        return [{"realized_pct": 0.42},
                {"realized_pct": 0.30},
                {"realized_pct": 0.50}]

    async def provider(_):
        return _facts("lifi", "lifi_quote_real")
    v = _build_verifier(provider, outcome_loader=loader)
    out, _ = asyncio.run(v.verify(_make_cand("lifi")))
    assert out is not None
    assert captured["called_with"] is not None
    assert captured["called_with"]["bridge"] == "lifi"
    assert captured["called_with"]["source_chain"] == "ethereum"
    assert captured["called_with"]["asset"] == "USDC"


def test_outcome_history_loader_exception_does_not_break_verify():
    async def loader(_):
        raise RuntimeError("db down")

    async def provider(_):
        return _facts("lifi", "lifi_quote_real")
    v = _build_verifier(provider, outcome_loader=loader)
    out, tag = asyncio.run(v.verify(_make_cand("lifi")))
    # Verification must still proceed (loader failure is silent).
    assert out is not None


def test_outcome_history_loader_default_is_none():
    async def provider(_):
        return _facts("lifi", "lifi_quote_real")
    v = _build_verifier(provider)
    assert v.outcome_history_loader is None
    out, _ = asyncio.run(v.verify(_make_cand("lifi")))
    assert out is not None
