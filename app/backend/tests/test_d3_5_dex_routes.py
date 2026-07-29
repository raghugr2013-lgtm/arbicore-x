"""Tests for D-3.5 — DEX scanner HTTP routes.

Covers all 5 new endpoints exposed under /api/arbicore/scanners/dex_arb/*
and verifies operator-controlled lifecycle preservation (scanner remains
disabled by default — only POST resume flips state).

Authentication is required via cookie session — same flow as the existing
arbicore route tests. Tests use live HTTP through the auth flow.
"""
from __future__ import annotations

import os
import time
import requests

import pytest


BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://arbitcore-handover.preview.emergentagent.com",
).rstrip("/")
USERNAME = "admin"
PASSWORD = "ArbiCore2026!"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": USERNAME, "password": PASSWORD}, timeout=10)
    if r.status_code != 200:
        pytest.skip(f"auth not available: {r.status_code} {r.text[:120]}")
    yield s


# ----- /scanners/dex_arb/status --------------------------------------------

def test_dex_status_shape(session):
    r = session.get(f"{BASE_URL}/api/arbicore/scanners/dex_arb/status", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wave"] == "D-3.4"
    assert body["scanner_id"] == "dex_arb"
    assert body["primary_metric"] == "mev_adjusted_net_pct"
    # 8 venue sources + 1 HINT
    assert len(body["sources_registered"]) == 9
    assert "dexscreener_hint" in body["sources_registered"]
    assert "DEX_ARBITRAGE" in body["verifiers_registered"]
    # Operator-controlled disabled-by-default posture
    assert body["enabled"] is False
    # Config surface present
    assert "interval_s" in body["config"]
    assert "tier_a_pairs" in body["config"]
    assert "gate_thresholds" in body["config"]
    # Stats present
    assert "scanner_stats" in body
    assert "gate_rejections" in body["scanner_stats"]


# ----- /scanners/dex_arb/{kill,resume} -------------------------------------

def test_dex_kill_resume_toggles_persistent_state(session):
    # kill (idempotent)
    r = session.post(f"{BASE_URL}/api/arbicore/scanners/dex_arb/kill", timeout=10)
    assert r.status_code == 200, r.text
    # status reflects disabled
    r = session.get(f"{BASE_URL}/api/arbicore/scanners/dex_arb/status", timeout=10)
    assert r.json()["enabled"] is False
    # resume flips state
    r = session.post(f"{BASE_URL}/api/arbicore/scanners/dex_arb/resume", timeout=10)
    assert r.status_code == 200, r.text
    time.sleep(0.5)
    r = session.get(f"{BASE_URL}/api/arbicore/scanners/dex_arb/status", timeout=10)
    assert r.json()["enabled"] is True
    # IMMEDIATE re-kill — leave disabled per operator's D-3.6 shadow-rollout
    # requirement (no D-3.5 test should leave the scanner enabled)
    session.post(f"{BASE_URL}/api/arbicore/scanners/dex_arb/kill", timeout=10)
    r = session.get(f"{BASE_URL}/api/arbicore/scanners/dex_arb/status", timeout=10)
    assert r.json()["enabled"] is False


# ----- /scanners/dex_arb/config --------------------------------------------

def test_dex_config_update_rejects_empty_patch(session):
    r = session.put(f"{BASE_URL}/api/arbicore/scanners/dex_arb/config",
                    json={}, timeout=10)
    assert r.status_code == 400


def test_dex_config_update_accepts_partial_patch(session):
    r = session.put(f"{BASE_URL}/api/arbicore/scanners/dex_arb/config",
                    json={"interval_s": 90}, timeout=10)
    assert r.status_code == 200, r.text
    # Restore via second patch (interval_s was 60 by D-3.0 default)
    session.put(f"{BASE_URL}/api/arbicore/scanners/dex_arb/config",
                json={"interval_s": 60}, timeout=10)


def test_dex_config_update_accepts_gate_thresholds_patch(session):
    new_thresholds = {
        "default": {
            "min_net_spread_after_slip_after_gas_pct": 0.35,
            "min_depth_usd": 5000, "min_confidence": 55,
        },
    }
    r = session.put(f"{BASE_URL}/api/arbicore/scanners/dex_arb/config",
                    json={"gate_thresholds": new_thresholds}, timeout=10)
    assert r.status_code == 200, r.text
    # Verify reflected in status
    r = session.get(f"{BASE_URL}/api/arbicore/scanners/dex_arb/status", timeout=10)
    th = r.json()["config"]["gate_thresholds"]["default"]
    assert th["min_net_spread_after_slip_after_gas_pct"] == 0.35
    # Restore D-3.0 default (0.30)
    session.put(f"{BASE_URL}/api/arbicore/scanners/dex_arb/config",
                json={"gate_thresholds": {"default": {
                    "min_net_spread_after_slip_after_gas_pct": 0.30,
                    "min_depth_usd": 5000, "min_confidence": 55,
                }}}, timeout=10)


# ----- /scanners/dex_arb/gate-analysis -------------------------------------

def test_dex_gate_analysis_shape(session):
    r = session.get(
        f"{BASE_URL}/api/arbicore/scanners/dex_arb/gate-analysis",
        params={"window_minutes": 60}, timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wave"] == "D-3.4"
    assert body["scanner_id"] == "dex_arb"
    assert body["primary_metric"] == "mev_adjusted_net_pct"
    assert body["window_minutes"] == 60
    # Empty universe is fine — scanner disabled by default; assert keys present
    assert "totals" in body
    assert {"observed", "validated", "rejected"}.issubset(body["totals"])
    assert "rejections_by_gate" in body
    assert "rejection_pct_by_gate" in body
    assert "scanner_stats_live" in body


def test_dex_gate_analysis_accepts_pair_and_venue_filters(session):
    r = session.get(
        f"{BASE_URL}/api/arbicore/scanners/dex_arb/gate-analysis",
        params={"window_minutes": 60, "pair": "WETH", "venue": "uniswap_v3:arbitrum"},
        timeout=10,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scanner_id"] == "dex_arb"


# ----- Auth gating ---------------------------------------------------------

def test_dex_routes_require_auth():
    """Unauthenticated requests must be rejected — operator-controlled.

    Tries localhost first (preview-environment infra-agnostic), then falls
    back to the public preview URL. The D-3.5 wave shipped before this
    defensive pattern existed in tests; the same pattern is used in D-4.6
    routes test (test_d4_6_launch_routes.py)."""
    for base in ("http://localhost:8001", BASE_URL):
        try:
            r = requests.get(
                f"{base}/api/arbicore/scanners/dex_arb/status", timeout=10,
            )
            if r.status_code == 404:
                continue   # base not reachable; try next
            assert r.status_code in (401, 403)
            r = requests.post(
                f"{base}/api/arbicore/scanners/dex_arb/resume", timeout=10,
            )
            assert r.status_code in (401, 403)
            return
        except requests.RequestException:
            continue
    pytest.skip("no auth-gated dex_arb endpoint reachable in this environment")
