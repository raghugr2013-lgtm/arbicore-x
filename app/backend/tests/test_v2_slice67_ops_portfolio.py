"""Slice 6 (Portfolio) + Slice 7 (Operations) canonicalization tests.

Runs against the external ingress URL from REACT_APP_BACKEND_URL. Uses
session-cookie auth via POST /api/auth/login (admin/hotfix-v293).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://base-v3-live.preview.emergentagent.com",
).rstrip("/")

ADMIN_USER = "admin"
ADMIN_PASS = "hotfix-v293"

OPERATIONS_ENDPOINTS_GET = [
    "/api/arbicore/operations/scanners",
    "/api/arbicore/operations/cycles",
    "/api/arbicore/operations/venues",
    "/api/arbicore/operations/interlock",
    "/api/arbicore/operations/integrations",
    "/api/arbicore/operations/queues",
    "/api/arbicore/operations/alerts",
]
PORTFOLIO_ENDPOINTS_GET = [
    "/api/arbicore/portfolio/positions",
    "/api/arbicore/portfolio/balances",
    "/api/arbicore/portfolio/transfers",
    "/api/arbicore/portfolio/deployable",
    "/api/arbicore/portfolio/treasury",
    "/api/arbicore/portfolio/ledger",
    "/api/arbicore/portfolio/exposure",
    "/api/arbicore/portfolio/allocation",
]

EXPECTED_FAMILIES = {
    "CEX_ARBITRAGE", "FUNDING_ARBITRAGE", "DEX_ARBITRAGE",
    "LAUNCH_ARBITRAGE", "CROSS_CHAIN_ARBITRAGE", "FLASH_LOAN_ARBITRAGE",
}
FORBIDDEN_FAMILIES = {"SPATIAL_ARBITRAGE", "STATISTICAL_ARBITRAGE"}


@pytest.fixture(scope="module")
def anon():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USER, "password": ADMIN_PASS},
        timeout=15,
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ---------- Slice 7 auth-gate matrix ----------
@pytest.mark.parametrize("path", OPERATIONS_ENDPOINTS_GET)
def test_operations_get_anon_401(anon, path):
    r = anon.get(f"{BASE_URL}{path}", timeout=10)
    assert r.status_code == 401, f"{path} → {r.status_code} {r.text[:200]}"
    assert r.json().get("detail") == "not_authenticated"


def test_operations_scanner_action_anon_401(anon):
    r = anon.post(
        f"{BASE_URL}/api/arbicore/operations/scanners/CEX_ARBITRAGE/action"
        "?action=start",
        timeout=10,
    )
    assert r.status_code == 401
    assert r.json().get("detail") == "not_authenticated"


def test_operations_interlock_action_anon_401(anon):
    r = anon.post(
        f"{BASE_URL}/api/arbicore/operations/interlock/action?action=arm",
        timeout=10,
    )
    assert r.status_code == 401


def test_operations_alert_ack_anon_401(anon):
    r = anon.post(
        f"{BASE_URL}/api/arbicore/operations/alerts/foo/ack", timeout=10,
    )
    assert r.status_code == 401


# ---------- Slice 6 auth-gate matrix ----------
@pytest.mark.parametrize("path", PORTFOLIO_ENDPOINTS_GET)
def test_portfolio_get_anon_401(anon, path):
    r = anon.get(f"{BASE_URL}{path}", timeout=10)
    assert r.status_code == 401, f"{path} → {r.status_code} {r.text[:200]}"
    assert r.json().get("detail") == "not_authenticated"


# ---------- Slice 7 · /operations/scanners ----------
def test_scanners_shape_and_families(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/operations/scanners", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "generated_at" in body
    assert isinstance(body["items"], list)
    assert len(body["items"]) == 6
    families = {it["family"] for it in body["items"]}
    assert families == EXPECTED_FAMILIES
    assert not (families & FORBIDDEN_FAMILIES)
    for it in body["items"]:
        assert set(["family", "state", "cadence_s", "last_run",
                    "opps_1h", "gates_dropped_1h", "errors_1h"]).issubset(it)
        assert it["state"] in ("RUNNING", "IDLE")
        assert isinstance(it["cadence_s"], int)
        assert it["last_run"] is None
        assert it["opps_1h"] == 0
        assert it["gates_dropped_1h"] == 0
        assert it["errors_1h"] == 0


# ---------- Slice 7 · /operations/scanners/{family}/action ----------
def test_scanner_action_start_pause_stop_persist(auth):
    base = f"{BASE_URL}/api/arbicore/operations/scanners"

    r = auth.post(f"{base}/CEX_ARBITRAGE/action?action=start", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["family"] == "CEX_ARBITRAGE"
    assert body["state"] == "RUNNING"

    # persistence via GET
    lst = auth.get(f"{base}", timeout=15).json()["items"]
    cex = next(it for it in lst if it["family"] == "CEX_ARBITRAGE")
    assert cex["state"] == "RUNNING"

    r = auth.post(f"{base}/CEX_ARBITRAGE/action?action=pause", timeout=15)
    assert r.status_code == 200
    assert r.json()["state"] == "IDLE"

    lst = auth.get(f"{base}", timeout=15).json()["items"]
    cex = next(it for it in lst if it["family"] == "CEX_ARBITRAGE")
    assert cex["state"] == "IDLE"

    r = auth.post(f"{base}/CEX_ARBITRAGE/action?action=start", timeout=15)
    assert r.json()["state"] == "RUNNING"
    r = auth.post(f"{base}/CEX_ARBITRAGE/action?action=stop", timeout=15)
    assert r.json()["state"] == "IDLE"

    lst = auth.get(f"{base}", timeout=15).json()["items"]
    cex = next(it for it in lst if it["family"] == "CEX_ARBITRAGE")
    assert cex["state"] == "IDLE"


def test_scanner_action_unknown_family(auth):
    r = auth.post(
        f"{BASE_URL}/api/arbicore/operations/scanners/FOO/action?action=start",
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["state"] is None


def test_scanner_action_unknown_action(auth):
    r = auth.post(
        f"{BASE_URL}/api/arbicore/operations/scanners/CEX_ARBITRAGE/action"
        "?action=wobble",
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["state"] is None


# ---------- Slice 7 · empty shapes ----------
def test_venues_shape(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/operations/venues", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"items", "generated_at"}
    assert isinstance(body["items"], list)
    for it in body["items"]:
        for k in ("venue", "kind", "state", "role", "latency_ms", "last_seen"):
            assert k in it


def test_queues_shape_discovery_only(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/operations/queues", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body and "generated_at" in body
    queues = [it["queue"] for it in body["items"]]
    # discovery is the only expected queue today; allow list to be empty on
    # composition failure but if present must be discovery only
    assert set(queues).issubset({"discovery"})
    for it in body["items"]:
        assert set(["queue", "pending", "in_flight",
                    "failed_1h", "rate_per_min"]).issubset(it)
        assert it["failed_1h"] == 0
        assert it["rate_per_min"] == 0
        assert isinstance(it["pending"], int)
        assert isinstance(it["in_flight"], int)


def test_cycles_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/operations/cycles", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert "generated_at" in body


def test_alerts_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/operations/alerts", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_integrations_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/operations/integrations", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert "generated_at" in body


def test_interlock_disarmed_default(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/operations/interlock", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["armed"] is False
    assert body["state"] == "DISARMED"
    assert body["reason"] is None
    assert body["gates"] == []
    assert body["last_transition_at"] is None


def test_interlock_action_arm_disarm(auth):
    r = auth.post(
        f"{BASE_URL}/api/arbicore/operations/interlock/action?action=arm",
        timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["state"] == "ARMED"

    r = auth.post(
        f"{BASE_URL}/api/arbicore/operations/interlock/action?action=disarm",
        timeout=10,
    )
    assert r.json()["state"] == "DISARMED"

    r = auth.post(
        f"{BASE_URL}/api/arbicore/operations/interlock/action?action=wobble",
        timeout=10,
    )
    assert r.json()["state"] == "DISARMED"


def test_alert_ack(auth):
    r = auth.post(
        f"{BASE_URL}/api/arbicore/operations/alerts/alr-test/ack", timeout=10,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["id"] == "alr-test"
    assert body["acked"] is True
    assert "generated_at" in body


# ---------- Slice 6 · Portfolio empty shapes ----------
def test_positions_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/positions", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "items": [], "total": 0, "total_size_usd": 0.0,
        "total_upnl_usd": 0.0, "generated_at": body["generated_at"],
    }


def test_balances_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/balances", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0
    assert body["total_usd"] == 0.0


def test_transfers_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/transfers", timeout=15)
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_deployable_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/deployable", timeout=15)
    body = r.json()
    assert body["total_deployable_usd"] == 0.0
    assert body["total_utilised_usd"] == 0.0
    assert body["total_capital_usd"] == 0.0
    assert body["utilisation_pct"] == 0.0
    assert body["per_venue"] == []


def test_treasury_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/treasury", timeout=15)
    body = r.json()
    assert body["vaults"] == []
    assert body["total_usd"] == 0.0


def test_ledger_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/ledger", timeout=15)
    body = r.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_exposure_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/exposure", timeout=15)
    body = r.json()
    assert body["by_asset"] == []
    assert body["by_chain"] == []
    assert body["total_usd"] == 0.0


def test_allocation_empty(auth):
    r = auth.get(f"{BASE_URL}/api/arbicore/portfolio/allocation", timeout=15)
    body = r.json()
    assert body["items"] == []
    assert body["total_target_usd"] == 0.0
    assert body["total_actual_usd"] == 0.0


# ---------- Regression sanity: Slice 1-5 endpoints still auth-gated + 200 ----------
REG_ENDPOINTS = [
    "/api/arbicore/opportunities",
    "/api/arbicore/opportunities/summary",
    "/api/arbicore/discovery/candidates",
    "/api/arbicore/intelligence/recommendations",
    "/api/arbicore/intelligence/decisions",
    "/api/arbicore/intelligence/calibration",
    "/api/arbicore/intelligence/models",
    "/api/arbicore/intelligence/certification",
    "/api/arbicore/intelligence/entities",
    "/api/arbicore/dashboard/pulse",
    "/api/arbicore/dashboard/deck",
]


@pytest.mark.parametrize("path", REG_ENDPOINTS)
def test_regression_anon_401(anon, path):
    r = anon.get(f"{BASE_URL}{path}", timeout=10)
    assert r.status_code == 401, f"{path} → {r.status_code}"


@pytest.mark.parametrize("path", REG_ENDPOINTS)
def test_regression_auth_200(auth, path):
    r = auth.get(f"{BASE_URL}{path}", timeout=15)
    assert r.status_code == 200, f"{path} → {r.status_code} {r.text[:200]}"
