"""T1 smoke: backend health, canonical auth, and read-only control/safety APIs."""
import os
import re

import pytest
import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")

CREDS = "/app/memory/test_credentials.md"


def _creds(role):
    txt = open(CREDS).read()
    m = re.search(rf"\|\s*{role}\s*\|\s*(\S+)\s*\|\s*(\S+)\s*\|", txt, re.I)
    assert m, f"{role} creds not found"
    return m.group(1), m.group(2)


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    u, p = _creds("Admin")
    r = s.post(f"{BASE_URL}/api/auth/login", json={"username": u, "password": p},
               timeout=30)
    assert r.status_code == 200, f"admin login failed {r.status_code} {r.text[:300]}"
    body = r.json()
    assert body["username"] == u and body["role"] == "admin"
    return s


def test_root_health():
    r = requests.get(f"{BASE_URL}/api/", timeout=30)
    assert r.status_code == 200


def test_login_wrong_password_401():
    u, _ = _creds("Admin")
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"username": u, "password": "wrong-pass"}, timeout=30)
    assert r.status_code == 401


def test_operator_login():
    u, p = _creds("Operator")
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"username": u, "password": p}, timeout=30)
    assert r.status_code == 200
    assert r.json()["role"] in ("operator", "admin")


def test_auth_me(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=30)
    assert r.status_code == 200
    assert r.json()["username"] == _creds("Admin")[0]


@pytest.mark.parametrize("path", [
    "/api/arbicore/control/readiness",
    "/api/arbicore/control/mode",
    "/api/arbicore/engine/checkpoint",
])
def test_readonly_control_endpoints_no_5xx(admin_session, path):
    r = admin_session.get(f"{BASE_URL}{path}", timeout=60)
    assert r.status_code < 500, f"{path} -> {r.status_code} {r.text[:300]}"


def test_no_signing_material_leaked(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/arbicore/control/readiness", timeout=60)
    body = r.text.lower()
    for bad in ("private_key", "signed_tx", "raw_tx",
                "eth_sendrawtransaction", "personal_sign"):
        assert bad not in body, f"leaked {bad}"
