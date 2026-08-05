"""Iteration 11 - Historical Drift Analyzer API integration tests.

Covers the new HDA endpoints and authority-chain non-regression.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://arbix-router-repair.preview.emergentagent.com").rstrip("/")
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "ArbiCore2026!"

PRIMARY = [30, 60, 120, 300, 600, 900]
SECONDARY = [1800, 3600, 7200]
RISK_LABELS = {"LOW", "MEDIUM", "HIGH", "VERY_HIGH"}
REGIME_LABELS = {"Stable", "Volatile", "Extremely Volatile"}
VERDICTS = {"NOT_TRADEABLE", "TRADEABLE", "HIGH_CONFIDENCE"}


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
               timeout=15)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code} {r.text[:200]}")
    return s


# ----- HDA endpoints -----

def test_drift_run_forces_recompute(session):
    r = session.post(f"{BASE_URL}/api/execution/drift-analysis/run", json={}, timeout=30)
    assert r.status_code == 200, r.text
    body = r.json()
    summaries = body.get("summaries") or body.get("results") or []
    assert isinstance(summaries, list) and len(summaries) >= 1
    item = summaries[0]
    for k in ("symbol", "venue", "computed_at", "compute_time_ms", "regime", "risk_label", "risk_score"):
        assert k in item, f"missing key {k} in summary: {item}"


def test_drift_analysis_snapshot_schema(session):
    # Force a recompute first
    session.post(f"{BASE_URL}/api/execution/drift-analysis/run", json={}, timeout=30)
    r = session.get(f"{BASE_URL}/api/execution/drift-analysis", timeout=15)
    assert r.status_code == 200
    snap = r.json()
    assert snap.get("available") is True, f"snap not available: {snap}"
    for k in ("schema_version", "symbol", "venue", "computed_at", "sample_count_summary",
              "horizons_primary_s", "horizons_secondary_s", "drift", "survivability",
              "liquidity_survivability", "opportunity_capacity", "cycle_duration_map",
              "regime", "risk_score", "model"):
        assert k in snap, f"missing {k}"
    assert snap["horizons_primary_s"] == PRIMARY
    assert snap["horizons_secondary_s"] == SECONDARY
    assert snap["risk_score"]["label"] in RISK_LABELS
    assert snap["regime"]["label"] in REGIME_LABELS


def test_drift_history_has_entries(session):
    # Trigger a second run to ensure 2+ entries
    session.post(f"{BASE_URL}/api/execution/drift-analysis/run", json={}, timeout=30)
    time.sleep(0.5)
    session.post(f"{BASE_URL}/api/execution/drift-analysis/run", json={}, timeout=30)
    r = session.get(f"{BASE_URL}/api/execution/drift-analysis/history?limit=5", timeout=15)
    assert r.status_code == 200
    body = r.json()
    entries = body.get("snapshots") or body.get("history") or body.get("entries") or []
    assert isinstance(entries, list)
    assert len(entries) >= 2, f"expected 2+ history entries, got {len(entries)}: {entries}"
    for e in entries[:2]:
        for k in ("computed_at", "computed_at_ts", "regime", "risk_label", "risk_score",
                  "max_buy_usd", "recommended_buy_usd",
                  "opportunity_capacity_score_0_100", "sample_count_summary"):
            assert k in e, f"history entry missing {k}: {e}"


def test_drift_symbols_lists_runner(session):
    r = session.get(f"{BASE_URL}/api/execution/drift-analysis/symbols", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "pairs" in body and isinstance(body["pairs"], list)
    assert "runner" in body
    runner = body["runner"]
    assert runner.get("running") is True
    assert runner.get("default_period_s") == 600
    if body["pairs"]:
        p = body["pairs"][0]
        for k in ("symbol", "venue", "computed_at", "risk_label", "regime"):
            assert k in p


# ----- Authority-chain non-regression -----

def test_operator_console_unchanged_and_has_drift_block(session):
    r = session.get(f"{BASE_URL}/api/execution/operator-console", timeout=15)
    assert r.status_code == 200
    body = r.json()
    for k in ("phase", "monitor", "risk", "verdict", "quote_verification",
              "actions", "guardrails", "links", "generated_at", "historical_drift"):
        assert k in body, f"operator-console missing {k}"
    assert body["verdict"]["verdict"] in VERDICTS
    assert body["guardrails"]["execution_enabled"] is False
    assert body["guardrails"]["wallet_enabled"] is False
    hd = body["historical_drift"]
    for k in ("available", "regime", "opportunity_survival_prob_at_expected_cycle",
              "risk_label", "risk_score_0_100", "opportunity_capacity_score_0_100",
              "max_buy_usd", "recommended_buy_usd", "min_buy_usd", "feasible", "model_kind"):
        assert k in hd, f"historical_drift missing {k}: {hd}"
    assert hd["min_buy_usd"] == 50


def test_buy_price_audit_unchanged(session):
    r = session.get(f"{BASE_URL}/api/execution/buy-price-audit", timeout=15)
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_quote_capture_unchanged(session):
    r = session.get(f"{BASE_URL}/api/execution/quote-capture", timeout=15)
    assert r.status_code == 200


def test_executable_quote_unchanged(session):
    r = session.get(f"{BASE_URL}/api/execution/executable-quote", timeout=15)
    assert r.status_code == 200


def test_opportunity_gate_buy_price_source(session):
    r = session.get(f"{BASE_URL}/api/execution/opportunity/gate", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "buy_price_source" in body, f"opportunity/gate missing buy_price_source: {list(body.keys())}"
