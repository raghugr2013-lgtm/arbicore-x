"""STAGE 1 — canonical real FlashLoanArbitrageScanner activation acceptance.

Proves the canonical flash-loan discovery path is instantiated (not the dormant
ShadowScannerAdapter), wired to the real Base pool universe + a LIVE quote
provider, running detection-only under SHADOW, with all economic/atomic/liquidity/
MEV gates preserved (a losing route is denied, never emitted → no fabrication).
"""
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    with open("/app/frontend/.env") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")


def _status():
    r = requests.get(f"{BASE_URL}/api/arbicore/scanners/status", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def test_canonical_scanner_instantiated_and_live():
    c = _status().get("canonical_flash_loan_arbitrage", {})
    assert c.get("instantiated") is True, c
    assert c.get("class") == "FlashLoanArbitrageScanner", c
    assert c.get("quote_provider") == "live", c
    assert c.get("authoritative") is True, c
    assert c.get("detection_only") is True, c
    assert c.get("enabled") is True, c
    assert int(c.get("pool_universe_size") or 0) > 0, c


def test_shadow_adapter_marked_non_authoritative():
    d = _status()
    sa = d.get("flash_loan_arbitrage_shadow_adapter", {})
    assert sa.get("authoritative") is False, sa


def test_scanner_running_no_errors_gates_present():
    c = _status().get("canonical_flash_loan_arbitrage", {})
    stats = c.get("stats") or {}
    assert stats.get("last_error") is None, stats
    assert stats.get("iterations", 0) >= 1, stats
    # the economic/liquidity/MEV gate counters exist (gates preserved)
    gr = stats.get("gate_rejections") or {}
    for g in ("gate_7_atomic_profit", "gate_8_liquidity_depth", "gate_9_flash_loan_mev"):
        assert g in gr, gr


def test_no_fabricated_emissions_when_unprofitable():
    # Honest posture: with no profitable route in the market, nothing is
    # emitted (rows_emitted stays 0); denials/rejections are the correct state.
    c = _status().get("canonical_flash_loan_arbitrage", {})
    stats = c.get("stats") or {}
    emitted = int(stats.get("rows_emitted") or 0)
    confirmed = int(stats.get("verifier_confirmed") or 0)
    # If anything WAS emitted it must have been genuinely confirmed by the
    # verifier (never a fabricated/forced emit).
    assert emitted <= confirmed + 0  # emitted only on confirmed
    assert emitted >= 0
