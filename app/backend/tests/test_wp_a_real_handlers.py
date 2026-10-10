"""WP-A final verification — real resolver + real network handlers.

Closes the independent-review coverage gaps:
  * runtime exercise of ``server._resolve_current_user`` (not mocked)
  * runtime exercise of ``v2_settings_network_apply`` / ``rollback`` with the
    real ``_require_admin_dep`` dependency

Isolation: network repo apply/rollback and ``sync_env_from_network_config``
are replaced with harmless AsyncMocks *after* auth so unauthorized paths
never mutate configuration. No production hosts, secrets inspection, signing,
broadcast, or execution.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_TEST_SECRET = "wp-a-real-handler-jwt-secret-32chars!!"
os.environ["JWT_SECRET"] = _TEST_SECRET
os.environ["ARBICORE_JWT_SECRET"] = _TEST_SECRET
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "wp_a_real_handler_verification")
# Keep import-time side effects inert for offline verification.
os.environ.setdefault("ARBICORE_LEGACY_AUTH_SEED", "0")
os.environ.setdefault("SIGNING_ACTIVE_KEY_VERSION", "")

# Import the real server module (heavy). Fail loudly if unavailable — do not
# fall back to a mirrored mini-app gate.
import server as srv  # noqa: E402
from services import auth as sauth  # noqa: E402


def _issue(
    user_id: str,
    username: str,
    *,
    secret: str = _TEST_SECRET,
    sv: int = 1,
    exp_delta: timedelta = timedelta(hours=1),
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    payload: Dict[str, Any] = {
        "sub": user_id,
        "username": username,
        "sv": sv,
        "type": "access",
        "exp": datetime.now(timezone.utc) + exp_delta,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, secret, algorithm="HS256")


def _request_with_cookie(token: Optional[str] = None,
                         authorization: Optional[str] = None) -> Request:
    headers = []
    if token:
        headers.append((b"cookie", f"access_token={token}".encode()))
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": ("127.0.0.1", 9),
        "server": ("test", 80),
        "root_path": "",
    }
    return Request(scope)


# ---------------------------------------------------------------------------
# Real ``_resolve_current_user``
# ---------------------------------------------------------------------------

class TestRealResolveCurrentUser:
    def test_module_symbols_are_server_implementations(self):
        assert srv._resolve_current_user.__module__ == "server"
        assert srv._require_admin_dep.__module__ == "server"
        assert srv.v2_settings_network_apply.__module__ == "server"
        assert srv.v2_settings_network_rollback.__module__ == "server"

    def test_missing_jwt_secret_fail_closed(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        token = _issue("a1", "admin")
        ctx = asyncio.run(srv._resolve_current_user(_request_with_cookie(token), None))
        assert ctx is None

    def test_short_jwt_secret_fail_closed(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "too-short")
        token = jwt.encode(
            {
                "sub": "a1",
                "username": "admin",
                "sv": 1,
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            "too-short",
            algorithm="HS256",
        )
        ctx = asyncio.run(srv._resolve_current_user(_request_with_cookie(token), None))
        assert ctx is None

    def test_forged_token_rejected(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)

        async def _boom(*_a, **_k):
            raise AssertionError("DB must not be consulted for forged signature")

        monkeypatch.setattr(sauth, "get_user_by_payload", _boom)
        forged = _issue("a1", "admin", secret="forged-secret-value-32chars-long!!")
        ctx = asyncio.run(srv._resolve_current_user(_request_with_cookie(forged), None))
        assert ctx is None

    def test_expired_token_rejected(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        expired = _issue("a1", "admin", exp_delta=timedelta(minutes=-10))
        ctx = asyncio.run(srv._resolve_current_user(_request_with_cookie(expired), None))
        assert ctx is None

    def test_valid_admin_session_resolved(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)

        async def _admin(_payload):
            return {
                "id": "a1",
                "username": "admin",
                "role": "admin",
                "session_version": 1,
                "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _admin)
        token = _issue("a1", "admin")
        ctx = asyncio.run(srv._resolve_current_user(_request_with_cookie(token), None))
        assert ctx is not None
        assert ctx["user_id"] == "a1"
        assert ctx["username"] == "admin"
        assert ctx["role"] == "admin"

    def test_role_from_db_not_token_claim(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)

        async def _op(_payload):
            return {
                "id": "op1",
                "username": "operator",
                "role": "operator",
                "session_version": 1,
                "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _op)
        token = _issue("op1", "operator", extra={"role": "admin"})
        ctx = asyncio.run(srv._resolve_current_user(_request_with_cookie(token), None))
        assert ctx is not None
        assert ctx["role"] == "operator"

    def test_legacy_bearer_rejected_via_resolver(self, monkeypatch):
        """Legacy Tree-B token (no type=access) must not authenticate via resolver."""
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setenv("ARBICORE_JWT_SECRET", _TEST_SECRET)
        from arbicore import auth as lauth

        legacy = lauth.issue_token({
            "user_id": "legacy-1",
            "username": "admin",
            "role": "admin",
        })
        authz = f"Bearer {legacy['token']}"
        ctx = asyncio.run(
            srv._resolve_current_user(
                _request_with_cookie(authorization=authz),
                authz,
            )
        )
        assert ctx is None


# ---------------------------------------------------------------------------
# Real network handlers + real ``_require_admin_dep``
# ---------------------------------------------------------------------------

class TestRealNetworkHandlers:
    def _app(self) -> FastAPI:
        """Mount the *actual* server handlers with the *actual* admin dep."""
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/settings/network/apply",
            srv.v2_settings_network_apply,
            methods=["POST"],
            dependencies=[Depends(srv._require_admin_dep)],
        )
        app.add_api_route(
            "/api/arbicore/settings/network/rollback",
            srv.v2_settings_network_rollback,
            methods=["POST"],
            dependencies=[Depends(srv._require_admin_dep)],
        )
        return app

    def _isolate_mutations(self, monkeypatch):
        """Harmless fixtures for post-auth side effects only."""
        counters = {"apply": 0, "rollback": 0, "env_sync": 0}

        async def fake_apply(**_kw):
            counters["apply"] += 1
            return {"revision": "r-test-1", "chains": {}}

        async def fake_rollback(**_kw):
            counters["rollback"] += 1
            return {"revision": "r-test-0", "chains": {}}

        async def fake_sync(_repo):
            counters["env_sync"] += 1
            return {"ARBICORE_RPC_URL": "isolated-test-value"}

        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(
                apply=AsyncMock(side_effect=fake_apply),
                rollback=AsyncMock(side_effect=fake_rollback),
            ),
        )
        # Handler looks up this name as a server-module global at runtime.
        monkeypatch.setattr(srv, "sync_env_from_network_config", fake_sync)
        monkeypatch.setattr(srv, "_PROVIDERS_AVAILABLE", False)
        return counters

    def test_unauthenticated_apply_401_no_env_sync(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_mutations(monkeypatch)
        client = TestClient(self._app())
        r = client.post("/api/arbicore/settings/network/apply", json={"reason": "x"})
        assert r.status_code == 401
        assert counters["apply"] == 0
        assert counters["env_sync"] == 0

    def test_operator_apply_403_no_env_sync(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_mutations(monkeypatch)

        async def _op(_payload):
            return {
                "id": "op1",
                "username": "operator",
                "role": "operator",
                "session_version": 1,
                "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _op)
        token = _issue("op1", "operator")
        client = TestClient(self._app())
        r = client.post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "x", "role": "admin"},
            cookies={"access_token": token},
        )
        assert r.status_code == 403, r.text
        assert counters["apply"] == 0
        assert counters["env_sync"] == 0

    def test_forged_admin_apply_401_no_env_sync(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_mutations(monkeypatch)
        forged = _issue("a1", "admin", secret="forged-secret-value-32chars-long!!")
        client = TestClient(self._app())
        r = client.post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "x"},
            cookies={"access_token": forged},
        )
        assert r.status_code == 401
        assert counters["apply"] == 0
        assert counters["env_sync"] == 0

    def test_admin_apply_invokes_handler_and_env_sync(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_mutations(monkeypatch)

        async def _admin(_payload):
            return {
                "id": "a1",
                "username": "admin",
                "role": "admin",
                "session_version": 1,
                "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _admin)
        token = _issue("a1", "admin")
        client = TestClient(self._app())
        r = client.post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "wp-a-real-handler"},
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("config", {}).get("revision") == "r-test-1"
        assert "ARBICORE_RPC_URL" in (body.get("env_synced") or [])
        assert counters["apply"] == 1
        assert counters["env_sync"] == 1

    def test_operator_rollback_403_no_env_sync(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_mutations(monkeypatch)

        async def _op(_payload):
            return {
                "id": "op1",
                "username": "operator",
                "role": "operator",
                "session_version": 1,
                "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _op)
        token = _issue("op1", "operator")
        client = TestClient(self._app())
        r = client.post(
            "/api/arbicore/settings/network/rollback",
            json={"reason": "x"},
            cookies={"access_token": token},
        )
        assert r.status_code == 403, r.text
        assert counters["rollback"] == 0
        assert counters["env_sync"] == 0

    def test_admin_rollback_invokes_handler_and_env_sync(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_mutations(monkeypatch)

        async def _admin(_payload):
            return {
                "id": "a1",
                "username": "admin",
                "role": "admin",
                "session_version": 1,
                "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _admin)
        token = _issue("a1", "admin")
        client = TestClient(self._app())
        r = client.post(
            "/api/arbicore/settings/network/rollback",
            json={"reason": "wp-a-real-handler"},
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("config", {}).get("revision") == "r-test-0"
        assert counters["rollback"] == 1
        assert counters["env_sync"] == 1

    def test_server_routes_still_declare_admin_dep(self):
        """Confirm production route table still wires the real admin dep."""
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        assert (
            '@api_router.post("/arbicore/settings/network/apply", '
            "dependencies=[Depends(_require_admin_dep)])"
        ) in text
        assert (
            '@api_router.post("/arbicore/settings/network/rollback", '
            "dependencies=[Depends(_require_admin_dep)])"
        ) in text
