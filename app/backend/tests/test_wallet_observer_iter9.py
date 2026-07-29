"""Iter9 — BlockDAG Connectivity Diagnostic + RPC failover backend tests."""
import os
import time

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
TEST_ADDR = "0xA52fD71308E8a36b5C6497FbDB8E36949A673974"
TEST_TX = "0x7a8a61c0849383fcd6794aa98e004b072cb34d8812c777da2353b0902e983b2d"
EXPECTED_CHAIN_ID = 1404


@pytest.fixture(scope="session")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": "admin", "password": "ArbiCore2026!"},
               timeout=20)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    return s


# ---------------- guardrails regression ----------------

def test_guardrails_still_off(session):
    r = session.get(f"{BASE_URL}/api/execution/observer/status", timeout=15)
    assert r.status_code == 200
    g = r.json()["guardrails"]
    for f in ("execution_enabled", "wallet_enabled", "transaction_signing",
              "autonomous_execution", "fund_movement"):
        assert g[f] is False, f"{f} should be False"
    r2 = session.get(f"{BASE_URL}/api/execution/status", timeout=15)
    assert r2.status_code == 200
    assert r2.json()["execution_enabled"] is False
    r3 = session.get(f"{BASE_URL}/api/execution/operator-console?investment_usd=50", timeout=20)
    assert r3.status_code == 200


# ---------------- diagnostic ----------------

@pytest.fixture(scope="session")
def diagnostic_report(session):
    """Run the full diagnostic once and share across tests (35s)."""
    r = session.post(f"{BASE_URL}/api/execution/observer/diagnostic",
                     json={"test_address": TEST_ADDR, "test_tx": TEST_TX,
                           "expected_chain_id": EXPECTED_CHAIN_ID},
                     timeout=120)
    assert r.status_code == 200, f"diagnostic failed: {r.status_code} {r.text[:300]}"
    return r.json()


def test_diagnostic_top_level_keys(diagnostic_report):
    for k in ("ran_at", "ran_at_iso", "test_address", "test_tx",
              "expected_chain_id", "rpc_primary", "rpc_secondary",
              "explorer_primary", "explorer_secondary",
              "cross_chain_check", "address_activity_demo", "recommendation"):
        assert k in diagnostic_report, f"missing top-level key: {k}"
    assert diagnostic_report["expected_chain_id"] == EXPECTED_CHAIN_ID


def test_diagnostic_rpc_primary(diagnostic_report):
    p = diagnostic_report["rpc_primary"]
    assert p["name"] == "rpc.bdagscan.com"
    reach = p["reachability"]
    assert "stability_pct" in reach and "latency_ms_avg" in reach and "statuses" in reach
    evm = p["evm"]
    assert evm["eth_chainId"]["matches_expected"] is True
    assert evm["eth_chainId"]["decoded_int"] == EXPECTED_CHAIN_ID
    assert evm["eth_blockNumber"]["verdict"] == "PASS"
    assert evm["eth_blockNumber"]["decoded_int"] > 1e7
    assert evm["eth_getBalance"]["verdict"] == "PASS"
    assert (evm["eth_getBalance"]["decoded_bdag"] or 0) > 1e6
    assert evm["eth_getLogs"]["verdict"] == "PASS"
    assert evm["eth_getTransactionByHash_positive_control"]["verdict"] == "PASS"


def test_diagnostic_rpc_secondary_is_blocked(diagnostic_report):
    s = diagnostic_report["rpc_secondary"]
    assert s["name"] == "rpc.blockdag.engineering"
    # all EVM calls should FAIL (Cloudflare 403) — but reachability HTTP responded
    for k in ("eth_chainId", "eth_blockNumber", "eth_getBalance",
              "eth_getTransactionByHash", "eth_getLogs"):
        assert s["evm"][k]["verdict"] == "FAIL", f"{k} unexpectedly passed on secondary"


def test_diagnostic_explorers_unusable(diagnostic_report):
    for k in ("explorer_primary", "explorer_secondary"):
        e = diagnostic_report[k]["explorer"]
        assert e.get("etherscan_works") is False
        assert e.get("blockscout_works_address_history") is False
        assert e.get("blockscout_works_tx_lookup") is False


def test_diagnostic_cross_chain_check(diagnostic_report):
    cc = diagnostic_report["cross_chain_check"]["bsc_mainnet"]
    assert cc["found"] is True
    assert (cc["from"] or "").lower().startswith("0xa52fd71308")
    assert isinstance(cc["block_decimal"], int)


def test_diagnostic_address_activity_demo(diagnostic_report):
    a = diagnostic_report["address_activity_demo"]
    for k in ("url", "address", "lookback_blocks", "head_block", "matched",
              "found_activity", "verdict"):
        assert k in a, f"missing key {k} in address_activity_demo"
    assert isinstance(a["matched"], list)


def test_diagnostic_recommendation(diagnostic_report):
    rec = diagnostic_report["recommendation"]
    assert rec["primary"] == "rpc.bdagscan.com"
    assert rec["verdict"] == "PASS"
    assert isinstance(rec["reliability_score"], (int, float))
    assert rec["reliability_score"] >= 50
    assert isinstance(rec["notes"], list)


def test_diagnostic_last_endpoint(session, diagnostic_report):
    r = session.get(f"{BASE_URL}/api/execution/observer/diagnostic/last", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("available") is not False  # should have a stored diag
    assert body["recommendation"]["primary"] == diagnostic_report["recommendation"]["primary"]


# ---------------- rpc-health ----------------

def test_rpc_health_endpoint(session):
    r = session.get(f"{BASE_URL}/api/execution/observer/rpc-health", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["expected_chain_id"] == 1404
    for side in ("primary", "secondary"):
        assert side in body
        for f in ("url", "healthy", "last_latency_ms", "total_calls",
                  "total_failures", "consecutive_failures", "consecutive_successes"):
            assert f in body[side], f"missing {f} in {side}"


# ---------------- failover proof ----------------

def test_failover_force_down_and_recovery(session):
    # configure
    r = session.put(f"{BASE_URL}/api/execution/observer/config",
                    json={"enabled": True,
                          "operator_bdag_address": TEST_ADDR,
                          "force_primary_down": True,
                          "max_blocks_per_tick": 10},
                    timeout=15)
    assert r.status_code == 200, r.text[:300]

    # poll with primary forced down
    r = session.post(f"{BASE_URL}/api/execution/observer/poll", timeout=120)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    assert "rpc_health" in body and body["rpc_health"] is not None
    health = body["rpc_health"]
    assert health["primary"]["healthy"] is False
    assert "forced-down" in (health["primary"].get("last_error") or "")
    sec = health["secondary"]
    assert sec is not None
    assert sec["total_calls"] > 0, "secondary was not attempted"

    # restore primary
    r = session.put(f"{BASE_URL}/api/execution/observer/config",
                    json={"force_primary_down": False}, timeout=15)
    assert r.status_code == 200

    # poll again
    time.sleep(1)
    r = session.post(f"{BASE_URL}/api/execution/observer/poll", timeout=120)
    assert r.status_code == 200
    body = r.json()
    health = body["rpc_health"]
    assert health["primary"]["healthy"] is True
    assert health["primary"].get("last_error") in (None, "")
    assert health["primary"]["consecutive_successes"] >= 1


# ---------------- poller integration ----------------

def test_observer_poll_integration(session):
    session.put(f"{BASE_URL}/api/execution/observer/config",
                json={"enabled": True, "operator_bdag_address": TEST_ADDR,
                      "max_blocks_per_tick": 10}, timeout=15)
    r = session.post(f"{BASE_URL}/api/execution/observer/poll", timeout=120)
    assert r.status_code == 200
    body = r.json()
    assert body.get("skipped") is False
    assert body.get("bdag_tx_seen", -1) >= 0
    assert body.get("rpc_health") is not None


# ---------------- legacy config migration ----------------

def test_legacy_explorer_fields_ignored(session):
    # patch legacy fields
    r = session.put(f"{BASE_URL}/api/execution/observer/config",
                    json={"blockdag_explorer_base": "https://example.com",
                          "blockdag_explorer_kind": "blockscout"},
                    timeout=15)
    assert r.status_code == 200
    cfg = r.json()
    # rpc_primary should remain default (not overwritten by legacy fields)
    assert cfg["blockdag_rpc_primary"] == "https://rpc.bdagscan.com"
    # legacy keys should not have leaked back into the doc
    assert "blockdag_explorer_kind" not in cfg or cfg.get("blockdag_explorer_kind") in (None,)


# ---------------- regression: coinstore-sell still works ----------------

def test_coinstore_sell_regression(session):
    create = session.post(f"{BASE_URL}/api/execution/arb-cycles",
                          json={"input_amount": 50.0, "quote_price": 0.05,
                                "bdag_expected": 1000000, "best_bid": 0.06,
                                "expected_roi_pct": 5.0,
                                "note": "TEST_iter9 regression"},
                          timeout=15)
    assert create.status_code == 200, create.text[:300]
    cycle_id = create.json()["id"]
    stamp = session.post(f"{BASE_URL}/api/execution/observer/coinstore-sell",
                         json={"cycle_id": cycle_id, "order_id": "TEST_iter9_ord",
                               "bdag_sold": 1000000, "usdt_received": 50.0,
                               "fee_usdt": 0.1, "best_bid_at_sell": 0.06},
                         timeout=20)
    assert stamp.status_code == 200, stamp.text[:300]
    res = stamp.json()
    assert res["cycle"]["state"] == "SOLD"
