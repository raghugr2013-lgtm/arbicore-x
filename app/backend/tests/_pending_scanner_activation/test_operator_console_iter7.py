"""Iter7 — Operator Console endpoint + hard-guardrail regression tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://flashloan-readiness.preview.emergentagent.com").rstrip("/")
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


# ---------- operator-console ----------
class TestOperatorConsole:
    def test_default_shape(self, client):
        r = client.get(f"{BASE_URL}/api/execution/operator-console")
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        for k in ("phase", "generated_at", "monitor", "risk", "verdict",
                  "quote_verification", "actions", "guardrails", "links"):
            assert k in d, f"missing top-level key: {k}"
        assert d["monitor"]["investment_usd"] == 50.0

    def test_investment_100(self, client):
        r = client.get(f"{BASE_URL}/api/execution/operator-console",
                       params={"investment_usd": 100})
        assert r.status_code == 200
        d = r.json()
        assert d["monitor"]["investment_usd"] == 100.0

    def test_investment_zero_400(self, client):
        r = client.get(f"{BASE_URL}/api/execution/operator-console",
                       params={"investment_usd": 0})
        assert r.status_code == 400
        assert "must be > 0" in (r.json().get("detail") or "")

    def test_monitor_block_keys(self, client):
        d = client.get(f"{BASE_URL}/api/execution/operator-console").json()
        m = d["monitor"]
        for k in ("captured_bdag_price", "coinstore_best_bid",
                  "gross_spread_pct", "net_spread_pct", "net_profit_usd",
                  "coinstore_orderbook_depth_quote",
                  "coinstore_orderbook_depth_base",
                  "coinstore_total_levels", "venue"):
            assert k in m, f"monitor missing {k}"

    def test_risk_block(self, client):
        d = client.get(f"{BASE_URL}/api/execution/operator-console").json()
        r = d["risk"]
        for k in ("closed_cycles_observed", "avg_cycle_duration_s",
                  "worst_cycle_duration_s", "buyer_stability_label",
                  "drift_estimate_pct_over_cycle", "risk_level"):
            assert k in r, f"risk missing {k}"
        assert r["risk_level"] in ("LOW", "MEDIUM", "HIGH")

    def test_verdict_block(self, client):
        d = client.get(f"{BASE_URL}/api/execution/operator-console").json()
        v = d["verdict"]
        assert v["verdict"] in ("NOT_TRADEABLE", "TRADEABLE", "HIGH_CONFIDENCE")
        assert isinstance(v["reasons"], list) and len(v["reasons"]) >= 1

    def test_quote_verification(self, client):
        d = client.get(f"{BASE_URL}/api/execution/operator-console").json()
        qv = d["quote_verification"]
        for k in ("available", "fresh", "age_s", "fresh_window_s",
                  "source", "effective_price", "note"):
            assert k in qv, f"quote_verification missing {k}"

    def test_actions_shape_and_execute_gated(self, client):
        d = client.get(f"{BASE_URL}/api/execution/operator-console").json()
        a = d["actions"]
        for key in ("open_swap_page", "verify_quote",
                    "execute_trade", "open_coinstore"):
            assert key in a, f"actions missing {key}"
            for f in ("label", "enabled", "url", "note"):
                assert f in a[key], f"action {key} missing field {f}"
        # execute_trade gated by HIGH_CONFIDENCE + fresh quote
        if (d["verdict"]["verdict"] != "HIGH_CONFIDENCE"
                or not d["quote_verification"]["fresh"]):
            assert a["execute_trade"]["enabled"] is False

    def test_guardrails(self, client):
        d = client.get(f"{BASE_URL}/api/execution/operator-console").json()
        g = d["guardrails"]
        for k in ("execution_enabled", "wallet_enabled", "transaction_signing",
                  "autonomous_execution", "fund_movement"):
            assert g[k] is False, f"guardrail {k} must be False"


# ---------- Hard-guardrail regression ----------
class TestGuardrailRegression:
    def test_intel_buy_price_unchanged(self, client):
        # find BDAG route id
        # Use opportunity/gate endpoint which resolves a default BDAG route
        gate = client.get(f"{BASE_URL}/api/execution/opportunity/gate").json()
        route_id = gate.get("route_id") or gate.get("route", {}).get("id")
        if not route_id:
            # fallback: scan routes
            r = client.get(f"{BASE_URL}/api/routes")
            if r.status_code == 200:
                for rt in r.json().get("routes", []):
                    if (rt.get("purchase") or {}).get("asset") == "BDAG":
                        route_id = rt["id"]; break
        assert route_id, "no BDAG route id discovered"
        intel = client.get(f"{BASE_URL}/api/execution/intel/{route_id}").json()
        bp = intel.get("buy_price")
        assert bp is not None
        # Captured price is ~3.6e-5; portal feed should be > 3.7e-5
        assert bp > 3.7e-5, f"buy_price={bp} appears to be captured value (should be portal feed)"

    def test_execution_status_disabled(self, client):
        d = client.get(f"{BASE_URL}/api/execution/status").json()
        assert d["execution_enabled"] is False
        assert d["wallet_enabled"] is False
