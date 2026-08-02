"""Iter6 — Quote Capture Layer + updated Quote Resolver tests."""
import os
import time
import copy
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
USERNAME = 'admin'
PASSWORD = 'ArbiCore2026!'


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": USERNAME, "password": PASSWORD})
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


# ---------------- GET /quote-capture status ----------------

def test_quote_capture_status_shape(client):
    r = client.get(f"{BASE_URL}/api/execution/quote-capture")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "phase" in d and "generated_at" in d
    assert d.get("fresh_window_s") == 300
    assert "latest" in d and "rolling" in d
    assert "recent_captures" in d and isinstance(d["recent_captures"], list)
    assert len(d["recent_captures"]) <= 20
    assert d["rolling"].get("rolling_window") == 20
    if d["latest"].get("available"):
        for k in ("effective_price",):
            assert k in d["latest"]


def test_quote_capture_list(client):
    r = client.get(f"{BASE_URL}/api/execution/quote-capture/list?limit=10")
    assert r.status_code == 200
    d = r.json()
    assert "captures" in d and isinstance(d["captures"], list)
    assert len(d["captures"]) <= 10


# ---------------- POST /quote-capture validation ----------------

def test_quote_capture_post_zero_input(client):
    r = client.post(f"{BASE_URL}/api/execution/quote-capture",
                    json={"input_amount": 0, "bdag_allocated": 100})
    assert r.status_code == 400, r.text
    assert "input_amount" in (r.json().get("detail") or "")


def test_quote_capture_post_zero_bdag(client):
    r = client.post(f"{BASE_URL}/api/execution/quote-capture",
                    json={"input_amount": 50, "bdag_allocated": 0})
    assert r.status_code == 400, r.text
    assert "bdag_allocated" in (r.json().get("detail") or "")


def test_quote_capture_post_success_and_persist(client):
    payload = {"input_amount": 100, "bdag_allocated": 2777778,
               "source": "swap_ui_api_response", "note": "qa"}
    pre = client.get(f"{BASE_URL}/api/execution/quote-capture").json()
    pre_count = pre.get("rolling", {}).get("count", 0)

    r = client.post(f"{BASE_URL}/api/execution/quote-capture", json=payload)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert "id" in doc
    assert doc["input_amount"] == 100
    assert doc["bdag_allocated"] == 2777778
    assert doc["source"] == "swap_ui_api_response"
    assert doc["note"] == "qa"
    assert doc["input_token"] == "USDT"
    assert "created_at" in doc
    eff = doc["effective_price"]
    assert abs(eff - 3.6e-5) < 1e-7, f"effective_price={eff}"

    # next GET should reflect the new capture
    post = client.get(f"{BASE_URL}/api/execution/quote-capture").json()
    assert post["rolling"]["count"] == pre_count + 1
    assert abs(post["latest"]["effective_price"] - 3.6e-5) < 1e-7


# ---------------- POST /quote-resolver ACTIVE=captured_quote ----------------

def test_quote_resolver_captured_quote_active(client):
    # ensure a fresh capture exists
    client.post(f"{BASE_URL}/api/execution/quote-capture",
                json={"input_amount": 50, "bdag_allocated": 1388889,
                      "source": "swap_ui_state_observed", "note": "iter6_fresh"})
    r = client.post(f"{BASE_URL}/api/execution/quote-resolver",
                    json={"investment_usd": 50})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["active_strategy"] == "captured_quote", d.get("active_strategy")
    assert d["verdict"] == "READY", d.get("reasons")
    assert abs(d["quote"]["effective_price"] - 3.6e-5) < 1e-6
    # implied_bonus_pct may be present from the calibration block (10-13%)
    ibp = d["quote"].get("implied_bonus_pct")
    if ibp is not None:
        assert 5 <= ibp <= 20, f"implied_bonus_pct={ibp}"

    strategies = {s["strategy"]: s for s in d["strategies"]}
    assert strategies["captured_quote"]["status"] == "ACTIVE"
    assert strategies["executed_calibration"]["status"] == "WAITING"
    assert strategies["eth_call_preview"]["status"] == "NOT_APPLICABLE"
    assert strategies["ui_quote_api"]["status"] == "endpoint_unknown"

    sd = d["strategy_details"]
    for key in ("captured_quote", "executed_calibration",
                "eth_call_preview", "ui_quote_api"):
        assert key in sd, f"strategy_details missing {key}"
    assert d.get("consumed_by_arbicore_for_roi") is False


# ---------------- GET /quote-resolver/strategies ----------------

def test_strategies_eth_not_applicable(client):
    r = client.get(f"{BASE_URL}/api/execution/quote-resolver/strategies")
    assert r.status_code == 200
    d = r.json()
    strategies = {s["strategy"]: s for s in d["strategies"]}
    assert strategies["eth_call_preview"]["status"] == "NOT_APPLICABLE"
    note = (strategies["eth_call_preview"].get("note") or "").lower()
    assert "blockdag" in note


# ---------------- Hard guardrails ----------------

def test_execution_disabled(client):
    r = client.get(f"{BASE_URL}/api/execution/status")
    assert r.status_code == 200
    assert r.json()["execution_enabled"] is False


def test_intel_buy_price_unchanged(client):
    # find a BDAG route
    import pymongo
    # find any BDAG route via the cycle-model
    cm = client.get(f"{BASE_URL}/api/execution/cycle-model").json()
    route_id = cm.get("route", {}).get("id") or cm.get("route_id")
    if not route_id:
        pytest.skip("no route id available from cycle-model")
    r = client.get(f"{BASE_URL}/api/execution/intel/{route_id}")
    assert r.status_code == 200
    bp = r.json().get("buy_price")
    # should still be Portal Feed price ~4e-5, NOT the captured 3.6e-5
    assert bp is not None
    assert bp > 3.7e-5, f"buy_price={bp} appears polluted by capture"


# ---------------- Precedence proof (drop + restore) ----------------

@pytest.fixture
def mongo_coll():
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get('MONGO_URL')
        db_name = os.environ.get('DB_NAME')
        if not mongo_url or not db_name:
            pytest.skip("MONGO_URL/DB_NAME not exported")
        c = MongoClient(mongo_url)
        return c[db_name]["executable_quote_captures"]
    except Exception as e:
        pytest.skip(f"mongo unavailable: {e}")


def test_precedence_falls_through_without_captures(client, mongo_coll):
    rows = list(mongo_coll.find({}))
    backup = copy.deepcopy(rows)
    try:
        mongo_coll.delete_many({})
        r = client.post(f"{BASE_URL}/api/execution/quote-resolver",
                        json={"investment_usd": 50})
        assert r.status_code == 200
        d = r.json()
        # Should NOT be captured_quote
        assert d["active_strategy"] != "captured_quote"
        strategies = {s["strategy"]: s for s in d["strategies"]}
        cap_status = (strategies["captured_quote"]["status"] or "").lower()
        assert "no_captures" in cap_status or cap_status == "no_captures"
    finally:
        if backup:
            for r in backup:
                r.pop("_id", None)
            mongo_coll.insert_many(backup)


def test_freshness_falls_through_when_stale(client, mongo_coll):
    from datetime import datetime, timezone, timedelta
    # Capture original latest doc
    latest = list(mongo_coll.find({}).sort("created_at", -1).limit(1))
    if not latest:
        pytest.skip("no captures to backdate")
    doc = latest[0]
    original_created_at = doc["created_at"]
    backdated = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    try:
        # backdate ALL rows to fall outside fresh window
        all_rows = list(mongo_coll.find({}))
        original_map = {r["_id"]: r["created_at"] for r in all_rows}
        mongo_coll.update_many({}, {"$set": {"created_at": backdated}})

        r = client.post(f"{BASE_URL}/api/execution/quote-resolver",
                        json={"investment_usd": 50})
        d = r.json()
        assert d["active_strategy"] != "captured_quote"
        cap = d["strategy_details"]["captured_quote"]
        assert cap.get("available") is False
        assert cap.get("status") == "stale"
    finally:
        # restore all created_at values
        for _id, ca in original_map.items():
            mongo_coll.update_one({"_id": _id}, {"$set": {"created_at": ca}})
