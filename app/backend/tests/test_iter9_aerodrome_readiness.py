"""Iteration 9 backend tests — Aerodrome on-chain settlement adapter readiness."""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://defi-exec-audit.preview.emergentagent.com").rstrip("/")
USERNAME = "operator"
PASSWORD = "ShadowOperator!2026"


@pytest.fixture(scope="module")
def auth_session():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": USERNAME, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return s


def test_readiness_matrix_unauth():
    r = requests.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=30)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"


def test_checkpoint_unauth():
    r = requests.get(f"{BASE_URL}/api/arbicore/engine/checkpoint", timeout=30)
    assert r.status_code == 401, f"Expected 401, got {r.status_code}"


def test_readiness_matrix_dex_adapters_green(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/readiness-matrix", timeout=60)
    assert r.status_code == 200, r.text
    data = r.json()
    print("Readiness matrix:", data)
    # Locate gates
    caps = data.get("capabilities", [])
    def find_gate(name):
        for g in caps:
            if g.get("capability") == name:
                return g
        return None

    dex = find_gate("DEX_ADAPTERS_SETTLE")
    assert dex is not None, f"DEX_ADAPTERS_SETTLE not found; data={data}"
    status = dex.get("status")
    assert str(status).upper() == "GREEN", f"DEX_ADAPTERS_SETTLE not GREEN: {dex}"

    liq = find_gate("LIQUIDITY_DEPTH")
    assert liq is not None
    assert str(liq.get("status")).upper() == "GREEN", liq

    sim = find_gate("SIMULATION_ONCHAIN")
    assert sim is not None
    assert str(sim.get("status")).upper() == "YELLOW", sim

    hist = find_gate("HISTORICAL_REPLAY")
    assert hist is not None
    assert str(hist.get("status")).upper() == "YELLOW", hist

    fork = find_gate("FORK_VALIDATION")
    assert fork is not None
    assert str(fork.get("status")).upper() == "RED", fork

    overall = data.get("overall_status")
    assert str(overall).upper() == "RED", f"overall_status expected RED, got {overall}"

    modes = data.get("modes", {})
    ll = modes.get("LIMITED_LIVE", {})
    fa = modes.get("FULL_AUTOMATION", {})
    assert ll.get("can_activate") is False, f"LIMITED_LIVE.can_activate must be False: {ll}"
    assert fa.get("can_activate") is False, f"FULL_AUTOMATION.can_activate must be False: {fa}"


def test_checkpoint_blockers(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/checkpoint", timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    print("Checkpoint:", data)
    blockers = data.get("limited_live_blockers") or data.get("blockers") or []
    blockers_str = str(blockers).upper()
    assert "DEX_ADAPTERS_SETTLE" not in blockers_str, f"DEX_ADAPTERS_SETTLE should no longer block: {blockers}"
    for req in ["FORK_VALIDATION", "SIMULATION_ONCHAIN", "HISTORICAL_REPLAY"]:
        assert req in blockers_str, f"{req} should still be in blockers: {blockers}"
    # walk owners/actions present
    if isinstance(blockers, list) and blockers and isinstance(blockers[0], dict):
        for b in blockers:
            assert "owner" in b or "action" in b, f"blocker missing owner/action: {b}"


def test_scan_once_funnel(auth_session):
    r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/scan-once", timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    print("scan-once keys:", list(data.keys()))
    assert "quote_failure_reasons" in r.text, f"quote_failure_reasons missing: {data}"


def test_scanner_status(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/scanner/status", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    print("scanner status:", data)
    # confirm running-ish
    running = data.get("running") if "running" in data else data.get("status")
    assert running in (True, "running", "RUNNING") or data.get("state") in ("running", "RUNNING"), f"scanner not running: {data}"


def test_no_signing_broadcast_strings(auth_session):
    # sample scan-once response and confirm no sign/broadcast leaks
    r = auth_session.post(f"{BASE_URL}/api/arbicore/engine/scan-once", timeout=120)
    assert r.status_code == 200
    text = r.text.lower()
    for forbidden in ["private_key", "signed_tx", "raw_tx", "eth_sendrawtransaction"]:
        assert forbidden not in text, f"forbidden string leak: {forbidden}"


def test_safety_state(auth_session):
    # kill switch + mode
    r = auth_session.get(f"{BASE_URL}/api/arbicore/engine/checkpoint", timeout=60)
    assert r.status_code == 200
    data = r.json()
    txt = str(data).lower()
    # mode should mention shadow
    assert "shadow" in txt, f"SHADOW mode not indicated: {data}"
    # kill switch disengaged if present
    ks = data.get("kill_switch") or data.get("killSwitch")
    if ks is not None:
        s = str(ks).lower()
        assert "disengag" in s or ks in (False, "disengaged", "DISENGAGED"), f"kill switch not disengaged: {ks}"


def test_decide_opportunity_and_live_quote(auth_session):
    r1 = auth_session.post(f"{BASE_URL}/api/arbicore/control/decide-opportunity", json={}, timeout=90)
    assert r1.status_code in (200, 400, 422), f"decide-opportunity unexpected: {r1.status_code} {r1.text}"
    r2 = auth_session.post(f"{BASE_URL}/api/arbicore/control/live-quote", json={}, timeout=90)
    assert r2.status_code in (200, 400, 422), f"live-quote unexpected: {r2.status_code} {r2.text}"
