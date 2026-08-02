"""Backend tests for the Quote Resolver (read-only, non-committing).

Covers:
  - Auth via httpOnly cookie
  - POST /api/execution/quote-resolver with various investment amounts ($50/$500/$1000/$5000)
  - Validation (0 and negative amounts)
  - Strategy precedence + calibration shape
  - GET /api/execution/quote-resolver/strategies overview
  - Negative path: drop empirical-quote samples → verify NO_GO / needs_samples → restore
  - Hard guardrails: execution_enabled=false; arbitrage_intel buy_price unchanged
"""
import os
import time
import requests
import pytest
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCore2026!"

# Direct mongo handle (negative-path capture/restore)
MONGO_URL = os.environ.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME", "test_database")


# ---------------- Fixtures ----------------

@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS},
               timeout=15)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    return s


@pytest.fixture(scope="module")
def mongo_db():
    if not MONGO_URL:
        pytest.skip("MONGO_URL env var not set")
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


# ---------------- Quote Resolver POST ----------------

class TestQuoteResolver:
    def test_quote_50_ready(self, session):
        t0 = time.time()
        r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                         json={"investment_usd": 50}, timeout=20)
        elapsed = time.time() - t0
        assert r.status_code == 200, r.text[:300]
        assert elapsed < 12, f"Quote took {elapsed:.1f}s (>12s budget)"
        d = r.json()

        assert d["active_strategy"] == "executed_calibration"
        assert d["verdict"] == "READY", f"verdict={d['verdict']} reasons={d.get('reasons')}"

        q = d["quote"]
        assert abs(q["bdag_expected"] - 1388889) < 200, f"bdag_expected={q['bdag_expected']}"
        assert abs(q["effective_price"] - 3.6e-5) / 3.6e-5 < 0.01
        assert abs(q["implied_bonus_pct"] - 10.847) < 0.5

        e = d["economics"]
        assert e["available"] is True
        assert e["roi_pct"] > 2.0, f"roi_pct={e['roi_pct']}"
        assert e["roi_pct"] < 10.0  # near 5.57%
        assert e["meets_coinstore_min_deposit"] is True
        # Venue can be xt or coinstore per test brief
        assert e["venue"] in ("xt", "coinstore"), f"venue={e['venue']}"

        assert d["consumed_by_arbicore_for_roi"] is False
        consts = d["constants"]
        assert consts["min_calibration_samples"] == 3
        assert consts["coinstore_min_deposit_bdag"] == 3703
        assert consts["fresh_roi_floor_pct"] == 2.0

    def test_quote_500_higher_roi(self, session):
        r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                         json={"investment_usd": 500}, timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert d["verdict"] == "READY"
        assert d["quote"]["bdag_expected"] > 13_000_000, \
            f"bdag_expected@$500={d['quote']['bdag_expected']}"
        assert abs(d["quote"]["effective_price"] - 3.6e-5) / 3.6e-5 < 0.01
        assert abs(d["quote"]["implied_bonus_pct"] - 10.847) < 0.5
        # ROI should be ~7.5% (larger size dilutes fixed-fee drag)
        assert 5.0 < d["economics"]["roi_pct"] < 10.0, \
            f"roi_pct@$500={d['economics']['roi_pct']}"

    def test_quote_roi_increases_with_size(self, session):
        rois = {}
        for amt in (50, 500, 1000, 5000):
            r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                             json={"investment_usd": amt}, timeout=20)
            assert r.status_code == 200, f"{amt} -> {r.status_code}"
            d = r.json()
            assert d["verdict"] == "READY", f"verdict@${amt}={d['verdict']}"
            rois[amt] = d["economics"]["roi_pct"]
        # Strictly increasing ROI with size (fixed-cost dilution)
        assert rois[50] < rois[500] < rois[1000] < rois[5000], rois

    def test_quote_zero_amount_rejected(self, session):
        r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                         json={"investment_usd": 0}, timeout=10)
        # Should be HTTP 400 per spec, but allow 422 as well if Pydantic raises
        assert r.status_code in (400, 422), r.status_code
        # The detail message should mention > 0
        body = r.json()
        detail = str(body.get("detail", body))
        assert "> 0" in detail or "greater" in detail.lower(), detail

    def test_quote_negative_amount_rejected(self, session):
        r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                         json={"investment_usd": -5}, timeout=10)
        assert r.status_code in (400, 422), r.status_code

    def test_quote_strategies_shape(self, session):
        r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                         json={"investment_usd": 50}, timeout=20)
        d = r.json()
        strats = d["strategies"]
        assert len(strats) == 3
        names = [s["strategy"] for s in strats]
        assert names == ["executed_calibration", "eth_call_preview", "ui_quote_api"]

        # executed_calibration should be ACTIVE (we have ≥3 samples)
        ec = next(s for s in strats if s["strategy"] == "executed_calibration")
        assert ec["status"] == "ACTIVE"

        # eth_call_preview is not_configured
        eth = next(s for s in strats if s["strategy"] == "eth_call_preview")
        assert eth["status"] == "not_configured"
        eth_needs = d["strategy_details"]["eth_call_preview"]["needs"]
        assert eth_needs["swap_contract_address"] is None
        assert eth_needs["swap_preview_fn_signature"] is None
        assert eth_needs["evm_rpc_url"] is None

        # ui_quote_api endpoint_unknown
        ui = next(s for s in strats if s["strategy"] == "ui_quote_api")
        assert ui["status"] == "endpoint_unknown"

    def test_quote_calibration_detail(self, session):
        r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                         json={"investment_usd": 50}, timeout=20)
        d = r.json()
        cal = d["strategy_details"]["executed_calibration"]["calibration"]
        assert abs(cal["live_api_base_price"] - 4.038e-5) / 4.038e-5 < 0.1, \
            f"live_api_base_price={cal['live_api_base_price']}"
        assert abs(cal["rolling_avg_effective_price"] - 3.6e-5) / 3.6e-5 < 0.01
        assert abs(cal["bonus_factor"] - 0.8915) < 0.02
        assert abs(cal["implied_bonus_pct"] - 10.847) < 0.5
        assert cal["samples_count"] >= 3
        assert cal["min_samples_required"] == 3
        assert cal["confidence"] in ("medium", "high")

    def test_cross_check_matches(self, session):
        r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                         json={"investment_usd": 50}, timeout=20)
        d = r.json()
        cc = d["cross_check"]
        assert cc["executable_quote_authoritative_source"] == "executed_history"
        assert cc["matches_chosen_quote"] is True


# ---------------- Strategies overview GET ----------------

class TestStrategiesOverview:
    def test_get_strategies(self, session):
        r = session.get(f"{BASE_URL}/api/execution/quote-resolver/strategies", timeout=15)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert len(d["strategies"]) == 3
        cfg = d["configuration"]
        assert cfg["ui_quote_endpoint_hint"] is None
        assert cfg["swap_contract_address"] is None
        assert cfg["swap_preview_fn_signature"] is None
        assert cfg["evm_rpc_url"] is None
        assert cfg["min_calibration_samples"] == 3


# ---------------- Hard guardrails ----------------

class TestHardGuardrails:
    def test_execution_disabled_unchanged(self, session):
        r = session.get(f"{BASE_URL}/api/execution/status", timeout=10)
        assert r.status_code == 200
        assert r.json()["execution_enabled"] is False

    def test_intel_buy_price_unchanged(self, session):
        # Pick the first BDAG route id (try /api/routes first)
        routes = session.get(f"{BASE_URL}/api/routes", timeout=10)
        if routes.status_code != 200:
            pytest.skip(f"/api/routes returned {routes.status_code}")
        rlist = routes.json()
        rid = None
        items = rlist if isinstance(rlist, list) else (
            rlist.get("routes") or rlist.get("items") or [])
        for it in items:
            pa = (it.get("purchase") or {}).get("asset")
            if pa == "BDAG":
                rid = it.get("id")
                break
        if not rid:
            pytest.skip("No BDAG route id discoverable")
        r = session.get(f"{BASE_URL}/api/execution/intel/{rid}", timeout=15)
        assert r.status_code == 200
        intel = r.json()
        # buy_price should NOT be 3.6e-5 (the executed-history value).
        # It should still be the Portal Feed live-API-base value (~4.0e-5).
        bp = intel.get("buy_price")
        assert bp is not None
        assert bp > 3.8e-5, f"intel buy_price={bp} — looks like resolver leaked into ROI"


# ---------------- Negative path ----------------

class TestNegativePath:
    """Capture + drop + verify NO_GO + restore the empirical-quote rows."""

    def test_no_samples_returns_no_go(self, session, mongo_db):
        col = mongo_db["buy_price_empirical_quotes"]
        captured = list(col.find({}))
        try:
            if captured:
                col.delete_many({})
            r = session.post(f"{BASE_URL}/api/execution/quote-resolver",
                             json={"investment_usd": 50}, timeout=20)
            assert r.status_code == 200, r.text[:300]
            d = r.json()
            # No production-grade strategy: active_strategy=None and verdict=NO_GO
            assert d["active_strategy"] is None, f"active_strategy={d['active_strategy']}"
            assert d["verdict"] == "NO_GO"
            assert any("No production-grade strategy" in s for s in d.get("reasons", []))
            ec = d["strategy_details"]["executed_calibration"]
            assert ec["status"] in ("needs_samples", "unavailable"), ec["status"]
        finally:
            # RESTORE — strip _id from captured docs before insert
            if captured:
                for doc in captured:
                    doc.pop("_id", None)
                col.insert_many(captured)
            # Verify post-restore count matches
            assert col.count_documents({}) == len(captured)
