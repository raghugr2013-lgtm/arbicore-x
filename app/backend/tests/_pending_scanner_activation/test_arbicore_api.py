"""ArbiCore backend API tests — routes, snapshot, positions, transfers, connectors."""
import os
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", timeout=30,
               json={"username": "admin", "password": "ArbiCore#2026"})
    assert r.status_code == 200, f"auth failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def seeded_route(session):
    r = session.get(f"{API}/routes", timeout=30)
    assert r.status_code == 200, r.text
    routes = r.json()
    assert isinstance(routes, list) and len(routes) >= 1
    target = next((x for x in routes if "BDAG" in x.get("name", "")), routes[0])
    assert "id" in target
    return target


# ------- Routes & connectors -------

class TestRoutesAndConnectors:
    def test_get_routes_has_bdag_xt(self, session):
        r = session.get(f"{API}/routes", timeout=30)
        assert r.status_code == 200
        routes = r.json()
        names = [x.get("name") for x in routes]
        assert any("BDAG" in (n or "") for n in names), f"No BDAG route found: {names}"

    def test_connectors_lists_13_exchanges_plus_wallet(self, session):
        r = session.get(f"{API}/connectors", timeout=30)
        assert r.status_code == 200
        data = r.json()
        assert "exchanges" in data and "wallets" in data
        ex_keys = {e.get("key") for e in data["exchanges"]}
        for live in ("xt", "mexc", "gate", "bitmart"):
            assert live in ex_keys, f"Missing live connector: {live}"
        assert len(data["exchanges"]) >= 13, f"Expected >=13 exchange connectors, got {len(data['exchanges'])}: {ex_keys}"
        assert any("coinstore" in (e.get("key") or "").lower() for e in data["exchanges"]), "coinstore stub missing"
        wallet_keys = {w.get("key") for w in data["wallets"]}
        assert "evm_watch" in wallet_keys


# ------- Snapshot -------

class TestSnapshotLive:
    def test_snapshot_shape_and_verdict(self, session, seeded_route):
        # Allow collector to do at least one cycle
        time.sleep(12)
        rid = seeded_route["id"]
        r = session.get(f"{API}/routes/{rid}/snapshot", timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("route", "evaluation", "comparison", "orderbook", "spread_history", "system"):
            assert k in d, f"Missing {k}"

        ev = d["evaluation"]
        assert ev is not None, "Evaluation should be present after collector cycle"
        # Verdict is live-data dependent: NO_GO when XT BDAG deposits are flagged
        # disabled, WAIT when the deposit flag is unknown/open but other criteria hold.
        assert ev.get("verdict") in ("NO_GO", "WAIT"), f"Unexpected verdict {ev.get('verdict')}"

        gates = {g["id"]: g for g in ev.get("gates", [])}
        assert "G1_DEPOSIT" in gates
        # G1 reflects the live deposit gate flag; when it fails the verdict must be NO_GO.
        if gates["G1_DEPOSIT"]["passed"] is False:
            assert ev.get("verdict") == "NO_GO", f"G1 failed but verdict={ev.get('verdict')}"
        # G2/G3/G4 should pass (data fresh, market online, profitable)
        for gk in ("G2_MARKET", "G3_FRESHNESS", "G4_PROFITABLE"):
            assert gk in gates, f"Missing gate {gk}; got {list(gates)}"
            assert gates[gk]["passed"] is True, f"Gate {gk} should pass: {gates[gk]}"

        scores = ev.get("scores", {})
        for s in ("spread", "liquidity", "volatility", "transfer_risk", "overall"):
            assert s in scores, f"Missing score {s}"

        assert ev.get("spread", {}).get("gross_pct") is not None
        assert ev.get("spread", {}).get("net_pct") is not None
        be = ev.get("breakeven", {})
        assert be.get("price") is not None
        assert "distance_pct" in be

        cap = ev.get("capacity", {})
        for k in ("min_buy", "recommended", "max_safe", "optimal"):
            assert k in cap, f"Missing capacity field {k}"

        comp = d["comparison"]
        assert len(comp) == 5  # xt, mexc, gate, bitmart, coinstore (Sprint 2+)
        by_ex = {c["exchange"]: c for c in comp}
        assert by_ex["xt"]["listed"] is True
        assert by_ex["bitmart"]["listed"] is True
        assert by_ex["bitmart"].get("deposit_enabled") is True
        assert by_ex["mexc"]["listed"] is False
        assert by_ex["gate"]["listed"] is False

        ob = d["orderbook"]
        assert ob is not None and "bids" in ob and "asks" in ob
        assert len(ob["bids"]) > 0 and len(ob["asks"]) > 0

        assert isinstance(d["spread_history"], list)

        networks = d["system"]["networks"]
        assert "BSC" in networks and "BLOCKDAG" in networks
        assert networks["BSC"]["healthy"] is True
        assert networks["BLOCKDAG"]["healthy"] is False


# ------- Positions lifecycle -------

class TestPositionsLifecycle:
    def test_create_negative_price_rejected(self, session, seeded_route):
        r = session.post(f"{API}/positions",
                         json={"route_id": seeded_route["id"], "buy_price": -1, "qty": 1000}, timeout=30)
        assert r.status_code == 400

    def test_position_full_lifecycle(self, session, seeded_route):
        rid = seeded_route["id"]
        r = session.post(f"{API}/positions",
                         json={"route_id": rid, "buy_price": 0.000035, "qty": 5000000,
                               "notes": "TEST_lifecycle"}, timeout=30)
        assert r.status_code == 200, r.text
        pos = r.json()
        assert pos["status"] == "BOUGHT"
        pid = pos["id"]

        # GET verify
        g = session.get(f"{API}/positions?route_id={rid}", timeout=30)
        assert g.status_code == 200
        assert any(p["id"] == pid for p in g.json())

        # invalid status
        bad = session.patch(f"{API}/positions/{pid}", json={"status": "INVALID"}, timeout=30)
        assert bad.status_code == 400

        # advance through statuses
        for s in ["IN_WALLET", "TRANSFERRING", "ON_EXCHANGE"]:
            rr = session.patch(f"{API}/positions/{pid}", json={"status": s}, timeout=30)
            assert rr.status_code == 200
            assert rr.json()["status"] == s

        sold = session.patch(f"{API}/positions/{pid}",
                             json={"status": "SOLD",
                                   "sell": {"price": 0.00004, "qty": 5000000,
                                            "proceeds_quote": 0.00004 * 5000000}}, timeout=30)
        assert sold.status_code == 200
        sold_doc = sold.json()
        assert sold_doc["status"] == "SOLD"
        expected_pnl = 0.00004 * 5000000 - 0.000035 * 5000000
        assert sold_doc["realized_pnl_quote"] == pytest.approx(expected_pnl, rel=1e-6)

        sett = session.patch(f"{API}/positions/{pid}", json={"status": "SETTLED"}, timeout=30)
        assert sett.status_code == 200
        assert sett.json()["status"] == "SETTLED"


# ------- Transfers -------

class TestTransfers:
    def test_create_transfer_with_duration(self, session, seeded_route):
        sent = "2026-01-10T10:00:00+00:00"
        cred = "2026-01-10T10:05:30+00:00"
        body = {"route_id": seeded_route["id"], "qty": 5000000,
                "sent_at": sent, "credited_at": cred,
                "tx_hash": "TEST_0xabc", "notes": "TEST_transfer"}
        r = session.post(f"{API}/transfers", json=body, timeout=30)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc["status"] == "complete"
        assert doc["duration_s"] == 330.0

        g = session.get(f"{API}/transfers?route_id={seeded_route['id']}", timeout=30)
        assert g.status_code == 200
        assert any(t.get("tx_hash") == "TEST_0xabc" for t in g.json())


# ------- Simulation mode -------

class TestSimulationMode:
    def test_mode_switch_simulation_and_back(self, session, seeded_route):
        rid = seeded_route["id"]

        # Switch to simulation
        r = session.patch(f"{API}/routes/{rid}", json={"mode": "simulation"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["mode"] == "simulation"

        # Wait for collector cycle
        time.sleep(15)
        snap = session.get(f"{API}/routes/{rid}/snapshot", timeout=30).json()
        ev = snap.get("evaluation")
        assert ev is not None
        assert ev.get("mode") == "simulation", f"Evaluation mode should be simulation, got {ev.get('mode')}"

        # Comparison rows should reflect sim source
        sources = {c["exchange"]: c.get("source") for c in snap["comparison"]}
        sim_count = sum(1 for s in sources.values() if s == "sim")
        assert sim_count >= 3, f"Expected >=3 sim sources, got {sources}"

        # Verdict should NOT be blocked by G1 in sim default
        gates = {g["id"]: g for g in ev.get("gates", [])}
        assert gates["G1_DEPOSIT"]["passed"] is True, "Sim default should have deposits enabled"

        # Restore to live
        r2 = session.patch(f"{API}/routes/{rid}", json={"mode": "live"}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["mode"] == "live"
