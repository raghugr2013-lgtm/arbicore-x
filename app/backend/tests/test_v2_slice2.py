"""UI v2 Slice 2 — Discovery + Intelligence backend tests."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://arbicore-canonical-1.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


# -------- Discovery --------
class TestDiscovery:
    def test_candidates_list_shape(self, s):
        r = s.get(f"{API}/arbicore/discovery/candidates")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and isinstance(d["items"], list) and len(d["items"]) > 0
        assert "total" in d
        assert "generated_at" in d
        st = d["stats"]
        for k in ("total", "new", "watching", "promoted", "dismissed"):
            assert k in st, f"missing stats key {k}"

    def test_filter_status_new(self, s):
        r = s.get(f"{API}/arbicore/discovery/candidates", params={"status": "NEW"})
        assert r.status_code == 200
        assert all(c["status"] == "NEW" for c in r.json()["items"])

    def test_filter_kind_asset(self, s):
        r = s.get(f"{API}/arbicore/discovery/candidates", params={"kind": "asset"})
        assert r.status_code == 200
        assert all(c["kind"] == "asset" for c in r.json()["items"])

    def test_action_watch_then_verify(self, s):
        r = s.post(f"{API}/arbicore/discovery/candidates/cand-001/action", params={"action": "watch"})
        assert r.status_code == 200
        d = r.json()
        assert d["ok"] is True and d["status"] == "WATCHING"
        g = s.get(f"{API}/arbicore/discovery/candidates").json()
        c1 = next(c for c in g["items"] if c["id"] == "cand-001")
        assert c1["status"] == "WATCHING"

    def test_action_promote(self, s):
        r = s.post(f"{API}/arbicore/discovery/candidates/cand-001/action", params={"action": "promote"})
        assert r.status_code == 200 and r.json()["status"] == "PROMOTED"

    def test_action_dismiss(self, s):
        r = s.post(f"{API}/arbicore/discovery/candidates/cand-001/action", params={"action": "dismiss"})
        assert r.status_code == 200 and r.json()["status"] == "DISMISSED"
        # reset for other tests
        s.post(f"{API}/arbicore/discovery/candidates/cand-001/action", params={"action": "reset"})


# -------- Intelligence --------
class TestIntelligence:
    def test_recommendations(self, s):
        r = s.get(f"{API}/arbicore/intelligence/recommendations")
        assert r.status_code == 200
        d = r.json()
        for k in ("top_routes", "top_chains", "top_entities", "generated_at"):
            assert k in d
        assert isinstance(d["top_routes"], list) and len(d["top_routes"]) > 0
        assert isinstance(d["top_chains"], list)
        assert isinstance(d["top_entities"], list)

    def test_decisions_shape(self, s):
        r = s.get(f"{API}/arbicore/intelligence/decisions")
        assert r.status_code == 200
        d = r.json()
        assert "items" in d and "total" in d and "generated_at" in d
        first = d["items"][0]
        for k in ("id", "opp_id", "asset", "family", "verdict", "confidence", "regime", "top_factors", "at"):
            assert k in first

    def test_decisions_verdict_go(self, s):
        r = s.get(f"{API}/arbicore/intelligence/decisions", params={"verdict": "GO"})
        assert r.status_code == 200
        assert all(i["verdict"] == "GO" for i in r.json()["items"])

    def test_decisions_family_cex(self, s):
        r = s.get(f"{API}/arbicore/intelligence/decisions", params={"family": "CEX_ARBITRAGE"})
        assert r.status_code == 200
        assert all(i["family"] == "CEX_ARBITRAGE" for i in r.json()["items"])

    def test_decisions_min_confidence(self, s):
        r = s.get(f"{API}/arbicore/intelligence/decisions", params={"min_confidence": 0.7})
        assert r.status_code == 200
        assert all(i["confidence"] >= 0.7 for i in r.json()["items"])
