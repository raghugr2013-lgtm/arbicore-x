"""Phase E4.5 — Shadow Certification Campaign tests (hands-off, NON-EXECUTING).

Verifies the campaign control surface (status / start / stop / history), the
single-active-campaign invariant, target validation, that starting a campaign
takes ownership of the shadow flag and stopping it disables shadow + finalizes a
verdict. The campaign drives Shadow Mode only — no trading, no wallet, no
withdrawals, no fund movement.
"""
import os
from pathlib import Path

import pytest
import requests

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    envp = Path("/app/frontend/.env")
    if envp.exists():
        for line in envp.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                _BASE = line.split("=", 1)[1].strip()
                break
assert _BASE
BASE = _BASE.rstrip("/")

VERDICTS = {"INSUFFICIENT_DATA", "NOT_READY",
            "PROMISING_NEEDS_MORE_DATA", "READY_FOR_MICROCAPITAL_REVIEW"}


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _stop_any(client):
    """Best-effort: ensure no campaign is running and shadow is OFF."""
    try:
        client.post(f"{BASE}/api/execution/campaign/stop", json={}, timeout=15)
    except Exception:
        pass
    client.patch(f"{BASE}/api/execution/config", json={"shadow_enabled": False}, timeout=15)


def _shadow_campaigns_col():
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    mc = MongoClient(os.environ["MONGO_URL"])
    return mc, mc[os.environ["DB_NAME"]]["shadow_campaigns"]


def _campaign_ids():
    mc, col = _shadow_campaigns_col()
    try:
        return {d["id"] for d in col.find({}, {"id": 1})}
    finally:
        mc.close()


@pytest.fixture(scope="module", autouse=True)
def _purge_temp_campaigns(client):
    """Snapshot existing campaign ids, then after this module finishes delete any
    NEW zero-cycle / dummy campaigns it spawned (start→stop fixtures) so the test
    suite never pollutes the authoritative shadow_campaigns collection. Real
    completed certification campaigns (completed_count > 0) are always preserved."""
    baseline = _campaign_ids()
    yield
    _stop_any(client)
    mc, col = _shadow_campaigns_col()
    try:
        col.delete_many({
            "id": {"$nin": list(baseline)},
            "$or": [{"completed_count": {"$lte": 0}},
                    {"completed_count": {"$exists": False}},
                    {"completed_count": None}],
        })
    finally:
        mc.close()


class TestCampaignStatus:
    def test_status_shape(self, client):
        r = client.get(f"{BASE}/api/execution/campaign/status", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "monitor_running" in d
        assert d["monitor_running"] is True  # lifespan started the monitor
        assert d["default_target"] == 20
        assert "default_thresholds" in d
        for k in ("max_stuck_rate_pct", "max_variance_pct",
                  "min_recovery_rate_pct", "min_sample"):
            assert k in d["default_thresholds"], k

    def test_status_anon_blocked(self):
        r = requests.get(f"{BASE}/api/execution/campaign/status", timeout=10)
        assert r.status_code == 401

    def test_history_endpoint(self, client):
        r = client.get(f"{BASE}/api/execution/campaign/history", timeout=20)
        assert r.status_code == 200
        assert isinstance(r.json()["campaigns"], list)


class TestCampaignValidation:
    def test_negative_target_rejected(self, client):
        _stop_any(client)
        r = client.post(f"{BASE}/api/execution/campaign/start",
                        json={"target_completed": -3}, timeout=20)
        assert r.status_code == 400, r.text


class TestCampaignLifecycle:
    def test_start_stop_flow(self, client):
        _stop_any(client)
        # start
        r = client.post(f"{BASE}/api/execution/campaign/start",
                        json={"target_completed": 20}, timeout=20)
        assert r.status_code == 200, r.text
        camp = r.json()
        assert camp["status"] == "running"
        assert camp["target_completed"] == 20

        # campaign owns the shadow flag → shadow enabled
        cfg = client.get(f"{BASE}/api/execution/config", timeout=20).json()
        assert cfg["shadow_enabled"] is True

        # status reflects an active campaign + live report + progress
        st = client.get(f"{BASE}/api/execution/campaign/status", timeout=20).json()
        assert st["campaign"]["status"] == "running"
        assert "progress_pct" in st
        assert st["live_report"]["verdict"] in VERDICTS

        # cannot start a second campaign while one is running
        dup = client.post(f"{BASE}/api/execution/campaign/start",
                          json={"target_completed": 5}, timeout=20)
        assert dup.status_code == 400

        # stop → finalized + shadow disabled + verdict recorded
        stop = client.post(f"{BASE}/api/execution/campaign/stop", json={}, timeout=20)
        assert stop.status_code == 200, stop.text
        ended = stop.json()
        assert ended["status"] == "stopped_manual"
        assert ended["final_verdict"] in VERDICTS

        cfg2 = client.get(f"{BASE}/api/execution/config", timeout=20).json()
        assert cfg2["shadow_enabled"] is False  # campaign released the flag

        # stopping again → 400 (no running campaign)
        again = client.post(f"{BASE}/api/execution/campaign/stop", json={}, timeout=20)
        assert again.status_code == 400

    def test_terminal_status_exposes_final(self, client):
        st = client.get(f"{BASE}/api/execution/campaign/status", timeout=20).json()
        camp = st["campaign"]
        if camp and camp["status"] != "running":
            assert camp["final_verdict"] in VERDICTS
            # full final report attached on terminal status
            assert "final_report" in st
