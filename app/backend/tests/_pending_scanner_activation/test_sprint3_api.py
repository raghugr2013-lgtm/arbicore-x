"""Sprint 3 API regression tests — auth, vault, alerts, economics, capabilities, WS.
Run: cd /app/backend && python -m pytest tests/test_sprint3_api.py -v
Requires the backend running on localhost:8001 and credentials from
/app/memory/test_credentials.md (admin / ArbiCore#2026).
"""
import httpx
import pytest

BASE = "http://localhost:8001/api"
USERNAME = "admin"
PASSWORD = "ArbiCore#2026"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        yield c


@pytest.fixture(scope="module")
def authed(client):
    r = client.post("/auth/login", json={"username": USERNAME, "password": PASSWORD})
    assert r.status_code == 200, f"login failed: {r.text}"
    return client  # cookies persist on the client


# ---------- auth ----------

def test_status_public(client):
    r = client.get("/auth/status")
    assert r.status_code == 200
    assert r.json()["setup_complete"] is True


def test_setup_locked(client):
    r = client.post("/auth/setup", json={"username": "intruder", "password": "hackhackhack"})
    assert r.status_code == 403


def test_protected_routes_require_auth():
    with httpx.Client(base_url=BASE, timeout=30) as anon:
        for path in ("/routes", "/vault/keys", "/alerts/settings", "/capabilities",
                     "/system/status", "/docs-package"):
            assert anon.get(path).status_code == 401, f"{path} not protected"


def test_login_bad_password(client):
    with httpx.Client(base_url=BASE, timeout=30) as anon:
        r = anon.post("/auth/login", json={"username": USERNAME, "password": "definitely-wrong"})
        assert r.status_code == 401


def test_me_and_refresh(authed):
    me = authed.get("/auth/me")
    assert me.status_code == 200 and me.json()["username"] == USERNAME
    assert authed.post("/auth/refresh").status_code == 200


# ---------- vault ----------

def test_vault_crud_and_health(authed):
    r = authed.post("/vault/keys", json={"exchange": "gate", "label": "pytest dummy",
                                         "api_key": "pytest-key-123", "api_secret": "pytest-secret-123"})
    assert r.status_code == 200
    key = r.json()
    assert key["key_mask"].startswith("pyte") and "status" in key
    # secrets never returned
    listing = authed.get("/vault/keys").json()
    assert all("key_enc" not in k and "secret_enc" not in k for k in listing)
    # health test with dummy creds → graceful error, status flips to error
    t = authed.post(f"/vault/keys/{key['id']}/test").json()
    assert t["ok"] is False and t["key"]["status"] == "error"
    assert authed.delete(f"/vault/keys/{key['id']}").status_code == 200


def test_vault_rejects_unknown_exchange(authed):
    r = authed.post("/vault/keys", json={"exchange": "binance", "api_key": "x" * 10,
                                         "api_secret": "y" * 10})
    assert r.status_code == 400


# ---------- alerts ----------

def test_alerts_dormant_lifecycle(authed):
    s = authed.get("/alerts/settings").json()
    assert {"enabled", "chat_id", "rules", "token_set"} <= set(s.keys())
    # save without token keeps dormant config
    r = authed.put("/alerts/settings", json={"enabled": False, "chat_id": "",
                                             "rules": {"min_net_spread_pct": 3.0}})
    assert r.status_code == 200 and r.json()["rules"]["min_net_spread_pct"] == 3.0
    # restore default
    authed.put("/alerts/settings", json={"enabled": False, "chat_id": "", "rules": {}})
    # test message without token → guidance, not crash
    t = authed.post("/alerts/test").json()
    assert t["ok"] is False and "token" in t["message"].lower()


# ---------- economics / capabilities / ws ----------

def test_economics(authed):
    rid = authed.get("/routes").json()[0]["id"]
    r = authed.get(f"/routes/{rid}/economics", params={"hours": 24})
    assert r.status_code == 200
    d = r.json()
    for k in ("raw", "executable", "capture_ratio_pct", "gate_blockage", "recent_episodes"):
        assert k in d
    for col in (d["raw"], d["executable"]):
        for k in ("episodes", "total_minutes", "avg_duration_min", "avg_net_pct", "est_profit_quote"):
            assert k in col


def test_capabilities_persisted(authed):
    caps = authed.get("/capabilities", params={"currency": "BDAG"}).json()
    assert isinstance(caps, list)
    if caps:  # collector needs one fee cycle to populate
        assert {"exchange", "currency", "deposit_enabled", "withdraw_enabled"} <= set(caps[0].keys())
    hist = authed.get("/capabilities/history").json()
    assert isinstance(hist, list)


def test_ws_status(authed):
    ws = authed.get("/system/status").json()["websockets"]
    assert set(ws.keys()) == {"xt", "bitmart"}
    for st in ws.values():
        assert {"connected", "mode", "subscriptions"} <= set(st.keys())
        assert st["mode"] in ("ws", "rest-fallback")


# ---------- session security (run last: revokes sessions) ----------

def test_change_password_and_logout_all():
    with httpx.Client(base_url=BASE, timeout=30) as c:
        assert c.post("/auth/login", json={"username": USERNAME, "password": PASSWORD}).status_code == 200
        # wrong current password rejected
        r = c.post("/auth/change-password", json={"current_password": "nope-nope",
                                                  "new_password": "whatever123"})
        assert r.status_code == 401
        # change and revert (keeps documented credentials valid)
        assert c.post("/auth/change-password", json={"current_password": PASSWORD,
                                                     "new_password": "TempPass#9999"}).status_code == 200
        assert c.get("/auth/me").status_code == 200  # this session survived
        assert c.post("/auth/change-password", json={"current_password": "TempPass#9999",
                                                     "new_password": PASSWORD}).status_code == 200
        # logout-all kills every session
        assert c.post("/auth/logout-all").status_code == 200
        assert c.get("/auth/me").status_code == 401
