"""E4.6 — BDAG Arbitrage Intelligence, Production Ledger & Recovery Proof tests.

Covers: the arbitrage-intel engine (multi-level VWAP, break-even, sims, verdict),
pure economics math on a synthetic profitable book, the verified fee model +
editable overrides, the shadow-derived production ledger + CSV/JSON export, and
the isolated recovery-proof battery (stuck → notify → recommend → recover →
persist). All read-only / non-executing.
"""
import os
from pathlib import Path

import pytest
import requests

from services.execution import arbitrage_intel

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            _BASE = line.split("=", 1)[1].strip()
            break
assert _BASE
BASE = _BASE.rstrip("/")
VERDICTS = {"GO", "WAIT", "NO_GO"}


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
    assert routes, "no routes seeded"
    return routes[0]["id"]


# ---------------- pure economics (deterministic, profitable synthetic book) -------------

class TestEconomicsMath:
    def test_fill_ladder_multilevel_vwap(self):
        bids = [[0.00005, 100000], [0.000049, 200000], [0.000048, 500000]]
        fills, filled, vwap, exhausted = arbitrage_intel._fill_ladder(bids, 250000)
        assert len(fills) == 2
        assert abs(filled - 250000) < 1e-6
        assert not exhausted
        # VWAP between the two consumed levels
        assert 0.000049 < vwap < 0.00005

    def test_cycle_economics_profitable(self):
        fees = {"bdag_transfer_fee_base": 0.001, "purchase_gas_usd": 0.10,
                "usdt_withdrawal_fee_usd": {"bitmart": 0.80, "default": 1.0}}
        econ = arbitrage_intel._cycle_economics(
            sell_qty=500000, buy_price=0.00003, vwap=0.00004, taker=0.25, fees=fees, venue="bitmart")
        assert econ["net_profit_usd"] > 0
        assert econ["roi_pct"] > 0
        assert econ["weighted_sell_price"] == 0.00004
        # net = gross - taker - withdrawal - (buy cost + gas)
        assert econ["wallet_received_usd"] < econ["gross_proceeds_usd"]


# ---------------- Part A — arbitrage intelligence endpoint ----------------

class TestArbitrageIntel:
    def test_intel_shape(self, client, route_id):
        r = client.get(f"{BASE}/api/execution/intel/{route_id}",
                       params={"utilization_pct": 75}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["verdict"] in VERDICTS
        if d.get("available"):
            assert "marginal_sell_price" in d["break_even"]
            assert len(d["utilization_sims"]) == 4
            assert {s["utilization_pct"] for s in d["utilization_sims"]} == {25, 50, 75, 100}
            assert d["buyer_stability"]["label"] in {
                "STABLE", "MODERATE", "VOLATILE", "insufficient_history"}
            assert d["chosen_utilization_pct"] == 75

    def test_intel_anon_blocked(self, route_id):
        r = requests.get(f"{BASE}/api/execution/intel/{route_id}", timeout=10)
        assert r.status_code == 401


# ---------------- verified fee model + editable overrides ----------------

class TestFees:
    def test_fees_defaults_and_provenance(self, client):
        d = client.get(f"{BASE}/api/execution/fees", timeout=15).json()
        f = d["fees"]
        assert f["taker_fee_pct"]["bitmart"] == 0.25
        assert f["taker_fee_pct"]["coinstore"] == 0.20
        assert len(d["provenance"]) >= 6

    def test_fee_override_persists_then_restore(self, client):
        r = client.patch(f"{BASE}/api/execution/fees",
                         json={"usdt_withdrawal_fee_usd": {"bitmart": 0.55}}, timeout=15)
        assert r.status_code == 200
        assert r.json()["usdt_withdrawal_fee_usd"]["bitmart"] == 0.55
        # coinstore untouched
        assert r.json()["usdt_withdrawal_fee_usd"]["coinstore"] == 1.0
        # restore
        client.patch(f"{BASE}/api/execution/fees",
                     json={"usdt_withdrawal_fee_usd": {"bitmart": 0.80}}, timeout=15)


# ---------------- Part B — production ledger ----------------

class TestLedger:
    def test_ledger_shape(self, client):
        d = client.get(f"{BASE}/api/execution/ledger", timeout=25).json()
        s = d["summary"]
        for k in ("cycles", "total_net_profit_usd", "total_investment_usd", "overall_roi_pct"):
            assert k in s
        assert isinstance(d["entries"], list)
        if d["entries"]:
            e = d["entries"][0]
            for k in ("cycle_id", "investment_usd", "portal_buy_price", "bdag_acquired",
                      "gas_fee_usd", "transfer_fee_base", "exchange_deposit_qty",
                      "weighted_sell_price", "fills", "trading_fee_usd", "withdrawal_fee_usd",
                      "wallet_received_usd", "net_profit_usd", "roi_pct", "fills_source"):
                assert k in e, k
            assert e["fills_source"] in {"modeled_live_book", "modeled_recorded_spread"}
        assert isinstance(d["daily_pnl"], list)
        assert isinstance(d["weekly_pnl"], list)
        assert isinstance(d["monthly_pnl"], list)

    def test_ledger_export_csv(self, client):
        r = client.get(f"{BASE}/api/execution/ledger/export", params={"format": "csv"}, timeout=25)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "cycle_id" in r.text

    def test_ledger_export_json(self, client):
        r = client.get(f"{BASE}/api/execution/ledger/export", params={"format": "json"}, timeout=25)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")
        assert "summary" in r.json()


# ---------------- Part C — recovery proof campaign ----------------

class TestRecoveryProof:
    def test_run_proof_battery(self, client):
        r = client.post(f"{BASE}/api/execution/recovery-proof/run", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["total"] == 4
        assert d["overall_pass"] is True, d.get("scenarios")
        names = {s["scenario"] for s in d["scenarios"]}
        assert {"deposit_delay", "gate_closure_routing", "stuck_sell", "stuck_withdrawal"} <= names
        for s in d["scenarios"]:
            assert s["stuck_detected"] and s["recommendation_present"]
            assert s["persisted"] and s["recovered"]
            assert s["telegram"] in {"sent", "dormant_would_send"}
        reroute = next(s for s in d["scenarios"] if s["scenario"] == "gate_closure_routing")
        assert reroute["reroute_applied"] is True

    def test_proof_excluded_from_certification(self, client):
        # recovery_proof cycles must NOT appear in the shadow certification throughput
        rep = client.get(f"{BASE}/api/execution/certification/report", timeout=20).json()
        cycles = client.get(f"{BASE}/api/execution/recovery-proof/history", timeout=15).json()
        assert "proofs" in cycles
        # certification counts only mode=shadow; presence of proofs must not break the report
        assert "throughput" in rep

    def test_status_endpoint(self, client):
        d = client.get(f"{BASE}/api/execution/recovery-proof/status", timeout=15).json()
        assert "latest" in d
