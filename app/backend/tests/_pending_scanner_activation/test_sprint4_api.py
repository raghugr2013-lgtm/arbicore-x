"""Sprint 4 API regression tests — portfolio, balances, deployable, allocation,
exchange health, opportunity quality. Read-only intelligence only.
Run: cd /app/backend && python -m pytest tests/test_sprint4_api.py -v
"""
import httpx
import pytest

BASE = "http://localhost:8001/api"
USERNAME = "admin"
PASSWORD = "ArbiCore#2026"

FACTORS = {"CAPITAL_LIMITED", "LIQUIDITY_LIMITED", "DEPOSIT_GATE_LIMITED",
           "WITHDRAWAL_GATE_LIMITED", "ROUTE_LIMITED", "NO_KEY"}


@pytest.fixture(scope="module")
def authed():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert r.status_code == 200, f"login failed: {r.text}"
        yield c


def test_portfolio_routes_require_auth():
    with httpx.Client(base_url=BASE, timeout=30) as anon:
        for path in ("/portfolio/balances", "/portfolio/deployable", "/portfolio/allocation",
                     "/health/exchanges", "/quality"):
            assert anon.get(path).status_code == 401, f"{path} not protected"
        assert anon.post("/portfolio/refresh").status_code == 401


def test_balances_status_shape(authed):
    d = authed.get("/portfolio/balances").json()
    assert d["polling"]["interval_s"] == 60 and d["polling"]["running"] is True
    assert set(d["exchanges"].keys()) == {"xt", "mexc", "gate", "bitmart", "coinstore"}
    for ex in d["exchanges"].values():
        assert ex["status"] in ("ok", "no_key", "error", "rate_limited")
        # graceful empty state without keys
        if ex["status"] == "no_key":
            assert ex["balances"] == [] and ex["total_usd"] is None


def test_manual_refresh(authed):
    d = authed.post("/portfolio/refresh").json()
    assert "ok" in d and "message" in d  # ok may be False if a poll just ran (guard)


def test_deployable_limiting_factors(authed):
    d = authed.get("/portfolio/deployable").json()
    assert d["base"] and d["quote"] and d["price"]
    assert "no transfers" in d["note"].lower() or "no execution" in d["note"].lower() \
        or "informational" in d["note"].lower()
    assert len(d["venues"]) >= 3
    for v in d["venues"]:
        assert v["limiting_factor"] in FACTORS, v
        assert v["reason"]
        # without keys, listed venues must degrade to NO_KEY (liquidity view), never crash
        if v["listed"] and not v["has_key"]:
            assert v["limiting_factor"] == "NO_KEY"
            assert v["deployable_base"] is None
    listed = [v for v in d["venues"] if v["listed"]]
    assert any(v["potential_profit_quote"] is not None for v in listed)


def test_allocation(authed):
    d = authed.get("/portfolio/allocation", params={"hours": 24}).json()
    assert "venues" in d and "recommendations" in d and d["recommendations"]
    for v in d["venues"]:
        assert {"exchange", "capital_usd", "capital_pct", "go_minutes", "opportunity_pct"} <= set(v.keys())
    assert "no transfers or rebalancing" in d["note"].lower()


def test_health_exchanges(authed):
    d = authed.get("/health/exchanges", params={"hours": 24}).json()
    rows = {h["exchange"]: h for h in d["exchanges"]}
    assert set(rows.keys()) == {"xt", "mexc", "gate", "bitmart", "coinstore"}
    for h in rows.values():
        for k in ("api_uptime_pct", "deposit_uptime_pct", "withdraw_uptime_pct",
                  "avg_gate_open_min", "flips_per_day", "reliability_score"):
            assert k in h
    assert rows["xt"]["ws_mode"] in ("ws", "rest-fallback")


def test_quality_and_readiness(authed):
    d = authed.get("/quality", params={"hours": 24}).json()
    assert d["venues"] and "weights" in d
    assert abs(sum(d["weights"].values()) - 1.0) < 1e-6
    scores = []
    for v in d["venues"]:
        m = v["metrics"]
        for k in ("episodes_per_day", "avg_duration_min", "avg_net_spread_pct",
                  "avg_capacity_base", "avg_confidence", "est_deployable_base",
                  "est_profit_per_day_quote"):
            assert k in m, f"missing metric {k}"
        assert set(v["factors"].keys()) == {"frequency", "duration", "spread", "capacity",
                                            "confidence", "stability", "exchange_health",
                                            "gate_reliability"}
        assert v["readiness_label"] in ("READY", "PROMISING", "NOT READY", "INSUFFICIENT DATA")
        if v["readiness_score"] is not None:
            assert 0 <= v["readiness_score"] <= 100
            scores.append(v["readiness_score"])
    # ranked descending
    assert scores == sorted(scores, reverse=True)


def test_quality_sim_data_excluded(authed):
    """MEXC/Gate don't list BDAG — with live-mode filtering they must have no episodes."""
    d = authed.get("/quality", params={"hours": 24}).json()
    rows = {v["exchange"]: v for v in d["venues"]}
    for ex in ("mexc", "gate"):
        if ex in rows:
            assert rows[ex]["metrics"]["episodes"] == 0, f"sim pollution on {ex}"


def test_historical_collections_exist(authed):
    """Requirement 8: datasets keep accumulating (collections + indexes in place)."""
    import asyncio
    import os
    from pathlib import Path

    from dotenv import load_dotenv
    from motor.motor_asyncio import AsyncIOMotorClient

    load_dotenv(Path(__file__).parent.parent / ".env")

    async def check():
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        names = await db.list_collection_names()
        for col in ("orderbook_snapshots", "evaluations", "capability_history",
                    "fee_snapshots"):
            assert col in names, f"{col} missing"
        # Sprint 4 collections appear after first writes; indexes ensured at startup
        assert await db.evaluations.estimated_document_count() > 0
        c.close()

    asyncio.run(check())
