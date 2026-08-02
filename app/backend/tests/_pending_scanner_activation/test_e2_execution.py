"""Phase E2 — Execution Framework backend tests (SIMULATED / DRY-RUN).

Covers: status, venues + role swap, config + limit patch + restore, funding calc,
opportunity widget, classification, manual opportunities, cycle lifecycle
(create→advance→audit→abort and force manual-review), limit enforcement
(per-cycle / concurrent / daily-volume), auth gate, regression (routes/portal/observation).
"""
import os
from pathlib import Path

import pytest
import requests

# Load REACT_APP_BACKEND_URL from /app/frontend/.env if not in env
_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    envp = Path("/app/frontend/.env")
    if envp.exists():
        for line in envp.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                _BASE = line.split("=", 1)[1].strip()
                break
assert _BASE, "REACT_APP_BACKEND_URL not set"
BASE = _BASE.rstrip("/")
ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCore#2026"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def first_route_id(client):
    r = client.get(f"{BASE}/api/routes", timeout=15)
    assert r.status_code == 200
    j = r.json()
    routes = j.get("routes") if isinstance(j, dict) else j
    assert routes, "no routes seeded"
    return routes[0]["id"]


# ---------------- auth gate ----------------
class TestAuthGate:
    """Every /api/execution/* endpoint must reject anon callers (401)."""

    @pytest.mark.parametrize("path", [
        "/api/execution/status", "/api/execution/venues", "/api/execution/config",
        "/api/execution/funding?size_usd=25", "/api/execution/cycles",
    ])
    def test_anon_blocked(self, path):
        r = requests.get(f"{BASE}{path}", timeout=10)
        assert r.status_code == 401, f"{path} expected 401 got {r.status_code}"

    def test_anon_post_cycle_blocked(self):
        r = requests.post(f"{BASE}/api/execution/cycles",
                          json={"route_id": "x", "size_usd": 10}, timeout=10)
        assert r.status_code == 401


# ---------------- status ----------------
class TestStatus:
    def test_status_shape(self, client):
        r = client.get(f"{BASE}/api/execution/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "E2" in d["phase"]
        assert d["execution_enabled"] is False
        assert d["wallet_enabled"] is False
        assert d["mode"] == "SIMULATED / DRY-RUN"
        ft = d["fund_tracker"]
        assert ft["running"] is True
        assert isinstance(ft["state_flow"], list) and "CREATED" in ft["state_flow"]
        assert "COMPLETE" in ft["state_flow"]
        assert "counters" in ft and "cycles_total" in ft["counters"]


# ---------------- venues ----------------
class TestVenues:
    def test_list_venues_roles(self, client):
        r = client.get(f"{BASE}/api/execution/venues", timeout=15)
        assert r.status_code == 200
        d = r.json()
        venues = {v["exchange"]: v["role"] for v in d["venues"]}
        assert venues.get("coinstore") == "primary"
        assert venues.get("bitmart") == "backup"
        assert venues.get("xt") == "watch"
        assert venues.get("mexc") == "disabled"
        assert venues.get("gate") == "disabled"
        assert len(d["venues"]) == 5

    def test_role_swap_demotes_old_primary(self, client):
        # Promote bitmart to primary; expect coinstore demoted to backup.
        r = client.patch(f"{BASE}/api/execution/venues/bitmart",
                         json={"role": "primary"}, timeout=15)
        assert r.status_code == 200
        r2 = client.get(f"{BASE}/api/execution/venues", timeout=15)
        venues = {v["exchange"]: v["role"] for v in r2.json()["venues"]}
        assert venues["bitmart"] == "primary"
        assert venues["coinstore"] == "backup"
        primaries = [e for e, role in venues.items() if role == "primary"]
        assert len(primaries) == 1, f"more than one primary: {primaries}"
        # Restore: coinstore=primary, bitmart=backup
        client.patch(f"{BASE}/api/execution/venues/coinstore", json={"role": "primary"}, timeout=15)
        r3 = client.get(f"{BASE}/api/execution/venues", timeout=15)
        venues = {v["exchange"]: v["role"] for v in r3.json()["venues"]}
        assert venues["coinstore"] == "primary"
        assert venues["bitmart"] == "backup"


# ---------------- config ----------------
class TestConfig:
    def test_defaults(self, client):
        r = client.get(f"{BASE}/api/execution/config", timeout=15)
        assert r.status_code == 200
        d = r.json()
        lim = d["limits"]
        assert lim["max_cycle_usd"] == 25.0
        assert lim["max_purchase_usd"] == 25.0
        assert lim["max_daily_volume_usd"] == 100.0
        assert lim["max_daily_loss_usd"] == 20.0
        assert lim["max_concurrent_cycles"] == 1
        assert lim["min_net_spread_pct"] == 2.0

    def test_patch_and_restore(self, client):
        # change min_net_spread_pct, then restore
        r = client.patch(f"{BASE}/api/execution/config",
                         json={"limits": {"min_net_spread_pct": 2.5},
                               "execution_enabled": False, "wallet_enabled": False,
                               "hard_freeze": False}, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["limits"]["min_net_spread_pct"] == 2.5
        # restore
        rr = client.patch(f"{BASE}/api/execution/config",
                          json={"limits": {"min_net_spread_pct": 2.0}}, timeout=15)
        assert rr.status_code == 200
        assert rr.json()["limits"]["min_net_spread_pct"] == 2.0


# ---------------- funding ----------------
class TestFunding:
    def test_funding_breakdown(self, client):
        r = client.get(f"{BASE}/api/execution/funding?size_usd=25", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["bdag_qty_gross"] > 0
        assets = {a["asset"]: a for a in d["funding_assets"]}
        assert "USDT" in assets and "BNB" in assets and "ETH" in assets
        assert abs(assets["USDT"]["amount_required"] - 25.0) < 0.01
        for sym in ("BNB", "ETH"):
            assert assets[sym]["amount_required"] > 0


# ---------------- opportunity ----------------
class TestOpportunity:
    def test_opportunity_shape(self, client, first_route_id):
        r = client.get(f"{BASE}/api/execution/opportunity/{first_route_id}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        for k in ("portal_price", "best_exchange", "best_exchange_price",
                  "gross_spread_pct", "net_spread_pct", "liquidity_quote_2pct",
                  "max_safe_size_base", "max_safe_size_quote",
                  "expected_profit_quote", "verdict"):
            assert k in d, f"missing key {k}"
        assert d["verdict"] in ("GO", "WAIT", "NO_GO")


# ---------------- classification ----------------
class TestClassification:
    def test_classification_shape(self, client, first_route_id):
        r = client.get(f"{BASE}/api/execution/classification/{first_route_id}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        venues = d.get("venues") or d.get("classification") or d
        # Try venues list — fall back to dict of {exchange: {...}}
        rows = venues if isinstance(venues, list) else list(venues.values()) if isinstance(venues, dict) else []
        assert rows, f"no classification rows in {d}"
        for v in rows:
            assert v.get("classification") in ("A", "B", "C")
            cov = v.get("automation_coverage_pct")
            assert cov is not None and cov % 20 == 0
            assert "manual_steps" in v
            assert "role" in v


# ---------------- manual opportunities ----------------
class TestManualOpportunities:
    def test_manual_opportunity_shape(self, client, first_route_id):
        r = client.get(f"{BASE}/api/execution/manual-opportunities/{first_route_id}", timeout=20)
        assert r.status_code == 200
        d = r.json()
        opps = d.get("opportunities") or d
        if isinstance(opps, list) and opps:
            o = opps[0]
            assert o.get("buy_venue") == "BlockDAG Portal"
            for k in ("sell_venue", "qty_base", "net_spread_pct",
                      "est_profit_quote", "liquidity_quote", "manual_actions",
                      "classification"):
                assert k in o, f"missing {k} in opp"
            assert isinstance(o["manual_actions"], list)


# ---------------- cycle lifecycle ----------------
class TestCycleLifecycle:
    """Create → advance several states → audit → abort. Ensures max_concurrent cleared."""

    def test_full_lifecycle(self, client, first_route_id):
        r = client.post(f"{BASE}/api/execution/cycles",
                        json={"route_id": first_route_id, "size_usd": 20, "funding_asset": "BNB"},
                        timeout=15)
        assert r.status_code == 200, r.text
        c = r.json()
        assert c["simulated"] is True
        assert c["dry_run"] is True
        assert c["state"] == "CREATED"
        assert c["fund_location"]["state"] == "CREATED"
        ledger = c["ledger"]
        assert all(v["status"] == "pending" for v in ledger.values())
        cid = c["id"]
        try:
            # advance twice → PURCHASE_ORDER_CREATED, PAYMENT_SENT
            r1 = client.post(f"{BASE}/api/execution/cycles/{cid}/advance", timeout=15)
            assert r1.status_code == 200
            assert r1.json()["state"] == "PURCHASE_ORDER_CREATED"
            r2 = client.post(f"{BASE}/api/execution/cycles/{cid}/advance", timeout=15)
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2["state"] == "PAYMENT_SENT"
            # Ledger legs become confirmed (purchase_order from prior step; payment_tx from this one)
            assert d2["ledger"]["purchase_order"]["status"] == "confirmed"
            assert d2["ledger"]["payment_tx"]["status"] == "confirmed"
            assert d2["ledger"]["payment_tx"]["reference"].startswith("SIM-")
            # GET cycle
            rg = client.get(f"{BASE}/api/execution/cycles/{cid}", timeout=15)
            assert rg.status_code == 200
            assert rg.json()["state"] == "PAYMENT_SENT"
            # audit
            ra = client.get(f"{BASE}/api/execution/cycles/{cid}/audit", timeout=15)
            assert ra.status_code == 200
            trail = ra.json()["trail"]
            assert any(e.get("phase") == "intent" or e.get("kind") == "intent" for e in trail)
            assert any((e.get("external_ref") or "").startswith("SIM-") for e in trail)
        finally:
            ab = client.post(f"{BASE}/api/execution/cycles/{cid}/abort", timeout=15)
            assert ab.status_code == 200
            assert ab.json()["state"] == "ABORTED"

    def test_manual_review(self, client, first_route_id):
        r = client.post(f"{BASE}/api/execution/cycles",
                        json={"route_id": first_route_id, "size_usd": 10, "funding_asset": "USDT"},
                        timeout=15)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        try:
            mr = client.post(f"{BASE}/api/execution/cycles/{cid}/manual-review", timeout=15)
            assert mr.status_code == 200
            assert mr.json()["state"] == "MANUAL_REVIEW"
        finally:
            client.post(f"{BASE}/api/execution/cycles/{cid}/abort", timeout=15)


# ---------------- limit enforcement ----------------
class TestLimits:
    def test_size_over_max_cycle(self, client, first_route_id):
        r = client.post(f"{BASE}/api/execution/cycles",
                        json={"route_id": first_route_id, "size_usd": 50, "funding_asset": "USDT"},
                        timeout=15)
        assert r.status_code == 400, r.text

    def test_concurrent_cap(self, client, first_route_id):
        r1 = client.post(f"{BASE}/api/execution/cycles",
                         json={"route_id": first_route_id, "size_usd": 10, "funding_asset": "USDT"},
                         timeout=15)
        assert r1.status_code == 200, r1.text
        cid = r1.json()["id"]
        try:
            r2 = client.post(f"{BASE}/api/execution/cycles",
                             json={"route_id": first_route_id, "size_usd": 10, "funding_asset": "USDT"},
                             timeout=15)
            assert r2.status_code == 400, r2.text
        finally:
            client.post(f"{BASE}/api/execution/cycles/{cid}/abort", timeout=15)


# ---------------- regression ----------------
class TestRegression:
    def test_routes_list(self, client):
        r = client.get(f"{BASE}/api/routes", timeout=15)
        assert r.status_code == 200

    def test_route_snapshot_portal_block(self, client, first_route_id):
        r = client.get(f"{BASE}/api/routes/{first_route_id}/snapshot", timeout=20)
        assert r.status_code == 200
        d = r.json()
        assert "portal_price" in d
        assert d["portal_price"].get("bdag_price", 0) > 0

    def test_observation_status(self, client):
        r = client.get(f"{BASE}/api/observation/status", timeout=15)
        assert r.status_code == 200
        assert r.json().get("running") is True

    def test_portal_price(self, client):
        r = client.get(f"{BASE}/api/portal/price", timeout=15)
        assert r.status_code == 200
        assert r.json().get("bdag_price", 0) > 0
