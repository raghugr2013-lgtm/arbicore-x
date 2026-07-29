"""Phase E1 — Portal Price Connector tests (READ-ONLY price discovery)."""
import asyncio
import os
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE = "http://localhost:8001/api"
USERNAME = "admin"
PASSWORD = "ArbiCore#2026"


@pytest.fixture(scope="module")
def authed():
    with httpx.Client(base_url=BASE, timeout=60) as c:
        r = c.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert r.status_code == 200, f"login failed: {r.text}"
        yield c


def test_portal_price_requires_auth():
    with httpx.Client(base_url=BASE, timeout=30) as anon:
        assert anon.get("/portal/price").status_code == 401
        assert anon.get("/portal/price/history").status_code == 401


def test_portal_price_status_shape(authed):
    d = authed.get("/portal/price").json()
    assert d["running"] is True
    assert d["poll_interval_s"] == 60
    assert d["source"].endswith("/getInfo")
    assert "no execution" in d["note"].lower()
    # live price present and sane (BDAG ~ 1e-5 .. 1e-4)
    assert isinstance(d["bdag_price"], (int, float)) and 1e-6 < d["bdag_price"] < 1e-3
    assert d["stale"] is False
    assert "ETH" in d["coin_prices"]


def test_portal_price_history(authed):
    d = authed.get("/portal/price/history?hours=24").json()
    assert d["count"] >= 1
    for p in d["points"]:
        assert "ts" in p and "bdag_price" in p


def test_manual_refresh(authed):
    d = authed.post("/portal/price/refresh").json()
    assert d["ok"] is True
    assert d["bdag_price"] > 0


def test_snapshot_carries_portal_block(authed):
    routes = authed.get("/routes").json()
    rid = routes[0]["id"]
    snap = authed.get(f"/routes/{rid}/snapshot").json()
    assert "portal_price" in snap
    assert snap["portal_price"]["source"] == "sw-api/getInfo"


def test_buy_price_precedence_resolver():
    """Active position → manual override → live portal → manual fallback."""
    from services.collector import CollectorService
    resolve = CollectorService._resolve_buy_price

    bdag_route = {"purchase": {"asset": "BDAG"},
                  "manual_buy": {"price": 0.000035, "qty": 10_000_000, "override": False}}
    non_bdag = {"purchase": {"asset": "FOO"},
                "manual_buy": {"price": 1.23, "qty": 100, "override": False}}

    # 1. active position cost basis wins over everything
    r = resolve(bdag_route, {"buy_price": 0.00003, "qty": 999})
    assert r["source"] == "position" and r["price"] == 0.00003 and r["qty"] == 999

    # 2. manual override (no position) → manual
    over = {"purchase": {"asset": "BDAG"},
            "manual_buy": {"price": 0.000040, "qty": 5, "override": True}}
    r = resolve(over, None)
    assert r["source"] == "manual_override" and r["price"] == 0.000040

    # 3. BDAG, no position, no override → live portal price
    import time as _t
    from services.portal_price import portal_price
    portal_price.bdag_price = 0.0000379
    portal_price._fetched_mono = _t.monotonic()   # mark fresh
    pp = portal_price.current_bdag_price()
    assert pp == 0.0000379
    r = resolve(bdag_route, None)
    assert r["source"] == "portal" and r["price"] == pp

    # 4. non-BDAG falls back to stored manual price
    r = resolve(non_bdag, None)
    assert r["source"] == "manual_fallback" and r["price"] == 1.23


def test_portal_stale_returns_none():
    """A fresh service with no fetch must report stale and yield no price."""
    async def run():
        from services.portal_price import PortalPriceService
        svc = PortalPriceService()
        assert svc.current_bdag_price() is None  # never fetched → stale
        assert svc.status_brief()["stale"] is True
    asyncio.run(run())
