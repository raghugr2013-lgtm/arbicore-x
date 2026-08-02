"""Phase E3 — Shadow Mode backend tests (NON-EXECUTING).

Covers: shadow status endpoint, shadow_enabled config toggle, cycle timeline
endpoint (segments / durations / events) on a scaffold cycle, and an integration
test of the shadow runner driving a SHADOW cycle off live data (opportunity
detection → route selection → state transitions → would-decisions → profit calc).

All non-executing — no wallet/exchange transactions, no fund movement.
"""
import os
import time
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
    j = r.json()
    routes = j.get("routes") if isinstance(j, dict) else j
    assert routes, "no routes seeded"
    return routes[0]["id"]


class TestShadowStatus:
    def test_shadow_status_shape(self, client):
        r = client.get(f"{BASE}/api/execution/shadow/status", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["running"] is True
        assert "enabled" in d
        assert set(d["shadow_cycles"]) >= {"total", "open", "complete", "stuck"}
        assert set(d["shadow_pnl"]) >= {"expected_total_quote", "realized_total_quote"}

    def test_status_includes_shadow_block(self, client):
        r = client.get(f"{BASE}/api/execution/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "shadow_enabled" in d
        assert "shadow" in d
        assert d["execution_enabled"] is False  # never enabled in E3

    def test_shadow_anon_blocked(self):
        r = requests.get(f"{BASE}/api/execution/shadow/status", timeout=10)
        assert r.status_code == 401


class TestShadowConfig:
    def test_toggle_shadow_enabled(self, client):
        try:
            r = client.patch(f"{BASE}/api/execution/config", json={"shadow_enabled": True}, timeout=15)
            assert r.status_code == 200
            assert r.json()["shadow_enabled"] is True
        finally:
            r2 = client.patch(f"{BASE}/api/execution/config", json={"shadow_enabled": False}, timeout=15)
            assert r2.json()["shadow_enabled"] is False


class TestTimeline:
    def test_timeline_on_scaffold_cycle(self, client, first_route_id):
        r = client.post(f"{BASE}/api/execution/cycles",
                        json={"route_id": first_route_id, "size_usd": 10, "funding_asset": "USDT"},
                        timeout=15)
        assert r.status_code == 200, r.text
        cid = r.json()["id"]
        try:
            for _ in range(3):
                client.post(f"{BASE}/api/execution/cycles/{cid}/advance", timeout=15)
            tl = client.get(f"{BASE}/api/execution/cycles/{cid}/timeline", timeout=15)
            assert tl.status_code == 200, tl.text
            d = tl.json()
            assert d["mode"] == "scaffold"
            assert len(d["segments"]) >= 4
            seg = d["segments"][0]
            assert {"state", "duration_s", "kind", "fund_location"} <= set(seg)
            assert "events" in d
        finally:
            client.post(f"{BASE}/api/execution/cycles/{cid}/abort", timeout=15)

    def test_timeline_404(self, client):
        r = client.get(f"{BASE}/api/execution/cycles/does-not-exist/timeline", timeout=15)
        assert r.status_code == 404


class TestShadowRunner:
    """Integration: enable shadow + a permissive floor, let the runner open and drive
    a SHADOW cycle off live data. Skips only if the live market presents no opportunity."""

    def test_runner_opens_and_drives_shadow_cycle(self, client, first_route_id):
        orig = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        orig_floor = orig["limits"]["min_net_spread_pct"]
        client.patch(f"{BASE}/api/execution/config",
                     json={"limits": {"min_net_spread_pct": -100}, "shadow_enabled": True}, timeout=15)
        shadow_cycle = None
        try:
            deadline = time.time() + 90
            while time.time() < deadline:
                cs = client.get(f"{BASE}/api/execution/cycles", timeout=15).json()["cycles"]
                sc = [c for c in cs if c.get("mode") == "shadow"]
                if sc:
                    shadow_cycle = sorted(sc, key=lambda c: c["created_at"])[-1]
                    if len(shadow_cycle.get("shadow_decisions", [])) >= 2:
                        break
                time.sleep(8)
            if not shadow_cycle:
                pytest.skip("no live opportunity surfaced within window (market-dependent)")
            assert shadow_cycle["mode"] == "shadow"
            assert shadow_cycle["simulated"] is True
            actions = [d.get("action") for d in shadow_cycle.get("shadow_decisions", [])]
            assert "opportunity_detected" in actions
            assert shadow_cycle.get("sell_venue")
            assert shadow_cycle.get("expected_profit_quote") is not None
            # timeline must reflect the shadow run
            tl = client.get(f"{BASE}/api/execution/cycles/{shadow_cycle['id']}/timeline", timeout=15).json()
            assert tl["mode"] == "shadow"
            assert len(tl["segments"]) >= 2
        finally:
            client.patch(f"{BASE}/api/execution/config",
                         json={"limits": {"min_net_spread_pct": orig_floor}, "shadow_enabled": False}, timeout=15)
            # abort any open shadow cycles to leave a clean state
            cs = client.get(f"{BASE}/api/execution/cycles", timeout=15).json()["cycles"]
            for c in cs:
                if c.get("mode") == "shadow" and c["state"] not in ("COMPLETE", "ABORTED"):
                    client.post(f"{BASE}/api/execution/cycles/{c['id']}/abort", timeout=15)
