"""Iteration 5 — Slice 1.1 session-cookie auth gate on /arbicore/opportunities*.

Coverage matrix:
  A. AUTH GATE (new for 1.1):
     A1-A6 anonymous callers get 401 on all 6 endpoints w/ {"detail":"not_authenticated"}.
     A7-A12 invalid bearer -> 401.
     A13-A18 valid cookie -> 200 on GET / mutation OK.
     A19-A24 valid bearer (from cookie value) -> 200 on GET.
     A25 after logout, stale cookie -> 401.

  B. REGRESSION under auth (Slice 1 iter4 findings still hold):
     B1 source='canonical' list/summary
     B2 empty DB → empty items/summary shapes preserved
     B3 unknown opp id → 404 {error:'not_found', id:<id>} on detail/approve/reject
     B4 approve on fresh canonical opp seeds journal ['discovered','operator_approved']
     B5 reject seeds ['discovered','operator_rejected']
     B6 timeline uses RAW kind (no 'journal:' prefix)
     B7 mutations append, no duplicate journal row
     B8 auth v2.9.3 surface unchanged

  C. CONTRACT: 200 shapes byte-identical (fields), filters honored.
  D. PERFORMANCE: latency smoke.
"""
from __future__ import annotations

import os
import statistics
import time
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


@pytest.fixture(scope="module")
def anon() -> requests.Session:
    return requests.Session()


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


@pytest.fixture(scope="module")
def bearer_token() -> str:
    s = requests.Session()
    r = _login(s)
    assert r.status_code == 200
    tok = s.cookies.get("access_token")
    assert tok, "access_token cookie not present after login"
    return tok


def _seed_canonical_opp(mongo, *, status: str = "candidate") -> str:
    opp_id = f"iter5-{status}-{uuid.uuid4().hex[:8]}"
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
        "rejection_reason": None,
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
    mongo[OPPS_COL].delete_many({"opportunity_id": {"$regex": "^iter5-"}})
    mongo[JOURNAL_COL].delete_many({"opportunity_id": {"$regex": "^iter5-"}})


# =========================================================================== A · AUTH GATE

class TestAuthGateAnonymous:
    """All 6 opportunity endpoints must return 401 for anonymous callers."""

    def _assert_401(self, r):
        assert r.status_code == 401, f"expected 401 got {r.status_code}: {r.text[:120]}"
        body = r.json()
        # Body shape: {"detail": "not_authenticated"}
        assert body.get("detail") == "not_authenticated", f"unexpected body: {body}"

    def test_A1_list_anon_401(self, anon):
        self._assert_401(anon.get(f"{API}/arbicore/opportunities"))

    def test_A2_summary_anon_401(self, anon):
        self._assert_401(anon.get(f"{API}/arbicore/opportunities/summary"))

    def test_A3_detail_anon_401(self, anon):
        self._assert_401(anon.get(f"{API}/arbicore/opportunities/some-id"))

    def test_A4_approve_anon_401(self, anon):
        self._assert_401(anon.post(f"{API}/arbicore/opportunities/some-id/approve"))

    def test_A5_reject_anon_401(self, anon):
        self._assert_401(anon.post(f"{API}/arbicore/opportunities/some-id/reject",
                                    json={"reason": "x"}))

    def test_A6_timeline_anon_401(self, anon):
        self._assert_401(anon.get(f"{API}/arbicore/opportunities/some-id/timeline"))


class TestAuthGateInvalidBearer:
    HDR = {"Authorization": "Bearer this-is-not-a-valid-jwt-token"}

    def test_A7_list_bad_bearer_401(self):
        r = requests.get(f"{API}/arbicore/opportunities", headers=self.HDR)
        assert r.status_code == 401
        assert r.json().get("detail") == "not_authenticated"

    def test_A8_summary_bad_bearer_401(self):
        r = requests.get(f"{API}/arbicore/opportunities/summary", headers=self.HDR)
        assert r.status_code == 401

    def test_A9_detail_bad_bearer_401(self):
        r = requests.get(f"{API}/arbicore/opportunities/x", headers=self.HDR)
        assert r.status_code == 401

    def test_A10_approve_bad_bearer_401(self):
        r = requests.post(f"{API}/arbicore/opportunities/x/approve", headers=self.HDR)
        assert r.status_code == 401

    def test_A11_reject_bad_bearer_401(self):
        r = requests.post(f"{API}/arbicore/opportunities/x/reject",
                          headers=self.HDR, json={"reason": "x"})
        assert r.status_code == 401

    def test_A12_timeline_bad_bearer_401(self):
        r = requests.get(f"{API}/arbicore/opportunities/x/timeline", headers=self.HDR)
        assert r.status_code == 401


class TestAuthGateValidCookie:

    def test_A13_list_cookie_200(self, auth_client):
        r = auth_client.get(f"{API}/arbicore/opportunities")
        assert r.status_code == 200
        assert r.json().get("source") == "canonical"

    def test_A14_summary_cookie_200(self, auth_client):
        r = auth_client.get(f"{API}/arbicore/opportunities/summary")
        assert r.status_code == 200
        assert r.json().get("source") == "canonical"

    def test_A15_detail_cookie_known_200(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r = auth_client.get(f"{API}/arbicore/opportunities/{opp_id}")
        assert r.status_code == 200
        body = r.json()
        # Detail returns the opportunity object directly (per iter4 contract)
        got_id = body.get("id") or body.get("item", {}).get("id")
        assert got_id == opp_id, f"expected id {opp_id}, got body keys={list(body)[:8]}"

    def test_A16_approve_cookie_200(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r = auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        assert r.status_code == 200
        b = r.json()
        assert b.get("ok") is True and b.get("id") == opp_id

    def test_A17_reject_cookie_200(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r = auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/reject",
                              json={"reason": "iter5"})
        assert r.status_code == 200
        b = r.json()
        assert b.get("ok") is True and b.get("status") == "rejected"

    def test_A18_timeline_cookie_200(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        r = auth_client.get(f"{API}/arbicore/opportunities/{opp_id}/timeline")
        assert r.status_code == 200


class TestAuthGateValidBearer:
    """Bearer token extracted from access_token cookie must also authenticate."""

    def _hdr(self, token: str):
        return {"Authorization": f"Bearer {token}"}

    def test_A19_list_bearer_200(self, bearer_token):
        r = requests.get(f"{API}/arbicore/opportunities", headers=self._hdr(bearer_token))
        assert r.status_code == 200, r.text[:200]
        assert r.json().get("source") == "canonical"

    def test_A20_summary_bearer_200(self, bearer_token):
        r = requests.get(f"{API}/arbicore/opportunities/summary",
                         headers=self._hdr(bearer_token))
        assert r.status_code == 200

    def test_A21_detail_bearer_200(self, bearer_token, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r = requests.get(f"{API}/arbicore/opportunities/{opp_id}",
                         headers=self._hdr(bearer_token))
        assert r.status_code == 200

    def test_A22_approve_bearer_200(self, bearer_token, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r = requests.post(f"{API}/arbicore/opportunities/{opp_id}/approve",
                          headers=self._hdr(bearer_token))
        assert r.status_code == 200

    def test_A23_reject_bearer_200(self, bearer_token, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r = requests.post(f"{API}/arbicore/opportunities/{opp_id}/reject",
                          headers=self._hdr(bearer_token), json={"reason": "b"})
        assert r.status_code == 200

    def test_A24_timeline_bearer_200(self, bearer_token, mongo):
        opp_id = _seed_canonical_opp(mongo)
        requests.post(f"{API}/arbicore/opportunities/{opp_id}/approve",
                      headers=self._hdr(bearer_token))
        r = requests.get(f"{API}/arbicore/opportunities/{opp_id}/timeline",
                         headers=self._hdr(bearer_token))
        assert r.status_code == 200


class TestAuthGateAfterLogout:

    def test_A25_after_logout_returns_401(self):
        s = requests.Session()
        r = _login(s)
        assert r.status_code == 200
        # Sanity: cookie works
        assert s.get(f"{API}/arbicore/opportunities").status_code == 200
        # Logout
        lo = s.post(f"{API}/auth/logout")
        assert lo.status_code == 200
        # Follow-up call with (now cleared/stale) cookies must 401.
        # requests.Session cookies get cleared by logout Set-Cookie expiry;
        # if server also invalidates, this must 401 either way.
        r2 = s.get(f"{API}/arbicore/opportunities")
        assert r2.status_code == 401, f"expected 401 after logout, got {r2.status_code}"
        assert r2.json().get("detail") == "not_authenticated"


# =========================================================================== B · REGRESSION under auth

class TestRegressionUnderAuth:

    def test_B1_source_canonical(self, auth_client):
        for path in ("/arbicore/opportunities", "/arbicore/opportunities/summary"):
            body = auth_client.get(f"{API}{path}").json()
            assert body.get("source") == "canonical", f"{path}: {body}"

    def test_B2_summary_shape(self, auth_client):
        b = auth_client.get(f"{API}/arbicore/opportunities/summary").json()
        for k in ("total", "by_family", "by_chain", "by_status"):
            assert k in b, f"summary missing {k}"

    def test_B3_unknown_id_404_shape(self, auth_client):
        bogus = "iter5-nope-xyz"
        for method, path in (
            ("get", f"{API}/arbicore/opportunities/{bogus}"),
            ("post", f"{API}/arbicore/opportunities/{bogus}/approve"),
            ("post", f"{API}/arbicore/opportunities/{bogus}/reject"),
        ):
            r = getattr(auth_client, method)(path, json={"reason": "x"}) if method == "post" \
                else getattr(auth_client, method)(path)
            assert r.status_code == 404, f"{path} => {r.status_code}"
            detail = r.json().get("detail", r.json())
            assert detail.get("error") == "not_found"
            assert detail.get("id") == bogus

    def test_B4_approve_seeds_journal(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        assert mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id}) is None
        r = auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        assert r.status_code == 200
        entry = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})
        assert entry is not None
        kinds = [e.get("kind") for e in (entry.get("events") or [])]
        assert "discovered" in kinds and "operator_approved" in kinds
        assert entry.get("execution_status") == r.json().get("status")

    def test_B5_reject_seeds_journal(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r = auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/reject",
                              json={"reason": "iter5"})
        assert r.status_code == 200
        entry = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})
        kinds = [e.get("kind") for e in (entry.get("events") or [])]
        assert "discovered" in kinds and "operator_rejected" in kinds
        assert entry.get("execution_status") == "rejected"

    def test_B6_timeline_raw_kinds_no_prefix(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        tl = auth_client.get(f"{API}/arbicore/opportunities/{opp_id}/timeline").json()
        events = tl.get("events") or tl.get("timeline") or []
        jkinds = [e.get("kind") for e in events if e.get("collection") == "opportunity_journal"]
        assert jkinds
        for k in jkinds:
            assert not str(k).startswith("journal:"), f"prefix leak: {k}"
        assert "operator_approved" in jkinds

    def test_B7_mutations_append_no_dup(self, auth_client, mongo):
        opp_id = _seed_canonical_opp(mongo)
        r1 = auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/approve")
        assert r1.status_code == 200
        n1 = mongo[JOURNAL_COL].count_documents({"opportunity_id": opp_id})
        assert n1 == 1
        ev1 = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})["events"]
        r2 = auth_client.post(f"{API}/arbicore/opportunities/{opp_id}/reject",
                                json={"reason": "flip"})
        assert r2.status_code == 200
        n2 = mongo[JOURNAL_COL].count_documents({"opportunity_id": opp_id})
        assert n2 == 1
        ev2 = mongo[JOURNAL_COL].find_one({"opportunity_id": opp_id})["events"]
        assert len(ev2) > len(ev1)

    def test_B8_auth_surface_unchanged(self):
        # /me anon -> 401
        assert requests.get(f"{API}/auth/me").status_code == 401
        # login cookies HttpOnly + SameSite=Lax
        s = requests.Session()
        r = _login(s)
        assert r.status_code == 200
        sc = r.headers.get("set-cookie", "").lower()
        assert "access_token" in sc and "refresh_token" in sc
        assert "httponly" in sc and "samesite=lax" in sc
        # /me with cookie -> 200
        me = s.get(f"{API}/auth/me")
        assert me.status_code == 200
        assert me.json().get("username") == "admin"
        # logout
        assert s.post(f"{API}/auth/logout").status_code == 200


# =========================================================================== C · CONTRACT

class TestContract:

    REQUIRED_LIST_ITEM_KEYS = {"id", "opportunity_type", "chain", "verdict",
                               "confidence", "canonical"}

    def test_C1_list_shape_and_filters(self, auth_client):
        r = auth_client.get(f"{API}/arbicore/opportunities",
                             params={"limit": 3, "sort_by": "confidence"})
        assert r.status_code == 200
        body = r.json()
        assert body["source"] == "canonical"
        assert isinstance(body["items"], list)
        assert len(body["items"]) <= 3
        confs = [i["confidence"] for i in body["items"]]
        assert confs == sorted(confs, reverse=True)
        for item in body["items"]:
            missing = self.REQUIRED_LIST_ITEM_KEYS - set(item.keys())
            assert not missing, f"list item missing keys: {missing}"
            assert item["canonical"] is True

    def test_C2_min_confidence_filter(self, auth_client):
        r = auth_client.get(f"{API}/arbicore/opportunities",
                             params={"min_confidence": 0.99})
        assert r.status_code == 200
        for i in r.json()["items"]:
            assert i["confidence"] >= 0.99


# =========================================================================== D · PERFORMANCE

class TestPerformance:

    def _time_n(self, sess: requests.Session, path: str, n: int = 12) -> List[float]:
        lats: List[float] = []
        for _ in range(n):
            t0 = time.perf_counter()
            r = sess.get(f"{API}{path}")
            lats.append((time.perf_counter() - t0) * 1000)
            assert r.status_code == 200
        return lats

    def test_D1_list_latency(self, auth_client):
        lats = self._time_n(auth_client, "/arbicore/opportunities")
        avg = statistics.mean(lats)
        p95 = sorted(lats)[int(0.95 * len(lats)) - 1]
        print(f"\n[iter5] /opportunities avg={avg:.2f}ms p95={p95:.2f}ms")
        assert avg < 2000

    def test_D2_summary_latency(self, auth_client):
        lats = self._time_n(auth_client, "/arbicore/opportunities/summary")
        avg = statistics.mean(lats)
        p95 = sorted(lats)[int(0.95 * len(lats)) - 1]
        print(f"\n[iter5] /opportunities/summary avg={avg:.2f}ms p95={p95:.2f}ms")
        assert avg < 2000
