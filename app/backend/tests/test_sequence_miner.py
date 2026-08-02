"""Phase C Wave 3 — Sequence Miner tests (Mongo-backed; uses module-scoped loop)."""
import asyncio
import time

import pytest

from arbicore.learning.concrete.sequence_miner import (
    MIN_SUPPORT,
    SequenceMiner,
    _pattern_id,
    _smoothed_confidence,
)


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


def test_pattern_id_deterministic():
    p1 = _pattern_id(["CALM", "TRENDING"])
    p2 = _pattern_id(["CALM", "TRENDING"])
    p3 = _pattern_id(["VOLATILE"])
    assert p1 == p2
    assert p1 != p3
    assert p1.startswith("seq:") and len(p1) > 4


def test_smoothed_confidence_bounds():
    assert _smoothed_confidence(0, 0) == 0.5  # no data → 50%
    high = _smoothed_confidence(99, 100)
    low = _smoothed_confidence(1, 100)
    assert 0.0 < low < 0.5 < high < 1.0


def test_mine_with_no_data_no_throws(event_loop):
    from arbicore.data.mongo.regime_snapshot_repo_mongo import (
        MongoRegimeSnapshotRepository,
    )
    miner = SequenceMiner(regime_repo=MongoRegimeSnapshotRepository())
    result = _run(event_loop, miner.mine())
    assert "patterns_written" in result
    assert result["patterns_written"] >= 0


def test_count_endpoint(event_loop):
    from arbicore.data.mongo.regime_snapshot_repo_mongo import (
        MongoRegimeSnapshotRepository,
    )
    miner = SequenceMiner(regime_repo=MongoRegimeSnapshotRepository())
    n = _run(event_loop, miner.count())
    assert isinstance(n, int) and n >= 0


def test_list_patterns_respects_min_support(event_loop):
    from arbicore.data.mongo.regime_snapshot_repo_mongo import (
        MongoRegimeSnapshotRepository,
    )
    miner = SequenceMiner(regime_repo=MongoRegimeSnapshotRepository())
    rows = _run(event_loop, miner.list_patterns(limit=10, min_support=100_000))
    # Almost certainly no patterns with support ≥ 100k yet
    assert rows == []
