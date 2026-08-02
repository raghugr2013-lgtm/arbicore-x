"""D-5.1 — Cross-Chain DiscoverySources tests."""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import pytest

from arbicore.models.enums import DataProvenance, OpportunityType
from arbicore.scanners.cross_chain_arbitrage.sources import (
    LiFiAggregatorSource, StargateSource, build_all_cross_chain_sources,
)


@pytest.fixture
def base_cfg() -> Dict[str, Any]:
    return {
        "bridges": {
            "lifi":     {"enabled": False, "probe_assets": ["USDC", "WETH"],
                         "max_corridors_per_cycle": 12,
                         "base_url": "https://li.quest/v1"},
            "stargate": {"enabled": False, "max_corridors_per_cycle": 8},
        },
        "chains": {
            "ethereum": {"enabled": False, "chain_id": 1},
            "arbitrum": {"enabled": False, "chain_id": 42161},
            "base":     {"enabled": False, "chain_id": 8453},
            "optimism": {"enabled": False, "chain_id": 10},
            "polygon":  {"enabled": False, "chain_id": 137},
            "solana":   {"enabled": False, "chain_id": 0},
        },
    }


# ============================================================================
# Discovery contract
# ============================================================================

def test_lifi_source_attributes():
    s = LiFiAggregatorSource(config_loader=lambda: {})
    assert s.source_id == "lifi_aggregator"
    assert s.tier == 1
    assert OpportunityType.CROSS_CHAIN_ARBITRAGE in s.opportunity_types
    assert s.provenance_of_hint == DataProvenance.REAL
    asyncio.run(s.close())


def test_stargate_source_attributes():
    s = StargateSource(config_loader=lambda: {})
    assert s.source_id == "stargate_direct"
    assert s.tier == 1
    assert OpportunityType.CROSS_CHAIN_ARBITRAGE in s.opportunity_types
    assert s.provenance_of_hint == DataProvenance.REAL
    asyncio.run(s.close())


def test_lifi_disabled_by_default_emits_nothing(base_cfg):
    s = LiFiAggregatorSource(config_loader=lambda: base_cfg)
    out = asyncio.run(s.discover())
    assert out == []
    asyncio.run(s.close())


def test_stargate_disabled_by_default_emits_nothing(base_cfg):
    s = StargateSource(config_loader=lambda: base_cfg)
    out = asyncio.run(s.discover())
    assert out == []
    asyncio.run(s.close())


def test_lifi_skips_when_no_chains_enabled(base_cfg):
    base_cfg["bridges"]["lifi"]["enabled"] = True
    s = LiFiAggregatorSource(config_loader=lambda: base_cfg)
    out = asyncio.run(s.discover())
    assert out == []
    asyncio.run(s.close())


def test_stargate_skips_when_no_chains_enabled(base_cfg):
    base_cfg["bridges"]["stargate"]["enabled"] = True
    s = StargateSource(config_loader=lambda: base_cfg)
    out = asyncio.run(s.discover())
    assert out == []
    asyncio.run(s.close())


def test_lifi_emits_corridors_when_enabled_with_chains(base_cfg, monkeypatch):
    base_cfg["bridges"]["lifi"]["enabled"] = True
    base_cfg["chains"]["ethereum"]["enabled"] = True
    base_cfg["chains"]["arbitrum"]["enabled"] = True
    s = LiFiAggregatorSource(config_loader=lambda: base_cfg)

    async def _ok_probe(self, **kwargs):
        return True
    monkeypatch.setattr(LiFiAggregatorSource, "_probe_connections", _ok_probe)
    cands = asyncio.run(s.discover())
    assert cands, "should emit candidates when chains and bridge enabled"
    for c in cands:
        assert c.opportunity_type == OpportunityType.CROSS_CHAIN_ARBITRAGE
        assert c.hint_source == "lifi_aggregator"
        assert c.hint_metric["bridge"] == "lifi"
        assert c.hint_metric["source_chain"] != c.hint_metric["destination_chain"]
        assert c.hint_metric["source_chain"] in {
            "ethereum", "arbitrum", "base", "optimism", "polygon", "solana"}
    asyncio.run(s.close())


def test_stargate_emits_deprecation_signal_when_enabled(base_cfg):
    """Upstream Stargate v1 API was deprecated (HTTP 410) in 2026-06.
    Source now emits a clear deprecation message via last_error rather
    than attempting dead API calls. LI.FI internally routes Stargate."""
    base_cfg["bridges"]["stargate"]["enabled"] = True
    # explicitly leave "deprecated" at its True default
    base_cfg["chains"]["ethereum"]["enabled"] = True
    base_cfg["chains"]["arbitrum"]["enabled"] = True
    s = StargateSource(config_loader=lambda: base_cfg)
    cands = asyncio.run(s.discover())
    assert cands == [], "deprecated source must not emit candidates"
    h = asyncio.run(s.health())
    assert h.ok is False
    assert "stargate_api_deprecated" in (h.last_error or "")
    asyncio.run(s.close())


def test_stargate_can_be_un_deprecated_for_future_revival(base_cfg):
    """If/when Stargate ships a new compatible API, an operator can flip
    ``deprecated=False`` in the bridge config to re-enable the source."""
    base_cfg["bridges"]["stargate"]["enabled"] = True
    base_cfg["bridges"]["stargate"]["deprecated"] = False
    base_cfg["chains"]["ethereum"]["enabled"] = True
    base_cfg["chains"]["arbitrum"]["enabled"] = True
    s = StargateSource(config_loader=lambda: base_cfg)
    cands = asyncio.run(s.discover())
    assert cands, "with deprecation cleared, source should emit corridors"
    for c in cands:
        assert c.opportunity_type == OpportunityType.CROSS_CHAIN_ARBITRAGE
        assert c.hint_source == "stargate_direct"
        assert c.hint_metric["bridge"] == "stargate"
    asyncio.run(s.close())


def test_stargate_excludes_solana(base_cfg):
    base_cfg["bridges"]["stargate"]["enabled"] = True
    base_cfg["bridges"]["stargate"]["deprecated"] = False
    base_cfg["chains"]["ethereum"]["enabled"] = True
    base_cfg["chains"]["solana"]["enabled"] = True
    s = StargateSource(config_loader=lambda: base_cfg)
    cands = asyncio.run(s.discover())
    for c in cands:
        assert "solana" not in (c.hint_metric["source_chain"],
                                  c.hint_metric["destination_chain"])
    asyncio.run(s.close())


def test_lifi_health_default():
    s = LiFiAggregatorSource(config_loader=lambda: {})
    h = asyncio.run(s.health())
    assert h.source_id == "lifi_aggregator"
    assert h.ok is True
    asyncio.run(s.close())


def test_build_all_cross_chain_sources_returns_two():
    out = build_all_cross_chain_sources(config_loader=lambda: {})
    assert len(out) == 2
    ids = sorted(s.source_id for s in out)
    assert ids == ["lifi_aggregator", "stargate_direct"]


def test_inv1_sources_emit_discovery_candidate_not_canonical(base_cfg,
                                                              monkeypatch):
    """INV-1: sources must produce DiscoveryCandidate — never canonical."""
    from arbicore.models.discovery import DiscoveryCandidate
    base_cfg["bridges"]["lifi"]["enabled"] = True
    base_cfg["chains"]["ethereum"]["enabled"] = True
    base_cfg["chains"]["base"]["enabled"] = True

    async def _ok_probe(self, **kwargs):
        return True
    monkeypatch.setattr(LiFiAggregatorSource, "_probe_connections", _ok_probe)
    s = LiFiAggregatorSource(config_loader=lambda: base_cfg)
    out = asyncio.run(s.discover())
    assert out
    assert all(isinstance(c, DiscoveryCandidate) for c in out)
    asyncio.run(s.close())


def test_inv2_sources_do_not_import_emission_bus():
    """INV-2: sources module must not import EmissionBus."""
    import arbicore.scanners.cross_chain_arbitrage.sources as src_mod
    src_text = open(src_mod.__file__).read()
    assert "from ...emission_bus" not in src_text
    assert "from ...runtime.event_bus" not in src_text
