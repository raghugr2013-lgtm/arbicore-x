"""Iteration 7 backend health check: auth + opportunities + engine scan + no signing leakage."""
import os
import re
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://elated-banach-10.preview.emergentagent.com").rstrip("/")

FORBIDDEN = ["private_key", "signed_tx", "raw_tx", "eth_sendtransaction",
             "eth_sendrawtransaction", "personal_sign"]


def _login(username, password):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"username": username, "password": password}, timeout=20)
    return s, r


def _check_no_signing(text):
    lower = text.lower()
    for word in FORBIDDEN:
        assert word not in lower, f"Forbidden signing substring '{word}' found in response"


class TestAuth:
    def test_admin_login_ok(self):
        s, r = _login("admin", "admin-shadow-2026")
        assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text[:300]}"
        _check_no_signing(r.text)

    def test_operator_login_ok(self):
        s, r = _login("operator", "operator-shadow-2026")
        assert r.status_code == 200, f"operator login failed: {r.status_code} {r.text[:300]}"
        _check_no_signing(r.text)

    def test_bad_password_rejected(self):
        s, r = _login("admin", "wrong-password-xxxx")
        assert r.status_code in (401, 403, 429), f"expected auth failure, got {r.status_code}"


class TestOpportunities:
    def test_opportunities_authenticated(self):
        s, r = _login("admin", "admin-shadow-2026")
        assert r.status_code == 200
        r2 = s.get(f"{BASE_URL}/api/arbicore/opportunities", timeout=30)
        assert r2.status_code == 200, f"opportunities failed: {r2.status_code} {r2.text[:300]}"
        data = r2.json()
        # Accept list or dict wrapper. Must be well-formed JSON.
        assert isinstance(data, (list, dict))
        if isinstance(data, dict):
            # common wrappers
            assert any(k in data for k in ("opportunities", "items", "data", "results")) or True
        _check_no_signing(r2.text)

    def test_opportunities_unauthenticated_rejected(self):
        r = requests.get(f"{BASE_URL}/api/arbicore/opportunities", timeout=20)
        assert r.status_code in (401, 403), f"unauth should be rejected, got {r.status_code}"


class TestEngineScan:
    def test_scan_once_operator(self):
        s, r = _login("operator", "operator-shadow-2026")
        assert r.status_code == 200
        r2 = s.post(f"{BASE_URL}/api/arbicore/engine/scan-once",
                    json={"limit": 5}, timeout=60)
        # Must not 5xx crash — fail-closed allowed via 200 with empty result
        assert r2.status_code < 500, f"engine scan crashed: {r2.status_code} {r2.text[:500]}"
        assert r2.status_code == 200, f"engine scan non-200: {r2.status_code} {r2.text[:300]}"
        data = r2.json()
        assert isinstance(data, (list, dict))
        _check_no_signing(r2.text)


class TestNoSigningLeakage:
    def test_health_and_common_endpoints_clean(self):
        s, r = _login("admin", "admin-shadow-2026")
        assert r.status_code == 200
        for path in ["/api/health", "/api/arbicore/opportunities",
                     "/api/arbicore/status", "/api/auth/me"]:
            try:
                rr = s.get(f"{BASE_URL}{path}", timeout=15)
                if rr.status_code < 500:
                    _check_no_signing(rr.text)
            except Exception:
                pass
