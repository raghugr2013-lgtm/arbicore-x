"""Phase C Wave 1 — RouteSuccessTracker concrete (Mongo-backed)."""
import asyncio
import time

import pytest

from arbicore.learning.concrete.route_success_tracker import (
    MongoRouteSuccessTracker,
    route_key_for,
)
from arbicore.models import DataProvenance


@pytest.fixture(scope="module")
def event_loop():
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import db as _db_mod
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _db_mod.client = AsyncIOMotorClient(os.environ['MONGO_URL'], io_loop=loop)
    _db_mod.db = _db_mod.client[os.environ['DB_NAME']]
    yield loop
    loop.close()


def _run(loop, coro):
    return loop.run_until_complete(coro)


def test_route_key_returns_none_when_either_side_missing():
    assert route_key_for(None, "Y") is None
    assert route_key_for("X", None) is None
    assert route_key_for("", "Y") is None
    assert route_key_for("X", "Y") == "X->Y"


def test_record_outcome_provenance_gate(event_loop):
    rt = MongoRouteSuccessTracker()
    key = f"test-prov-{int(time.time()*1000)}->dst"
    wrote = _run(event_loop, rt.record_outcome(
        key, succeeded=True, realized_outcome=0.5, provenance=DataProvenance.SIMULATED,
    ))
    assert wrote is False
    stats = _run(event_loop, rt.get(key))
    assert stats is None  # no row written


def test_record_outcome_real_writes_and_aggregates(event_loop):
    rt = MongoRouteSuccessTracker()
    key = f"test-agg-{int(time.time()*1000)}->dst"
    _run(event_loop, rt.record_outcome(
        key, succeeded=True, realized_outcome=1.0, provenance=DataProvenance.REAL,
    ))
    _run(event_loop, rt.record_outcome(
        key, succeeded=False, realized_outcome=-0.5, provenance=DataProvenance.REAL,
    ))
    _run(event_loop, rt.record_outcome(
        key, succeeded=True, realized_outcome=0.5, provenance=DataProvenance.VERIFIED_REAL,
    ))
    s = _run(event_loop, rt.get(key))
    assert s is not None
    assert s.trials == 3
    assert s.wins == 2
    assert abs(s.realized_outcome_sum - 1.0) < 1e-9
    assert abs(s.win_rate - (2 / 3)) < 1e-9
    assert abs(s.realized_outcome_mean - (1.0 / 3)) < 1e-9


def test_record_outcome_empty_key_noop(event_loop):
    rt = MongoRouteSuccessTracker()
    wrote = _run(event_loop, rt.record_outcome(
        "", succeeded=True, realized_outcome=1.0, provenance=DataProvenance.REAL,
    ))
    assert wrote is False
