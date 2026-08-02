"""D-5.1 — CrossChainArbitrageScanner orchestrator tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
)
from arbicore.models.enums import OpportunityType
from arbicore.scanners.cross_chain_arbitrage.scanner import (
    CrossChainArbitrageScanner,
)


def _base_cfg() -> Dict[str, Any]:
    return {
        "interval_s": 1,
        "default_notional_usd": 1000.0,
        "verifier_concurrency": 2,
        "bridges": {
            "lifi":     {"enabled": False, "probe_assets": ["USDC"]},
            "stargate": {"enabled": False},
        },
        "chains": {
            "ethereum": {"enabled": False, "gas_token": "ETH"},
            "arbitrum": {"enabled": False, "gas_token": "ETH"},
            "base":     {"enabled": False, "gas_token": "ETH"},
            "optimism": {"enabled": False, "gas_token": "ETH"},
            "polygon":  {"enabled": False, "gas_token": "MATIC"},
            "solana":   {"enabled": False, "gas_token": "SOL"},
        },
        "gate_thresholds": {
            "default": {
                "min_bridge_health_score": 70.0,
                "min_bridge_liveness_score": 75.0,
                "min_bridge_inventory_pct": 30.0,
                "max_inbound_latency_p95_s": 1800.0,
                "max_chain_congestion_score": 80.0,
                "max_chain_finality_s": 1800.0,
                "max_cross_chain_mev_risk_class": "MEDIUM",
            }
        },
        "roi_probability": {"min_sample_size": 2, "winsor_low_pct": 5.0},
        "transfer_model": {"corridor_overrides": {}},
    }


def _make_scanner(*, enabled: bool, transfer_provider=None):
    cfg = _base_cfg()
    state = {"enabled": enabled}
    queue = MagicMock()
    queue.upsert_many = AsyncMock(return_value=None)
    queue.claim_batch = AsyncMock(return_value=[])
    queue.mark_processed = AsyncMock(return_value=None)
    bus = MagicMock()
    bus.emit = AsyncMock(return_value=None)
    caps = MagicMock()
    return CrossChainArbitrageScanner(
        emission_bus=bus,
        discovery_queue=queue,
        venue_capability_repo=caps,
        config_loader=lambda: cfg,
        state_loader=lambda: state,
        transfer_provider=transfer_provider,
    ), bus, queue, cfg, state


def test_scanner_id():
    s, *_ = _make_scanner(enabled=False)
    assert s.scanner_id == "cross_chain_arb"
    assert s.opportunity_type == OpportunityType.CROSS_CHAIN_ARBITRAGE


def test_scanner_disabled_at_boot():
    s, *_ = _make_scanner(enabled=False)
    assert not s.is_enabled()


def test_transfer_provider_is_default():
    s, *_ = _make_scanner(enabled=False)
    assert s.transfer_provider_is_default


def test_sources_registered():
    s, *_ = _make_scanner(enabled=False)
    ids = s.source_registry.ids()
    assert "lifi_aggregator" in ids
    assert "stargate_direct" in ids


def test_verifier_registered():
    s, *_ = _make_scanner(enabled=False)
    types = s.verifier_registry.types()
    assert "CROSS_CHAIN_ARBITRAGE" in types


def test_tick_noops_when_disabled():
    s, bus, queue, *_ = _make_scanner(enabled=False)
    asyncio.run(s._tick())
    bus.emit.assert_not_called()
    queue.claim_batch.assert_not_called()


def test_tick_default_provider_yields_denied_unreadable():
    s, bus, queue, *_ = _make_scanner(enabled=True)
    cid = make_candidate_id(
        hint_source="t",
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        subject_id="cross_chain:lifi:ethereum→arbitrum:USDC",
        asset="USDC",
        candidate_venues=["lifi:ethereum", "lifi:arbitrum"],
        hint_observed_at=1.0,
    )
    cand = DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        hint_source="t", hint_observed_at=1.0,
        subject_id="cross_chain:lifi:ethereum→arbitrum:USDC", asset="USDC",
        candidate_venues=["lifi:ethereum", "lifi:arbitrum"],
        hint_metric={"bridge": "lifi", "source_chain": "ethereum",
                      "destination_chain": "arbitrum"},
        reason="t",
    )
    queue.claim_batch = AsyncMock(return_value=[cand])
    asyncio.run(s._tick())
    bus.emit.assert_not_called()
    call = queue.mark_processed.call_args
    assert call.args[1] == VerifiedOutcome.DENIED_VENUE_UNREADABLE
    assert s.stats["denied_venue_unreadable"] == 1


def test_tick_routes_wrong_opportunity_type_to_no_verifier():
    s, bus, queue, *_ = _make_scanner(enabled=True)
    cid = make_candidate_id(
        hint_source="t",
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        subject_id="abc", asset="BTCUSDT",
        candidate_venues=["bybit"], hint_observed_at=1.0,
    )
    cand = DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        hint_source="t", hint_observed_at=1.0, subject_id="abc",
        asset="BTCUSDT", candidate_venues=["bybit"], hint_metric={},
        reason="t",
    )
    queue.claim_batch = AsyncMock(return_value=[cand])
    asyncio.run(s._tick())
    call = queue.mark_processed.call_args
    assert call.args[1] == VerifiedOutcome.DENIED_NO_VERIFIER


def test_tick_emits_when_provider_returns_valid_facts():
    async def provider(c):
        return {
            "bridge": "lifi", "source_chain": "ethereum",
            "destination_chain": "arbitrum", "asset": c.asset,
            "primary_venue_id": "lifi:ethereum:USDC",
            "secondary_venue_id": "lifi:arbitrum:USDC",
            "source_id": "lifi_quote_real",
            "expected_out_amount": 995.0, "expected_out_amount_usd": 995.0,
            "slippage_bridge_pct": 0.3,
            "transfer_modelling_confidence": 0.9,
            "primary_fee_bps": 5, "secondary_fee_bps": 5,
            "total_bridge_fee_usd": 2.0,
            "inbound_latency_p50_s": 180.0,
            "inbound_latency_p95_s": 400.0,
            "verified_at_ts": 1.0, "quote_source": "lifi:/quote",
            "notional_usd": 1000.0,
        }
    s, bus, queue, *_ = _make_scanner(enabled=True,
                                       transfer_provider=provider)
    cid = make_candidate_id(
        hint_source="t",
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        subject_id="cross_chain:lifi:ethereum→arbitrum:USDC",
        asset="USDC",
        candidate_venues=["lifi:ethereum", "lifi:arbitrum"],
        hint_observed_at=1.0,
    )
    cand = DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        hint_source="t", hint_observed_at=1.0,
        subject_id="cross_chain:lifi:ethereum→arbitrum:USDC", asset="USDC",
        candidate_venues=["lifi:ethereum", "lifi:arbitrum"],
        hint_metric={"bridge": "lifi", "source_chain": "ethereum",
                      "destination_chain": "arbitrum"},
        reason="t",
    )
    queue.claim_batch = AsyncMock(return_value=[cand])
    asyncio.run(s._tick())
    bus.emit.assert_called_once()
    emitted = bus.emit.call_args.args[0]
    assert isinstance(emitted, CanonicalOpportunity)
    assert emitted.opportunity_type == OpportunityType.CROSS_CHAIN_ARBITRAGE
    assert bus.emit.call_args.kwargs["actor"] == "cross_chain_arb_scanner"
    assert s.stats["rows_emitted"] == 1
    assert s.stats["verifier_confirmed"] == 1


def test_set_transfer_provider_updates_default_flag():
    s, *_ = _make_scanner(enabled=False)
    async def provider(c):
        return None
    s.set_transfer_provider(provider)
    assert not s.transfer_provider_is_default


def test_inv2_only_one_emit_site_in_scanner_module():
    import arbicore.scanners.cross_chain_arbitrage.scanner as mod
    text = open(mod.__file__).read()
    count = text.count("self._bus.emit(")
    assert count == 1, (
        f"INV-2: cross_chain_arb scanner must have exactly 1 emit site; "
        f"got {count}")


def test_inv2_no_emit_outside_scanner():
    from pathlib import Path
    pkg = Path("/app/backend/arbicore/scanners/cross_chain_arbitrage")
    for f in pkg.glob("*.py"):
        if f.name == "scanner.py":
            continue
        text = f.read_text(encoding="utf-8")
        assert "from ...emission_bus" not in text, (
            f"{f.name} imports EmissionBus")
        assert "_bus.emit(" not in text, f"{f.name} calls _bus.emit"
