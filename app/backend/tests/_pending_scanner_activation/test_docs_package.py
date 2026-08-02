"""Backend tests for ArbiCore Architecture Review docs-package endpoints.
Updated Sprint 4: endpoints require auth; package has grown to 20 documents."""
import os

import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api"

CORE_IDS = [
    "executive-summary", "feasibility-audit", "system-architecture", "module-breakdown",
    "connector-framework", "event-flows", "technology-stack", "database-schema",
    "api-integration-plan", "security-model", "risk-assessment", "mvp-roadmap",
    "sprint1-plan", "future-expansion",
]
SPRINT_IDS = ["coinstore-audit", "blockdag-data-audit", "auth-security",
              "route-feasibility", "discovery-confidence", "exchange-audit-bdag"]

EXPECTED_SECTIONS = {"Overview", "Architecture", "Data Layer", "Integration",
                     "Risk & Security", "Delivery Plan"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", timeout=30,
               json={"username": "admin", "password": "ArbiCore#2026"})
    assert r.status_code == 200, f"auth failed: {r.text}"
    return s


@pytest.fixture(scope="module")
def package(session):
    r = session.get(f"{API}/docs-package", timeout=15)
    assert r.status_code == 200, f"docs-package failed: {r.status_code} {r.text[:200]}"
    return r.json()


def test_docs_require_auth():
    assert requests.get(f"{API}/docs-package", timeout=15).status_code == 401


def test_package_metadata(package):
    assert package["version"]
    assert "SPRINT" in package["status"].upper()
    assert package["package"]


def test_package_has_all_documents(package):
    docs = package["documents"]
    ids = {d["id"] for d in docs}
    assert set(CORE_IDS) <= ids, f"missing core docs: {set(CORE_IDS) - ids}"
    assert set(SPRINT_IDS) <= ids, f"missing sprint docs: {set(SPRINT_IDS) - ids}"
    assert len(docs) >= 20, f"Expected >=20 docs got {len(docs)}"
    # audit & execution-architecture docs added in the execution branch
    assert {"automation-readiness-audit", "purchase-portal-audit",
            "purchase-automation-feasibility", "execution-architecture"} <= ids


def test_package_document_shape(package):
    for d in package["documents"]:
        assert set(d.keys()) >= {"id", "title", "section", "order"}
        assert d["section"] in EXPECTED_SECTIONS
        assert isinstance(d["order"], (int, float))


def test_package_documents_sorted_by_order(package):
    orders = [d["order"] for d in package["documents"]]
    assert orders == sorted(orders)


@pytest.mark.parametrize("doc_id", CORE_IDS + SPRINT_IDS)
def test_get_each_doc(session, doc_id):
    r = session.get(f"{API}/docs-package/{doc_id}", timeout=15)
    assert r.status_code == 200, f"{doc_id} -> {r.status_code}"
    body = r.json()
    assert body["id"] == doc_id
    assert len(body["content"]) > 200


def test_unknown_doc_returns_404(session):
    r = session.get(f"{API}/docs-package/not-a-doc", timeout=15)
    assert r.status_code == 404
