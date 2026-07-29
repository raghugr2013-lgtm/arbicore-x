"""Phase C Wave 1 — Wave-1 endpoints (admin-gated)."""
import os

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://bdag-readiness.preview.emergentagent.com",
).rstrip("/")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ArbiCore2026!"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"admin login unavailable ({r.status_code})")
    return s


def test_learning_status_shape(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/learning-status", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wave"] in ("C-1", "C-2", "C-3", "C-4", "C-5")  # wave advances as Phase C waves ship
    assert "outcome_tracker" in body
    for k in ("emissions_recorded", "rows_seeded", "rows_evaluated"):
        assert k in body["outcome_tracker"]
    assert body["outcome_evaluator"]["running"] is True
    assert body["outcome_evaluator"]["interval_s"] >= 5
    assert "audit_log_count" in body
    assert "route_stats_count" in body


def test_route_stats_endpoint(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/route-stats?limit=10", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_outcomes_endpoint_no_subject_returns_due_window(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/outcomes?limit=10", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    assert isinstance(body["items"], list)


def test_outcomes_endpoint_with_subject_filter(auth_session):
    r = auth_session.get(
        f"{BASE_URL}/api/arbicore/outcomes",
        params={"subject_id": "nonexistent-subject", "limit": 5},
        timeout=10,
    )
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_health_includes_wave1_fields(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/health", timeout=10)
    body = r.json()
    assert "learning_wave_1" in body
    assert "outcome_tracker_stats" in body["learning_wave_1"]
    assert body["wiring"]["outcome_tracker_alive"] is True
    assert body["wiring"]["route_tracker_alive"] is True
    assert body["wiring"]["outcome_evaluator"]["running"] is True
    # audit_log should now have at least one entry (initialisation)
    assert body["audit_log"]["size"] >= 1
