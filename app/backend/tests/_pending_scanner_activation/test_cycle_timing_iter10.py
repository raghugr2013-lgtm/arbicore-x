"""Iter10 - Cycle Timing + Risk Decay backend tests."""
import os
import time
import pytest
import requests

def _load_frontend_env_url():
    try:
        with open("/app/frontend/.env") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().rstrip("/")
    except Exception:
        pass
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env_url() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL not set"
ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCore2026!"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# ---------------- /cycle-timing endpoint ----------------

class TestCycleTiming:
    def test_report_top_keys(self, client):
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("phase", "generated_at", "closed_cycles_used",
                  "total_duration_s", "stage_durations_s",
                  "drift_distribution_pct", "per_cycle", "guardrails"):
            assert k in d, f"missing key: {k}"
        assert isinstance(d["closed_cycles_used"], int)
        # 7 stages in order
        names = [s["stage"] for s in d["stage_durations_s"]]
        assert names == [
            "quote_to_swap_submit", "swap_settlement", "wallet_credit",
            "transfer_send", "transfer_to_coinstore", "ready_to_sell",
            "withdraw_to_wallet"], names
        # drift sub-keys
        drift = d["drift_distribution_pct"]
        for sub in ("end_drift_pct", "worst_drift_pct", "best_drift_pct", "samples_used"):
            assert sub in drift
        # guardrails all false
        for k, v in d["guardrails"].items():
            assert v is False, f"guardrail {k} not False"

    def test_limit_zero_invalid(self, client):
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing?limit=0")
        assert r.status_code == 400
        assert "must be in (0, 500]" in r.json().get("detail", "")

    def test_limit_too_large(self, client):
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing?limit=501")
        assert r.status_code == 400


# ---------------- /cycle-timing/forecast endpoint ----------------

class TestForecast:
    def test_forecast_happy_path(self, client):
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing/forecast",
                       params={"captured_price": 3.6e-5,
                               "best_bid": 3.94e-5,
                               "investment_usd": 50})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d.get("available") is True
        assert abs(d["spread_pct"] - 9.4444) < 0.05
        assert abs(d["expected_gross_proceeds_usd"] - 54.7222) < 0.5
        assert abs(d["expected_profit_usd"] - 4.61) < 0.2
        assert abs(d["trading_fee_usd"] - 0.1094) < 0.05
        assert abs(d["breakeven_drift_pct"] - (-9.4444)) < 0.05
        assert "history_block" in d
        hb = d["history_block"]
        assert "closed_cycles_used" in hb and "duration" in hb and "drift" in hb
        # If zero closed cycles, these fields must be null but math intact
        if hb["closed_cycles_used"] == 0:
            assert d["expected_drift_pct"] is None
            assert d["worst_observed_drift_pct"] is None
            assert d["risk_adjusted_profit_avg_usd"] is None
            assert d["probability_profit_disappears"] is None

    def test_forecast_captured_zero(self, client):
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing/forecast",
                       params={"captured_price": 0,
                               "best_bid": 3.94e-5,
                               "investment_usd": 50})
        assert r.status_code == 400
        assert "must all be > 0" in r.json().get("detail", "")

    def test_forecast_bestbid_negative(self, client):
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing/forecast",
                       params={"captured_price": 3.6e-5,
                               "best_bid": -1,
                               "investment_usd": 50})
        assert r.status_code == 400

    def test_forecast_investment_zero(self, client):
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing/forecast",
                       params={"captured_price": 3.6e-5,
                               "best_bid": 3.94e-5,
                               "investment_usd": 0})
        assert r.status_code == 400


# ---------------- E2E: create REAL CLOSED cycle, verify aggregates ----------------

class TestE2EClosedCycle:
    cycle_id = None

    def test_create_and_close_cycle(self, client):
        r = client.post(f"{BASE_URL}/api/execution/arb-cycles",
                        json={"input_amount": 50, "quote_price": 3.6e-5,
                              "bdag_expected": 1388888, "best_bid": 3.9e-5,
                              "expected_roi_pct": 5})
        assert r.status_code in (200, 201), r.text[:300]
        cid = r.json()["id"]
        TestE2EClosedCycle.cycle_id = cid

        sequence = ["SWAP_SUBMITTED", "SWAP_CONFIRMED", "BDAG_RECEIVED",
                    "TRANSFER_SUBMITTED", "DEPOSIT_CONFIRMED"]
        for st in sequence:
            time.sleep(0.1)
            tr = client.post(f"{BASE_URL}/api/execution/arb-cycles/{cid}/transition",
                             json={"to_state": st})
            assert tr.status_code == 200, f"{st}: {tr.text[:200]}"

        # SOLD via observer coinstore-sell stamp
        time.sleep(0.1)
        sell = client.post(f"{BASE_URL}/api/execution/observer/coinstore-sell",
                           json={"cycle_id": cid, "order_id": f"TEST_{cid[:8]}",
                                 "bdag_sold": 1388888, "usdt_received": 54})
        assert sell.status_code == 200, sell.text[:300]

        for st in ["WITHDRAWN", "CLOSED"]:
            time.sleep(0.1)
            tr = client.post(f"{BASE_URL}/api/execution/arb-cycles/{cid}/transition",
                             json={"to_state": st})
            assert tr.status_code == 200, f"{st}: {tr.text[:200]}"

    def test_cycle_timing_picks_up_closed(self, client):
        assert TestE2EClosedCycle.cycle_id, "previous test created no cycle"
        r = client.get(f"{BASE_URL}/api/execution/cycle-timing")
        assert r.status_code == 200
        d = r.json()
        assert d["closed_cycles_used"] >= 1
        assert d["total_duration_s"].get("count", 0) >= 1
        # at least one stage has count >= 1
        assert any(s.get("count", 0) >= 1 for s in d["stage_durations_s"])
        # drift samples used either 0 or >=1 (depends on snapshot coverage)
        assert d["drift_distribution_pct"]["samples_used"] >= 0


# ---------------- Operator Console integration ----------------

class TestOperatorConsole:
    def test_risk_block_new_fields(self, client):
        r = client.get(f"{BASE_URL}/api/execution/operator-console",
                       params={"investment_usd": 50})
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        # find risk block
        risk = d.get("risk") or d.get("cycle_risk_engine") or {}
        # Search recursively if not at top level
        if not risk:
            for v in d.values():
                if isinstance(v, dict) and "probability_profit_disappears" in v:
                    risk = v
                    break
        for key in ("median_cycle_duration_s", "p95_cycle_duration_s",
                    "historical_worst_drift_pct", "historical_p5_worst_drift_pct",
                    "probability_profit_disappears", "stage_durations_s"):
            assert key in risk, f"risk missing {key}; risk keys={list(risk.keys())}"
        # closed_cycles_observed should match cycle-timing
        ct = client.get(f"{BASE_URL}/api/execution/cycle-timing").json()
        cco = risk.get("closed_cycles_observed")
        assert cco == ct["closed_cycles_used"], (cco, ct["closed_cycles_used"])

    def test_guardrails_false(self, client):
        for path in ["/api/execution/status", "/api/execution/operator-console",
                     "/api/execution/observer/status", "/api/execution/cycle-timing"]:
            r = client.get(f"{BASE_URL}{path}",
                           params={"investment_usd": 50} if "operator-console" in path else None)
            assert r.status_code == 200, f"{path} -> {r.status_code}"
            d = r.json()
            if path == "/api/execution/status":
                assert d.get("execution_enabled") is False
                assert d.get("wallet_enabled") is False
            else:
                g = d.get("guardrails")
                if g:
                    for k, v in g.items():
                        if isinstance(v, bool):
                            assert v is False, f"{path} guardrail {k}={v}"


# ---------------- Iter9 regression smoke ----------------

class TestIter9Regression:
    def test_observer_endpoints(self, client):
        for path in ["/api/execution/observer/rpc-health",
                     "/api/execution/observer/status"]:
            r = client.get(f"{BASE_URL}{path}")
            assert r.status_code == 200, f"{path} -> {r.status_code}"

    def test_observer_diagnostic_last(self, client):
        r = client.get(f"{BASE_URL}/api/execution/observer/diagnostic/last")
        assert r.status_code == 200
