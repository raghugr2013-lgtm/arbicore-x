"""ArbiCore Sprint 2 backend tests — snapshot v2 (confidence, hold_probability, venue_matrix),
replay, treasury+ledger, discovery, coinstore connector, preset switching."""
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
def route(session):
    r = session.get(f"{API}/routes", timeout=30)
    assert r.status_code == 200
    routes = r.json()
    target = next((x for x in routes if "BDAG" in (x.get("name") or "")), routes[0])
    return target


# ---------- Connectors (Coinstore live) ----------

class TestConnectorsCoinstoreLive:
    def test_coinstore_is_live(self, session):
        r = session.get(f"{API}/connectors", timeout=30)
        assert r.status_code == 200
        data = r.json()
        ex = {e["key"]: e for e in data["exchanges"]}
        assert "coinstore" in ex
        assert ex["coinstore"].get("live") is True, f"coinstore must be live: {ex['coinstore']}"
        live = [e for e in data["exchanges"] if e.get("live")]
        assert len(live) >= 5, f"Expected >=5 live connectors, got {len(live)}"
        assert len(data["exchanges"]) >= 13


# ---------- Snapshot v2 ----------

class TestSnapshotV2:
    def test_snapshot_confidence_holdprob_venue_matrix(self, session, route):
        time.sleep(12)
        rid = route["id"]
        r = session.get(f"{API}/routes/{rid}/snapshot", timeout=30)
        assert r.status_code == 200
        d = r.json()
        ev = d["evaluation"]
        assert ev is not None

        # confidence
        conf = ev.get("confidence")
        assert conf is not None, "confidence missing"
        assert "score" in conf and isinstance(conf["score"], (int, float))
        assert 0 <= conf["score"] <= 100
        comps = conf.get("components", {})
        for k in ("spread", "liquidity", "capacity", "transfer",
                  "exchange_capability", "exchange_trust",
                  "hold_probability", "route_feasibility"):
            assert k in comps, f"confidence.components missing {k}: {comps}"
        assert "missing" in conf and isinstance(conf["missing"], list)

        # hold_probability
        hp = ev.get("hold_probability")
        assert hp is not None, "hold_probability missing"
        for k in ("probability", "sample_count", "horizon_min", "status", "quantiles"):
            assert k in hp, f"hold_probability missing {k}"
        assert hp["status"] in ("active", "collecting")
        if hp.get("quantiles") is not None:
            for q in ("p10", "p50", "p90"):
                assert q in hp["quantiles"]

        # venue_matrix
        vm = ev.get("venue_matrix")
        assert isinstance(vm, list) and len(vm) == 5
        by_ex = {v["exchange"]: v for v in vm}
        for k in ("xt", "mexc", "gate", "bitmart", "coinstore"):
            assert k in by_ex, f"venue_matrix missing {k}"
        # XT listed, deposit disabled
        assert by_ex["xt"]["listed"] is True
        assert by_ex["xt"].get("deposit_enabled") is False
        for k in ("verdict", "confidence", "net_spread_pct", "recommended", "overall"):
            assert k in by_ex["xt"], f"xt row missing {k}"
        # BitMart listed, deposit enabled
        assert by_ex["bitmart"]["listed"] is True
        assert by_ex["bitmart"].get("deposit_enabled") is True
        # Coinstore listed
        assert by_ex["coinstore"]["listed"] is True
        # not-listed venues
        assert by_ex["mexc"]["listed"] is False
        assert by_ex["gate"]["listed"] is False

        # comparison has 5 rows including coinstore with live last
        comp = d["comparison"]
        assert len(comp) == 5
        by_c = {c["exchange"]: c for c in comp}
        assert by_c["coinstore"]["listed"] is True
        assert by_c["coinstore"].get("last") is not None
        assert by_c["coinstore"].get("source") == "live"


# ---------- Replay ----------

class TestReplay:
    def test_replay_6h(self, session, route):
        r = session.get(f"{API}/routes/{route['id']}/replay?hours=6", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["evaluations_count"] > 0
        vc = d["verdict_counts"]; vp = d["verdict_pct"]
        assert isinstance(vc, dict) and isinstance(vp, dict)
        total_pct = sum(vp.values())
        assert 99.0 <= total_pct <= 101.0, f"verdict_pct should ~sum to 100: {vp}"
        ns = d["net_spread"]
        for k in ("min", "max", "avg", "last"):
            assert k in ns
        gf = d["gate_failures"]
        assert isinstance(gf, dict)
        # G1_DEPOSIT must dominate (XT deposits disabled)
        if gf:
            top = max(gf, key=gf.get)
            assert top == "G1_DEPOSIT", f"Expected G1_DEPOSIT dominant: {gf}"
        bo = d["blocked_opportunity"]
        assert "evaluations" in bo and "approx_minutes" in bo
        tl = d["timeline"]
        assert isinstance(tl, list) and len(tl) > 0
        for k in ("ts", "verdict", "net_pct", "overall"):
            assert k in tl[0]

    def test_replay_hours_clamped(self, session, route):
        r = session.get(f"{API}/routes/{route['id']}/replay?hours=500", timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["hours"] <= 72, f"hours should be clamped to <=72: {d['hours']}"


# ---------- Treasury + ledger ----------

class TestTreasuryAndLedger:
    def test_treasury_summary_and_conversion(self, session, route):
        r = session.get(f"{API}/treasury/{route['id']}", timeout=30)
        assert r.status_code == 200
        d = r.json()
        s = d["summary"]
        for k in ("cost_quote", "proceeds_quote", "realized_pnl_quote",
                  "open_qty", "open_value_quote", "unrealized_pnl_quote",
                  "positions", "open_positions"):
            assert k in s, f"summary missing {k}"
        conv = d["conversion"]
        assert conv["pair"] == "BNB/USDT"
        assert 300 < conv["rate"] < 1500, f"BNB rate looks off: {conv['rate']}"
        assert "taker_fee_pct" in conv

    def test_ledger_entries_on_position_lifecycle(self, session, route):
        rid = route["id"]
        # Create position -> 'purchase' ledger
        r = session.post(f"{API}/positions",
                         json={"route_id": rid, "buy_price": 0.000035, "qty": 1000000,
                               "notes": "TEST_s2_ledger"}, timeout=30)
        assert r.status_code == 200
        pid = r.json()["id"]

        # SOLD -> 'sell' ledger
        for s in ("IN_WALLET", "TRANSFERRING", "ON_EXCHANGE"):
            assert session.patch(f"{API}/positions/{pid}", json={"status": s}, timeout=30).status_code == 200
        sold = session.patch(f"{API}/positions/{pid}",
                             json={"status": "SOLD",
                                   "sell": {"price": 0.00004, "qty": 1000000,
                                            "proceeds_quote": 40.0}}, timeout=30)
        assert sold.status_code == 200

        # SETTLED -> 'settlement' ledger
        sett = session.patch(f"{API}/positions/{pid}",
                             json={"status": "SETTLED",
                                   "settlement": {"coin": "BNB", "amount": 0.06, "quote_value": 36.4}},
                             timeout=30)
        assert sett.status_code == 200

        # Verify ledger has all 3 entry types for this position
        tr = session.get(f"{API}/treasury/{rid}", timeout=30).json()
        legs = [e.get("leg") for e in tr["ledger"] if e.get("position_id") == pid]
        assert "purchase" in legs, f"missing purchase leg; got {legs}"
        assert "sell" in legs, f"missing sell leg; got {legs}"
        assert "settlement" in legs, f"missing settlement leg; got {legs}"


# ---------- Discovery ----------

class TestDiscovery:
    def test_discovery_scan_and_latest(self, session):
        r = session.post(f"{API}/discovery/scan?asset=BDAG", timeout=30)
        assert r.status_code == 200
        d = r.json()
        sources = d.get("sources", {})
        assert sources.get("connectors") == "ok"
        assert sources.get("coingecko") in ("ok", "throttled", "error", "off")
        venues = d.get("venues", [])
        assert len(venues) >= 5
        by_key = {v.get("key"): v for v in venues if v.get("source") == "connector"}
        for k in ("xt", "bitmart", "coinstore"):
            assert by_key.get(k, {}).get("listed") is True, f"{k} should be listed"
        for k in ("mexc", "gate"):
            assert by_key.get(k, {}).get("listed") is False, f"{k} should not be listed"

        latest = session.get(f"{API}/discovery/latest?asset=BDAG", timeout=30)
        assert latest.status_code == 200
        ld = latest.json()
        assert ld is not None and ld.get("asset") == "BDAG"
        assert "venues" in ld and "sources" in ld


# ---------- Preset switching (exit venue) ----------

class TestPresetSwitching:
    def test_switch_exit_to_bitmart_then_restore(self, session, route):
        rid = route["id"]
        try:
            r = session.patch(f"{API}/routes/{rid}",
                              json={"exit": {"exchange": "bitmart", "base": "BDAG", "quote": "USDT"}},
                              timeout=30)
            assert r.status_code == 200
            assert r.json()["exit"]["exchange"] == "bitmart"

            # wait for collector to re-run with new exit
            time.sleep(17)
            snap = session.get(f"{API}/routes/{rid}/snapshot", timeout=30).json()
            ev = snap["evaluation"]
            assert ev["exchange"] == "bitmart", f"snapshot still on {ev['exchange']}"
            gates = {g["id"]: g for g in ev.get("gates", [])}
            # G1 should pass on bitmart (deposits enabled)
            assert gates.get("G1_DEPOSIT", {}).get("passed") is True, f"G1 should pass on bitmart: {gates.get('G1_DEPOSIT')}"
        finally:
            # restore to xt
            rb = session.patch(f"{API}/routes/{rid}",
                               json={"exit": {"exchange": "xt", "base": "BDAG", "quote": "USDT"}},
                               timeout=30)
            assert rb.status_code == 200
            assert rb.json()["exit"]["exchange"] == "xt"
