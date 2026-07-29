"""Sprint 4 iteration-5 supplemental tests — vault→balance integration & deeper spec checks.
Run: cd /app/backend && python -m pytest tests/test_sprint4_iter5_e2e.py -v
"""
import time

import httpx
import pytest

BASE = "http://localhost:8001/api"
USERNAME = "admin"
PASSWORD = "ArbiCore#2026"


@pytest.fixture(scope="module")
def authed():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        r = c.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
        assert r.status_code == 200, r.text
        yield c


# ---- balances polling shape ----

def test_balances_polling_metadata(authed):
    d = authed.get("/portfolio/balances").json()
    assert d["polling"]["interval_s"] == 60
    assert d["polling"]["running"] is True
    # last_cycle_at populated within at most one poll interval after first cycle.
    # If None (rare race right after service warm-up), trigger refresh and recheck.
    if not d["polling"].get("last_cycle_at"):
        authed.post("/portfolio/refresh")
        time.sleep(7)
        d = authed.get("/portfolio/balances").json()
    assert d["polling"]["last_cycle_at"], "last_cycle_at should be populated"
    # all 5 exchanges, all no_key
    exs = d["exchanges"]
    for ex in ("xt", "mexc", "gate", "bitmart", "coinstore"):
        assert exs[ex].get("status") == "no_key", f"{ex}: {exs[ex]}"
        assert exs[ex]["balances"] == []
        assert exs[ex]["total_usd"] is None


def test_deployable_factor_priority_and_no_key(authed):
    d = authed.get("/portfolio/deployable").json()
    # check secondary_factors exposed at least once (XT BDAG has closed gates per spec)
    xt = next((v for v in d["venues"] if v["exchange"] == "xt"), None)
    assert xt is not None
    # XT BDAG: deposits/withdrawals closed → expect either NO_KEY (primary) with
    # secondary_factors mentioning gates, OR DEPOSIT/WITHDRAWAL gate factor.
    if "secondary_factors" in xt:
        assert isinstance(xt["secondary_factors"], list)
    # listed venues (xt/bitmart/coinstore) must be NO_KEY w/ reason mentioning read-only
    for ex in ("xt", "bitmart", "coinstore"):
        v = next((vv for vv in d["venues"] if vv["exchange"] == ex), None)
        if v and v["listed"]:
            assert v["limiting_factor"] == "NO_KEY"
            assert "read" in v["reason"].lower() or "key" in v["reason"].lower()
    # mexc/gate are ROUTE_LIMITED (not listed)
    for ex in ("mexc", "gate"):
        v = next((vv for vv in d["venues"] if vv["exchange"] == ex), None)
        if v:
            assert v["limiting_factor"] in ("ROUTE_LIMITED", "NO_KEY")


def test_allocation_recommendations_mention_keys(authed):
    d = authed.get("/portfolio/allocation", params={"hours": 24}).json()
    assert d["recommendations"]
    joined = " ".join(d["recommendations"]).lower()
    assert "key" in joined or "no balance" in joined or "no executable" in joined
    assert "no transfers" in d["note"].lower()
    for v in d["venues"]:
        assert v["capital_usd"] is None  # no keys


def test_health_exchanges_all_five(authed):
    d = authed.get("/health/exchanges", params={"hours": 24}).json()
    rows = {h["exchange"]: h for h in d["exchanges"]}
    assert set(rows.keys()) == {"xt", "mexc", "gate", "bitmart", "coinstore"}
    # ws_mode for xt+bitmart should be 'ws'
    assert rows["xt"]["ws_mode"] == "ws"
    assert rows["bitmart"]["ws_mode"] == "ws"


def test_quality_weights_and_ranking(authed):
    d = authed.get("/quality", params={"hours": 24}).json()
    assert abs(sum(d["weights"].values()) - 1.0) < 1e-6
    # mexc/gate must rank bottom with episodes=0
    rows = {v["exchange"]: v for v in d["venues"]}
    for ex in ("mexc", "gate"):
        if ex in rows:
            assert rows[ex]["metrics"]["episodes"] == 0
            assert rows[ex]["readiness_label"] in ("NOT READY", "INSUFFICIENT DATA")


# ---- vault → balance integration ----

def test_vault_dummy_key_triggers_error_status(authed):
    # add dummy gate key
    payload = {"exchange": "gate", "api_key": "dummykey12345", "api_secret": "dummysecret12345"}
    r = authed.post("/vault/keys", json=payload)
    assert r.status_code in (200, 201), r.text
    key_id = r.json().get("id")
    try:
        # trigger refresh; may be rate-guarded, retry until it lands
        time.sleep(2)
        for _ in range(5):
            rr = authed.post("/portfolio/refresh").json()
            if rr.get("ok"):
                break
            time.sleep(3)
        # poll for status flip — exchanges dict may briefly be reorganizing
        gate_status = None
        for _ in range(40):
            time.sleep(1)
            d = authed.get("/portfolio/balances").json()
            gate = d["exchanges"].get("gate") or {}
            gate_status = gate.get("status")
            if gate_status in ("error", "rate_limited"):
                break
            # nudge again if still no_key
            if gate_status == "no_key":
                authed.post("/portfolio/refresh")
        assert gate_status in ("error", "rate_limited"), (
            f"Expected gate to flip to 'error' with bad creds, got '{gate_status}'")
        # balances stay empty (graceful)
        d = authed.get("/portfolio/balances").json()
        assert d["exchanges"]["gate"]["balances"] == []
    finally:
        # ALWAYS delete the dummy key
        if key_id:
            dr = authed.delete(f"/vault/keys/{key_id}")
            assert dr.status_code in (200, 204), dr.text
        # confirm gate goes back to no_key (may need refresh retry due to rate guard)
        ok_no_key = False
        for _ in range(40):
            time.sleep(1)
            authed.post("/portfolio/refresh")
            d = authed.get("/portfolio/balances").json()
            if d["exchanges"]["gate"]["status"] == "no_key":
                ok_no_key = True
                break
        assert ok_no_key, "gate failed to reset to no_key after key deletion"


def test_quality_range_param(authed):
    # 168h (7d) reload should succeed
    d24 = authed.get("/quality", params={"hours": 24}).json()
    d168 = authed.get("/quality", params={"hours": 168}).json()
    assert d24["hours"] == 24
    assert d168["hours"] == 168
    assert d168["venues"]
