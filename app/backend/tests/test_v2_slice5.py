"""UI v2 · Slice 5 — Settings backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://exec-readiness-x.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestAccount:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/settings/account")
        assert r.status_code == 200
        d = r.json()
        assert "account" in d
        a = d["account"]
        for k in ["username", "display_name", "email", "role", "mfa_enabled", "session_ttl_min", "last_login_at", "created_at"]:
            assert k in a

    def test_patch(self, client):
        r = client.patch(f"{API}/arbicore/settings/account", json={"display_name": "Ops Desk 02", "session_ttl_min": 90})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["account"]["display_name"] == "Ops Desk 02"
        assert d["account"]["session_ttl_min"] == 90
        # Reset
        client.patch(f"{API}/arbicore/settings/account", json={"display_name": "Ops Desk 01", "session_ttl_min": 60})


class TestVaults:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/settings/vaults")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d
        assert len(d["items"]) >= 3
        v = d["items"][0]
        for k in ["vault", "kind", "custody", "address", "signers_required", "signers_total", "state", "reconciled_at"]:
            assert k in v

    def test_reconcile(self, client):
        r = client.post(f"{API}/arbicore/settings/vaults/cold_wallet/reconcile")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["vault"] == "cold_wallet"


class TestExecution:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/settings/execution")
        assert r.status_code == 200
        d = r.json()
        assert "config" in d
        c = d["config"]
        for k in ["max_position_usd", "max_daily_notional_usd", "slippage_bps", "min_confidence", "min_safety", "freshness_max_s", "auto_execute_enabled", "kill_switch_wired"]:
            assert k in c

    def test_patch(self, client):
        r = client.patch(f"{API}/arbicore/settings/execution", json={"slippage_bps": 12, "min_confidence": 0.7})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["config"]["slippage_bps"] == 12
        assert d["config"]["min_confidence"] == 0.7
        # Reset
        client.patch(f"{API}/arbicore/settings/execution", json={"slippage_bps": 8, "min_confidence": 0.60})


class TestExchanges:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/settings/exchanges")
        assert r.status_code == 200
        d = r.json()
        assert len(d["items"]) >= 5
        x = d["items"][0]
        for k in ["key", "label", "kind", "role", "api_key_masked", "state", "read_only", "last_tested_at"]:
            assert k in x
        # No plaintext keys leak
        assert "•" in x["api_key_masked"] or "*" in x["api_key_masked"]

    def test_test_connectivity_ok(self, client):
        r = client.post(f"{API}/arbicore/settings/exchanges/binance/test")
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True
        assert d["state"] == "CONNECTED"
        assert d["latency_ms"] is not None

    def test_test_connectivity_fail(self, client):
        r = client.post(f"{API}/arbicore/settings/exchanges/gate-io/test")
        d = r.json()
        assert d["ok"] is False
        assert d["state"] == "DISCONNECTED"


class TestNotifications:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/settings/notifications")
        assert r.status_code == 200
        c = r.json()["config"]
        for k in ["telegram_enabled", "telegram_chat", "email_enabled", "email_to", "webhook_enabled", "severities", "events"]:
            assert k in c
        for s in ["info", "warn", "error"]:
            assert s in c["severities"]

    def test_patch(self, client):
        r = client.patch(f"{API}/arbicore/settings/notifications", json={"telegram_enabled": False})
        assert r.status_code == 200
        assert r.json()["config"]["telegram_enabled"] is False
        # Reset
        client.patch(f"{API}/arbicore/settings/notifications", json={"telegram_enabled": True})


class TestDocumentation:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/settings/documentation")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 6
        d = items[0]
        for k in ["title", "path", "category"]:
            assert k in d
        cats = {x["category"] for x in items}
        assert "guide" in cats and "reference" in cats


class TestOperational:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/settings/operational")
        assert r.status_code == 200
        c = r.json()["config"]
        for k in ["maintenance_mode", "trading_paused", "read_only", "dev_mode", "verbose_logging", "feature_flags"]:
            assert k in c
        assert "ui_v2" in c["feature_flags"]

    def test_patch_flag(self, client):
        r = client.patch(f"{API}/arbicore/settings/operational", json={"feature_flags": {"auto_execute": True}})
        assert r.status_code == 200
        assert r.json()["config"]["feature_flags"]["auto_execute"] is True
        # Reset
        client.patch(f"{API}/arbicore/settings/operational", json={"feature_flags": {"auto_execute": False}})
