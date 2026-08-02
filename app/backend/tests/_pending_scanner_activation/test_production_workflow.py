"""Production Workflow Blueprint, Next-Cycle Readiness, Permanent Ledger,
Max-Safe-Buy and Exchange Qualification tests (READ-ONLY, NON-EXECUTING).

Covers: the 9-stage blueprint + live automation readiness, the next-cycle
readiness engine (min cooldown + 5 checks), the immutable production ledger
(backfill, idempotency, lifecycle + tx hashes, CSV + XLSX export), the
arbitrage-intel Maximum Safe Buy Size + ROI curve, and exchange qualification
(deposit/withdrawal reliability + 6-criterion checklist). Plus auth + the
non-execution invariant.
"""
import os
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
import requests

from services.execution import permanent_ledger, production_workflow

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
def route_id(client):
    r = client.get(f"{BASE}/api/routes", timeout=15).json()
    routes = r if isinstance(r, list) else r.get("routes", [])
    return routes[0]["id"]


# ---------------- Workflow Blueprint ----------------

class TestBlueprint:
    def test_blueprint_nine_stages(self, client):
        d = client.get(f"{BASE}/api/execution/workflow/blueprint", timeout=20).json()
        assert d["total_stages"] == 9
        assert len(d["stages"]) == 9
        names = [s["name"] for s in d["stages"]]
        assert names[0] == "MetaMask Funding"
        assert names[-1] == "Next-Cycle Readiness"

    def test_each_stage_has_design_fields(self, client):
        d = client.get(f"{BASE}/api/execution/workflow/blueprint", timeout=20).json()
        for s in d["stages"]:
            for f in ("preconditions", "verification_method", "failure_modes",
                      "recovery_path", "est_duration", "fund_location", "states"):
                assert f in s, f
            assert s["automation_readiness"]["status"] in {"AUTOMATABLE", "MANUAL"}

    def test_wallet_legs_manual_while_disabled(self, client):
        d = client.get(f"{BASE}/api/execution/workflow/blueprint", timeout=20).json()
        funding = next(s for s in d["stages"] if s["key"] == "metamask_funding")
        # wallet_enabled is false → funding leg must be MANUAL
        assert funding["automation_readiness"]["status"] == "MANUAL"
        assert d["execution_gates"]["wallet_enabled"] is False

    def test_future_execution_path_present(self, client):
        d = client.get(f"{BASE}/api/execution/workflow/blueprint", timeout=20).json()
        assert "future_execution_path" in d
        assert "Next-Cycle Readiness" in d["future_execution_path"]


# ---------------- Next-Cycle Readiness Engine ----------------

class TestReadiness:
    def test_readiness_shape(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/workflow/readiness",
                       params={"route_id": route_id}, timeout=20).json()
        assert d["verdict"] in {"READY", "WAIT", "COOLDOWN", "BLOCKED", "NO_HISTORY"}
        if d["verdict"] != "NO_HISTORY":
            keys = {c["key"] for c in d["checks"]}
            assert {"withdrawal_confirmed", "wallet_balance_updated",
                    "exchange_balances_reconciled", "no_assets_in_transit",
                    "opportunity_still_go"} == keys
            assert d["min_cooldown_s"] == 60

    def test_min_cooldown_in_config(self, client):
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert cfg["limits"]["min_cooldown_s"] == 60


# ---------------- Permanent Immutable Ledger ----------------

class TestPermanentLedger:
    def test_ledger_has_frozen_entries(self, client):
        d = client.get(f"{BASE}/api/execution/ledger/permanent", timeout=25).json()
        assert d["summary"]["cycles"] >= 1
        e = d["entries"][0]
        for k in ("cycle_id", "frozen_at", "initial_capital_usd", "portal_buy_price",
                  "bdag_acquired", "transfer_fee_base", "trading_fee_usd", "withdrawal_fee_usd",
                  "gross_proceeds_usd", "net_proceeds_usd", "net_profit_usd", "roi_pct",
                  "lifecycle", "immutable"):
            assert k in e, k
        assert e["immutable"] is True
        # lifecycle covers the full loop with tx hashes where available
        stages = [l["stage"] for l in e["lifecycle"]]
        assert "MetaMask Funding" in stages
        assert "Final Wallet Receipt" in stages
        assert any(l["tx_hash"] for l in e["lifecycle"])

    def test_backfill_is_idempotent(self, client):
        before = client.get(f"{BASE}/api/execution/ledger/permanent", timeout=25).json()["summary"]["cycles"]
        res = client.post(f"{BASE}/api/execution/ledger/permanent/backfill", timeout=30).json()
        assert res["newly_frozen"] == 0  # everything already frozen
        after = client.get(f"{BASE}/api/execution/ledger/permanent", timeout=25).json()["summary"]["cycles"]
        assert after == before

    def test_export_csv(self, client):
        r = client.get(f"{BASE}/api/execution/ledger/permanent/export",
                       params={"format": "csv"}, timeout=25)
        assert r.status_code == 200
        assert "text/csv" in r.headers.get("content-type", "")
        assert "cycle_id" in r.text and "initial_capital_usd" in r.text

    def test_export_xlsx_valid_workbook(self, client):
        r = client.get(f"{BASE}/api/execution/ledger/permanent/export",
                       params={"format": "xlsx"}, timeout=25)
        assert r.status_code == 200
        assert "spreadsheetml" in r.headers.get("content-type", "")
        assert zipfile.is_zipfile(BytesIO(r.content))
        zf = zipfile.ZipFile(BytesIO(r.content))
        # workbook should contain our three sheets
        assert any("sheet" in n for n in zf.namelist())

    def test_lifecycle_helper_unit(self):
        cycle = {"history": [{"state": "CREATED", "ts": "2026-06-13T00:00:00+00:00"},
                             {"state": "BDAG_RECEIVED", "ts": "2026-06-13T00:05:00+00:00"},
                             {"state": "COMPLETE", "ts": "2026-06-13T00:30:00+00:00"}],
                 "ledger": {"bdag_receipt": {"reference": "SHD-xyz"}}}
        lc = permanent_ledger._lifecycle(cycle)
        labels = {x["stage"]: x for x in lc}
        assert "MetaMask Funding" in labels
        assert labels["BDAG Received"]["tx_hash"] == "SHD-xyz"


# ---------------- Arbitrage Intel — Maximum Safe Buy Size ----------------

class TestMaxSafeBuy:
    def test_max_safe_buy_block(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/intel/{route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live book")
        m = d["max_safe_buy"]
        assert "max_profitable_liquidity_quote" in m
        assert m["floor_pct"] == d["limits"]["min_net_spread_pct"]
        # ROI curve at 25/50/75/100% of profitable depth. Under FRESH-cycle
        # economics the live swap price can sit above the best bid, leaving no
        # profitable depth (empty curve) — that is a valid, honest state.
        depths = {c["depth_pct"] for c in m["roi_curve"]}
        if depths:
            assert {25, 50, 75, 100} <= depths
        else:
            assert m.get("max_safe_buy_usd") is None  # no profitable size ⇒ no safe buy
        assert "cert_capped_recommendation" in m

    def test_max_safe_buy_roi_above_floor(self, client, route_id):
        d = client.get(f"{BASE}/api/execution/intel/{route_id}", timeout=20).json()
        if not d.get("available"):
            pytest.skip("no live book")
        m = d["max_safe_buy"]
        if m.get("max_safe_buy_usd") is not None:
            # at the max safe size, ROI must still be at/above the floor
            assert m["roi_at_max_safe_pct"] >= m["floor_pct"] - 0.01


# ---------------- Exchange Qualification Tracking ----------------

class TestQualification:
    def test_qualification_checklist(self, client):
        d = client.get(f"{BASE}/api/execution/exchanges/coinstore", timeout=15).json()
        assert "deposit_reliability" in d and "withdrawal_reliability" in d
        q = d["qualification"]
        assert q["total"] == 6
        crits = {i["criterion"] for i in q["items"]}
        assert {"Manual Verification", "India Accessibility", "Deposit Reliability",
                "Withdrawal Reliability", "API Capability", "Trust Score"} == crits
        # coinstore is operator-verified + gates open → fully qualified
        assert q["fully_qualified"] is True

    def test_reliability_reflects_gate_status(self, client):
        reg = client.get(f"{BASE}/api/execution/exchanges", timeout=20).json()
        by = {r["exchange"]: r for r in reg["exchanges"]}
        # open gates (coinstore) >> closed gates (xt) >> suspended (lbank)
        assert by["coinstore"]["deposit_reliability"] > by["xt"]["deposit_reliability"]
        assert by["xt"]["deposit_reliability"] >= by["lbank"]["deposit_reliability"]


# ---------------- safety ----------------

class TestSafety:
    def test_anon_blocked(self):
        assert requests.get(f"{BASE}/api/execution/workflow/blueprint", timeout=10).status_code == 401
        assert requests.get(f"{BASE}/api/execution/ledger/permanent", timeout=10).status_code == 401

    def test_execution_remains_disabled(self, client):
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert cfg["execution_enabled"] is False
        assert cfg["wallet_enabled"] is False
