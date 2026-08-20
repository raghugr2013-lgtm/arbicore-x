"""Phase C Wave 3 — Confidence engine regime integration + HTTP endpoints."""
import asyncio
import os
import time

import pytest
import requests

from arbicore.data._inmemory import (
    InMemoryMetricsRepository,
    InMemoryRegimeSnapshotRepository,
)
from arbicore.data.regime_snapshot_repo import RegimeSnapshot
from arbicore.data.state_observer import StateObserverRegistry
from arbicore.learning.concrete.adaptive_weights import MongoBackedAdaptiveWeights
from arbicore.learning.concrete.confidence_engine import (
    BASE_CONFIDENCE,
    REGIME_INFLUENCE_RANGE,
    AdaptiveConfidenceEngine,
)
from arbicore.learning.concrete.route_success_tracker import MongoRouteSuccessTracker
from arbicore.models import CanonicalOpportunity, DataProvenance, OpportunityType


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://defi-exec-audit.preview.emergentagent.com",
).rstrip("/")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ArbiCore2026!"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---- Unit: confidence engine + regime --------------------------------------

def _engine(regimes):
    weights = MongoBackedAdaptiveWeights(InMemoryMetricsRepository())
    return AdaptiveConfidenceEngine(
        weights=weights,
        route_tracker=MongoRouteSuccessTracker(),
        observer_registry=StateObserverRegistry(),
        regime_repo=regimes,
    )


def test_illiquid_regime_lowers_confidence():
    regimes = InMemoryRegimeSnapshotRepository()
    _run(regimes.append(RegimeSnapshot(
        captured_at=time.time(), dominant_regime="ILLIQUID",
        tags=["thin_liquidity"], confidence=0.8,
    )))
    engine = _engine(regimes)
    bd = _run(engine.score_with_breakdown(CanonicalOpportunity(
        opportunity_type=OpportunityType.CEX_ARBITRAGE, asset="A",
    )))
    # ILLIQUID = -5, plus thin_liquidity = -2 → clamped to -5
    assert bd.regime_dominant == "ILLIQUID"
    assert bd.regime_contribution == -REGIME_INFLUENCE_RANGE
    assert bd.final < BASE_CONFIDENCE


def test_calm_regime_raises_confidence():
    regimes = InMemoryRegimeSnapshotRepository()
    _run(regimes.append(RegimeSnapshot(
        captured_at=time.time(), dominant_regime="CALM",
        tags=["low_volatility"], confidence=0.9,
    )))
    engine = _engine(regimes)
    bd = _run(engine.score_with_breakdown(CanonicalOpportunity(
        opportunity_type=OpportunityType.CEX_ARBITRAGE, asset="A",
    )))
    assert bd.regime_dominant == "CALM"
    assert bd.regime_contribution > 0
    assert bd.final > BASE_CONFIDENCE


def test_no_regime_data_no_contribution():
    engine = _engine(InMemoryRegimeSnapshotRepository())
    bd = _run(engine.score_with_breakdown(CanonicalOpportunity(
        opportunity_type=OpportunityType.CEX_ARBITRAGE, asset="A",
    )))
    assert bd.regime_contribution == 0.0
    assert bd.regime_dominant is None
    assert bd.final == BASE_CONFIDENCE


def test_regime_engine_clamps_to_range():
    regimes = InMemoryRegimeSnapshotRepository()
    _run(regimes.append(RegimeSnapshot(
        captured_at=time.time(), dominant_regime="ILLIQUID",
        # Pile every negative tag to attempt to exceed range
        tags=["thin_liquidity", "high_volatility"], confidence=0.9,
    )))
    engine = _engine(regimes)
    bd = _run(engine.score_with_breakdown(CanonicalOpportunity(
        opportunity_type=OpportunityType.CEX_ARBITRAGE, asset="A",
    )))
    assert -REGIME_INFLUENCE_RANGE <= bd.regime_contribution <= REGIME_INFLUENCE_RANGE


# ---- HTTP endpoints --------------------------------------------------------

@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login unavailable ({r.status_code})")
    return s


def test_learning_status_advertises_wave_3(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/learning-status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["wave"] in ("C-3", "C-4", "C-5")
    assert body["regime_worker"]["running"] is True
    assert "regime_snapshot_count" in body
    assert "sequence_pattern_count" in body


def test_survival_endpoint_returns_none_for_unknown_subject(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/survival/nonexistent-subject", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["survival"] is None
    assert body["reason"] == "insufficient_state_snapshots"


def test_regime_latest_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/regime/latest", timeout=10)
    assert r.status_code == 200
    body = r.json()
    # Either no snapshots yet, or one with the canonical fields
    if body.get("regime") is not None:
        assert "dominant_regime" in body["regime"]
        assert "tags" in body["regime"]


def test_regime_history_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/regime/history?limit=5", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "count" in body
    assert isinstance(body["items"], list)


def test_sequences_patterns_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/sequences/patterns?limit=10", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "count" in body and "total_patterns" in body
    assert isinstance(body["items"], list)


def test_no_write_endpoints_in_wave_3(auth_session):
    for path in ("survival/x", "regime/latest", "regime/history", "sequences/patterns"):
        for verb in ("post", "put", "delete"):
            r = getattr(auth_session, verb)(f"{BASE_URL}/api/arbicore/{path}", timeout=10)
            assert r.status_code in (404, 405)
