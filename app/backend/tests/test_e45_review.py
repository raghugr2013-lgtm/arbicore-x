"""Phase E4.5 — Certification Review package tests (READ-ONLY evidence layer).

Verifies the 10-section review composition, the strict readiness criteria +
evidence/threshold transparency, the 3-value recommendation, Markdown/JSON
downloads, the auto-snapshot on campaign completion, and the per-campaign
lookup. Reporting only — no trading, wallet, withdrawals, or fund movement.
"""
import os
from pathlib import Path

import pytest
import requests

_BASE = os.environ.get("REACT_APP_BACKEND_URL")
if not _BASE:
    envp = Path("/app/frontend/.env")
    if envp.exists():
        for line in envp.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                _BASE = line.split("=", 1)[1].strip()
                break
assert _BASE
BASE = _BASE.rstrip("/")

RECS = {"READY_FOR_MICROCAPITAL_REVIEW", "NEEDS_MORE_DATA", "NOT_READY"}
EXPECTED_TITLES = [
    "1. Final Verdict", "2. Recovery Statistics", "3. Stuck-Cycle Analysis",
    "4. Expected vs Realized PnL Analysis", "5. Venue Comparison (Coinstore vs BitMart)",
    "6. Route Comparison", "7. Recommended Safe Cycle Size",
    "8. Key Failure Modes Discovered", "9. Micro-Capital Readiness Assessment",
    "10. Final Recommendation",
]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore#2026"}, timeout=15)
    assert r.status_code == 200, r.text
    return s


def _shadow_campaigns_col():
    from dotenv import load_dotenv
    from pymongo import MongoClient
    load_dotenv("/app/backend/.env")
    mc = MongoClient(os.environ["MONGO_URL"])
    return mc, mc[os.environ["DB_NAME"]]["shadow_campaigns"]


def _campaign_ids():
    mc, col = _shadow_campaigns_col()
    try:
        return {d["id"] for d in col.find({}, {"id": 1})}
    finally:
        mc.close()


@pytest.fixture(scope="module", autouse=True)
def _purge_temp_campaigns(client):
    """After this module finishes, delete any NEW zero-cycle / dummy campaigns it
    spawned (the auto-snapshot test starts→stops a campaign) so the suite never
    pollutes the authoritative shadow_campaigns collection. Real completed
    certification campaigns (completed_count > 0) are always preserved."""
    baseline = _campaign_ids()
    yield
    try:
        client.post(f"{BASE}/api/execution/campaign/stop", json={}, timeout=15)
        client.patch(f"{BASE}/api/execution/config", json={"shadow_enabled": False}, timeout=15)
    except Exception:
        pass
    mc, col = _shadow_campaigns_col()
    try:
        col.delete_many({
            "id": {"$nin": list(baseline)},
            "$or": [{"completed_count": {"$lte": 0}},
                    {"completed_count": {"$exists": False}},
                    {"completed_count": None}],
        })
    finally:
        mc.close()


def _assert_package(pkg):
    assert pkg["available"] is True
    assert pkg["recommendation"] in RECS
    titles = [s["title"] for s in pkg["sections"]]
    assert titles == EXPECTED_TITLES, titles
    # readiness criteria thresholds are exposed (transparency)
    rc = pkg["readiness_criteria"]
    for k in ("min_completed_cycles", "min_recovery_success_rate_pct",
              "max_stuck_rate_pct", "max_variance_pct", "min_profitable_rate_pct"):
        assert k in rc, k
    # section 9 — every criterion carries actual + threshold + status (evidence)
    sec9 = next(s for s in pkg["sections"] if s["title"].startswith("9."))
    assert len(sec9["criteria"]) >= 5
    for c in sec9["criteria"]:
        assert c["status"] in {"PASS", "FAIL", "N/A"}
        assert "actual" in c and "threshold" in c and "severity" in c
    # section 10 — recommendation echoes top-level + has next steps
    sec10 = next(s for s in pkg["sections"] if s["title"].startswith("10."))
    assert sec10["recommendation"] == pkg["recommendation"]
    assert isinstance(sec10["next_steps"], list) and sec10["next_steps"]
    # recommended size never exceeds certification cap
    sec7 = next(s for s in pkg["sections"] if s["title"].startswith("7."))
    assert sec7["recommended_usd"] <= sec7["max_cycle_cap_usd"]
    # guard-rail / non-execution note present
    assert "fund movement" in pkg["note"].lower()


class TestReviewEndpoint:
    def test_review_shape(self, client):
        r = client.get(f"{BASE}/api/execution/certification/review", timeout=25)
        assert r.status_code == 200, r.text
        pkg = r.json()
        if pkg.get("available"):
            _assert_package(pkg)
        else:
            assert pkg["recommendation"] is None
            assert "message" in pkg

    def test_review_anon_blocked(self):
        r = requests.get(f"{BASE}/api/execution/certification/review", timeout=10)
        assert r.status_code == 401

    def test_review_for_unknown_campaign_404(self, client):
        r = client.get(f"{BASE}/api/execution/certification/review",
                       params={"campaign_id": "does-not-exist"}, timeout=20)
        assert r.status_code == 404


class TestReviewDownloads:
    def test_markdown_download(self, client):
        r = client.get(f"{BASE}/api/execution/certification/review/download",
                       params={"format": "md"}, timeout=25)
        assert r.status_code == 200
        assert "text/markdown" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        assert "# Shadow Certification Review" in r.text

    def test_json_download(self, client):
        r = client.get(f"{BASE}/api/execution/certification/review/download",
                       params={"format": "json"}, timeout=25)
        assert r.status_code == 200
        assert "application/json" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        body = r.json()
        assert "recommendation" in body or body.get("available") is False


class TestAutoSnapshot:
    def test_completed_campaign_snapshots_review(self, client):
        # clean slate
        client.post(f"{BASE}/api/execution/campaign/stop", json={}, timeout=15)
        client.patch(f"{BASE}/api/execution/config", json={"shadow_enabled": False}, timeout=15)

        start = client.post(f"{BASE}/api/execution/campaign/start",
                            json={"target_completed": 20}, timeout=20)
        assert start.status_code == 200, start.text
        cid = start.json()["id"]

        stop = client.post(f"{BASE}/api/execution/campaign/stop", json={}, timeout=25)
        assert stop.status_code == 200, stop.text
        ended = stop.json()
        # auto-snapshot frozen into the campaign record
        review = ended.get("certification_review")
        assert review is not None, "campaign did not snapshot a certification_review"
        assert review["recommendation"] in RECS
        assert [s["title"] for s in review["sections"]] == EXPECTED_TITLES

        # per-campaign lookup returns the stored snapshot
        r = client.get(f"{BASE}/api/execution/certification/review",
                       params={"campaign_id": cid}, timeout=25)
        assert r.status_code == 200
        assert r.json()["campaign"]["id"] == cid

        # shadow released (non-execution invariant)
        cfg = client.get(f"{BASE}/api/execution/config", timeout=15).json()
        assert cfg["shadow_enabled"] is False
        assert cfg["execution_enabled"] is False
        assert cfg["wallet_enabled"] is False
