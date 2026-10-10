"""Emergency fix — config/history auth + RPC credential redaction.

Covers Emergent Handoff-2 finding: anonymous GET
``/api/arbicore/settings/config/history`` leaked raw ``rpc_urls``.

Also regresses network validate/draft/apply/rollback response redaction.
Synthetic credentials only. No production access.
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

_TEST_SECRET = "wp-ab-cfghist-jwt-secret-32chars-min!!"
os.environ["JWT_SECRET"] = _TEST_SECRET
os.environ["ARBICORE_JWT_SECRET"] = _TEST_SECRET
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "wp_ab_config_history_redact_test")
os.environ.setdefault("ARBICORE_LEGACY_AUTH_SEED", "0")
os.environ.setdefault("SIGNING_ACTIVE_KEY_VERSION", "")

import server as srv  # noqa: E402
from services import auth as sauth  # noqa: E402

_SYNTH = (
    "https://base-mainnet.g.alchemy.com/v2/SYNTHETIC_CFGHIST_KEY_NOT_REAL_77"
)
_SYNTH_MARKER = "SYNTHETIC_CFGHIST_KEY_NOT_REAL_77"


def _issue(user_id: str, username: str) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "username": username,
            "sv": 1,
            "type": "access",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        _TEST_SECRET,
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


def _assert_no_synth(text: str):
    assert _SYNTH_MARKER not in text, f"synthetic credential leaked: {text[:300]}"


class TestConfigHistoryAuthAndRedaction:
    def _app(self) -> FastAPI:
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/settings/config/history",
            srv.v2_config_history,
            methods=["GET"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        return app

    def _history_items(self):
        return [
            {
                "kind": "network",
                "revision": "n1",
                "snapshot": {
                    "rpc_urls": {"base": [_SYNTH]},
                    "chains": {"base": {"enabled": True}},
                },
            },
            {
                "kind": "telegram",
                "revision": "t1",
                "snapshot": {"enabled": False, "chat_id": "123"},
            },
            {
                # Nested network-like payload under a non-network kind label
                "kind": "operational",
                "revision": "o1",
                "config": {"rpc_urls": {"base": [_SYNTH]}},
            },
        ]

    def test_server_route_requires_operator_and_redacts(self):
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        # Multi-line decorator as shipped in this fix.
        assert (
            '@api_router.get("/arbicore/settings/config/history",\n'
            "                dependencies=[Depends(_require_operator_dep)])"
        ) in text
        start = text.index("async def v2_config_history")
        body = text[start:start + 800]
        assert "_redact_network_payload(items)" in body

    def test_anonymous_config_history_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_CONFIG_REPO",
            MagicMock(
                all_history=AsyncMock(return_value=self._history_items()),
                history=AsyncMock(return_value=self._history_items()),
            ),
        )
        r = TestClient(self._app()).get("/api/arbicore/settings/config/history")
        assert r.status_code == 401
        _assert_no_synth(r.text)

    def test_forged_token_config_history_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_CONFIG_REPO",
            MagicMock(all_history=AsyncMock(return_value=self._history_items())),
        )
        forged = jwt.encode(
            {
                "sub": "a1",
                "username": "admin",
                "sv": 1,
                "type": "access",
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            "forged-secret-value-32chars-long!!",
            algorithm="HS256",
        )
        r = TestClient(self._app()).get(
            "/api/arbicore/settings/config/history",
            cookies={"access_token": forged},
        )
        assert r.status_code == 401
        _assert_no_synth(r.text)

    def test_operator_config_history_redacts_network_and_nested(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv,
            "_CONFIG_REPO",
            MagicMock(
                all_history=AsyncMock(return_value=self._history_items()),
                history=AsyncMock(return_value=self._history_items()[:1]),
            ),
        )
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        token = _issue("op1", "operator")
        client = TestClient(self._app())

        r = client.get(
            "/api/arbicore/settings/config/history",
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        _assert_no_synth(r.text)
        assert "[REDACTED]" in r.text
        body = r.json()
        assert body["count"] == 3
        # Non-network telegram record still present (not dropped)
        kinds = {i.get("kind") for i in body["items"]}
        assert "telegram" in kinds
        assert "network" in kinds

        r2 = client.get(
            "/api/arbicore/settings/config/history",
            params={"kind": "network"},
            cookies={"access_token": token},
        )
        assert r2.status_code == 200, r2.text
        _assert_no_synth(r2.text)
        assert "[REDACTED]" in r2.text


class TestNetworkMutationResponseRedaction:
    def _app(self) -> FastAPI:
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/settings/network/validate",
            srv.v2_settings_network_validate,
            methods=["POST"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        app.add_api_route(
            "/api/arbicore/settings/network/draft",
            srv.v2_settings_network_draft,
            methods=["POST"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
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

    def _wire_repo(self, monkeypatch):
        cfg = {"revision": "r1", "rpc_urls": {"base": [_SYNTH]}}

        async def fake_sync(_repo):
            return {"ARBICORE_RPC_URL": "marker"}

        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(
                validate=MagicMock(
                    return_value={
                        "ok": False,
                        "errors": [f"bad rpc {_SYNTH}"],
                        "normalized": {"rpc_urls": {"base": [_SYNTH]}},
                    }
                ),
                save_draft=AsyncMock(return_value={"rpc_urls": {"base": [_SYNTH]}}),
                apply=AsyncMock(return_value=cfg),
                rollback=AsyncMock(return_value=cfg),
            ),
        )
        monkeypatch.setattr(srv, "sync_env_from_network_config", fake_sync)
        monkeypatch.setattr(srv, "_PROVIDERS_AVAILABLE", False)

    def test_validate_error_redacts(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        self._wire_repo(monkeypatch)
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        r = TestClient(self._app()).post(
            "/api/arbicore/settings/network/validate",
            json={"rpc_urls": {"base": [_SYNTH]}},
            cookies={"access_token": _issue("op1", "operator")},
        )
        assert r.status_code == 200, r.text
        _assert_no_synth(r.text)
        assert "[REDACTED]" in r.text

    def test_draft_redacts(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        self._wire_repo(monkeypatch)
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        r = TestClient(self._app()).post(
            "/api/arbicore/settings/network/draft",
            json={"rpc_urls": {"base": [_SYNTH]}},
            cookies={"access_token": _issue("op1", "operator")},
        )
        assert r.status_code == 200, r.text
        _assert_no_synth(r.text)

    def test_apply_rollback_redact(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        self._wire_repo(monkeypatch)
        _stub_user(monkeypatch, user_id="a1", username="admin", role="admin")
        tok = _issue("a1", "admin")
        client = TestClient(self._app())
        r = client.post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "t", "patch": {"rpc_urls": {"base": [_SYNTH]}}},
            cookies={"access_token": tok},
        )
        assert r.status_code == 200, r.text
        _assert_no_synth(r.text)
        r2 = client.post(
            "/api/arbicore/settings/network/rollback",
            json={"reason": "t"},
            cookies={"access_token": tok},
        )
        assert r2.status_code == 200, r2.text
        _assert_no_synth(r2.text)

    def test_apply_validation_error_redacts(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        self._wire_repo(monkeypatch)
        monkeypatch.setattr(
            srv,
            "_NETWORK_CONFIG",
            MagicMock(
                apply=AsyncMock(side_effect=ValueError(f"invalid rpc {_SYNTH}")),
            ),
        )
        _stub_user(monkeypatch, user_id="a1", username="admin", role="admin")
        r = TestClient(self._app()).post(
            "/api/arbicore/settings/network/apply",
            json={"reason": "t"},
            cookies={"access_token": _issue("a1", "admin")},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is False
        _assert_no_synth(r.text)
        assert "[REDACTED]" in r.text
