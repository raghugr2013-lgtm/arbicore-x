"""Phase C Wave 2 — AdaptiveConfidenceEngine tests."""
import asyncio

from arbicore.data._inmemory import (
    InMemoryMetricsRepository,
)
from arbicore.data.state_observer import StateObserverRegistry
from arbicore.learning.concrete.adaptive_weights import MongoBackedAdaptiveWeights
from arbicore.learning.concrete.confidence_engine import (
    BASE_CONFIDENCE,
    AdaptiveConfidenceEngine,
)
from arbicore.learning.concrete.route_success_tracker import MongoRouteSuccessTracker
from arbicore.learning.concrete.state_observers import make_default_observer
from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    OpportunityType,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _build_engine(metrics_repo=None,
                  observer_registry=None):
    metrics_repo = metrics_repo or InMemoryMetricsRepository()
    observer_registry = observer_registry or StateObserverRegistry()
    weights = MongoBackedAdaptiveWeights(metrics_repo)
    route_tracker = MongoRouteSuccessTracker()  # not used unless route_key set
    return AdaptiveConfidenceEngine(weights, route_tracker, observer_registry)


def _opp(**kw):
    base = dict(
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        asset="A/B",
        subject_id="subject-1",
        source_data_quality=DataProvenance.REAL,
    )
    base.update(kw)
    return CanonicalOpportunity(**base)


def test_reversibility_neutral_inputs_yield_base():
    """No signals + no route + no observer → exactly BASE_CONFIDENCE."""
    engine = _build_engine()
    opp = _opp()  # no category_metadata, no buy/sell venue
    bd = _run(engine.score_with_breakdown(opp))
    assert bd.final == BASE_CONFIDENCE
    assert bd.signal_contributions == []
    assert bd.route_contribution == 0.0
    assert bd.state_observation_available is False


def test_positive_signal_increases_confidence():
    engine = _build_engine()
    opp = _opp(category_metadata={"venue_health_score": 95.0})
    bd = _run(engine.score_with_breakdown(opp))
    assert bd.final > BASE_CONFIDENCE
    assert any(s == "venue_health_score" for s, _w, _d in bd.signal_contributions)


def test_negative_signal_decreases_confidence():
    engine = _build_engine()
    opp = _opp(category_metadata={"fee_drag_pct": 95.0})
    bd = _run(engine.score_with_breakdown(opp))
    assert bd.final < BASE_CONFIDENCE


def test_unknown_metadata_key_is_zero_contribution():
    """Soft-typed: unknown key warns once (Phase B) but contributes 0 to confidence."""
    engine = _build_engine()
    opp = _opp(category_metadata={"a_random_key_for_w2": 1234.0})
    bd = _run(engine.score_with_breakdown(opp))
    assert bd.signal_contributions == []
    assert bd.final == BASE_CONFIDENCE


def test_score_clamped_to_zero_hundred():
    """Adversarial signal stack — confidence must clamp."""
    engine = _build_engine()
    opp = _opp(category_metadata={
        "venue_health_score": 99999.0,
        "profitable_buyer_depth_usd": 99999.0,
        "combined_survival_prob": 99999.0,
    })
    bd = _run(engine.score_with_breakdown(opp))
    assert 0.0 <= bd.final <= 100.0


def test_observer_registered_flag():
    reg = StateObserverRegistry()
    reg.register(make_default_observer(OpportunityType.CEX_ARBITRAGE))
    engine = _build_engine(observer_registry=reg)
    opp = _opp()
    bd = _run(engine.score_with_breakdown(opp))
    assert bd.state_observation_available is True


def test_score_returns_float_in_range():
    engine = _build_engine()
    opp = _opp(category_metadata={"venue_health_score": 60.0})
    val = _run(engine.score(opp))
    assert isinstance(val, float)
    assert 0.0 <= val <= 100.0


def test_breakdown_serialises_to_dict():
    engine = _build_engine()
    opp = _opp(category_metadata={"venue_health_score": 60.0})
    bd = _run(engine.score_with_breakdown(opp))
    d = bd.to_dict()
    assert "final" in d
    assert "signal_contributions" in d
    assert isinstance(d["signal_contributions"], list)
