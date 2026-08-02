"""Tests for the signal confidence engine."""
from arbicore.intelligence import InMemoryConfidenceStore, SignalConfidenceEngine


def test_persistent_signals_drive_confidence():
    e = SignalConfidenceEngine()
    for _ in range(4):
        e.record_signal(opportunity_type="DEX_ARBITRAGE", asset="WETH/USDC",
                        route="uni->sushi", duration_seconds=45, spread_percent=1.0)
    assert e.get_confidence("DEX_ARBITRAGE", "WETH/USDC", "uni->sushi") == 100.0


def test_ephemeral_signals_lower_confidence():
    e = SignalConfidenceEngine()
    e.record_signal(opportunity_type="DEX_ARBITRAGE", asset="WETH/USDC",
                    route="uni->sushi", duration_seconds=45, spread_percent=1.0)
    e.record_signal(opportunity_type="DEX_ARBITRAGE", asset="WETH/USDC",
                    route="uni->sushi", duration_seconds=2, spread_percent=1.0)
    # 1 persistent of 2 total -> 50%
    assert e.get_confidence("DEX_ARBITRAGE", "WETH/USDC", "uni->sushi") == 50.0


def test_running_averages():
    e = SignalConfidenceEngine()
    e.record_signal(opportunity_type="DEX_ARBITRAGE", asset="A/B", route="r",
                    duration_seconds=40, spread_percent=1.0)
    s = e.record_signal(opportunity_type="DEX_ARBITRAGE", asset="A/B", route="r",
                        duration_seconds=20, spread_percent=3.0)
    assert s.total_signals == 2
    assert s.avg_spread_percent == 2.0
    assert s.avg_duration_seconds == 30.0
    assert s.max_spread_percent == 3.0


def test_store_persistence_isolation():
    store = InMemoryConfidenceStore()
    e1 = SignalConfidenceEngine(store=store)
    e1.record_signal(opportunity_type="T", asset="A/B", route="r",
                     duration_seconds=40, spread_percent=1.0)
    # a new engine on the same store sees prior data (survives "restart")
    e2 = SignalConfidenceEngine(store=store)
    assert e2.get_confidence("T", "A/B", "r") == 100.0


def test_unknown_route_zero_confidence():
    e = SignalConfidenceEngine()
    assert e.get_confidence("T", "X/Y", "none") == 0.0
