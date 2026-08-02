"""UI v2 · Slice 3 — Operations backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://unified-codebase-4.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# --- Scanners ---
class TestScanners:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/operations/scanners")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert len(data["items"]) == 8
        s = data["items"][0]
        for k in ["family", "state", "cadence_s", "opps_1h", "gates_dropped_1h", "errors_1h", "last_run"]:
            assert k in s

    def test_pause_and_start(self, client):
        r = client.post(f"{API}/arbicore/operations/scanners/CEX_ARBITRAGE/action", params={"action": "pause"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and d["state"] == "PAUSED"
        # Verify persistence
        g = client.get(f"{API}/arbicore/operations/scanners").json()
        cex = next(x for x in g["items"] if x["family"] == "CEX_ARBITRAGE")
        assert cex["state"] == "PAUSED"
        # Reset
        r2 = client.post(f"{API}/arbicore/operations/scanners/CEX_ARBITRAGE/action", params={"action": "start"})
        assert r2.json()["state"] == "RUNNING"


# --- Cycles ---
class TestCycles:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/operations/cycles")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data
        assert len(data["items"]) > 0
        c = data["items"][0]
        for k in ["id", "family", "route", "status", "realized_bps", "size_usd", "started_at", "ended_at"]:
            assert k in c

    def test_filter_settled(self, client):
        r = client.get(f"{API}/arbicore/operations/cycles", params={"status": "SETTLED"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(x["status"] == "SETTLED" for x in items)
        assert len(items) >= 1


# --- Venues ---
class TestVenues:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/operations/venues")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 9
        for v in items:
            for k in ["venue", "kind", "state", "role", "latency_ms", "last_seen"]:
                assert k in v
            assert v["state"] in {"READY", "DEGRADED", "OFFLINE"}


# --- Interlock ---
class TestInterlock:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/operations/interlock")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["armed"], bool)
        assert "state" in d and "last_transition_at" in d
        assert isinstance(d["gates"], list) and len(d["gates"]) == 5
        for g in d["gates"]:
            for k in ["gate", "state", "value", "threshold"]:
                assert k in g

    def test_actions(self, client):
        r1 = client.post(f"{API}/arbicore/operations/interlock/action", params={"action": "disarm"})
        assert r1.status_code == 200
        assert r1.json() == {**r1.json(), "ok": True, "state": "DISARMED"}
        r2 = client.post(f"{API}/arbicore/operations/interlock/action", params={"action": "arm"})
        assert r2.json()["state"] == "ARMED"


# --- Integrations ---
class TestIntegrations:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/operations/integrations")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 6
        for it in items:
            for k in ["key", "label", "state", "detail"]:
                assert k in it
        alch = next(x for x in items if x["key"] == "alchemy")
        assert alch["state"] == "DEGRADED"


# --- Queues ---
class TestQueues:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/operations/queues")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 5
        for q in items:
            for k in ["queue", "pending", "in_flight", "failed_1h", "rate_per_min"]:
                assert k in q
        ev = next(x for x in items if x["queue"] == "evidence_bundle")
        assert ev["failed_1h"] == 2


# --- Alerts ---
class TestAlerts:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/operations/alerts")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data
        items = data["items"]
        assert len(items) >= 5
        for a in items:
            for k in ["id", "severity", "source", "message", "at", "acked"]:
                assert k in a

    def test_filter_warn(self, client):
        r = client.get(f"{API}/arbicore/operations/alerts", params={"severity": "warn"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(x["severity"] == "warn" for x in items)
        assert len(items) >= 1

    def test_ack(self, client):
        r = client.post(f"{API}/arbicore/operations/alerts/alr-9/ack")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and d["acked"] is True
