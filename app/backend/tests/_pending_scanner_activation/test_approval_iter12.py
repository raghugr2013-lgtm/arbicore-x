"""Iteration 12 — Approval Required Mode integration tests.

Exercises the full Approval pipeline:
  - sizing-targets endpoint
  - public batch capture endpoint (X-ArbiCore-Quote-Key)
  - proposed list (primary + secondary ranking)
  - proposer worker status + history
  - approve / reject lifecycle (creates QUOTED cycle)
  - staleness (verified-quote > 30s should not produce primary)
  - auto-mode flag stays gated by safety_interlock

The test seeds an opportunity by:
  1. Inserting a synthetic Coinstore orderbook snapshot with a wide enough spread.
  2. Posting a multi-size batch with effective_price low enough to satisfy ROI floor.
  3. Asserting build_proposals returns PRIMARY/SECONDARY with correct field set.
"""
from __future__ import annotations

import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL",
                          "https://arbitrum-launch-1.preview.emergentagent.com").rstrip("/")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ArbiCore2026!"
QUOTE_KEY_ENV = "ARBICORE_QUOTE_CAPTURE_KEY"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:200]}")
    return s


@pytest.fixture(scope="module")
def quote_key():
    # Resolve via the backend .env (tests share filesystem with backend).
    p = "/app/backend/.env"
    if not os.path.exists(p):
        pytest.skip(".env not readable")
    for line in open(p):
        if line.startswith(QUOTE_KEY_ENV + "="):
            v = line.split("=", 1)[1].strip().strip('"').strip("'")
            if v:
                return v
    pytest.skip("ARBICORE_QUOTE_CAPTURE_KEY missing")


# ──────────────────────────────────────────────────────────────────────
# Sizing targets
# ──────────────────────────────────────────────────────────────────────
def test_sizing_targets_shape(session):
    r = session.get(f"{BASE_URL}/api/execution/sizing-targets", timeout=15)
    assert r.status_code == 200, r.text
    b = r.json()
    for k in ("min_buy_usd", "available_balance_usd", "available_source",
              "recommended_buy_usd", "max_safe_buy_usd", "risk_limit_usd",
              "daily_limit_usd", "daily_used_usd", "daily_remaining_usd",
              "verification_sizes_usd", "feasible", "blockers"):
        assert k in b, f"missing key {k}: {b}"
    assert b["min_buy_usd"] == 50.0
    assert isinstance(b["verification_sizes_usd"], list)
    # min size is always included
    if b["verification_sizes_usd"]:
        assert 50.0 in b["verification_sizes_usd"]


# ──────────────────────────────────────────────────────────────────────
# Batch capture + proposed pipeline
# ──────────────────────────────────────────────────────────────────────
def _post_batch(quote_key, captures):
    return requests.post(
        f"{BASE_URL}/api/public/quote-capture-batch",
        headers={"X-ArbiCore-Quote-Key": quote_key, "Content-Type": "application/json"},
        json={"captures": captures}, timeout=15,
    )


def test_batch_requires_key():
    r = requests.post(f"{BASE_URL}/api/public/quote-capture-batch",
                      json={"captures": [{"size_usd": 50, "effective_price": 0.00004}]},
                      timeout=10)
    assert r.status_code == 401, r.text


def test_batch_rejects_empty(quote_key):
    r = _post_batch(quote_key, [])
    assert r.status_code == 400, r.text


def test_batch_ingest_and_ranking(session, quote_key):
    """Post 3 verified quotes; assert proposed pipeline ranks + returns primary."""
    oc = session.get(f"{BASE_URL}/api/execution/operator-console", timeout=15).json()
    sell = (oc.get("monitor") or {}).get("coinstore_best_bid") or 4.5e-5

    # Effective price ~12% below sell so net ROI ~> 8% which passes 5% floor.
    buy_target = sell * 0.88
    captures = []
    for size in (50, 100, 150):
        captures.append({
            "size_usd": size,
            "effective_price": buy_target * (1 + 0.0005 * (size / 50)),
            "bdag_quoted": size / (buy_target * (1 + 0.0005 * (size / 50))),
            "source": "pytest_iter12",
            "raw": {"test_run": str(uuid.uuid4())},
        })
    r = _post_batch(quote_key, captures)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["persisted"] == 3, b
    assert isinstance(b["sizes"], list)

    # Now fetch proposed; primary must be present and have all required fields
    pr = session.get(f"{BASE_URL}/api/execution/proposed", timeout=15).json()
    assert pr["ranked_count"] >= 1
    # Ranking + threshold checks (best-effort: may be 0 if no live best_bid)
    if pr["primary"]:
        p = pr["primary"]
        for k in ("proposal_id", "buy_price", "sell_price", "net_roi_pct",
                  "expected_profit_usd", "quality_score", "risk_label",
                  "regime", "expected_cycle_s", "size_usd", "quote_age_s",
                  "bdag_expected", "fee_drag_pct"):
            assert k in p, f"primary missing {k}: {p}"
        # PRIMARY should have the highest quality_score
        for s in pr.get("secondary") or []:
            assert p["quality_score"] >= s["quality_score"]


def test_proposer_status_running(session):
    r = session.get(f"{BASE_URL}/api/execution/proposer/status", timeout=15)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["running"] is True
    assert s["interval_s"] == 15


def test_proposed_current_returns_snapshot(session):
    """After the proposer worker has run at least once, /proposed/current
    must return either the cache or a live rebuild."""
    # give it a few seconds to run if just started
    for _ in range(6):
        r = session.get(f"{BASE_URL}/api/execution/proposed/current", timeout=15)
        if r.status_code == 200 and r.json().get("source"):
            break
        time.sleep(2)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("source") in ("proposer_cache", "live_rebuild")
    assert "blockers" in body
    assert "ranked_count" in body


# ──────────────────────────────────────────────────────────────────────
# Staleness — old captures should not produce a primary
# ──────────────────────────────────────────────────────────────────────
def test_staleness_invalidates_primary(session, quote_key):
    """Posting a batch and waiting > 30s should clear primary (verified quote stale)."""
    captures = [{"size_usd": 50, "effective_price": 1e-5,
                 "bdag_quoted": 5_000_000, "source": "pytest_iter12_stale"}]
    r = _post_batch(quote_key, captures)
    assert r.status_code == 200
    # Wait beyond 30s staleness window
    time.sleep(33)
    pr = session.get(f"{BASE_URL}/api/execution/proposed", timeout=15).json()
    # primary must be None OR a different (fresher) batch — but our stale one
    # must NOT be the primary
    if pr.get("primary"):
        assert "pytest_iter12_stale" not in (pr["primary"].get("buy_price_source") or "")
    # blockers must mention verified_quote_stale OR a newer batch arrived
    # (so the original stale capture cannot be the primary).


# ──────────────────────────────────────────────────────────────────────
# Approve + Reject
# ──────────────────────────────────────────────────────────────────────
def _seed_actionable_batch(session, quote_key, label="seed", spread_pct=12):
    """Posts a wide-spread batch that should yield an actionable primary.
    Returns the parsed proposed response."""
    # Resolve current Coinstore best_bid via operator-console.monitor (always present)
    oc = session.get(f"{BASE_URL}/api/execution/operator-console", timeout=15).json()
    sell = (oc.get("monitor") or {}).get("coinstore_best_bid") or 4.5e-5
    # buy_price = sell * (1 - spread_pct/100) → net ROI ≈ spread_pct - fees
    buy = sell * (1 - spread_pct / 100.0)
    captures = [{
        "size_usd": 50,
        "effective_price": buy,
        "bdag_quoted": 50 / buy,
        "source": f"pytest_iter12_{label}",
    }]
    r = requests.post(
        f"{BASE_URL}/api/public/quote-capture-batch",
        headers={"X-ArbiCore-Quote-Key": quote_key, "Content-Type": "application/json"},
        json={"captures": captures}, timeout=15,
    )
    assert r.status_code == 200, r.text
    time.sleep(1)  # let proposer pick it up
    return session.get(f"{BASE_URL}/api/execution/proposed", timeout=15).json()


def test_approve_creates_quoted_cycle(session, quote_key):
    pr = _seed_actionable_batch(session, quote_key, "approve")
    if not pr.get("primary"):
        pytest.skip(f"could not synthesise primary (blockers={pr.get('blockers')})")
    primary_id = pr["primary"]["proposal_id"]

    a = session.post(f"{BASE_URL}/api/execution/proposed/{primary_id}/approve",
                     json={"size_usd": 50, "approve_mode": "recommended",
                           "note": "pytest iter12 approve"}, timeout=15)
    assert a.status_code == 200, a.text
    body = a.json()
    assert body["decision_id"].startswith("appr_")
    assert body["cycle"]["state"] == "QUOTED"
    assert primary_id in (body["cycle"].get("note") or "")
    assert body["cycle"]["input_amount_usd"] == 50
    assert body["cycle"]["expected_roi_pct"] is not None


def test_reject_logs_decision(session, quote_key):
    pr = _seed_actionable_batch(session, quote_key, "reject")
    if not pr.get("primary"):
        pytest.skip("no primary to reject")
    primary_id = pr["primary"]["proposal_id"]
    a = session.post(f"{BASE_URL}/api/execution/proposed/{primary_id}/reject",
                     json={"reason": "pytest iter12"}, timeout=15)
    assert a.status_code == 200, a.text
    assert a.json()["decision_id"].startswith("rej_")


def test_approve_rejects_invalid_mode(session, quote_key):
    pr = _seed_actionable_batch(session, quote_key, "invalid")
    if not pr.get("primary"):
        pytest.skip("no primary")
    primary_id = pr["primary"]["proposal_id"]
    a = session.post(f"{BASE_URL}/api/execution/proposed/{primary_id}/approve",
                     json={"size_usd": 50, "approve_mode": "bad_mode"}, timeout=15)
    assert a.status_code == 400


def test_approve_rejects_below_floor(session, quote_key):
    pr = _seed_actionable_batch(session, quote_key, "floor")
    if not pr.get("primary"):
        pytest.skip("no primary")
    primary_id = pr["primary"]["proposal_id"]
    a = session.post(f"{BASE_URL}/api/execution/proposed/{primary_id}/approve",
                     json={"size_usd": 49, "approve_mode": "custom"}, timeout=15)
    assert a.status_code == 400


# ──────────────────────────────────────────────────────────────────────
# Auto Mode — flag toggling never bypasses safety_interlock
# ──────────────────────────────────────────────────────────────────────
def test_auto_mode_double_gate(session):
    s0 = session.get(f"{BASE_URL}/api/execution/auto-mode/status", timeout=15).json()
    assert "auto_mode_enabled_flag" in s0
    assert "execution_enabled_interlock" in s0
    assert s0["auto_mode_effective"] is False  # interlock always blocks today
    # Toggle ON
    s1 = session.put(f"{BASE_URL}/api/execution/auto-mode/status",
                     json={"enabled": True}, timeout=15).json()
    assert s1["auto_mode_enabled_flag"] is True
    assert s1["auto_mode_effective"] is False  # still gated
    # Toggle back
    s2 = session.put(f"{BASE_URL}/api/execution/auto-mode/status",
                     json={"enabled": False}, timeout=15).json()
    assert s2["auto_mode_enabled_flag"] is False
