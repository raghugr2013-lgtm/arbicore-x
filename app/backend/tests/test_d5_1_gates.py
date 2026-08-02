"""D-5.1 — Gates 7 / 8 / 9 tests."""
from __future__ import annotations

from arbicore.models.enums import MevRiskLevel
from arbicore.scanners.cross_chain_arbitrage.filter import (
    CrossChainGate7BridgeLiveness,
    CrossChainGate8ChainLiveness,
    CrossChainGate9CrossChainMev,
)

_DEFAULT = {
    "min_bridge_health_score": 70.0,
    "min_bridge_liveness_score": 75.0,
    "min_bridge_inventory_pct": 30.0,
    "max_inbound_latency_p95_s": 1800.0,
    "max_chain_congestion_score": 80.0,
    "max_chain_finality_s": 1800.0,
    "max_cross_chain_mev_risk_class": "MEDIUM",
}


# ============================================================================
# Gate 7
# ============================================================================

def test_gate_7_pass():
    g = CrossChainGate7BridgeLiveness(thresholds=_DEFAULT)
    r = g.evaluate(bridge="lifi", bridge_health_score=85,
                    bridge_liveness_score=90, bridge_inventory_pct=80,
                    inbound_latency_p95_s=400)
    assert r.passed
    assert r.gate_id == "gate_7_bridge_liveness"


def test_gate_7_fail_health():
    g = CrossChainGate7BridgeLiveness(thresholds=_DEFAULT)
    r = g.evaluate(bridge="lifi", bridge_health_score=50,
                    bridge_liveness_score=90, bridge_inventory_pct=80,
                    inbound_latency_p95_s=400)
    assert not r.passed
    assert "bridge_health" in r.reason


def test_gate_7_fail_inventory():
    g = CrossChainGate7BridgeLiveness(thresholds=_DEFAULT)
    r = g.evaluate(bridge="lifi", bridge_health_score=85,
                    bridge_liveness_score=85, bridge_inventory_pct=10,
                    inbound_latency_p95_s=400)
    assert not r.passed


def test_gate_7_per_bridge_override_tighter_latency():
    g = CrossChainGate7BridgeLiveness(
        thresholds=_DEFAULT,
        per_bridge={"stargate": {"max_inbound_latency_p95_s": 600.0}},
    )
    r = g.evaluate(bridge="stargate", bridge_health_score=95,
                    bridge_liveness_score=95, bridge_inventory_pct=85,
                    inbound_latency_p95_s=900)
    assert not r.passed
    assert "p95" in r.reason


# ============================================================================
# Gate 8
# ============================================================================

def test_gate_8_pass():
    g = CrossChainGate8ChainLiveness(thresholds=_DEFAULT)
    r = g.evaluate(source_chain="ethereum", destination_chain="arbitrum",
                    source_finality_s=12, destination_finality_s=5,
                    source_congestion_score=30,
                    destination_congestion_score=25)
    assert r.passed


def test_gate_8_fail_congestion():
    g = CrossChainGate8ChainLiveness(thresholds=_DEFAULT)
    r = g.evaluate(source_chain="ethereum", destination_chain="arbitrum",
                    source_finality_s=12, destination_finality_s=5,
                    source_congestion_score=95,
                    destination_congestion_score=30)
    assert not r.passed
    assert "ethereum" in r.reason


def test_gate_8_fail_finality():
    g = CrossChainGate8ChainLiveness(thresholds=_DEFAULT)
    r = g.evaluate(source_chain="ethereum", destination_chain="arbitrum",
                    source_finality_s=12, destination_finality_s=3600,
                    source_congestion_score=30,
                    destination_congestion_score=30)
    assert not r.passed
    assert "finality" in r.reason


# ============================================================================
# Gate 9
# ============================================================================

def test_gate_9_pass_low():
    g = CrossChainGate9CrossChainMev(thresholds=_DEFAULT)
    r = g.evaluate(mev_risk_level=MevRiskLevel.LOW,
                    mev_risk_label="LOW", mev_score=10.0)
    assert r.passed


def test_gate_9_pass_medium_under_cap():
    g = CrossChainGate9CrossChainMev(thresholds=_DEFAULT)
    r = g.evaluate(mev_risk_level=MevRiskLevel.MEDIUM,
                    mev_risk_label="MEDIUM", mev_score=50.0)
    assert r.passed


def test_gate_9_fail_high():
    g = CrossChainGate9CrossChainMev(thresholds=_DEFAULT)
    r = g.evaluate(mev_risk_level=MevRiskLevel.HIGH,
                    mev_risk_label="HIGH", mev_score=85.0)
    assert not r.passed


def test_gate_9_cap_override_to_low():
    cfg = dict(_DEFAULT)
    cfg["max_cross_chain_mev_risk_class"] = "LOW"
    g = CrossChainGate9CrossChainMev(thresholds=cfg)
    r = g.evaluate(mev_risk_level=MevRiskLevel.MEDIUM,
                    mev_risk_label="MEDIUM", mev_score=50.0)
    assert not r.passed


def test_inv2_filter_module_no_emission_bus():
    import arbicore.scanners.cross_chain_arbitrage.filter as mod
    text = open(mod.__file__).read()
    assert "from ...emission_bus" not in text
    assert "from ...runtime.event_bus" not in text
