"""Iteration 4 — Slice 1 audit-trail fix verification + regression.

Focus:
  * RETEST HIGH#1 (iter3): approve/reject on a canonically-seeded opp that
    has NO pre-existing journal row must (a) return 200, (b) create a
    journal row seeded via record_discovery, (c) events include 'discovered'
    AND 'operator_approved'/'operator_rejected', (d) execution_status set,
    (e) GET /timeline returns raw kinds (no 'journal:' prefix).
  * REGRESSION: canonical source, no _V2_OPPS, filters/limits/sort, 404
    shape, summary, approve/reject on already-journaled opps still append.
  * Auth v2.9.3 regression.
  * Performance smoke.
"""
from __future__ import annotations

import os
import re
import statistics
import time
import uuid
from typing import Any, Dict, List, Optional

import pytest
import pymongo
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "arbicore_x_hotfix_test")

ADMIN = {"username": "admin", "password": "hotfix-v293"}

OPPS_COL = "arbicore_opportunities"
JOURNAL_COL = "arbicore_opportunity_journal"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client() -> requests.Session:
    """After Slice 1.1 auth gate, tests must authenticate to hit /arbicore/opportunities*."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=10)
    if r.status_code != 200:
        r = s.post(f"{API}/auth/setup", json=ADMIN, timeout=10)
        if r.status_code != 200:
            pytest.skip(f"auth setup/login failed: {r.status_code} {r.text[:120]}")
    return s


@pytest.fixture(scope="module")
def mongo():
    c = pymongo.MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="module")
def auth_client() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=10)
    if r.status_code != 200:
        r = s.post(f"{API}/auth/setup", json=ADMIN, timeout=10)
        if r.status_code != 200:
            pytest.skip(f"auth setup/login failed: {r.status_code} {r.text[:120]}")
    return s


def _seed_canonical_opp(mongo, *, status: str = "candidate",
                         opp_type: str = "CEX_ARBITRAGE",
                         chain: str = "ethereum") -> str:
    """Directly seed a canonical opportunity in Mongo with NO journal row."""
    opp_id = f"iter4-{status}-{uuid.uuid4().hex[:8]}"
    now = "2026-01-01T00:00:00+00:00"
    doc = {
        "opportunity_id": opp_id,
        "opportunity_type": opp_type,
        "subject_id": "ETH-USDT",
        "asset": "ETH-USDT",
        "chain": chain,
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
        "rejection_reason": None,
        "metadata": {},
        "category_metadata": None,
        "created_at": now,
        "updated_at": now,
    }
    mongo[OPPS_COL].update_one(
        {"opportunity_id": opp_id}, {"$set": doc}, upsert=True,
    )
    # Ensure journal row for this opp does NOT exist.
    mongo[JOURNAL_COL].delete_many({"opportunity_id": opp_id})
    return opp_id


# ===========================================================================
# Section A · Audit-trail fix (iter3 HIGH #1 retest)
# ===========================================================================

class TestAuditTrailFix:

    def test_A1_approve_seeds_journal_for_fresh_canonical_opp(self, client, mongo):
        opp_id = _seed_canonical_opp(mongo, status="candidate")
        # Pre-condition: no journal row.
        assert mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id}) is None

        r = client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("id") == opp_id
        assert body.get("status") in ("approved", "validated")

        # Journal row must now exist with both events.
        entry = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})
        assert entry is not None, "journal row was not created by approve"
        kinds = [e.get("kind") for e in (entry.get("events") or [])]
        assert "discovered" in kinds, f"missing 'discovered' seed event; kinds={kinds}"
        assert "operator_approved" in kinds, f"missing 'operator_approved'; kinds={kinds}"
        # execution_status reflects operator decision.
        assert entry.get("execution_status") == body["status"]

    def test_A2_reject_seeds_journal_for_fresh_canonical_opp(self, client, mongo):
        opp_id = _seed_canonical_opp(mongo, status="candidate")
        assert mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id}) is None

        r = client.post(f"{API}/arbicore/opportunities/{opp_id}/reject",
                        json={"reason": "iter4-test"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("status") == "rejected"

        entry = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})
        assert entry is not None, "journal row was not created by reject"
        kinds = [e.get("kind") for e in (entry.get("events") or [])]
        assert "discovered" in kinds
        assert "operator_rejected" in kinds
        assert entry.get("execution_status") == "rejected"

    def test_A3_timeline_returns_raw_kinds_no_prefix(self, client, mongo):
        opp_id = _seed_canonical_opp(mongo, status="candidate")
        r = client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        assert r.status_code == 200

        tl = client.get(f"{API}/arbicore/opportunities/{opp_id}/timeline").json()
        events = tl.get("events") or tl.get("timeline") or []
        # Collect only journal-derived events
        journal_kinds = [e.get("kind") for e in events
                          if e.get("collection") == "opportunity_journal"]
        assert journal_kinds, f"no journal events surfaced in timeline; events={events[:5]}"
        for k in journal_kinds:
            assert not str(k).startswith("journal:"), \
                f"timeline event kind still prefixed: {k}"
        assert "operator_approved" in journal_kinds

    def test_A4_idempotent_append_on_existing_journal_row(self, client, mongo):
        """Reject on an opp that already has a journal row (from an earlier
        discovery/approve) must APPEND, not replace, and not duplicate the row."""
        opp_id = _seed_canonical_opp(mongo, status="candidate")
        # First approve -> creates journal row with discovered + operator_approved
        r1 = client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        assert r1.status_code == 200
        row_count_1 = mongo[JOURNAL_COL].count_documents({"opportunity_id": opp_id})
        assert row_count_1 == 1
        entry1 = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})
        events1 = entry1.get("events") or []

        # Now reject the (approved) opp - FSM allows approved -> rejected
        r2 = client.post(f"{API}/arbicore/opportunities/{opp_id}/reject",
                          json={"reason": "flip"})
        assert r2.status_code == 200
        body2 = r2.json()
        # Should succeed since approved->rejected is a legal transition.
        row_count_2 = mongo[JOURNAL_COL].count_documents({"opportunity_id": opp_id})
        assert row_count_2 == 1, "duplicate journal row created"
        entry2 = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})
        events2 = entry2.get("events") or []
        assert len(events2) > len(events1), "events did not append"
        if body2.get("ok"):
            kinds2 = [e.get("kind") for e in events2]
            assert "operator_rejected" in kinds2

    def test_A5_approve_unknown_id_returns_404_with_error_id(self, client):
        bogus = "iter4-does-not-exist-zzz"
        r = client.post(f"{API}/arbicore/opportunities/{bogus}/approve")
        assert r.status_code == 404
        body = r.json()
        detail = body.get("detail", body)
        assert detail.get("error") == "not_found"
        assert detail.get("id") == bogus

    def test_A6_reject_unknown_id_returns_404_with_error_id(self, client):
        bogus = "iter4-nope-xyz"
        r = client.post(f"{API}/arbicore/opportunities/{bogus}/reject",
                        json={"reason": "test"})
        assert r.status_code == 404
        body = r.json()
        detail = body.get("detail", body)
        assert detail.get("error") == "not_found"
        assert detail.get("id") == bogus


# ===========================================================================
# Section B · Canonical API regression
# ===========================================================================

class TestCanonicalAPIRegression:

    def test_B1_list_source_canonical(self, client):
        r = client.get(f"{API}/arbicore/opportunities")
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "canonical"
        for item in body["items"]:
            assert item.get("canonical") is True

    def test_B2_summary_source_canonical(self, client):
        r = client.get(f"{API}/arbicore/opportunities/summary")
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "canonical"
        assert set(("total", "by_family", "by_chain", "by_status")).issubset(body)

    def test_B3_no_v2_opps_in_code(self):
        with open("/app/app/backend/server.py") as fh:
            src = fh.read()
        offenders = [ln for ln in src.splitlines()
                     if "_V2_OPPS" in ln and not ln.lstrip().startswith("#")]
        assert not offenders, f"_V2_OPPS still referenced: {offenders}"

    def test_B4_no_preview_merged_hybrid_markers(self, client):
        body = client.get(f"{API}/arbicore/opportunities").text.lower().replace(" ", "")
        for marker in ('"source":"preview"', '"source":"merged"', '"source":"hybrid"'):
            assert marker not in body

    def test_B5_limit_and_sort_by_confidence(self, client):
        r = client.get(f"{API}/arbicore/opportunities",
                       params={"limit": 3, "sort_by": "confidence"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) <= 3
        confs = [i["confidence"] for i in items]
        assert confs == sorted(confs, reverse=True)

    def test_B6_detail_unknown_404_shape(self, client):
        r = client.get(f"{API}/arbicore/opportunities/does-not-exist-iter4")
        assert r.status_code == 404
        detail = r.json().get("detail", r.json())
        assert detail.get("error") == "not_found"
        assert detail.get("id") == "does-not-exist-iter4"


# ===========================================================================
# Section C · Auth v2.9.3 regression
# ===========================================================================

class TestAuthRegression:

    def test_C1_me_without_cookie_401(self):
        r = requests.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_C2_login_sets_cookies_httponly_lax(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=ADMIN)
        if r.status_code != 200:
            r = s.post(f"{API}/auth/setup", json=ADMIN)
        assert r.status_code == 200, r.text
        sc = r.headers.get("set-cookie", "").lower()
        assert "access_token" in sc
        assert "refresh_token" in sc
        assert "httponly" in sc
        assert "samesite=lax" in sc

    def test_C3_me_with_cookie(self, auth_client):
        r = auth_client.get(f"{API}/auth/me")
        assert r.status_code == 200
        assert r.json()["username"] == "admin"

    def test_C4_logout_ok(self, auth_client):
        r = auth_client.post(f"{API}/auth/logout")
        assert r.status_code == 200


# ===========================================================================
# Section D · Performance smoke
# ===========================================================================

class TestPerformance:

    def _time_n(self, client, path, n=10):
        lats: List[float] = []
        for _ in range(n):
            t0 = time.perf_counter()
            r = client.get(f"{API}{path}")
            lats.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200
        return lats

    def test_D1_list_latency(self, client):
        lats = self._time_n(client, "/arbicore/opportunities", 10)
        avg = statistics.mean(lats)
        p95 = sorted(lats)[int(0.95 * len(lats)) - 1]
        print(f"\n/opportunities avg={avg:.2f}ms p95={p95:.2f}ms")
        assert avg < 2000

    def test_D2_summary_latency(self, client):
        lats = self._time_n(client, "/arbicore/opportunities/summary", 10)
        avg = statistics.mean(lats)
        p95 = sorted(lats)[int(0.95 * len(lats)) - 1]
        print(f"\n/opportunities/summary avg={avg:.2f}ms p95={p95:.2f}ms")
        assert avg < 2000
