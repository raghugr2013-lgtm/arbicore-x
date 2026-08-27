"""UI v2 · Slice 4 — Portfolio backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://elated-banach-10.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


class TestPositions:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/portfolio/positions")
        assert r.status_code == 200
        d = r.json()
        for k in ["items", "total", "total_size_usd", "total_upnl_usd", "generated_at"]:
            assert k in d
        assert d["total"] >= 5
        p = d["items"][0]
        for k in ["id", "venue", "market", "side", "size_usd", "entry_price", "mark_price", "upnl_bps", "upnl_usd"]:
            assert k in p
        assert p["side"] in {"LONG", "SHORT", "LP"}

    def test_filter_by_venue(self, client):
        r = client.get(f"{API}/arbicore/portfolio/positions", params={"venue": "binance"})
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(p["venue"] == "binance" for p in items)
        assert len(items) >= 1

    def test_filter_by_side(self, client):
        r = client.get(f"{API}/arbicore/portfolio/positions", params={"side": "SHORT"})
        items = r.json()["items"]
        assert all(p["side"] == "SHORT" for p in items)
        assert len(items) >= 1


class TestBalances:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/portfolio/balances")
        assert r.status_code == 200
        d = r.json()
        for k in ["items", "total", "total_usd", "generated_at"]:
            assert k in d
        assert d["total"] >= 5
        b = d["items"][0]
        for k in ["venue", "asset", "total", "available", "in_orders", "usd_value"]:
            assert k in b


class TestTransfers:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/portfolio/transfers")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d
        assert len(d["items"]) >= 5
        t = d["items"][0]
        for k in ["id", "kind", "from", "to", "asset", "amount", "usd_value", "status"]:
            assert k in t

    def test_filter_pending(self, client):
        r = client.get(f"{API}/arbicore/portfolio/transfers", params={"status": "PENDING"})
        items = r.json()["items"]
        assert all(t["status"] == "PENDING" for t in items)
        assert len(items) >= 1


class TestDeployable:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/portfolio/deployable")
        assert r.status_code == 200
        d = r.json()
        for k in ["total_deployable_usd", "total_utilised_usd", "total_capital_usd", "utilisation_pct", "per_venue"]:
            assert k in d
        assert len(d["per_venue"]) >= 5
        v = d["per_venue"][0]
        for k in ["venue", "deployable_usd", "utilised_usd", "utilisation_pct"]:
            assert k in v
        assert 0.0 <= d["utilisation_pct"] <= 1.0


class TestTreasury:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/portfolio/treasury")
        assert r.status_code == 200
        d = r.json()
        for k in ["vaults", "total_usd", "generated_at"]:
            assert k in d
        assert len(d["vaults"]) >= 3
        v = d["vaults"][0]
        for k in ["vault", "kind", "custody", "assets", "usd_value", "last_reconciled_at"]:
            assert k in v
        assert v["kind"] in {"COLD", "HOT", "MULTISIG", "EXCHANGE"}


class TestLedger:
    def test_list(self, client):
        r = client.get(f"{API}/arbicore/portfolio/ledger")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d
        assert len(d["items"]) >= 5
        e = d["items"][0]
        for k in ["id", "kind", "ref", "delta_usd", "balance_usd", "at", "note"]:
            assert k in e

    def test_filter_pnl(self, client):
        r = client.get(f"{API}/arbicore/portfolio/ledger", params={"kind": "PNL"})
        items = r.json()["items"]
        assert all(e["kind"] == "PNL" for e in items)
        assert len(items) >= 1


class TestExposure:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/portfolio/exposure")
        assert r.status_code == 200
        d = r.json()
        for k in ["by_asset", "by_chain", "total_usd", "generated_at"]:
            assert k in d
        assert len(d["by_asset"]) >= 4
        assert len(d["by_chain"]) >= 4
        # Percentages sum to ~1.0
        assert abs(sum(a["pct"] for a in d["by_asset"]) - 1.0) < 0.05
        assert abs(sum(c["pct"] for c in d["by_chain"]) - 1.0) < 0.05
        a = d["by_asset"][0]
        for k in ["asset", "usd_value", "pct"]:
            assert k in a


class TestAllocation:
    def test_get(self, client):
        r = client.get(f"{API}/arbicore/portfolio/allocation")
        assert r.status_code == 200
        d = r.json()
        for k in ["items", "total_target_usd", "total_actual_usd", "generated_at"]:
            assert k in d
        assert len(d["items"]) >= 4
        a = d["items"][0]
        for k in ["bucket", "target_pct", "actual_pct", "target_usd", "actual_usd", "delta_usd", "status"]:
            assert k in a
        assert a["status"] in {"UNDER", "OVER", "ON_TARGET"}
        # Target percentages sum to ~1.0
        assert abs(sum(x["target_pct"] for x in d["items"]) - 1.0) < 0.05
