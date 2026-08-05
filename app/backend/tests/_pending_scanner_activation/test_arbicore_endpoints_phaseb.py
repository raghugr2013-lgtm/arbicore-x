"""Phase B — arbicore HTTP endpoints (admin-gated).

Verifies:
  - /api/arbicore/health
  - /api/arbicore/opportunities (list)
  - /api/arbicore/opportunities/{id} (single)
  - /api/arbicore/provenance (registry dump)
  - No write endpoints exposed
  - Auth gate enforced
"""
import os
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://arbix-router-repair.preview.emergentagent.com",
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


def test_health_requires_auth():
    r = requests.get(f"{BASE_URL}/api/arbicore/health", timeout=10)
    assert r.status_code in (401, 403)


def test_health_returns_phase_and_provenance(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/health", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["phase"] == "B"
    assert "provenance" in body
    assert body["provenance"]["coverage_pct"] == 100.0
    assert body["provenance"]["counts"]["REAL"] >= 11
    assert body["provenance"]["counts"]["SIMULATED"] >= 4
    assert body["provenance"]["counts"]["VERIFIED_REAL"] == 0
    assert "wiring" in body
    assert body["wiring"]["opportunity_repo_alive"] is True
    assert body["wiring"]["outcome_repo_alive"] is True
    assert body["wiring"]["metrics_repo_alive"] is True
    assert body["wiring"]["regime_snapshot_repo_alive"] is True
    assert body["wiring"]["state_observer_registry_alive"] is True
    assert "category_metadata" in body
    assert "unknown_key_warnings" in body["category_metadata"]


def test_provenance_dump(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/provenance", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "registry" in body
    assert body["total_sources"] >= 15
    assert set(body["by_provenance"].keys()) == {
        "VERIFIED_REAL", "REAL", "SIMULATED", "CONTAMINATED", "DEAD"
    }


def test_opportunities_list_filters(auth_session):
    # Seed via the live HTTP write path? No write endpoints in Phase B.
    # The opportunity created by the mongo-adapter test (run earlier in
    # the suite, same session) and by the proposer worker are sufficient
    # to verify list filters. We additionally check that filtering returns
    # only CEX_ARBITRAGE items.
    r = auth_session.get(
        f"{BASE_URL}/api/arbicore/opportunities",
        params={"type": "CEX_ARBITRAGE", "limit": 50},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for item in body["items"]:
        assert item["opportunity_type"] == "CEX_ARBITRAGE"


def test_opportunities_list_unknown_filter_rejected(auth_session):
    r = auth_session.get(
        f"{BASE_URL}/api/arbicore/opportunities",
        params={"type": "BOGUS"},
        timeout=10,
    )
    assert r.status_code == 400


def test_opportunity_404(auth_session):
    r = auth_session.get(
        f"{BASE_URL}/api/arbicore/opportunities/nonexistent-deadbeef",
        timeout=10,
    )
    assert r.status_code == 404


def test_no_write_endpoints_exposed(auth_session):
    """Verify that POST/PUT/DELETE under /api/arbicore returns 4xx
    (FastAPI returns 405 Method Not Allowed when the route doesn't exist)."""
    for verb in ("post", "put", "delete"):
        r = getattr(auth_session, verb)(
            f"{BASE_URL}/api/arbicore/opportunities", timeout=10,
        )
        assert r.status_code in (404, 405)


def test_health_includes_arbicore_namespaced_collections_only(auth_session):
    """Sanity — the health endpoint exposes wiring; nothing in the response
    references legacy collections like arbitrage_cycles or venue_health."""
    r = auth_session.get(f"{BASE_URL}/api/arbicore/health", timeout=10)
    body_text = r.text.lower()
    for legacy in ("arbitrage_cycles", "venue_health", "venue_prices",
                   "proposed_cycles_current", "drift_analysis_cache"):
        assert legacy not in body_text, f"legacy collection {legacy} leaked"
