"""Phase B — Mongo adapters smoke tests.

Hits the live Mongo via the composition root. The arbicore_* collections
should already be created by server.py lifespan; we verify their indexes
exist + the adapter contracts round-trip.

Motor binds to the first asyncio event loop it sees, so we use a
session-scoped loop to keep all coroutines on the same loop as the
already-initialized Motor client.
"""
import asyncio
import time

import pytest

from arbicore.data._inmemory import InMemoryMetricsRepository, InMemoryRegimeSnapshotRepository
from arbicore.data.metrics_repo import SignalMetric
from arbicore.data.mongo.arbicore_collections import (
    COLLECTION_NAMES,
    ensure_indexes,
)
from arbicore.data.mongo.opportunity_repo_mongo import MongoOpportunityRepository
from arbicore.data.mongo.outcome_repo_mongo import MongoOutcomeRepository
from arbicore.data.outcome_repo import OutcomeRow
from arbicore.data.regime_snapshot_repo import RegimeSnapshot
from arbicore.models import (
    CanonicalOpportunity,
    DataProvenance,
    OpportunityStatus,
    OpportunityType,
)


@pytest.fixture(scope="module")
def event_loop():
    # Force motor + tests onto the same loop for this module.
    from services import db as _db_mod
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # Rebind motor client to this loop.
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    _db_mod.client = AsyncIOMotorClient(os.environ['MONGO_URL'], io_loop=loop)
    _db_mod.db = _db_mod.client[os.environ['DB_NAME']]
    yield loop
    loop.close()


def _run(loop, coro):
    return loop.run_until_complete(coro)


def test_ensure_indexes_idempotent(event_loop):
    rep = _run(event_loop, ensure_indexes())
    rep2 = _run(event_loop, ensure_indexes())
    assert rep["collections"] == rep2["collections"]
    # 14 unique collections expected (Phase B 11 + Wave 4 +3)
    assert len(set(rep["collections"])) == 14
    # 4 TTL indexes expected
    assert len(rep["ttl_indexes"]) == 4


def test_all_collection_names_unique_and_arbicore_namespaced():
    names = set(COLLECTION_NAMES.values())
    assert len(names) == len(COLLECTION_NAMES)
    assert all(n.startswith("arbicore_") for n in names)


def test_no_id_field_in_round_trip(event_loop):
    repo = MongoOpportunityRepository()
    opp_id = f"phaseb-rt-{int(time.time()*1000)}"
    opp = CanonicalOpportunity(
        opportunity_id=opp_id,
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        asset="BDAG/USDT",
        subject_id="BDAG/USDT-CEX-SPOT",
        source_data_quality=DataProvenance.REAL,
        status=OpportunityStatus.CANDIDATE,
    )
    _run(event_loop, repo.upsert(opp))
    out = _run(event_loop, repo.get(opp_id))
    assert out is not None
    assert out.opportunity_id == opp_id
    d = out.model_dump(mode="json")
    assert "_id" not in d


def test_mongo_opportunity_repo_rejects_dead(event_loop):
    repo = MongoOpportunityRepository()
    with pytest.raises(ValueError):
        _run(event_loop, repo.upsert(CanonicalOpportunity(
            opportunity_type=OpportunityType.CEX_ARBITRAGE,
            asset="X",
            source_data_quality=DataProvenance.DEAD,
        )))


def test_mongo_outcome_only_insert_semantics(event_loop):
    repo = MongoOutcomeRepository()
    row_id = f"phaseb-oi-{int(time.time()*1000)}"
    r = OutcomeRow(id=row_id, opportunity_id=row_id.replace("oi", "op"),
                   subject_id="S-X", horizon_label="5m", horizon_s=300,
                   due_at=time.time(), evaluated=True, realized_metric=42.0,
                   provenance="REAL")
    assert _run(event_loop, repo.upsert_outcome(r)) is True
    replaced = OutcomeRow(id=row_id, opportunity_id="other",
                          subject_id="S-X", horizon_label="5m", horizon_s=300,
                          due_at=time.time(), evaluated=False, realized_metric=9.0,
                          provenance="REAL")
    assert _run(event_loop, repo.upsert_outcome(replaced, only_insert=True)) is False


def test_inmemory_metrics_and_regime_smoke(event_loop):
    metrics = InMemoryMetricsRepository()
    _run(event_loop, metrics.upsert_signal_metric(SignalMetric(
        signal_id="s1", subject_id=None, horizon_label="5m", sample_count=10,
        score_impact_sum=-1.5, score_impact_mean=-0.15, win_rate=0.4,
        aggregated_at=time.time(),
    )))
    rows = _run(event_loop, metrics.list_signal_metrics(signal_id="s1"))
    assert len(rows) == 1 and rows[0].score_impact_mean == -0.15

    from arbicore.data._inmemory import InMemoryRegimeSnapshotRepository
    regime = InMemoryRegimeSnapshotRepository()
    _run(event_loop, regime.append(RegimeSnapshot(
        captured_at=time.time(), dominant_regime="CALM",
        tags=["asia_session", "thin_liquidity"], confidence=0.7,
    )))
    latest = _run(event_loop, regime.latest())
    assert latest.dominant_regime == "CALM"
    assert "thin_liquidity" in latest.tags
