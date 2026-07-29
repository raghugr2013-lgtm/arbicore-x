"""Phase E1 — Portal Price Connector LIVE tests against public URL.

Validates auth-gated endpoints, status shape, history series, manual refresh,
route snapshot portal_price block, evaluation price_source, manual_buy.override
persistence via PATCH, and observation recorder regression.
"""
import os
import time
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / "frontend" / ".env")

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"
USERNAME = "admin"
PASSWORD = "ArbiCore#2026"


@pytest.fixture(scope="module")
def anon():
    with httpx.Client(base_url=API, timeout=30, follow_redirects=True) as c:
        yield c


@pytest.fixture(scope="module")
def authed():
    with httpx.Client(base_url=API, timeout=60, follow_redirects=True) as c:
        r = c.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert r.status_code == 200, f"login failed: {r.text}"
        yield c


# --- auth gating ---
def test_portal_endpoints_anon_401(anon):
    assert anon.get("/portal/price").status_code == 401
    assert anon.get("/portal/price/history").status_code == 401
    assert anon.post("/portal/price/refresh").status_code == 401


# --- status shape ---
def test_portal_price_status_live(authed):
    d = authed.get("/portal/price").json()
    assert d["running"] is True
    assert d["poll_interval_s"] == 60
    assert d["source"].endswith("/getInfo")
    assert isinstance(d["bdag_price"], (int, float))
    assert 1e-6 < d["bdag_price"] < 1e-3, f"bdag_price out of range: {d['bdag_price']}"
    assert d["stale"] is False
    assert "ETH" in d["coin_prices"]
    assert "BNB" in d["coin_prices"]
    assert d["snapshots_total"] > 0
    assert "no execution" in d["note"].lower()


# --- history ---
def test_portal_price_history_live(authed):
    d = authed.get("/portal/price/history?hours=24").json()
    assert d["count"] >= 1
    assert isinstance(d["points"], list)
    for p in d["points"]:
        assert "ts" in p
        assert "bdag_price" in p
        assert p["bdag_price"] > 0


# --- manual refresh ---
def test_portal_price_refresh_live(authed):
    d = authed.post("/portal/price/refresh").json()
    assert d["ok"] is True
    assert d["bdag_price"] > 0


# --- route snapshot has portal_price block ---
def test_route_snapshot_includes_portal_price(authed):
    routes = authed.get("/routes").json()
    assert routes
    rid = routes[0]["id"]
    snap = authed.get(f"/routes/{rid}/snapshot").json()
    assert "portal_price" in snap
    pp = snap["portal_price"]
    assert pp["source"] == "sw-api/getInfo"
    assert pp["bdag_price"] is not None and pp["bdag_price"] > 0


# --- evaluation carries price_source ---
def test_evaluation_price_source_present(authed):
    routes = authed.get("/routes").json()
    rid = routes[0]["id"]
    # Force an evaluation cycle if endpoint exists; otherwise read latest
    evals = authed.get(f"/routes/{rid}/evaluations?limit=5").json()
    assert isinstance(evals, list) and evals, "no evaluations recorded yet"
    src = evals[0].get("inputs", {}).get("price_source")
    assert src in {"position", "manual_override", "portal", "manual_fallback"}, \
        f"unexpected price_source: {src}"


# --- manual_buy.override persistence via PATCH ---
def test_route_manual_buy_override_persists(authed):
    routes = authed.get("/routes").json()
    # pick first BDAG route
    target = next((r for r in routes if (r.get("purchase") or {}).get("asset") == "BDAG"), routes[0])
    rid = target["id"]
    original = (target.get("manual_buy") or {}).get("override", False)

    # toggle
    new_val = not original
    patch_body = {"manual_buy": {**(target.get("manual_buy") or {}), "override": new_val}}
    r = authed.patch(f"/routes/{rid}", json=patch_body)
    assert r.status_code in (200, 204), f"patch failed: {r.status_code} {r.text}"

    # verify via GET
    got = authed.get(f"/routes/{rid}").json()
    assert (got.get("manual_buy") or {}).get("override") == new_val

    # restore
    restore = {"manual_buy": {**(got.get("manual_buy") or {}), "override": original}}
    authed.patch(f"/routes/{rid}", json=restore)


# --- observation recorder regression ---
def test_observation_still_running(authed):
    d = authed.get("/observation/status").json()
    assert d["running"] is True
