"""E4.6.1 — Buy-price consistency + source transparency + portal diagnostic.

Verifies that the arbitrage-intel engine resolves the buy price via the SHARED
resolver (position → manual override → portal → manual fallback), exposes a full
transparency chain, resolves identically to the collector/evaluation path, and
that the read-only portal diagnostic reports endpoint/cache/24h-history/staleness.
READ-ONLY — no execution, no fund movement.
"""
import os
from pathlib import Path

import pytest
import requests

from services.execution import buy_price

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            _BASE = line.split("=", 1)[1].strip()
            break
assert _BASE
BASE = _BASE.rstrip("/")
PREC = ["position", "manual_override", "portal", "manual_fallback"]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def route_id(client):
    r = client.get(f"{BASE}/api/routes", timeout=15).json()
    routes = r if isinstance(r, list) else r.get("routes", [])
    return routes[0]["id"]


# ---------------- shared resolver precedence (pure) ----------------

class TestResolverPrecedence:
    BASE_ROUTE = {"id": "r1", "purchase": {"asset": "BDAG"},
                  "manual_buy": {"price": 3.5e-05, "qty": 100, "override": False}}

    def test_position_wins(self):
        r = buy_price.resolve_sync(self.BASE_ROUTE,
                                   {"id": "p1", "buy_price": 3.0e-05, "qty": 50, "status": "OPEN"})
        assert r["source"] == "position"
        assert r["price"] == 3.0e-05
        won = [c for c in r["chain"] if c["won"]]
        assert len(won) == 1 and won[0]["source"] == "position"

    def test_manual_override_beats_portal(self):
        route = {**self.BASE_ROUTE,
                 "manual_buy": {"price": 3.5e-05, "qty": 100, "override": True}}
        r = buy_price.resolve_sync(route, None)  # no position
        assert r["source"] == "manual_override"
        assert r["price"] == 3.5e-05

    def test_chain_complete_and_single_winner(self):
        r = buy_price.resolve_sync(self.BASE_ROUTE, None)
        assert [c["source"] for c in r["chain"]] == PREC
        assert sum(1 for c in r["chain"] if c["won"]) == 1
        assert r["precedence"] == PREC


# ---------------- intel uses the shared resolver (no separate path) ----------------

class TestIntelConsistency:
    def test_intel_exposes_resolution(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/intel/{route_id}", timeout=20).json()
        res = d.get("buy_price_resolution")
        assert res is not None
        assert res["source"] in PREC
        assert [c["source"] for c in res["chain"]] == PREC
        winners = [c for c in res["chain"] if c["won"]]
        assert len(winners) == 1
        # the engine's headline buy_price equals the winning source value
        assert d["buy_price_source"] == res["source"]
        if d.get("available"):
            assert abs(d["buy_price"] - res["price"]) < 1e-12

    def test_intel_matches_system_buy_price(self, client, route_id):
        """Intel must resolve the SAME buy price the rest of the system uses
        (collector/evaluation precedence)."""
        intel = client.get(f"{BASE}/api/execution/intel/{route_id}", timeout=20).json()
        # opportunity widget consumes the evaluation's resolved buy price
        opp = client.get(f"{BASE}/api/execution/opportunity", timeout=20)
        if opp.status_code == 200:
            ob = opp.json()
            opp_bp = (ob.get("opportunities") or [{}])[0].get("buy_price") if isinstance(ob, dict) else None
            if opp_bp and intel.get("buy_price"):
                assert abs(intel["buy_price"] - opp_bp) / opp_bp < 0.001


# ---------------- portal diagnostic (read-only) ----------------

class TestPortalDiagnostic:
    def test_diagnostic_shape(self, client):
        d = client.get(f"{BASE}/api/execution/portal/diagnostic", timeout=25).json()
        assert d["endpoint"].startswith("http")
        assert d["poll_frequency_s"] == 60
        assert "bdag_price" in d["cache"]
        assert "samples" in d["value_history_24h"]
        assert "distinct_values" in d["value_history_24h"]
        sc = d["swap_ui_comparison"]
        assert sc["api_bdag_price"] is not None
        assert "delta_pct_api_vs_swap" in sc
        assert isinstance(d["stale_evidence"], list)
        assert "recommendation" in d

    def test_diagnostic_anon_blocked(self):
        r = requests.get(f"{BASE}/api/execution/portal/diagnostic", timeout=10)
        assert r.status_code == 401
