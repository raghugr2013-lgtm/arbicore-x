"""Price Verification & Calculation Transparency + Minimum Executable Size tests
(READ-ONLY, NON-EXECUTING).

Part 1 — the sizing/opportunity/evidence layers surface the BlockDAG Live Swap
minimum purchase ($50) and never recommend a live cycle below it.
Part 2 — the /price-verification endpoint exposes every calculation input so the
operator can verify each number against the BlockDAG Live Swap + sell-venue book.
"""
import os
from pathlib import Path

import pytest
import requests

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            _BASE = line.split("=", 1)[1].strip()
            break
assert _BASE
BASE = _BASE.rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def bdag_route_id(client):
    d = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
    rid = (d.get("buy_price_basis") or {}).get("route_id")
    assert rid, "no BDAG route resolved"
    return rid


# ---------------- Part 1 — minimum executable size ----------------

class TestExecutableSizing:
    def test_config_exposes_min_executable(self, client):
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert "min_executable_purchase_usd" in cfg["limits"]
        assert cfg["limits"]["min_executable_purchase_usd"] == 50.0

    def test_intel_executable_sizing_block(self, client, bdag_route_id):
        d = client.get(f"{BASE}/api/execution/intel/{bdag_route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface right now")
        es = d["executable_sizing"]
        for k in ("certification_size_usd", "min_executable_size_usd",
                  "actual_executable_recommendation_usd", "actionable",
                  "min_exceeds_certification_cap"):
            assert k in es, k
        assert es["min_executable_size_usd"] == 50.0
        assert d["limits"]["min_executable_purchase_usd"] == 50.0

    def test_never_recommends_below_minimum(self, client, bdag_route_id):
        d = client.get(f"{BASE}/api/execution/intel/{bdag_route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface right now")
        es = d["executable_sizing"]
        # the actual executable recommendation is NEVER below the live-swap minimum
        assert es["actual_executable_recommendation_usd"] >= es["min_executable_size_usd"] - 1e-6

    def test_min_above_cert_flips_actionable_false(self, client, bdag_route_id):
        """With cert cap $25 and live-swap minimum $50, the smallest placeable
        cycle exceeds the certified size, so it is correctly NOT actionable."""
        d = client.get(f"{BASE}/api/execution/intel/{bdag_route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface right now")
        es = d["executable_sizing"]
        if es["min_executable_size_usd"] > es["certification_size_usd"]:
            assert es["min_exceeds_certification_cap"] is True
            assert es["actionable"] is False
            assert es["notes"], "expected an explanatory note for the cert/min conflict"

    def test_gate_surfaces_executable_sizing(self, client):
        g = client.get(f"{BASE}/api/execution/opportunity/gate", timeout=20).json()
        if not g.get("available"):
            pytest.skip("gate unavailable")
        assert g.get("min_executable_usd") == 50.0
        assert g.get("actual_executable_recommendation_usd") is not None
        assert g.get("executable_sizing") is not None

    def test_evidence_section7_executable_fields(self, client):
        d = client.get(f"{BASE}/api/execution/certification/evidence", timeout=25).json()
        if not d.get("available"):
            pytest.skip("no certification campaign")
        cap = d["sections"]["7_recommended_capital_size"]
        assert cap["certification_size_usd"] is not None
        assert cap["min_executable_size_usd"] == 50.0
        assert cap["actual_executable_recommendation_usd"] >= cap["min_executable_size_usd"] - 1e-6


# ---------------- Part 2 — price verification transparency ----------------

class TestPriceVerification:
    def test_endpoint_shape(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        assert d.get("available") is True, d
        for k in ("blockdag_live_swap", "market_data", "calculation_transparency",
                  "profitability_trace", "source_comparison", "decision_trace",
                  "executable_sizing"):
            assert k in d, k

    def test_live_swap_block(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        ls = d["blockdag_live_swap"]
        assert ls["source_url"] == "https://purchase3.blockdag.network/swap"
        assert ls["source_identifier"] == "sw-api/getInfo"
        for k in ("current_live_swap_price", "timestamp", "data_age_s", "stale"):
            assert k in ls, k

    def test_market_data_block(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        md = d["market_data"]
        for k in ("best_bid", "best_ask", "bid_ask_spread_pct",
                  "total_profitable_bid_depth_usd", "weighted_average_sell_price_used",
                  "order_book_timestamp", "data_age_s", "reference_url"):
            assert k in md, k

    def test_calculation_transparency_block(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        c = d["calculation_transparency"]
        assert c["buy_price_used"] is not None
        assert c["buy_source_used"]
        assert c["sell_source_used"] and "Best Bid" in c["sell_source_used"]
        assert "weighted_average_sell_price_used" in c

    def test_profitability_trace_block(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        tr = d["profitability_trace"]
        if tr.get("available") is False:
            pytest.skip("no profitable size right now")
        for k in ("capital_input_usd", "bdag_acquired_base", "trading_fees_usd",
                  "withdrawal_fees_usd", "gross_proceeds_usd", "net_proceeds_usd",
                  "net_profit_usd", "roi_pct"):
            assert k in tr, k

    def test_source_comparison_has_single_winner(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        sc = d["source_comparison"]
        cands = sc["candidates"]
        # all four precedence sources are always listed
        sources = {c["source"] for c in cands}
        assert {"position", "manual_override", "portal", "manual_fallback"} <= sources
        winners = [c for c in cands if c["winner"]]
        assert len(winners) == 1
        assert winners[0]["source"] == sc["winner_source"]

    def test_decision_trace_block(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        dt = d["decision_trace"]
        assert dt["gate_verdict"] in {"GO", "WAIT", "NO_GO"}
        assert dt["interlock_verdict"] in {"READY", "WAIT", "BLOCKED"}
        assert isinstance(dt["conditions"], list) and dt["conditions"]
        assert isinstance(dt["explanation"], list) and dt["explanation"]


# ---------------- Dual ROI model (fresh cycle = execution authority) ----------------

class TestDualRoi:
    def test_intel_exposes_dual_roi(self, client, bdag_route_id):
        d = client.get(f"{BASE}/api/execution/intel/{bdag_route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface right now")
        dr = d["dual_roi"]
        assert dr["authority"] == "fresh_cycle"
        assert dr["fresh_cycle"]["is_execution_authority"] is True
        assert dr["existing_position"]["is_execution_authority"] is False

    def test_fresh_cycle_uses_live_swap_not_position(self, client, bdag_route_id):
        """The authoritative buy price must be the FRESH (live swap) source, never
        the held-position cost basis."""
        d = client.get(f"{BASE}/api/execution/intel/{bdag_route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface right now")
        assert d["buy_price_source"] in {"portal", "manual_override", "manual_fallback"}
        assert d["buy_price_source"] != "position"
        # the fresh buy price equals the top-level (authoritative) buy price
        assert abs(d["dual_roi"]["fresh_cycle"]["buy_price"] - d["buy_price"]) < 1e-12

    def test_existing_position_is_informational(self, client, bdag_route_id):
        d = client.get(f"{BASE}/api/execution/intel/{bdag_route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live opportunity surface right now")
        ep = d["dual_roi"]["existing_position"]
        assert ep["buy_source"] == "Position Cost Basis"

    def test_gate_verdict_follows_fresh_roi(self, client):
        """The gate verdict must be consistent with the FRESH cycle ROI, not the
        (informational) existing-position ROI."""
        g = client.get(f"{BASE}/api/execution/opportunity/gate", timeout=20).json()
        if not g.get("available"):
            pytest.skip("gate unavailable")
        dr = g.get("dual_roi")
        assert dr is not None
        fresh_roi = dr["fresh_cycle"]["roi_pct"]
        # if fresh ROI is non-positive, the gate cannot be GO
        if fresh_roi is not None and fresh_roi <= 0:
            assert g["gate_verdict"] in {"WAIT", "NO_GO"}

    def test_price_verification_carries_dual_roi(self, client):
        d = client.get(f"{BASE}/api/execution/price-verification", timeout=25).json()
        assert d["dual_roi"]["authority"] == "fresh_cycle"
        assert d["dual_roi"]["fresh_cycle"]["is_execution_authority"] is True


# ---------------- auth + non-execution invariant ----------------

class TestSafety:
    def test_anon_blocked(self):
        assert requests.get(f"{BASE}/api/execution/price-verification", timeout=10).status_code == 401

    def test_execution_remains_disabled(self, client):
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert cfg["execution_enabled"] is False
        assert cfg["wallet_enabled"] is False
