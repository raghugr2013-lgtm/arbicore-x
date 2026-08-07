"""Backend tests for UI v2 Slice 1: universal opportunity feed + detail + approve/reject."""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://flashloan-readiness.preview.emergentagent.com').rstrip('/')
OPPS = f"{BASE_URL}/api/arbicore/opportunities"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


class TestOpportunitiesList:
    def test_list_returns_200_shape(self, s):
        r = s.get(OPPS, timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d and "generated_at" in d
        assert isinstance(d["items"], list) and len(d["items"]) >= 1
        item = d["items"][0]
        for k in ["id", "opportunity_type", "subject_id", "chain", "confidence",
                  "safety", "status", "verdict", "created_at"]:
            assert k in item, f"missing key {k}"

    def test_filter_family_cex(self, s):
        r = s.get(OPPS, params={"family": "CEX_ARBITRAGE"}, timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        assert all(it["opportunity_type"] == "CEX_ARBITRAGE" for it in items)

    def test_filter_verdict_go(self, s):
        r = s.get(OPPS, params={"verdict": "GO"}, timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) > 0
        assert all(it["verdict"] == "GO" for it in items)

    def test_filter_min_confidence(self, s):
        r = s.get(OPPS, params={"min_confidence": 0.7}, timeout=15)
        assert r.status_code == 200
        items = r.json()["items"]
        assert all(it["confidence"] >= 0.7 for it in items)


class TestOpportunityDetail:
    def test_detail_opp001(self, s):
        r = s.get(f"{OPPS}/opp-001", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ["id", "subject_id", "chain", "verdict", "confidence", "safety",
                  "route", "spread_bps", "depth_usd", "return_low", "return_high",
                  "age_s", "reasoning", "verification", "quote", "sizing", "evidence"]:
            assert k in d, f"missing key {k}"
        for rk in ["confidence_breakdown", "gates_passed", "gates_dropped"]:
            assert rk in d["reasoning"], f"reasoning missing {rk}"


class TestApproveReject:
    def test_approve(self, s):
        r = s.post(f"{OPPS}/opp-001/approve", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and d["id"] == "opp-001" and d["status"] == "APPROVED"

    def test_reject(self, s):
        r = s.post(f"{OPPS}/opp-002/reject", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and d["id"] == "opp-002" and d["status"] == "REJECTED"
