"""Phase 10.10.5 — /plans/build persistence surface + wei overflow.

Regression tests:
    * `/plans/build` returns an explicit `error` (with `attempted_plan_id`)
      when Mongo rejects the insert — no more silent-swallow that hands
      back an unpersisted plan_id.
    * MongoDB int64 boundary: min_amount_out_wei > 2^63-1 must not crash
      the operator; the endpoint returns a helpful OverflowError message.
    * Normal build with realistic wei values persists and returns
      {"plan": {plan_id: ...}} (happy path).
"""
from __future__ import annotations

import os
import pytest
import requests


API = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001") + "/api"


_VALID_BODY = {
    "strategy": "flash_loan_arbitrage",
    "chain": "base",
    "flash_loan_provider": "balancer_v2",
    "recipient": "0x91c0bf28E32b76889BB2B61E1A2dDE9F7e4f3DE3",
    "borrow_token": "0x4200000000000000000000000000000000000006",
    "borrow_amount_wei": "10000000000000000",
    "borrow_amount_usd": 25,
    "swap_hops": [
        {"dex": "uniswap_v3",
         "token_in": "0x4200000000000000000000000000000000000006",
         "token_out": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
         "fee_tier_bps": 5,
         "amount_in_wei": "10000000000000000",
         "min_amount_out_wei": "24500000"},
        {"dex": "uniswap_v3",
         "token_in": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
         "token_out": "0x4200000000000000000000000000000000000006",
         "fee_tier_bps": 5,
         "amount_in_wei": "24500000",
         "min_amount_out_wei": "9000000000000000000"},  # 9e18 — under int64 max
    ],
    "signer_wallet_id": "gas-wallet-1",
    "opportunity_id": "test-1010-5",
}


def test_happy_path_persists_and_is_retrievable():
    """Normal build → persists → GET on same id returns the plan."""
    body = dict(_VALID_BODY, opportunity_id="test-1010-5-happy")
    r = requests.post(f"{API}/arbicore/execution/plans/build", json=body, timeout=15)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "error" not in data, data
    plan_id = data["plan"]["plan_id"]
    # Immediate retrieval must succeed.
    g = requests.get(f"{API}/arbicore/execution/plans/{plan_id}", timeout=15).json()
    assert g.get("plan") is not None, f"plan {plan_id} not persisted"


def test_overflow_wei_surfaces_explicit_error_not_silent_success():
    """Value > 2^63-1 in a wei field must return an explicit error, NOT a
    fake plan_id whose plan never actually landed in Mongo (which was the
    pre-10.10.5 silent-swallow bug)."""
    body = dict(_VALID_BODY, opportunity_id="test-1010-5-overflow")
    body = {**body,
            "swap_hops": [
                *body["swap_hops"][:1],
                {**body["swap_hops"][1],
                 "min_amount_out_wei": "999999999999999999999"},  # 999e18 > 2^63
            ]}
    r = requests.post(f"{API}/arbicore/execution/plans/build", json=body, timeout=15)
    assert r.status_code == 200
    data = r.json()
    assert "error" in data, "expected explicit error, got: " + repr(data)
    assert "Overflow" in data["error"] or "8-byte" in data["error"], data["error"]
    # Attempted plan_id is surfaced for diagnostics.
    assert data.get("attempted_plan_id"), data
    # Critically: that attempted_plan_id must NOT exist in Mongo.
    g = requests.get(
        f"{API}/arbicore/execution/plans/{data['attempted_plan_id']}",
        timeout=15,
    ).json()
    assert g.get("plan") is None, \
        "an unpersisted attempt should NOT be findable"
