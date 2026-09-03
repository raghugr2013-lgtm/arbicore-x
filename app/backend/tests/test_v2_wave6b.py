"""Wave 6B · Execution Planning HTTP contract tests."""
from __future__ import annotations

import os

import pytest
import requests

BASE = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://arbicore-canonical-1.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE}/api"

TOKEN_A = "0x" + "aa" * 20
TOKEN_B = "0x" + "bb" * 20


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _sample_body(**over):
    body = {
        "strategy": "flash_loan_arbitrage",
        "chain": "base",
        "borrow_token": TOKEN_A,
        "borrow_amount_wei": 1_000_000_000,
        "borrow_amount_usd": 1000.0,
        "flash_loan_provider": "aave_v3",
        "swap_hops": [{
            "dex": "uniswap_v3",
            "token_in": TOKEN_A, "token_out": TOKEN_B,
            "amount_in_wei": 1_000_000_000, "min_amount_out_wei": 999_500_000,
            "fee_tier_bps": 5,
        }, {
            "dex": "aerodrome",
            "token_in": TOKEN_B, "token_out": TOKEN_A,
            "amount_in_wei": 999_500_000, "min_amount_out_wei": 1_001_000_000,
        }],
        "quote_effective_out_wei": 1_002_000_000,
        "gas_estimate_usd": 1.0,
    }
    body.update(over)
    return body


class TestAdapterCatalog:
    def test_shape(self, client):
        r = client.get(f"{API}/arbicore/execution/adapters")
        assert r.status_code == 200
        d = r.json()
        for k in ("flash_loan_providers", "dex_providers", "address_book",
                  "generated_at"):
            assert k in d
        providers = {p["provider"] for p in d["flash_loan_providers"]}
        assert providers == {"aave_v3", "balancer_v2", "uniswap_v3"}
        dexes = {p["dex"] for p in d["dex_providers"]}
        assert dexes == {"uniswap_v3", "aerodrome"}
        assert "base" in d["address_book"]

    def test_base_addresses_populated(self, client):
        d = client.get(f"{API}/arbicore/execution/adapters").json()
        base = d["address_book"]["base"]
        for k in ("aave_v3_pool", "balancer_v2_vault",
                  "uniswap_v3_router", "aerodrome_router"):
            assert base[k].startswith("0x")


class TestPlanBuild:
    def test_happy_path_returns_plan_and_economics(self, client):
        r = client.post(f"{API}/arbicore/execution/plans/build", json=_sample_body())
        assert r.status_code == 200
        d = r.json()
        assert "plan" in d
        plan = d["plan"]
        assert plan["mode"] in {"OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE"}  # state-independent since Phase 10.10.1
        assert plan["chain"] == "base"
        assert plan["flash_loan_provider"] == "aave_v3"
        assert plan["dex_route"] == ["uniswap_v3", "aerodrome"]
        kinds = [s["kind"] for s in plan["steps"]]
        assert kinds == ["borrow", "swap", "swap", "repay", "profit"]
        assert plan["plan_hash"].startswith("sha256:")
        # Economics attached.
        eco = plan["economics"]
        assert eco["engine_version"] == "dry_run@1"
        assert eco["profitable"] is True

    def test_deterministic_plan_hash(self, client):
        b = _sample_body()
        p1 = client.post(f"{API}/arbicore/execution/plans/build", json=b).json()["plan"]
        p2 = client.post(f"{API}/arbicore/execution/plans/build", json=b).json()["plan"]
        # plan_id + created_at differ; plan_hash must not.
        assert p1["plan_hash"] == p2["plan_hash"]
        assert p1["plan_id"] != p2["plan_id"]

    def test_rejects_unknown_flash_provider(self, client):
        r = client.post(f"{API}/arbicore/execution/plans/build",
                        json=_sample_body(flash_loan_provider="mystery"))
        d = r.json()
        assert "error" in d

    def test_rejects_unknown_dex(self, client):
        body = _sample_body()
        body["swap_hops"] = [{"dex": "unknown", "token_in": TOKEN_A,
                              "token_out": TOKEN_B, "amount_in_wei": 1,
                              "min_amount_out_wei": 1}]
        r = client.post(f"{API}/arbicore/execution/plans/build", json=body)
        assert "error" in r.json()

    def test_rejects_provider_chain_mismatch(self, client):
        body = _sample_body(chain="ethereum")
        # Keep aerodrome in the swap list — aerodrome is Base-only.
        r = client.post(f"{API}/arbicore/execution/plans/build", json=body)
        assert "error" in r.json()

    def test_rejects_empty_swap_hops(self, client):
        r = client.post(f"{API}/arbicore/execution/plans/build",
                        json=_sample_body(swap_hops=[]))
        assert "error" in r.json()


class TestPlanPersistence:
    def test_get_and_list(self, client):
        built = client.post(f"{API}/arbicore/execution/plans/build",
                            json=_sample_body()).json()["plan"]
        plan_id = built["plan_id"]
        one = client.get(f"{API}/arbicore/execution/plans/{plan_id}").json()
        assert one["plan"] is not None
        assert one["plan"]["plan_id"] == plan_id
        listed = client.get(f"{API}/arbicore/execution/plans",
                            params={"strategy": "flash_loan_arbitrage",
                                    "chain": "base", "limit": 20}).json()
        assert any(item["plan_id"] == plan_id for item in listed["items"])


class TestModeGuard:
    def test_limited_live_mode_now_accepted_by_plans_build(self, client):
        """Phase 10.10.1 (R2, 2026-08-01) — lifted the Wave-6B guard so
        ``/plans/build`` accepts LIMITED_LIVE plans.  The broadcast
        pipeline still enforces the LIMITED_LIVE gate at Gate 2
        (``broadcast.py:179``), so build-time relaxation is safe.
        FULL_LIVE remains blocked pending a future review.
        """
        # Build reflects whatever mode the strategy is currently in — no
        # rejection based on LIMITED_LIVE any more.  This test asserts
        # the guard boundary rather than a specific returned mode
        # (which depends on external / operator state).
        r = client.post(f"{API}/arbicore/execution/plans/build",
                        json=_sample_body())
        j = r.json()
        # No mode-related error.
        if j.get("error"):
            assert "LIMITED_LIVE" not in j["error"], j["error"]
            assert "Wave 6B" not in j["error"], j["error"]
        # A plan_id was produced OR the error was for an unrelated reason.
        assert j.get("plan", {}).get("plan_id") or j.get("error")


class TestBackwardCompatibility:
    def test_wave6a_endpoints_intact(self, client):
        for path in (
            "/arbicore/execution/mode",
            "/arbicore/execution/wallets",
            "/arbicore/execution/secrets/status",
        ):
            r = client.get(f"{API}{path}")
            assert r.status_code == 200

    def test_intelligence_endpoints_intact(self, client):
        for path in (
            "/arbicore/intelligence/calibration",
            "/arbicore/intelligence/weights/current",
            "/arbicore/intelligence/evidence/status",
            "/arbicore/intelligence/decisions",
        ):
            r = client.get(f"{API}{path}")
            assert r.status_code == 200
