"""Release-gate closure — route auth census, ladder LIVE hard-gate, redactor, JWT.

Synthetic credentials only. No production access.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_TEST_SECRET = "release-gate-jwt-secret-32chars-min!!"
os.environ["JWT_SECRET"] = _TEST_SECRET
os.environ["ARBICORE_JWT_SECRET"] = _TEST_SECRET
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "release_gate_closure_test")
os.environ.setdefault("ARBICORE_LEGACY_AUTH_SEED", "0")

import server as srv  # noqa: E402
from services import auth as sauth  # noqa: E402
from arbicore.control import OPERATOR_MODES  # noqa: E402
from arbicore.execution.mode import MODES  # noqa: E402

_PUBLIC_GET_PATHS = frozenset({
    "/",
    "/status",
    "/system/status",
    "/arbicore/version",
})

_SENSITIVE_SAMPLE = (
    "/api/arbicore/settings/telegram",
    "/api/arbicore/execution/secrets",
    "/api/arbicore/execution/wallets",
    "/api/arbicore/journal",
    "/api/arbicore/intelligence/weights/current",
    "/api/arbicore/execution/mode",
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


class TestModeEnumMapping:
    def test_ladder_and_control_enums_are_not_interchangeable(self):
        assert "FULL_LIVE" in MODES
        assert "FULL_AUTOMATION" in OPERATOR_MODES
        assert "FULL_LIVE" not in OPERATOR_MODES
        assert "FULL_AUTOMATION" not in MODES
        assert "OBSERVE" in MODES
        assert "OBSERVE" not in OPERATOR_MODES
        assert "PROFIT_ENGINE" in OPERATOR_MODES
        assert "PROFIT_ENGINE" not in MODES
        # Documented mapping constants in server
        assert srv._LADDER_TO_CONTROL_HARD_GATE["LIMITED_LIVE"] == "LIMITED_LIVE"
        assert srv._LADDER_TO_CONTROL_HARD_GATE["FULL_LIVE"] == "FULL_AUTOMATION"


class TestLadderLiveHardGate:
    def _app(self) -> FastAPI:
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/execution/mode/{strategy}",
            srv.v2_execution_mode_transition,
            methods=["POST"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        return app

    def test_limited_live_refused_no_repo_mutation(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        calls = {"n": 0}

        async def _boom(*_a, **_k):
            calls["n"] += 1
            raise AssertionError("transition must not be called for LIVE")

        monkeypatch.setattr(srv._EXECUTION_MODE_REPO, "transition", _boom)
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/mode/flash_loan_arbitrage",
            json={"to_mode": "LIMITED_LIVE", "reason": "bypass"},
            cookies={"access_token": _issue("op1", "operator")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("applied") is False
        assert body.get("decision", {}).get("allowed") is False
        assert "LIMITED_LIVE" in (body.get("error") or "")
        assert calls["n"] == 0

    def test_full_live_refused_maps_to_full_automation_analog(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv._EXECUTION_MODE_REPO,
            "transition",
            AsyncMock(side_effect=AssertionError("no transition")),
        )
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/mode/flash_loan_arbitrage",
            json={"to_mode": "FULL_LIVE", "reason": "bypass"},
            cookies={"access_token": _issue("op1", "operator")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("applied") is False
        assert body["decision"]["control_mode_analog"] == "FULL_AUTOMATION"
        assert body["decision"]["allowed"] is False

    def test_anonymous_mode_transition_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/mode/flash_loan_arbitrage",
            json={"to_mode": "PAPER"},
        )
        assert r.status_code == 401


class TestRouteCensus:
    def test_every_non_public_api_router_get_is_protected(self):
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        unauth = []
        for m in re.finditer(
            r"@api_router\.get\((.*?)\)\s*\nasync def (\w+)", text, re.S
        ):
            args, name = m.group(1), m.group(2)
            pm = re.search(r'["\']([^"\']+)["\']', args)
            path = pm.group(1) if pm else "?"
            prot = (
                "_require_operator_dep" in args or "_require_admin_dep" in args
            )
            if not prot and path not in _PUBLIC_GET_PATHS:
                unauth.append((path, name))
        assert unauth == [], f"unprotected GETs outside public allowlist: {unauth}"

    def test_public_allowlist_exactly(self):
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        public = []
        for m in re.finditer(
            r"@api_router\.get\((.*?)\)\s*\nasync def (\w+)", text, re.S
        ):
            args = m.group(1)
            pm = re.search(r'["\']([^"\']+)["\']', args)
            path = pm.group(1) if pm else "?"
            prot = (
                "_require_operator_dep" in args or "_require_admin_dep" in args
            )
            if not prot:
                public.append(path)
        assert set(public) == _PUBLIC_GET_PATHS

    def test_app_get_arbicore_all_protected(self):
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        unauth = []
        for m in re.finditer(
            r"@app\.get\((.*?)\)\s*\nasync def (\w+)", text, re.S
        ):
            args, name = m.group(1), m.group(2)
            if "arbicore" not in args:
                continue
            if "_require_operator_dep" not in args and "_require_admin_dep" not in args:
                unauth.append(name)
        assert unauth == []


class TestSensitiveGetAuth:
    def _mount(self, path: str, handler) -> FastAPI:
        app = FastAPI()
        app.add_api_route(
            path,
            handler,
            methods=["GET"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        return app

    @pytest.mark.parametrize("path,handler_name", [
        ("/api/arbicore/settings/telegram", "v2_settings_telegram"),
        ("/api/arbicore/execution/secrets", "v2_execution_secrets"),
        ("/api/arbicore/journal/summary", "v2_journal_summary"),
        ("/api/arbicore/execution/mode", "v2_execution_mode"),
    ])
    def test_anonymous_401(self, monkeypatch, path, handler_name):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        handler = getattr(srv, handler_name)
        # Stub IO so auth failure is the only gate of interest
        monkeypatch.setattr(
            srv, "_TELEGRAM",
            MagicMock(get_settings=AsyncMock(return_value={})),
        )
        monkeypatch.setattr(
            srv, "_SECRET_REGISTRY",
            MagicMock(list_handles=AsyncMock(return_value=[]), status={}),
        )
        monkeypatch.setattr(
            srv, "_OPPORTUNITY_JOURNAL",
            MagicMock(summary=AsyncMock(return_value={})),
        )
        monkeypatch.setattr(
            srv, "_EXECUTION_MODE_REPO",
            MagicMock(list_all=AsyncMock(return_value=[])),
        )
        r = TestClient(self._mount(path, handler)).get(path)
        assert r.status_code == 401

    def test_forged_token_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv, "_TELEGRAM",
            MagicMock(get_settings=AsyncMock(return_value={})),
        )
        forged = _issue("a1", "admin", secret="forged-secret-value-32chars-long!!")
        r = TestClient(
            self._mount("/api/arbicore/settings/telegram", srv.v2_settings_telegram)
        ).get(
            "/api/arbicore/settings/telegram",
            cookies={"access_token": forged},
        )
        assert r.status_code == 401

    def test_operator_200(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        monkeypatch.setattr(
            srv, "_TELEGRAM",
            MagicMock(get_settings=AsyncMock(return_value={"enabled": False})),
        )
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        r = TestClient(
            self._mount("/api/arbicore/settings/telegram", srv.v2_settings_telegram)
        ).get(
            "/api/arbicore/settings/telegram",
            cookies={"access_token": _issue("op1", "operator")},
        )
        assert r.status_code == 200, r.text


class TestRedactorEdgeCases:
    def test_tuple_passthrough_fixed(self):
        synth = "https://base-mainnet.g.alchemy.com/v2/SYNTHETIC_RELEASE_GATE_KEY_99"
        out = srv._redact_network_payload(({"rpc": synth}, synth))
        flat = str(out)
        assert "SYNTHETIC_RELEASE_GATE_KEY_99" not in flat
        assert "[REDACTED]" in flat

    def test_wss_scheme_redacted(self):
        from arbicore.log_redaction import redact_credential_url
        synth = "wss://base-mainnet.g.alchemy.com/v2/SYNTHETIC_WSS_KEY_NOT_REAL"
        out = redact_credential_url(synth)
        assert "SYNTHETIC_WSS_KEY_NOT_REAL" not in out
        assert "[REDACTED]" in out

    def test_embedded_wss_in_text(self):
        from arbicore.log_redaction import redact_credential_url
        text = "rpc=wss://h.example/v2/SYNTHETIC_EMBED_KEY_ABC12345 done"
        out = redact_credential_url(text)
        assert "SYNTHETIC_EMBED_KEY_ABC12345" not in out


class TestJwtRuntimeNoSecretLeak:
    def test_missing_secret_fail_closed_boolean_only(self, monkeypatch):
        monkeypatch.delenv("JWT_SECRET", raising=False)
        from services import auth as a
        with pytest.raises(a.AuthSecretError) as ei:
            a._secret()
        msg = str(ei.value)
        assert "JWT_SECRET" in msg
        # Must not echo any secret material — only the requirement.
        assert "release-gate" not in msg.lower()
        assert len(msg) < 200

    def test_short_secret_fail_closed(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "too-short")
        from services import auth as a
        with pytest.raises(a.AuthSecretError):
            a._secret()
