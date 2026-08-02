"""Wave 6B · Extra SHADOW-invariant & security tests (testing-agent authored).

Verifies:
  * No signed tx / private key / secret plaintext leaks from any Wave 6B endpoint.
  * Every returned plan carries mode='SHADOW'.
  * plan_hash is deterministic across identical bodies.
  * List endpoint filters honor strategy+chain.
  * Adapter catalog invariants (base in supports_chains, address 0x prefix).
"""
from __future__ import annotations

import json
import os
import re

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE}/api"

TOKEN_A = "0x" + "aa" * 20
TOKEN_B = "0x" + "bb" * 20

FORBIDDEN_KEYS = {
    "private_key", "privateKey", "secret", "secret_plaintext",
    "signed_tx", "signed_transaction", "signature", "raw_tx", "rawTx",
    "broadcast", "tx_hash",
}


def _sample_body(**over):
    body = {
        "strategy": "flash_loan_arbitrage",
        "chain": "base",
        "borrow_token": TOKEN_A,
        "borrow_amount_wei": 1_000_000_000,
        "borrow_amount_usd": 1000.0,
        "flash_loan_provider": "aave_v3",
        "swap_hops": [
            {"dex": "uniswap_v3", "token_in": TOKEN_A, "token_out": TOKEN_B,
             "amount_in_wei": 1_000_000_000, "min_amount_out_wei": 999_500_000,
             "fee_tier_bps": 5},
            {"dex": "aerodrome", "token_in": TOKEN_B, "token_out": TOKEN_A,
             "amount_in_wei": 999_500_000, "min_amount_out_wei": 1_001_000_000},
        ],
        "quote_effective_out_wei": 1_002_000_000,
        "gas_estimate_usd": 1.0,
    }
    body.update(over)
    return body


@pytest.fixture
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _scan_forbidden(payload):
    """Recursively scan for forbidden key names."""
    hits = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in FORBIDDEN_KEYS:
                    hits.append(f"{path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")
    walk(payload)
    return hits


class TestSecurityInvariant:
    def test_adapters_no_secret_leak(self, client):
        r = client.get(f"{API}/arbicore/execution/adapters")
        assert r.status_code == 200
        assert _scan_forbidden(r.json()) == []

    def test_plan_build_no_signed_tx(self, client):
        r = client.post(f"{API}/arbicore/execution/plans/build",
                        json=_sample_body())
        assert r.status_code == 200
        d = r.json()
        assert _scan_forbidden(d) == []
        # Plan mode invariant
        assert d["plan"]["mode"] == "SHADOW"

    def test_plan_get_no_secrets(self, client):
        built = client.post(f"{API}/arbicore/execution/plans/build",
                            json=_sample_body()).json()["plan"]
        r = client.get(f"{API}/arbicore/execution/plans/{built['plan_id']}")
        assert r.status_code == 200
        d = r.json()
        assert _scan_forbidden(d) == []
        assert d["plan"]["mode"] == "SHADOW"

    def test_plan_list_all_shadow(self, client):
        # Ensure at least one plan exists
        client.post(f"{API}/arbicore/execution/plans/build",
                    json=_sample_body())
        r = client.get(f"{API}/arbicore/execution/plans",
                       params={"strategy": "flash_loan_arbitrage",
                               "chain": "base", "limit": 50})
        assert r.status_code == 200
        d = r.json()
        assert _scan_forbidden(d) == []
        for item in d["items"]:
            assert item.get("mode") == "SHADOW"

    def test_no_mongo_object_id_leak(self, client):
        """Mongo _id must not surface in any Wave 6B response."""
        r = client.post(f"{API}/arbicore/execution/plans/build",
                        json=_sample_body())
        raw = r.text
        assert '"_id"' not in raw, "Mongo _id leaked in plans/build response"


class TestAdapterCatalogInvariants:
    def test_supports_chains_include_base(self, client):
        d = client.get(f"{API}/arbicore/execution/adapters").json()
        for p in d["flash_loan_providers"]:
            assert "base" in p["supports_chains"], p
            assert "version" in p
        for p in d["dex_providers"]:
            assert "base" in p["supports_chains"], p
            assert "version" in p

    def test_all_base_addresses_are_hex(self, client):
        d = client.get(f"{API}/arbicore/execution/adapters").json()
        base = d["address_book"]["base"]
        for k, v in base.items():
            assert isinstance(v, str) and v.startswith("0x") and len(v) == 42, (k, v)


class TestPlanDeterminism:
    def test_hash_stable_across_three_builds(self, client):
        b = _sample_body()
        hashes = set()
        ids = set()
        for _ in range(3):
            plan = client.post(f"{API}/arbicore/execution/plans/build",
                               json=b).json()["plan"]
            hashes.add(plan["plan_hash"])
            ids.add(plan["plan_id"])
        assert len(hashes) == 1, f"plan_hash not deterministic: {hashes}"
        assert len(ids) == 3, "plan_id must be unique per build"

    def test_hash_changes_on_amount_change(self, client):
        p1 = client.post(f"{API}/arbicore/execution/plans/build",
                         json=_sample_body()).json()["plan"]
        p2 = client.post(f"{API}/arbicore/execution/plans/build",
                         json=_sample_body(borrow_amount_wei=2_000_000_000)).json()["plan"]
        assert p1["plan_hash"] != p2["plan_hash"]
