"""Sprint 4.5 Observation Recorder tests — pure data capture validation.
Run: cd /app/backend && python -m pytest tests/test_sprint5_observation.py -v
"""
import asyncio
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE = "http://localhost:8001/api"
USERNAME = "admin"
PASSWORD = "ArbiCore#2026"
FAKE_ROUTE_ID = "pytest-obs-route"


@pytest.fixture(scope="module")
def authed():
    with httpx.Client(base_url=BASE, timeout=60) as c:
        r = c.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert r.status_code == 200, f"login failed: {r.text}"
        yield c


def test_observation_requires_auth():
    with httpx.Client(base_url=BASE, timeout=30) as anon:
        assert anon.get("/observation/status").status_code == 401
        assert anon.post("/observation/snapshot").status_code == 401


def test_observation_status_shape(authed):
    d = authed.get("/observation/status").json()
    assert d["running"] is True
    assert d["snapshot_interval_s"] == 3600
    for k in ("readiness_snapshots", "episodes_raw", "episodes_exec", "gate_cost_entries",
              "blocked_minutes_total", "missed_profit_total_quote", "calibration_pending",
              "calibration_resolved", "calibration_survival_rate_pct"):
        assert k in d["counters"], f"missing counter {k}"
    assert "no execution" in d["note"].lower()


def test_snapshot_now_persists_readiness(authed):
    r = authed.post("/observation/snapshot").json()
    assert r["ok"] is True
    status = authed.get("/observation/status").json()
    assert status["counters"]["readiness_snapshots"] > 0
    assert status["last_snapshot_at"]

    async def check_docs():
        from motor.motor_asyncio import AsyncIOMotorClient
        c = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = c[os.environ["DB_NAME"]]
        doc = await db.readiness_snapshots.find_one({}, {"_id": 0}, sort=[("ts", -1)])
        assert doc is not None
        for k in ("route_id", "exchange", "readiness_score", "readiness_label",
                  "factors", "metrics", "reliability_score", "deposit_uptime_pct"):
            assert k in doc, f"snapshot missing {k}"
        assert set(doc["factors"].keys()) == {"frequency", "duration", "spread", "capacity",
                                              "confidence", "stability", "exchange_health",
                                              "gate_reliability"}
        c.close()

    asyncio.run(check_docs())


def test_episode_archive_gate_ledger_and_calibration_machinery():
    """Synthetic end-to-end pass through the recorder internals:
    open raw episode -> samples -> close -> episode doc + gate-cost entry +
    calibration prediction resolved to 'unresolved' (no future evals exist)."""

    async def run():
        from services import db
        from services.observation import ObservationRecorder

        rec = ObservationRecorder()
        route = {"id": FAKE_ROUTE_ID, "mode": "live",
                 "risk_profile": {"min_net_spread_pct": 2.0},
                 "exit": {"base": "BDAG", "quote": "USDT"}}
        t0 = datetime.now(timezone.utc) - timedelta(minutes=45)

        def ev(ts, net, verdict="NO_GO"):
            return {"ts": ts.isoformat(),
                    "inputs": {"buy_price": 0.000035},
                    "hold_probability": {"probability": 0.8, "horizon_min": 30},
                    "venue_matrix": [{"exchange": "xt", "listed": True, "verdict": verdict,
                                      "confidence": 60.0, "net_spread_pct": net,
                                      "recommended": 100000.0, "deposit_enabled": False}]}

        # 3 open samples above min_net, then one below -> episode closes
        for i, net in enumerate((5.0, 6.5, 5.5)):
            await rec.on_evaluation(route, ev(t0 + timedelta(seconds=10 * i), net))
        assert (FAKE_ROUTE_ID, "xt", "raw") in rec._open
        await rec.on_evaluation(route, ev(t0 + timedelta(seconds=30), 0.5))
        assert (FAKE_ROUTE_ID, "xt", "raw") not in rec._open

        epi = await db.episodes_col.find_one({"route_id": FAKE_ROUTE_ID}, {"_id": 0})
        assert epi is not None
        assert epi["kind"] == "raw" and epi["samples"] == 3
        assert epi["peak_net_pct"] == 6.5 and epi["start_net_pct"] == 5.0 and epi["end_net_pct"] == 5.5
        assert epi["outcome"] == "blocked" and epi["had_go"] is False
        assert epi["end_reason"] == "spread_decayed"
        assert epi["blocking"].get("deposit_gate") == 3
        assert len(epi["decay_profile"]) == 3
        assert epi["est_profit_quote"] is not None and epi["est_profit_quote"] > 0

        ledger = await db.gate_cost_ledger.find_one({"route_id": FAKE_ROUTE_ID}, {"_id": 0})
        assert ledger is not None
        assert ledger["primary_blocker"] == "deposit_gate"
        assert ledger["blocked_minutes"] > 0
        assert ledger["est_missed_profit_quote"] == epi["est_profit_quote"]

        # calibration: one throttled prediction was recorded; resolve_after = t0+30m
        # which is ~15 min in the past (> 600s grace) and no evals exist for the
        # fake route -> resolver must mark it unresolved
        pred = await db.calibration_log.find_one({"route_id": FAKE_ROUTE_ID}, {"_id": 0})
        assert pred is not None
        assert pred["status"] == "pending"
        assert pred["predicted_confidence"] == 60.0 and pred["hold_probability"] == 0.8
        assert pred["horizon_min"] == 30
        await rec._resolve_due()
        pred2 = await db.calibration_log.find_one({"id": pred["id"]}, {"_id": 0})
        assert pred2["status"] == "unresolved"

        # cleanup synthetic docs
        await db.episodes_col.delete_many({"route_id": FAKE_ROUTE_ID})
        await db.gate_cost_ledger.delete_many({"route_id": FAKE_ROUTE_ID})
        await db.calibration_log.delete_many({"route_id": FAKE_ROUTE_ID})

    asyncio.run(run())


def test_sim_mode_not_recorded():
    async def run():
        from services.observation import ObservationRecorder
        rec = ObservationRecorder()
        route = {"id": FAKE_ROUTE_ID, "mode": "simulation",
                 "risk_profile": {"min_net_spread_pct": 2.0}}
        ev = {"ts": datetime.now(timezone.utc).isoformat(), "inputs": {"buy_price": 0.000035},
              "venue_matrix": [{"exchange": "xt", "verdict": "GO", "net_spread_pct": 9.0,
                                "recommended": 1000.0, "confidence": 90.0}]}
        await rec.on_evaluation(route, ev)
        assert rec._open == {}  # nothing tracked in simulation mode

    asyncio.run(run())
