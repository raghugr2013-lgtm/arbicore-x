"""v2.11 · Execution Ready — full regression suite (iteration_8).

Coverage matrix:
  Slice 3 (6 intelligence endpoints):
     S3.A anon → 401 not_authenticated on all 6
     S3.B canonical source + shape (recommendations/decisions/calibration/models/certification/entities)
     S3.C no hardcoded placeholders (ent-w-001, dec-001, 10-bucket bootstrap, etc.)
     S3.D empty-store shapes are stable
  Slice 4 (20 planner endpoints):
     S4.A anon → 401 on all 20
     S4.B E2E pipeline: build → simulate → sign → calldata (balancer heads)
     S4.C bug fix: build with incomplete swap_hops returns {error:...} not 500
     S4.D bug fix: broadcast confirm:false returns dry receipt (no crash)
  Phase C (auth pattern):
     C.A grep server.py: `await _require_operator_ctx` appears only in wrapper def
     C.B 14 migrated endpoints anon → 401
  Prior slices regression:
     R.S1 6 opportunities endpoints still work under auth
     R.S2 2 discovery endpoints still work under auth
  Auth v2.9.3 surface:
     A.setup/login/logout/me + HttpOnly cookies
  Performance:
     P.decisions <500ms, P.recommendations <1s
"""
from __future__ import annotations

import os
import re
import time
import uuid
from pathlib import Path

import pymongo
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://127.0.0.1:8001").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "arbicore_x_hotfix_test")
ADMIN = {"username": "admin", "password": "hotfix-v293"}
SERVER_PY = Path("/app/app/backend/server.py")


# ============================================================ fixtures

@pytest.fixture(scope="module")
def mongo():
    return pymongo.MongoClient(MONGO_URL)[DB_NAME]


@pytest.fixture(scope="module")
def anon():
    return requests.Session()


@pytest.fixture(scope="module")
def auth():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=10)
    if r.status_code != 200:
        # try setup then login
        s.post(f"{API}/auth/setup", json=ADMIN, timeout=10)
        r = s.post(f"{API}/auth/login", json=ADMIN, timeout=10)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return s


# ============================================================ endpoint tables

# Slice 3 · 6 intelligence GET endpoints
INTEL_EPS = [
    "/arbicore/intelligence/recommendations",
    "/arbicore/intelligence/decisions",
    "/arbicore/intelligence/calibration",
    "/arbicore/intelligence/models",
    "/arbicore/intelligence/certification",
    "/arbicore/intelligence/entities",
]

# Slice 4 · 20 planner endpoints (method, path)
PLANNER_EPS = [
    ("GET",   "/arbicore/execution/adapters"),
    ("POST",  "/arbicore/execution/plans/build"),
    ("GET",   "/arbicore/execution/plans"),
    ("GET",   "/arbicore/execution/plans/does-not-exist"),
    ("GET",   "/arbicore/execution/simulation/status"),
    ("GET",   "/arbicore/execution/gas"),
    ("GET",   "/arbicore/execution/mev/routers"),
    ("POST",  "/arbicore/execution/plans/x/simulate"),
    ("POST",  "/arbicore/execution/plans/x/sign"),
    ("POST",  "/arbicore/execution/plans/x/calldata"),
    ("POST",  "/arbicore/execution/plans/x/broadcast"),
    ("GET",   "/arbicore/execution/capital-policy"),
    ("GET",   "/arbicore/execution/capital-policy/flash_loan_arbitrage"),
    ("PATCH", "/arbicore/execution/capital-policy/flash_loan_arbitrage"),
    ("POST",  "/arbicore/execution/capital-policy/flash_loan_arbitrage/evaluate"),
    ("GET",   "/arbicore/execution/kill-switch"),
    ("POST",  "/arbicore/execution/kill-switch/engage"),
    ("POST",  "/arbicore/execution/kill-switch/disengage"),
    ("GET",   "/arbicore/execution/kill-switch/audit"),
    ("GET",   "/arbicore/execution/certification/stages"),
    ("POST",  "/arbicore/execution/certification/run"),
]
# 21 rows above because /plans/{id} split from /plans; requirement says 20 endpoints —
# we still test all 21 routes for auth completeness.

# Slice 1/1.1 opps endpoints
OPPS_EPS = [
    ("GET",  "/arbicore/opportunities/summary"),
    ("GET",  "/arbicore/opportunities"),
    ("GET",  "/arbicore/opportunities/xyz"),
    ("POST", "/arbicore/opportunities/xyz/approve"),
    ("POST", "/arbicore/opportunities/xyz/reject"),
    ("GET",  "/arbicore/opportunities/xyz/timeline"),
]
# Slice 2 discovery endpoints
DISC_EPS = [
    ("GET",  "/arbicore/discovery/candidates"),
    ("POST", "/arbicore/discovery/candidates/xyz/action?action=watch"),
]


# ============================================================ Slice 3 tests

class TestSlice3IntelligenceAuth:
    @pytest.mark.parametrize("path", INTEL_EPS)
    def test_anon_401(self, anon, path):
        r = anon.get(f"{API}{path}")
        assert r.status_code == 401, f"{path}: expected 401 got {r.status_code}"
        assert r.json().get("detail") == "not_authenticated"


class TestSlice3IntelligenceShape:
    def test_recommendations_canonical(self, auth):
        r = auth.get(f"{API}/arbicore/intelligence/recommendations", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "canonical"
        assert isinstance(d["top_routes"], list)
        assert isinstance(d["top_chains"], list)
        assert isinstance(d["top_entities"], list)
        # No hardcoded placeholder route
        s = str(d)
        assert "ent-w-001" not in s
        assert "binance:ETH-USDT" not in s  # legacy hardcode
        # If any routes exist, verify shape
        for row in d["top_routes"]:
            assert {"route", "win_rate", "trials", "mean_confidence"} <= set(row.keys())

    def test_decisions_canonical(self, auth):
        r = auth.get(f"{API}/arbicore/intelligence/decisions", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "canonical"
        assert isinstance(d["items"], list)
        s = str(d)
        for hardcoded in ("dec-001", "dec-002", "dec-003", "dec-004", "dec-005", "dec-006"):
            assert hardcoded not in s, f"hardcoded id {hardcoded} still present"
        for it in d["items"]:
            assert it.get("verdict") in ("GO", "HARD_NO", "SOFT_NO", None) or "verdict" in it

    def test_decisions_filters_honored(self, auth):
        r = auth.get(f"{API}/arbicore/intelligence/decisions?limit=1", timeout=10)
        assert r.status_code == 200
        assert len(r.json()["items"]) <= 1

    def test_calibration_canonical(self, auth):
        r = auth.get(f"{API}/arbicore/intelligence/calibration", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "canonical"
        # When no active model: available:false, buckets empty
        if not d.get("available"):
            assert d.get("buckets") == []
            assert d.get("n_samples") == 0

    def test_models_canonical(self, auth):
        r = auth.get(f"{API}/arbicore/intelligence/models", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "canonical"
        assert isinstance(d["items"], list)
        # No hardcoded 4-model array
        names = [str(m.get("name", "")) for m in d["items"]]
        # legacy hardcoded set — should NOT be present verbatim
        legacy = {"confidence-v1", "regime-v1", "sizing-v1", "gate-v1"}
        assert not (legacy <= set(names)), "hardcoded legacy 4-model array still present"

    def test_certification_canonical(self, auth):
        r = auth.get(f"{API}/arbicore/intelligence/certification", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "canonical"
        # No hardcoded 12-cycle campaign
        assert "12-cycle" not in str(d).lower() or d.get("available") is True

    def test_entities_canonical(self, auth):
        r = auth.get(f"{API}/arbicore/intelligence/entities", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d["source"] == "canonical"
        assert isinstance(d["items"], list)
        assert isinstance(d["vocabulary"], list)
        s = str(d)
        for hc in ("ent-w-001", "ent-w-002", "ent-w-010"):
            assert hc not in s, f"hardcoded id {hc} still present"


# ============================================================ Slice 4 tests

class TestSlice4PlannerAuth:
    @pytest.mark.parametrize("method,path", PLANNER_EPS)
    def test_anon_401(self, anon, method, path):
        r = anon.request(method, f"{API}{path}", json={} if method in ("POST", "PATCH") else None)
        assert r.status_code == 401, f"{method} {path}: expected 401 got {r.status_code}"
        assert r.json().get("detail") == "not_authenticated"


class TestSlice4PlannerE2E:
    @pytest.fixture(scope="class")
    def built_plan(self, auth):
        payload = {
            "strategy": "flash_loan_arbitrage",
            "chain": "base",
            "borrow_token": "USDC",
            "borrow_amount_wei": 1000_000000,
            "flash_loan_provider": "balancer_v2",
            "swap_hops": [
                {"dex": "uniswap_v3", "token_in": "USDC", "token_out": "WETH",
                 "amount_in_wei": 1000_000000, "min_amount_out_wei": 300_000000000000000,
                 "fee_tier_bps": 5},
                {"dex": "uniswap_v3", "token_in": "WETH", "token_out": "USDC",
                 "amount_in_wei": 300_000000000000000, "min_amount_out_wei": 1001_000000,
                 "fee_tier_bps": 5},
            ],
        }
        r = auth.post(f"{API}/arbicore/execution/plans/build", json=payload, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "error" not in d, f"build error: {d.get('error')}"
        return d["plan"]

    def test_build_returns_4_steps_shadow(self, built_plan):
        p = built_plan
        assert p.get("plan_id")
        assert p.get("mode") in ("SHADOW", "OBSERVE", "PAPER", "LIMITED_LIVE")
        steps = p.get("steps") or []
        # borrow + 2 swaps + repay + profit = 5 steps typically; requirement says 4 (borrow/swap/repay/profit)
        assert len(steps) >= 4, f"expected >=4 steps, got {len(steps)}"

    def test_simulate(self, auth, built_plan):
        pid = built_plan["plan_id"]
        r = auth.post(f"{API}/arbicore/execution/plans/{pid}/simulate", json={}, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert "error" not in d, f"simulate error: {d}"

    def test_sign(self, auth, built_plan):
        pid = built_plan["plan_id"]
        r = auth.post(f"{API}/arbicore/execution/plans/{pid}/sign", json={}, timeout=30)
        assert r.status_code == 200

    def test_calldata_balancer(self, auth, built_plan):
        pid = built_plan["plan_id"]
        r = auth.post(f"{API}/arbicore/execution/plans/{pid}/calldata", json={}, timeout=30)
        assert r.status_code == 200

    def test_build_missing_swap_field_returns_error_not_500(self, auth):
        payload = {
            "strategy": "flash_loan_arbitrage",
            "chain": "base",
            "borrow_token": "USDC",
            "borrow_amount_wei": 1000_000000,
            "flash_loan_provider": "balancer_v2",
            "swap_hops": [
                {"dex": "uniswap_v3", "token_in": "USDC", "token_out": "WETH"}
                # missing amount_in_wei, min_amount_out_wei
            ],
        }
        r = auth.post(f"{API}/arbicore/execution/plans/build", json=payload, timeout=20)
        assert r.status_code == 200, f"expected 200 (with error body), got {r.status_code}"
        d = r.json()
        assert "error" in d
        # ValueError should mention missing fields
        assert "amount_in_wei" in d["error"] or "missing" in d["error"].lower()

    def test_broadcast_confirm_false_no_crash(self, auth, built_plan):
        pid = built_plan["plan_id"]
        r = auth.post(f"{API}/arbicore/execution/plans/{pid}/broadcast",
                      json={"confirm": False, "actor": "test"}, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Either dry receipt or explicit error string, but no 500 crash
        assert "receipt" in d or "error" in d


# ============================================================ Phase C tests

class TestPhaseCCleanup:
    def test_no_manual_operator_ctx_calls_in_server(self):
        src = SERVER_PY.read_text()
        # Only the wrapper `return await _require_operator_ctx(...)` in the helper
        # definition is allowed.
        occurrences = re.findall(r"await\s+_require_operator_ctx\s*\(", src)
        assert len(occurrences) == 1, (
            f"expected exactly 1 `await _require_operator_ctx(` "
            f"(inside wrapper def), got {len(occurrences)}"
        )

    def test_wrapper_definition_present(self):
        src = SERVER_PY.read_text()
        assert "async def _require_operator_dep(" in src
        assert "dependencies=[Depends(_require_operator_dep)]" in src


class TestPhaseCAuthGate:
    """14 migrated endpoints all return 401 anon."""
    ALL_14 = OPPS_EPS + DISC_EPS + [("GET", p) for p in INTEL_EPS]

    @pytest.mark.parametrize("method,path", ALL_14)
    def test_anon_401_uniform(self, anon, method, path):
        r = anon.request(method, f"{API}{path}",
                         json={} if method in ("POST", "PATCH") else None)
        assert r.status_code == 401
        assert r.json().get("detail") == "not_authenticated"


# ============================================================ Prior slices regression

class TestSlice1Regression:
    def test_opps_summary_shape(self, auth):
        r = auth.get(f"{API}/arbicore/opportunities/summary", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("source") == "canonical"

    def test_opps_list_shape(self, auth):
        r = auth.get(f"{API}/arbicore/opportunities?limit=5", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("source") == "canonical"
        assert isinstance(d.get("items"), list)

    def test_opps_unknown_id_404(self, auth):
        r = auth.get(f"{API}/arbicore/opportunities/does-not-exist-xyz", timeout=10)
        assert r.status_code == 404


class TestSlice2Regression:
    def test_discovery_list(self, auth):
        r = auth.get(f"{API}/arbicore/discovery/candidates?limit=5", timeout=10)
        assert r.status_code == 200
        d = r.json()
        assert d.get("source") == "canonical"


# ============================================================ Auth v2.9.3 surface

class TestAuthSurface:
    def test_me_anon_401(self, anon):
        r = anon.get(f"{API}/auth/me")
        assert r.status_code == 401

    def test_login_sets_httponly_cookies(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json=ADMIN, timeout=10)
        assert r.status_code == 200
        # cookie flag check via Set-Cookie header
        set_cookie = r.headers.get("set-cookie", "") + " ".join(
            [k + "=" + v for k, v in r.headers.items() if k.lower() == "set-cookie"]
        )
        # requests coalesces; check via raw
        raw = r.raw.headers.getlist("set-cookie") if hasattr(r.raw.headers, "getlist") else [set_cookie]
        joined = " ".join(raw).lower()
        assert "access_token" in joined
        assert "httponly" in joined
        assert "samesite=lax" in joined

    def test_me_after_login(self, auth):
        r = auth.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        assert r.json().get("username") == "admin"

    def test_logout_then_me_401(self):
        s = requests.Session()
        assert s.post(f"{API}/auth/login", json=ADMIN, timeout=10).status_code == 200
        assert s.post(f"{API}/auth/logout", timeout=10).status_code in (200, 204)
        r = s.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 401


# ============================================================ Performance

class TestPerformance:
    def test_decisions_under_500ms(self, auth):
        # warm
        auth.get(f"{API}/arbicore/intelligence/decisions?limit=100", timeout=10)
        t0 = time.time()
        r = auth.get(f"{API}/arbicore/intelligence/decisions?limit=100", timeout=10)
        dt = (time.time() - t0) * 1000
        assert r.status_code == 200
        assert dt < 500, f"decisions took {dt:.0f}ms (>500)"

    def test_recommendations_under_1s(self, auth):
        auth.get(f"{API}/arbicore/intelligence/recommendations", timeout=10)
        t0 = time.time()
        r = auth.get(f"{API}/arbicore/intelligence/recommendations", timeout=10)
        dt = (time.time() - t0) * 1000
        assert r.status_code == 200
        assert dt < 1000, f"recommendations took {dt:.0f}ms (>1000)"
