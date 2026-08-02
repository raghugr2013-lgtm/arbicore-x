"""Tests for BlockDAG Buy-Price Source Audit (iter3)."""
import math
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    # fallback to reading frontend/.env
    try:
        with open("/app/frontend/.env") as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
                    break
    except Exception:
        pass

ADMIN_USER = "admin"
ADMIN_PASS = "ArbiCore2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USER, "password": ADMIN_PASS}, timeout=15)
    assert r.status_code == 200, f"Auth failed: {r.status_code} {r.text}"
    return s


# ---- Auth ------------
def test_auth_login(session):
    r = session.get(f"{BASE_URL}/api/execution/status", timeout=15)
    assert r.status_code == 200


# ---- GET audit basic structure ----
def test_audit_structure(session):
    t0 = time.time()
    r = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20)
    elapsed = time.time() - t0
    assert r.status_code == 200, r.text
    assert elapsed < 15, f"perf: {elapsed:.1f}s > 15s"
    d = r.json()
    assert d["phase"] == "BlockDAG Buy-Price Source Audit (read-only)"
    primary = d["primary_sources"]
    assert isinstance(primary, list) and len(primary) == 5
    expected_labels = [
        "Live Swap UI",
        "sw-api/getInfo",
        "Portal Feed",
        "Position Cost Basis",
        "Effective Executable Price",
    ]
    for i, lbl in enumerate(expected_labels):
        assert lbl in primary[i]["label"], f"slot {i+1}: {primary[i]['label']}"


def test_audit_sw_api_and_portal(session):
    d = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20).json()
    primary = d["primary_sources"]
    slot2, slot3 = primary[1], primary[2]
    # sw-api value
    assert slot2["value"] is not None and slot2["value"] > 0
    assert 1e-5 < slot2["value"] < 1e-4, f"slot2 value {slot2['value']} not ~4e-5"
    # portal == sw-api
    assert slot3["value"] is not None
    assert math.isclose(slot2["value"], slot3["value"], rel_tol=1e-6), \
        f"slot2={slot2['value']} slot3={slot3['value']}"
    # used_for_roi flags
    assert slot2["used_for_roi"] is True
    assert slot3["used_for_roi"] is True
    assert primary[0]["used_for_roi"] is False
    assert primary[3]["used_for_roi"] is False


def test_audit_price_used_for_roi(session):
    d = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20).json()
    primary = d["primary_sources"]
    pu = d["price_used_for_roi"]
    assert pu["value"] is not None
    assert math.isclose(pu["value"], primary[1]["value"], rel_tol=1e-6)
    assert "Live Portal Feed" in pu["source"], pu["source"]
    expl = pu["explanation"]
    assert "Live Portal Feed" in expl
    assert "manual_override" in expl and "portal" in expl and "manual_fallback" in expl
    assert "no manual override is set" in expl


def test_audit_secondary_sources(session):
    d = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20).json()
    sec = d["secondary_sources"]
    assert len(sec) == 2
    labels = " | ".join(s["label"] for s in sec)
    assert "current_price" in labels
    assert "tokenPrice" in labels or "preapi" in labels
    # presale extras
    presale = next((s for s in sec if "tokenPrice" in s["label"] or "preapi" in s["label"]), None)
    assert presale is not None
    if presale.get("ok"):
        extras = presale.get("extras") or {}
        assert "stage" in extras
        assert "next_stage_price" in extras


def test_audit_discrepancies(session):
    d = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20).json()
    disc = d["discrepancies"]
    assert isinstance(disc, list) and len(disc) > 0
    for x in disc:
        assert {"vs", "source", "source_value", "ref_value", "delta_pct", "severity"} <= set(x.keys())
        assert x["severity"] in ("critical", "informational")
    crit = [x for x in disc if x["severity"] == "critical"]
    assert len(crit) >= 2, f"expected >=2 critical, got {len(crit)}: {disc}"


# ---- POST empirical ----
def test_post_empirical_invalid(session):
    r = session.post(f"{BASE_URL}/api/execution/buy-price-audit/empirical",
                     json={"investment_usd": 0, "bdag_received": 1}, timeout=15)
    assert r.status_code == 400
    assert "> 0" in r.text


def test_post_empirical_valid_and_reflects(session):
    r = session.post(f"{BASE_URL}/api/execution/buy-price-audit/empirical",
                     json={"investment_usd": 50, "bdag_received": 1388889,
                           "reported_ui_price": 0.000036, "note": "qa test"}, timeout=15)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    assert body.get("id")
    assert math.isclose(body["effective_price"], 50 / 1388889, rel_tol=1e-3)

    # GET should now reflect
    d = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20).json()
    primary = d["primary_sources"]
    assert math.isclose(primary[0]["value"], 0.000036, rel_tol=1e-3), primary[0]
    assert math.isclose(primary[4]["value"], 50 / 1388889, rel_tol=1e-3), primary[4]
    ds = d["discrepancy_summary"]
    assert ds["ui_vs_sw_api_pct"] is not None
    assert ds["ui_vs_sw_api_pct"] < 0
    assert -15 < ds["ui_vs_sw_api_pct"] < -5
    assert ds["ui_vs_sw_api_severity"] == "critical"


def test_get_empirical_history(session):
    r = session.get(f"{BASE_URL}/api/execution/buy-price-audit/empirical", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "quotes" in body
    assert isinstance(body["quotes"], list)
    assert len(body["quotes"]) >= 1


# ---- Guardrails ----
def test_guardrails_execution_disabled(session):
    r = session.get(f"{BASE_URL}/api/execution/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d["execution_enabled"] is False


def test_guardrails_intel_buy_price_unchanged(session):
    # Find a BDAG route id from the audit
    d = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20).json()
    route_id = d.get("route_id")
    portal_price = d["primary_sources"][2]["value"]
    if not route_id:
        pytest.skip("no BDAG route")
    intel = session.get(f"{BASE_URL}/api/execution/intel/{route_id}", timeout=15).json()
    bp = intel.get("buy_price")
    assert bp is not None
    assert math.isclose(bp, portal_price, rel_tol=1e-6), f"intel.buy_price={bp} vs portal={portal_price}"


def test_guardrails_cycle_model_buy_price(session):
    d = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=20).json()
    portal_price = d["primary_sources"][2]["value"]
    cm = session.get(f"{BASE_URL}/api/execution/cycle-model", timeout=15).json()
    eo = cm.get("executable_opportunity_calculation") or {}
    bp_used = eo.get("buy_price_used")
    if bp_used is None:
        pytest.skip("cycle-model does not expose buy_price_used")
    assert math.isclose(bp_used, portal_price, rel_tol=1e-6), \
        f"cycle_model.buy_price_used={bp_used} vs portal={portal_price}"
