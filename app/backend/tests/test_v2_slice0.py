"""ArbiCore UI v2 · Slice 0 backend endpoint smoke tests."""
import os
import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") if os.environ.get("REACT_APP_BACKEND_URL") else "https://unified-codebase-4.preview.emergentagent.com"


@pytest.fixture
def api():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Pulse ----------
def test_pulse(api):
    r = api.get(f"{BASE_URL}/api/arbicore/dashboard/pulse", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["regime", "opportunity_vitals", "route_learning", "scanner_status",
              "venue_readiness", "feed_freshness", "interlock", "deployable_capital",
              "anomalies", "generated_at"]:
        assert k in d, f"missing key: {k}"
    assert d["regime"]["regime"] == "CALM"
    assert isinstance(d["opportunity_vitals"]["total"], int)


# ---------- Deck ----------
def test_deck(api):
    r = api.get(f"{BASE_URL}/api/arbicore/dashboard/deck", timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["fresh_opportunities", "fresh_opportunities_total", "pending_approvals",
              "requires_attention", "generated_at"]:
        assert k in d
    assert isinstance(d["fresh_opportunities"], list)
    assert d["fresh_opportunities_total"] == len(d["fresh_opportunities"])
    for item in d["fresh_opportunities"]:
        for k in ["id", "opportunity_type", "subject_id", "chain",
                  "confidence", "status", "created_at"]:
            assert k in item, f"missing item key: {k}"


def test_deck_limit(api):
    r = api.get(f"{BASE_URL}/api/arbicore/dashboard/deck", params={"limit": 2}, timeout=15)
    assert r.status_code == 200
    assert len(r.json()["fresh_opportunities"]) == 2


# ---------- Opportunities summary ----------
def test_opportunities_summary(api):
    r = api.get(f"{BASE_URL}/api/arbicore/opportunities/summary",
                params={"window_hours": 24}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["total", "by_family", "by_chain", "by_status", "generated_at"]:
        assert k in d
    assert isinstance(d["by_family"], dict)


# ---------- ROI probability ----------
def test_roi_probability(api):
    r = api.get(f"{BASE_URL}/api/arbicore/roi-probability",
                params={"route_id": "cex:BTC-USDT"}, timeout=15)
    assert r.status_code == 200
    d = r.json()
    for k in ["route_id", "sample_size", "win_rate", "realized_outcome_mean",
              "realized_outcome_sum", "last_outcome_at", "generated_at"]:
        assert k in d
    assert d["route_id"] == "cex:BTC-USDT"


# ---------- System status ----------
def test_system_status(api):
    r = api.get(f"{BASE_URL}/api/system/status", timeout=15)
    assert r.status_code == 200
    d = r.json()
    assert d.get("features", {}).get("ui_v2") is True
