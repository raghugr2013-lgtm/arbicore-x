"""Iteration 7 — Slice 2 RETEST after C7 fix.

New coverage vs iter6:
  C7   watch on REJECTED  -> ok:false, error contains 'rejected' and 'validated'
  C7b  watch on APPROVED  -> ok:false, InvalidTransitionError
  C7c  watch on VALIDATED -> ok:false, canonical FSM disallows validated->validated
  C7d  promote on REJECTED -> ok:false
  C7e  promote on APPROVED -> ok:false (approved->approved disallowed)
  C7f  promote from CANDIDATE (regression) -> ok:true, status:PROMOTED
  C7g  promote from VALIDATED (WATCHING) -> ok:true, status:PROMOTED (no double txn)
  C7h  dismiss on REJECTED -> ok:false (canonical disallows re-rejection)

Also asserts:
  - the failing responses do NOT mutate the underlying opp row
  - the failing responses do NOT add a new journal event
"""
from __future__ import annotations

import os
import uuid
from typing import List

import pymongo
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "arbicore_x_hotfix_test")

ADMIN = {"username": "admin", "password": "hotfix-v293"}

OPPS_COL = "arbicore_opportunities"
JOURNAL_COL = "arbicore_opportunity_journal"


# --------------------------------------------------------------------------- fixtures

@pytest.fixture(scope="module")
def mongo():
    return pymongo.MongoClient(MONGO_URL)[DB_NAME]


def _login(sess: requests.Session) -> requests.Response:
    r = sess.post(f"{API}/auth/login", json=ADMIN, timeout=10)
    if r.status_code != 200:
        r = sess.post(f"{API}/auth/setup", json=ADMIN, timeout=10)
    return r


@pytest.fixture(scope="module")
def auth_client() -> requests.Session:
    s = requests.Session()
    r = _login(s)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:120]}")
    return s


def _seed(mongo, *, status: str) -> str:
    opp_id = f"iter7-{status}-{uuid.uuid4().hex[:8]}"
    now = "2026-01-01T00:00:00+00:00"
    doc = {
        "opportunity_id": opp_id,
        "opportunity_type": "CEX_ARBITRAGE",
        "subject_id": "ETH-USDT",
        "asset": "ETH-USDT",
        "chain": "ethereum",
        "buy_venue": "binance",
        "sell_venue": "kucoin",
        "buy_price": 3000.0,
        "sell_price": 3005.0,
        "spread_pct": 0.001667,
        "expected_profit_usd": 50.0,
        "capital_required_usd": 10000.0,
        "confidence_score": 80.0,
        "risk_score": 20.0,
        "liquidity_score": 90.0,
        "execution_feasibility": 0.9,
        "mev_risk_level": "LOW",
        "market_regime": "UNKNOWN",
        "market_regime_tags": None,
        "route_health": "UNKNOWN",
        "source_data_quality": "SIMULATED",
        "status": status,
        "rejection_reason": "seed" if status == "rejected" else None,
        "metadata": {},
        "category_metadata": None,
        "created_at": now,
        "updated_at": now,
    }
    mongo[OPPS_COL].update_one({"opportunity_id": opp_id}, {"$set": doc}, upsert=True)
    mongo[JOURNAL_COL].delete_many({"opportunity_id": opp_id})
    return opp_id


@pytest.fixture(scope="module", autouse=True)
def _cleanup(mongo):
    yield
    mongo[OPPS_COL].delete_many({"opportunity_id": {"$regex": "^iter7-"}})
    mongo[JOURNAL_COL].delete_many({"opportunity_id": {"$regex": "^iter7-"}})


def _journal_count(mongo, opp_id: str) -> int:
    row = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})
    if not row:
        return 0
    return len(row.get("events") or [])


def _assert_invalid_transition(body: dict, *, expected_ui_status: str):
    """Common assertion for C7* invalid-FSM cases."""
    assert body.get("ok") is False, f"expected ok:false, got {body}"
    assert "error" in body and isinstance(body["error"], str) and body["error"], \
        f"error string missing: {body}"
    assert body.get("status") == expected_ui_status, \
        f"expected UI status {expected_ui_status}, got {body.get('status')}"


# =========================================================================== C7 · watch on REJECTED

class TestInvalidTransitions:

    def test_C7_watch_on_rejected(self, auth_client, mongo):
        opp_id = _seed(mongo, status="rejected")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "watch"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        _assert_invalid_transition(b, expected_ui_status="DISMISSED")
        assert b.get("id") == opp_id
        assert b.get("action") == "watch"
        # Error must mention 'rejected' and 'validated'
        err = b["error"].lower()
        assert "rejected" in err and "validated" in err, \
            f"expected 'rejected'/'validated' in error, got: {b['error']}"
        # No mutation
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "rejected"
        # No new journal event
        assert _journal_count(mongo, opp_id) == 0

    def test_C7b_watch_on_approved(self, auth_client, mongo):
        opp_id = _seed(mongo, status="approved")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "watch"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        _assert_invalid_transition(b, expected_ui_status="PROMOTED")
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "approved"
        assert _journal_count(mongo, opp_id) == 0

    def test_C7c_watch_on_validated(self, auth_client, mongo):
        opp_id = _seed(mongo, status="validated")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "watch"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        _assert_invalid_transition(b, expected_ui_status="WATCHING")
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "validated"
        assert _journal_count(mongo, opp_id) == 0

    def test_C7d_promote_on_rejected(self, auth_client, mongo):
        opp_id = _seed(mongo, status="rejected")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "promote"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        _assert_invalid_transition(b, expected_ui_status="DISMISSED")
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "rejected"
        assert _journal_count(mongo, opp_id) == 0

    def test_C7e_promote_on_approved(self, auth_client, mongo):
        opp_id = _seed(mongo, status="approved")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "promote"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        _assert_invalid_transition(b, expected_ui_status="PROMOTED")
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "approved"
        assert _journal_count(mongo, opp_id) == 0

    def test_C7f_promote_from_candidate_regression(self, auth_client, mongo):
        opp_id = _seed(mongo, status="candidate")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "promote"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True, f"expected ok:true, got {b}"
        assert b.get("status") == "PROMOTED"
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "approved"

    def test_C7g_promote_from_validated_regression(self, auth_client, mongo):
        opp_id = _seed(mongo, status="validated")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "promote"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        assert b.get("ok") is True, f"expected ok:true from validated->promoted, got {b}"
        assert b.get("status") == "PROMOTED"
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "approved"

    def test_C7h_dismiss_on_rejected(self, auth_client, mongo):
        opp_id = _seed(mongo, status="rejected")
        r = auth_client.post(
            f"{API}/arbicore/discovery/candidates/{opp_id}/action",
            params={"action": "dismiss"},
        )
        assert r.status_code == 200, r.text
        b = r.json()
        _assert_invalid_transition(b, expected_ui_status="DISMISSED")
        row = mongo[OPPS_COL].find_one({"opportunity_id": opp_id})
        assert row["status"] == "rejected"
        assert _journal_count(mongo, opp_id) == 0
