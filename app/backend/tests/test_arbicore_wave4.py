"""Phase C Wave 4 — Universal Entity Intelligence tests."""
import asyncio
import os
import time

import pytest
import requests

from arbicore.intel import EntityType, ref_id, ref_to_entity_id


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://arbicore-canonical-1.preview.emergentagent.com",
).rstrip("/")


@pytest.fixture(scope="module")
def event_loop():
    import os as _os
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import db as _db_mod
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _db_mod.client = AsyncIOMotorClient(_os.environ['MONGO_URL'], io_loop=loop)
    _db_mod.db = _db_mod.client[_os.environ['DB_NAME']]
    yield loop
    loop.close()


def _run(loop, coro):
    return loop.run_until_complete(coro)


# ---- Pure unit tests --------------------------------------------------------

def test_ref_id_deterministic_and_distinct():
    a = ref_id("evm_address", "0xABC")
    b = ref_id("evm_address", "0xABC")
    c = ref_id("cex_handle", "0xABC")
    d = ref_id("evm_address", "0xDEF")
    assert a == b
    assert a != c
    assert a != d
    assert a.startswith("ent:")


def test_ref_to_entity_id_uses_alphabetical_first_key():
    refs1 = {"evm_address": "0xABC", "chain": "evm"}
    refs2 = {"chain": "evm", "evm_address": "0xABC"}
    assert ref_to_entity_id(refs1) == ref_to_entity_id(refs2)
    # 'chain' is alphabetically before 'evm_address'
    assert ref_to_entity_id(refs1) == ref_id("chain", "evm")


def test_ref_to_entity_id_empty_raises():
    with pytest.raises(ValueError):
        ref_to_entity_id({})


def test_entity_type_enum_has_nine_values():
    assert len(list(EntityType)) == 9
    assert EntityType.WALLET.value == "WALLET"
    assert EntityType.MARKET_MAKER.value == "MARKET_MAKER"


# ---- Resolver / Repository --------------------------------------------------

def test_resolver_creates_entity_for_real_provenance(event_loop):
    from arbicore.intel import EntityResolver, MongoEntityRepository
    from arbicore.models.enums import DataProvenance
    resolver = EntityResolver()
    repo = MongoEntityRepository()
    ref = f"0xAAA-{int(time.time()*1000)}"
    eid = _run(event_loop, resolver.resolve_or_create(
        "evm_address", ref, entity_type=EntityType.WALLET,
        provenance=DataProvenance.REAL,
    ))
    assert eid is not None
    assert eid.startswith("ent:")
    e = _run(event_loop, repo.get(eid))
    assert e is not None
    assert e.entity_type == EntityType.WALLET.value


def test_resolver_rejects_simulated_provenance(event_loop):
    from arbicore.intel import EntityResolver
    from arbicore.models.enums import DataProvenance
    resolver = EntityResolver()
    eid = _run(event_loop, resolver.resolve_or_create(
        "evm_address", "0xSIM", provenance=DataProvenance.SIMULATED,
    ))
    assert eid is None


def test_lookup_by_ref_round_trips(event_loop):
    from arbicore.intel import EntityResolver
    from arbicore.models.enums import DataProvenance
    resolver = EntityResolver()
    ref = f"@maker-{int(time.time()*1000)}"
    created = _run(event_loop, resolver.resolve_or_create(
        "cex_handle", ref, entity_type=EntityType.MARKET_MAKER,
        provenance=DataProvenance.REAL,
    ))
    looked = _run(event_loop, resolver.lookup_by_ref("cex_handle", ref))
    assert looked == created


# ---- Cluster detector -------------------------------------------------------

def test_cluster_detector_no_data_no_throws(event_loop):
    from arbicore.intel import EntityClusterDetector
    det = EntityClusterDetector()
    result = _run(event_loop, det.detect(min_cooccur=100))
    assert result["clusters_written"] >= 0


# ---- Scorer -----------------------------------------------------------------

def test_scorer_records_and_reads(event_loop):
    from arbicore.data.mongo.metrics_repo_mongo import MongoMetricsRepository
    from arbicore.intel import EntityScorer
    from arbicore.models.enums import DataProvenance
    scorer = EntityScorer(MongoMetricsRepository())
    eid = f"ent:test-{int(time.time()*1000)}"
    ok1 = _run(event_loop, scorer.record_outcome(
        eid, EntityType.SMART_MONEY, succeeded=True,
        outcome_score=1.0, provenance=DataProvenance.REAL,
    ))
    ok2 = _run(event_loop, scorer.record_outcome(
        eid, EntityType.SMART_MONEY, succeeded=False,
        outcome_score=-0.5, provenance=DataProvenance.REAL,
    ))
    assert ok1 and ok2
    s = _run(event_loop, scorer.get(eid))
    assert s is not None
    assert s.sample_count == 2
    assert 0.0 < s.success_rate < 1.0
    assert s.entity_type == EntityType.SMART_MONEY.value


def test_scorer_provenance_gate(event_loop):
    from arbicore.data.mongo.metrics_repo_mongo import MongoMetricsRepository
    from arbicore.intel import EntityScorer
    from arbicore.models.enums import DataProvenance
    scorer = EntityScorer(MongoMetricsRepository())
    ok = _run(event_loop, scorer.record_outcome(
        "ent:noop", EntityType.WALLET, succeeded=True,
        outcome_score=1.0, provenance=DataProvenance.DEAD,
    ))
    assert ok is False


# ---- HTTP endpoints --------------------------------------------------------

@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore2026!"},
               timeout=15)
    if r.status_code != 200:
        pytest.skip("admin login unavailable")
    return s


def test_learning_status_advertises_wave_4(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/learning-status", timeout=10)
    assert r.status_code == 200
    # Wave label moves forward as Phase C waves ship — wave 4 endpoints
    # remain available under any wave >= 4.
    assert r.json()["wave"] in ("C-4", "C-5")


def test_entities_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/entities?limit=10", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and isinstance(body["items"], list)


def test_entities_endpoint_rejects_invalid_type(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/entities?entity_type=BOGUS", timeout=10)
    assert r.status_code == 400


def test_clusters_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/entities/clusters", timeout=10)
    assert r.status_code == 200
    assert "items" in r.json()


def test_scores_top_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/entities/scores/top", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json()["items"], list)


def test_entity_404_for_missing(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/entities/ent:nonexistent", timeout=10)
    assert r.status_code == 404


def test_no_write_endpoints_in_wave_4(auth_session):
    for path in ("entities", "entities/clusters", "entities/scores/top"):
        for verb in ("post", "put", "delete"):
            r = getattr(auth_session, verb)(f"{BASE_URL}/api/arbicore/{path}", timeout=10)
            assert r.status_code in (404, 405)
