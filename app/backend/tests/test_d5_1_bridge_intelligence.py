"""D-5.1 — BridgeRouteCatalog + MevRiskScorer tests."""
from __future__ import annotations

from arbicore.models.enums import MevRiskLevel
from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
    BridgeRouteCatalog, MevRiskScorer,
)


# ============================================================================
# BridgeRouteCatalog
# ============================================================================

def test_lifi_default_metadata():
    cat = BridgeRouteCatalog(config_loader=lambda: {})
    r = cat.get(bridge="lifi", source_chain="ethereum",
                destination_chain="arbitrum", asset="USDC")
    assert r.bridge == "lifi"
    assert r.bridge_health_score >= 70.0
    assert r.bridge_liveness_score >= 70.0
    assert r.inbound_latency_p50_s > 0
    assert r.corridor_id == "lifi:ethereum→arbitrum:USDC"


def test_stargate_default_metadata():
    cat = BridgeRouteCatalog(config_loader=lambda: {})
    r = cat.get(bridge="stargate", source_chain="ethereum",
                destination_chain="base", asset="USDC")
    assert r.bridge == "stargate"
    # Stargate is faster than LI.FI on default p95
    assert r.inbound_latency_p95_s < 900.0


def test_unknown_bridge_fails_low_for_gate_7():
    cat = BridgeRouteCatalog(config_loader=lambda: {})
    r = cat.get(bridge="unknown_bridge", source_chain="ethereum",
                destination_chain="arbitrum", asset="USDC")
    assert r.bridge_health_score == 0.0
    assert r.bridge_liveness_score == 0.0


def test_corridor_override_via_config():
    cfg = {
        "transfer_model": {
            "corridor_overrides": {
                "lifi:ethereum→arbitrum:USDC": {
                    "bridge_health_score":   95.0,
                    "bridge_liveness_score": 92.0,
                    "bridge_inventory_pct":  88.0,
                    "inbound_latency_p50_s": 120.0,
                    "inbound_latency_p95_s": 480.0,
                    "fee_curve_bps":         10.0,
                }
            }
        }
    }
    cat = BridgeRouteCatalog(config_loader=lambda: cfg)
    r = cat.get(bridge="lifi", source_chain="ethereum",
                destination_chain="arbitrum", asset="USDC")
    assert r.bridge_health_score == 95.0
    assert r.inbound_latency_p95_s == 480.0
    assert cat.known_corridors() == 1


def test_to_dict_carries_all_keys():
    cat = BridgeRouteCatalog(config_loader=lambda: {})
    r = cat.get(bridge="lifi", source_chain="ethereum",
                destination_chain="arbitrum", asset="USDC")
    d = r.to_dict()
    for k in ("bridge", "source_chain", "destination_chain", "asset",
              "corridor_id", "bridge_health_score", "bridge_liveness_score",
              "bridge_inventory_pct", "inbound_latency_p50_s",
              "inbound_latency_p95_s", "fee_curve_bps"):
        assert k in d


# ============================================================================
# MevRiskScorer
# ============================================================================

def test_mev_low_for_calm_chains_small_notional():
    sc = MevRiskScorer()
    v = sc.classify(bridge="stargate", source_chain_congestion=20,
                    destination_chain_congestion=15, asset="USDC",
                    notional_usd=500)
    assert v["level"] == MevRiskLevel.LOW
    assert v["label"] == "LOW"


def test_mev_high_for_congested_chains_hot_asset():
    sc = MevRiskScorer()
    v = sc.classify(bridge="lifi", source_chain_congestion=80,
                    destination_chain_congestion=75, asset="WETH",
                    notional_usd=250_000)
    assert v["level"] == MevRiskLevel.HIGH
    assert v["score"] >= 70.0


def test_mev_stargate_gets_credit_over_lifi():
    sc = MevRiskScorer()
    a = sc.classify(bridge="lifi", source_chain_congestion=40,
                    destination_chain_congestion=40, asset="USDC",
                    notional_usd=1000)
    b = sc.classify(bridge="stargate", source_chain_congestion=40,
                    destination_chain_congestion=40, asset="USDC",
                    notional_usd=1000)
    assert b["score"] < a["score"]


def test_mev_label_matches_level():
    sc = MevRiskScorer()
    v = sc.classify(bridge="stargate", source_chain_congestion=50,
                    destination_chain_congestion=50, asset="USDC",
                    notional_usd=1000)
    assert v["level"] == MevRiskLevel.MEDIUM
    assert v["label"] == "MEDIUM"


def test_mev_inv2_no_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.bridge_intelligence as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text
