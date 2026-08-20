"""Phase C Wave 2 — HTTP endpoint tests."""
import asyncio
import os
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://defi-exec-audit.preview.emergentagent.com",
).rstrip("/")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ArbiCore2026!"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login unavailable ({r.status_code})")
    return s


def test_learning_status_advertises_wave_2(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/learning-status", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["wave"] in ("C-2", "C-3", "C-4", "C-5")  # wave advances as Phase C waves ship


def test_weights_current_returns_neutral_defaults(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/weights/current", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["neutral_default"] == 1.0
    assert body["min"] == 0.1
    assert body["max"] == 2.0
    assert isinstance(body["weights"], dict)


def test_confidence_score_endpoint(auth_session):
    """Insert an opportunity via the Mongo adapter, then score it via API."""
    import os
    from motor.motor_asyncio import AsyncIOMotorClient
    from services import db as _db_mod

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _db_mod.client = AsyncIOMotorClient(os.environ['MONGO_URL'], io_loop=loop)
    _db_mod.db = _db_mod.client[os.environ['DB_NAME']]

    from arbicore.data.mongo.opportunity_repo_mongo import MongoOpportunityRepository
    from arbicore.models import (
        CanonicalOpportunity, OpportunityType, OpportunityStatus, DataProvenance,
    )
    repo = MongoOpportunityRepository()
    opp_id = f"w2-confidence-{int(time.time()*1000)}"
    opp = CanonicalOpportunity(
        opportunity_id=opp_id,
        opportunity_type=OpportunityType.CEX_ARBITRAGE,
        asset="A/B",
        subject_id="subj-w2",
        source_data_quality=DataProvenance.REAL,
        status=OpportunityStatus.CANDIDATE,
        category_metadata={"venue_health_score": 80.0, "fee_drag_pct": 0.1},
    )
    loop.run_until_complete(repo.upsert(opp))

    r = auth_session.get(
        f"{BASE_URL}/api/arbicore/confidence/score",
        params={"opportunity_id": opp_id},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["opportunity_id"] == opp_id
    assert 0.0 <= body["confidence"] <= 100.0
    assert "breakdown" in body
    assert "signal_contributions" in body["breakdown"]


def test_confidence_score_404_for_missing(auth_session):
    r = auth_session.get(
        f"{BASE_URL}/api/arbicore/confidence/score",
        params={"opportunity_id": "nope-deadbeef"},
        timeout=10,
    )
    assert r.status_code == 404


def test_no_write_endpoints_added_in_wave_2(auth_session):
    for path in ("weights/current", "confidence/score"):
        for verb in ("post", "put", "delete"):
            r = getattr(auth_session, verb)(
                f"{BASE_URL}/api/arbicore/{path}", timeout=10,
            )
            assert r.status_code in (404, 405)


def test_health_endpoint_still_works_after_wave_2(auth_session):
    """Zero-impact regression for the foundation health endpoint."""
    r = auth_session.get(f"{BASE_URL}/api/arbicore/health", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["phase"] == "B"
    assert body["wiring"]["outcome_tracker_alive"] is True
