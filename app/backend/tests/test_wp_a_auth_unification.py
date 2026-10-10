"""WP-A Authentication Unification — offline regression tests.

Covers F-AUTH-01 (JWT fail-closed / no legacy bearer) and F-AUTH-02
(admin-only network apply/rollback; no unauthorized env hot-load).

These tests exercise the real ``services.auth`` resolver and JWT codec.
They do **not** monkeypatch ``get_current_user`` / ``_resolve_current_user``.
No production RPC, deploy, signing, or broadcast.
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import jwt
import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Ensure a valid secret for modules that import at collection time.
# MONGO_URL is required by services.db at import; tests never contact it
# (get_user_by_payload is stubbed where a DB row would be needed).
_TEST_SECRET = "wp-a-test-jwt-secret-32chars-minimum!!"
os.environ.setdefault("JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("ARBICORE_JWT_SECRET", _TEST_SECRET)
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "wp_a_auth_unification_test")


# ---------------------------------------------------------------------------
# F-AUTH-01 — secret fail-closed + forged/expired/revoked tokens
# ---------------------------------------------------------------------------

class TestJwtSecretFailClosed:
    def test_canonical_secret_rejects_missing(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        from services import auth as sauth
        with pytest.raises(sauth.AuthSecretError):
            sauth._secret()

    def test_canonical_secret_rejects_short(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "too-short")
        from services import auth as sauth
        with pytest.raises(sauth.AuthSecretError):
            sauth._secret()

    def test_legacy_module_secret_rejects_missing(self, monkeypatch):
        monkeypatch.delenv("ARBICORE_JWT_SECRET", raising=False)
        from arbicore import auth as lauth
        with pytest.raises(lauth.AuthSecretError):
            lauth._jwt_secret()

    def test_legacy_module_no_mongo_url_fallback(self, monkeypatch):
        """Predictable sha256(MONGO_URL) fallback must not exist."""
        monkeypatch.delenv("ARBICORE_JWT_SECRET", raising=False)
        monkeypatch.setenv("MONGO_URL", "mongodb://predictable-seed")
        from arbicore import auth as lauth
        with pytest.raises(lauth.AuthSecretError):
            lauth._jwt_secret()
        # Body after docstring must not hash MONGO_URL into a secret.
        import inspect
        src = inspect.getsource(lauth._jwt_secret)
        body = src.split('"""')[-1]
        assert "hashlib" not in body
        assert "MONGO_URL" not in body
        assert "encode()" not in body or "raise AuthSecretError" in body


class TestCanonicalTokenPath:
    def test_forged_admin_token_rejected(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        from services import auth as sauth

        forged = jwt.encode(
            {
                "sub": "attacker",
                "username": "admin",
                "sv": 1,
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            "different-forged-secret-32chars-long!!",
            algorithm="HS256",
        )

        class _Req:
            cookies = {"access_token": forged}
            headers = {}

        async def _boom(*_a, **_k):
            raise AssertionError("DB must not be consulted for invalid signature")

        monkeypatch.setattr(sauth, "get_user_by_payload", _boom)
        with pytest.raises(HTTPException) as ei:
            asyncio.run(sauth.get_current_user(_Req()))  # type: ignore[arg-type]
        assert ei.value.status_code == 401

    def test_expired_token_rejected(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        from services import auth as sauth

        expired = jwt.encode(
            {
                "sub": "u1",
                "username": "admin",
                "sv": 1,
                "type": "access",
                "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
            },
            _TEST_SECRET,
            algorithm="HS256",
        )

        class _Req:
            cookies = {"access_token": expired}
            headers = {}

        with pytest.raises(HTTPException) as ei:
            asyncio.run(sauth.get_current_user(_Req()))  # type: ignore[arg-type]
        assert ei.value.status_code == 401
        assert "expired" in ei.value.detail.lower()

    def test_revoked_session_rejected(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        from services import auth as sauth

        token = jwt.encode(
            {
                "sub": "u1",
                "username": "admin",
                "sv": 1,
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            _TEST_SECRET,
            algorithm="HS256",
        )

        async def _revoked(payload):
            raise HTTPException(status_code=401, detail="Session revoked")

        monkeypatch.setattr(sauth, "get_user_by_payload", _revoked)

        class _Req:
            cookies = {"access_token": token}
            headers = {}

        with pytest.raises(HTTPException) as ei:
            asyncio.run(sauth.get_current_user(_Req()))  # type: ignore[arg-type]
        assert ei.value.status_code == 401
        assert "revoked" in ei.value.detail.lower()

    def test_role_taken_from_db_not_token_claim(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        from services import auth as sauth

        # Token claims admin; DB says operator — DB wins.
        token = jwt.encode(
            {
                "sub": "u-op",
                "username": "operator",
                "sv": 1,
                "type": "access",
                "role": "admin",  # unverified claim — must be ignored
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            _TEST_SECRET,
            algorithm="HS256",
        )

        async def _db_user(payload):
            assert payload.get("sub") == "u-op"
            return {
                "id": "u-op",
                "username": "operator",
                "role": "operator",
                "session_version": 1,
                "created_at": "2026-01-01T00:00:00Z",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _db_user)

        class _Req:
            cookies = {"access_token": token}
            headers = {}

        user = asyncio.run(sauth.get_current_user(_Req()))  # type: ignore[arg-type]
        assert user["role"] == "operator"

    def test_malformed_token_rejected(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        from services import auth as sauth

        class _Req:
            cookies = {"access_token": "not-a-jwt"}
            headers = {}

        with pytest.raises(HTTPException) as ei:
            asyncio.run(sauth.get_current_user(_Req()))  # type: ignore[arg-type]
        assert ei.value.status_code == 401


class TestLegacyBearerRemoved:
    def test_canonical_rejects_legacy_arbicore_auth_token(self, monkeypatch):
        """Legacy Tree-B token shape (no type=access) must not authenticate."""
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setenv("ARBICORE_JWT_SECRET", _TEST_SECRET)
        from arbicore import auth as lauth
        from services import auth as sauth

        legacy = lauth.issue_token({
            "user_id": "legacy-1",
            "username": "admin",
            "role": "admin",
        })
        legacy_jwt = legacy["token"]

        class _Req:
            cookies = {}
            headers = {"Authorization": f"Bearer {legacy_jwt}"}

        with pytest.raises(HTTPException) as ei:
            asyncio.run(sauth.get_current_user(_Req()))  # type: ignore[arg-type]
        assert ei.value.status_code == 401

    def test_server_resolver_source_has_no_legacy_decode(self):
        """Static check: `_resolve_current_user` no longer calls legacy decode."""
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        # Isolate the WP-A resolver function body.
        start = text.index("async def _resolve_current_user(")
        end = text.index("\n# ---------------------------------------------------------------------------\n# v2.9.3 — Legacy Tree-B", start)
        body = text[start:end]
        assert "_auth_decode_token" not in body
        assert "is_session_revoked" not in body
        assert "services.auth" in body or "services import auth" in body
        assert "get_current_user" in body


# ---------------------------------------------------------------------------
# F-AUTH-02 — network apply/rollback authorization + no partial env mutate
# ---------------------------------------------------------------------------

class TestNetworkConfigAuthz:
    def _mini_app(self, monkeypatch):
        """Minimal app using the *real* services.auth resolver (not monkeypatched).

        Mirrors server._require_admin_dep / network apply env-sync gating without
        importing the full server module (heavy optional deps).
        """
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        from services import auth as sauth
        from fastapi import APIRouter, Depends, Header
        from typing import Optional, Dict, Any

        app = FastAPI()
        applied = {"count": 0, "env_sync": 0}

        async def require_operator(
            request: Request,
            authorization: Optional[str] = Header(default=None),
        ) -> Dict[str, Any]:
            _ = authorization
            user = await sauth.get_current_user(request)
            return {
                "user_id": user.get("id"),
                "username": user.get("username"),
                "role": user.get("role"),
            }

        async def require_admin(
            request: Request,
            authorization: Optional[str] = Header(default=None),
        ) -> Dict[str, Any]:
            ctx = await require_operator(request, authorization)
            if ctx.get("role") != "admin":
                raise HTTPException(status_code=403, detail="admin_only")
            return ctx

        r = APIRouter()

        @r.post("/arbicore/settings/network/apply",
                dependencies=[Depends(require_admin)])
        async def apply(body: Optional[Dict[str, Any]] = None):
            applied["count"] += 1
            applied["env_sync"] += 1
            return {"ok": True, "config": {"revision": "r1"},
                    "env_synced": ["ARBICORE_RPC_URL"]}

        @r.post("/arbicore/settings/network/rollback",
                dependencies=[Depends(require_admin)])
        async def rollback(body: Optional[Dict[str, Any]] = None):
            applied["count"] += 1
            applied["env_sync"] += 1
            return {"ok": True, "config": {"revision": "r0"},
                    "env_synced": ["ARBICORE_RPC_URL"]}

        app.include_router(r, prefix="/api")

        # Prove server.py wires admin dep on these routes (static).
        srv = (BACKEND / "server.py").read_text(encoding="utf-8")
        assert 'network/apply", dependencies=[Depends(_require_admin_dep)]' in srv
        assert 'network/rollback", dependencies=[Depends(_require_admin_dep)]' in srv
        return app, applied

    def _issue(self, user_id: str, username: str, role: str, secret: str = _TEST_SECRET,
               sv: int = 1, exp_delta: timedelta = timedelta(hours=1)) -> str:
        return jwt.encode(
            {
                "sub": user_id,
                "username": username,
                "sv": sv,
                "type": "access",
                "exp": datetime.now(timezone.utc) + exp_delta,
            },
            secret,
            algorithm="HS256",
        )

    def test_unauthenticated_apply_401_no_mutation(self, monkeypatch):
        app, applied = self._mini_app(monkeypatch)
        client = TestClient(app)
        r = client.post("/api/arbicore/settings/network/apply", json={"reason": "x"})
        assert r.status_code == 401
        assert applied["count"] == 0
        assert applied["env_sync"] == 0

    def test_operator_apply_403_no_mutation(self, monkeypatch):
        app, applied = self._mini_app(monkeypatch)
        from services import auth as sauth

        async def _op(_payload):
            return {
                "id": "op1", "username": "operator", "role": "operator",
                "session_version": 1, "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _op)
        token = self._issue("op1", "operator", "operator")
        client = TestClient(app)
        r = client.post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "x", "role": "admin"},  # body role must be ignored
            cookies={"access_token": token},
        )
        assert r.status_code == 403, r.text
        assert applied["count"] == 0
        assert applied["env_sync"] == 0

    def test_admin_apply_ok_syncs_env(self, monkeypatch):
        app, applied = self._mini_app(monkeypatch)
        from services import auth as sauth

        async def _admin(_payload):
            return {
                "id": "a1", "username": "admin", "role": "admin",
                "session_version": 1, "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _admin)
        token = self._issue("a1", "admin", "admin")
        client = TestClient(app)
        r = client.post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "wp-a"},
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert applied["count"] == 1
        assert applied["env_sync"] == 1

    def test_forged_token_apply_401_no_mutation(self, monkeypatch):
        app, applied = self._mini_app(monkeypatch)
        forged = self._issue("a1", "admin", "admin",
                             secret="forged-secret-value-32chars-long!!")
        client = TestClient(app)
        r = client.post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "x"},
            cookies={"access_token": forged},
        )
        assert r.status_code == 401
        assert applied["count"] == 0
        assert applied["env_sync"] == 0

    def test_operator_rollback_403_no_mutation(self, monkeypatch):
        app, applied = self._mini_app(monkeypatch)
        from services import auth as sauth

        async def _op(_payload):
            return {
                "id": "op1", "username": "operator", "role": "operator",
                "session_version": 1, "created_at": "t",
            }

        monkeypatch.setattr(sauth, "get_user_by_payload", _op)
        token = self._issue("op1", "operator", "operator")
        client = TestClient(app)
        r = client.post(
            "/api/arbicore/settings/network/rollback",
            json={"reason": "x"},
            cookies={"access_token": token},
        )
        assert r.status_code == 403
        assert applied["count"] == 0
        assert applied["env_sync"] == 0
