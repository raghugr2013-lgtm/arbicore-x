"""Emergency Auth Reconciliation — WP-A finalization gaps.

Covers Emergent Handoff-1 residual surfaces that WP-A/WP-B left open:
  * unauthenticated network GET / history disclosure
  * RPC URL credential redaction in network responses
  * control-center mode-transition readiness gate (server-enforced)

Preserves real ``server`` handlers + WP-A resolver. No production access.
"""
from __future__ import annotations

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

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_TEST_SECRET = "wp-a-final-jwt-secret-32chars-minimum!!"
os.environ["JWT_SECRET"] = _TEST_SECRET
os.environ["ARBICORE_JWT_SECRET"] = _TEST_SECRET
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "wp_a_emergency_auth_finalization")
os.environ.setdefault("ARBICORE_LEGACY_AUTH_SEED", "0")
os.environ.setdefault("SIGNING_ACTIVE_KEY_VERSION", "")

import server as srv  # noqa: E402
from services import auth as sauth  # noqa: E402

# Synthetic URL used only in fixtures — must never appear unredacted in output.
_SENSITIVE_RPC = (
    "https://base-mainnet.g.alchemy.com/v2/SYNTHETIC_TEST_KEY_NOT_REAL_0001"
)


def _issue(user_id: str, username: str, *, secret: str = _TEST_SECRET) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "username": username,
            "sv": 1,
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        secret,
        algorithm="HS256",
    )


def _stub_user(monkeypatch, *, user_id: str, username: str, role: str):
    async def _user(_payload):
        return {
            "id": user_id,
            "username": username,
            "role": role,
            "session_version": 1,
            "created_at": "t",
        }

    monkeypatch.setattr(sauth, "get_user_by_payload", _user)


class TestLegacyBearerInventory:
    def test_no_legacy_decode_call_sites_in_server(self):
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        # Import aliases may remain dead; runtime invocations must not.
        assert "_auth_decode_token(" not in text
        assert "_auth_issue_token(" not in text
        body_start = text.index("async def _resolve_current_user(")
        body_end = text.index(
            "\n# ---------------------------------------------------------------------------\n"
            "# v2.9.3 — Legacy Tree-B",
            body_start,
        )
        resolver = text[body_start:body_end]
        assert "get_current_user" in resolver
        assert "_auth_decode_token" not in resolver

    def test_no_mongo_derived_jwt_fallback(self):
        from arbicore import auth as lauth
        import inspect
        src = inspect.getsource(lauth._jwt_secret)
        body = src.split('"""')[-1]
        assert "hashlib" not in body
        assert "MONGO_URL" not in body


class TestNetworkGetAuthAndRedaction:
    def _app(self) -> FastAPI:
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/settings/network",
            srv.v2_settings_network,
            methods=["GET"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        app.add_api_route(
            "/api/arbicore/settings/network/history",
            srv.v2_settings_network_history,
            methods=["GET"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        return app

    def _fixture_config(self) -> Dict[str, Any]:
        return {
            "revision": "r1",
            "rpc_urls": {"base": [_SENSITIVE_RPC]},
            "chains": {"base": {"enabled": True}},
        }

    def test_server_routes_require_operator(self):
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        assert (
            '@api_router.get("/arbicore/settings/network", '
            "dependencies=[Depends(_require_operator_dep)])"
        ) in text
        assert (
            '@api_router.get("/arbicore/settings/network/history", '
            "dependencies=[Depends(_require_operator_dep)])"
        ) in text

    def test_unauthenticated_network_get_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(
                get=AsyncMock(return_value=self._fixture_config()),
                get_draft=AsyncMock(return_value=None),
            ),
        )
        r = TestClient(self._app()).get("/api/arbicore/settings/network")
        assert r.status_code == 401

    def test_forged_token_network_get_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(
                get=AsyncMock(return_value=self._fixture_config()),
                get_draft=AsyncMock(return_value=None),
            ),
        )
        forged = _issue("a1", "admin", secret="forged-secret-value-32chars-long!!")
        r = TestClient(self._app()).get(
            "/api/arbicore/settings/network",
            cookies={"access_token": forged},
        )
        assert r.status_code == 401

    def test_operator_network_get_redacts_rpc_credentials(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(
                get=AsyncMock(return_value=self._fixture_config()),
                get_draft=AsyncMock(return_value={"rpc_urls": {"base": [_SENSITIVE_RPC]}}),
            ),
        )
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        token = _issue("op1", "operator")
        r = TestClient(self._app()).get(
            "/api/arbicore/settings/network",
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        text = r.text
        assert "SYNTHETIC_TEST_KEY_NOT_REAL_0001" not in text
        assert "[REDACTED]" in text
        body = r.json()
        assert body["config"]["rpc_urls"]["base"][0].endswith("/v2/[REDACTED]") or \
            "[REDACTED]" in body["config"]["rpc_urls"]["base"][0]

    def test_unauthenticated_history_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(history=AsyncMock(return_value=[{"rpc_urls": {"base": [_SENSITIVE_RPC]}}])),
        )
        r = TestClient(self._app()).get("/api/arbicore/settings/network/history")
        assert r.status_code == 401

    def test_operator_history_redacts_rpc_credentials(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(history=AsyncMock(return_value=[
                {"revision": "r0", "rpc_urls": {"base": [_SENSITIVE_RPC]}},
            ])),
        )
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        token = _issue("op1", "operator")
        r = TestClient(self._app()).get(
            "/api/arbicore/settings/network/history",
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        assert "SYNTHETIC_TEST_KEY_NOT_REAL_0001" not in r.text
        assert "[REDACTED]" in r.text


class TestModeTransitionReadinessGate:
    def _app(self) -> FastAPI:
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/control/mode",
            srv.v2_control_set_mode,
            methods=["POST"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        return app

    def test_limited_live_refused_server_side(self, monkeypatch):
        """Handler must consult readiness and refuse without mutating mode."""
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        set_calls = {"n": 0}
        gate_calls = {"n": 0}

        async def _fake_set(*_a, **_k):
            set_calls["n"] += 1

        async def _fake_get():
            return "SHADOW"

        async def _refuse(target: str):
            gate_calls["n"] += 1
            return {
                "allowed": False,
                "reason": f"{target} is hard-gated and blocked in this build",
                "target_mode": target,
                "blockers": ["hard-gated"],
            }

        monkeypatch.setattr(srv._CONTROL_STATE_REPO, "set_mode", _fake_set)
        monkeypatch.setattr(srv._CONTROL_STATE_REPO, "get_mode", _fake_get)
        # Isolate from live Mongo: stub the readiness decision, prove handler
        # honors allowed=False (same contract as ExecutionReadinessEngine).
        monkeypatch.setattr(srv._READINESS_ENGINE, "can_transition", _refuse)
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        token = _issue("op1", "operator")
        r = TestClient(self._app()).post(
            "/api/arbicore/control/mode",
            json={"mode": "LIMITED_LIVE", "reason": "bypass-attempt"},
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("applied") is False
        assert body.get("decision", {}).get("allowed") is False
        assert gate_calls["n"] == 1
        assert set_calls["n"] == 0

    def test_unauthenticated_mode_change_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        r = TestClient(self._app()).post(
            "/api/arbicore/control/mode",
            json={"mode": "SHADOW"},
        )
        assert r.status_code == 401

    def test_can_transition_hard_gates_live_modes(self):
        """Engine-level invariant with offline fakes — LIMITED_LIVE refused."""
        import asyncio
        from arbicore.control.readiness import ExecutionReadinessEngine

        class _KS:
            async def state(self):
                class S:
                    engaged = False
                return S()

        class _Wallets:
            async def list_all(self, chain=None, execution_role=None):
                return []

        eng = ExecutionReadinessEngine(
            db=None, kill_switch=_KS(), wallet_registry=_Wallets(),
        )
        d = asyncio.run(eng.can_transition("LIMITED_LIVE"))
        assert d["allowed"] is False
        d2 = asyncio.run(eng.can_transition("FULL_AUTOMATION"))
        assert d2["allowed"] is False