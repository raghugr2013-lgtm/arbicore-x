"""WP-B / F-AUTH-03 — kill-switch disengage authorization hardening.

Exercises the real ``server`` handlers and real ``_require_admin_dep`` /
``_resolve_current_user`` path. Authorization is never mocked to force a
pass. Post-auth persistence is isolated with harmless fixtures.
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
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_TEST_SECRET = "wp-b-kill-switch-jwt-secret-32chars!!"
os.environ["JWT_SECRET"] = _TEST_SECRET
os.environ["ARBICORE_JWT_SECRET"] = _TEST_SECRET
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "wp_b_kill_switch_auth_test")
os.environ.setdefault("ARBICORE_LEGACY_AUTH_SEED", "0")
os.environ.setdefault("SIGNING_ACTIVE_KEY_VERSION", "")

import server as srv  # noqa: E402
from services import auth as sauth  # noqa: E402


def _issue(
    user_id: str,
    username: str,
    *,
    secret: str = _TEST_SECRET,
    sv: int = 1,
    exp_delta: timedelta = timedelta(hours=1),
) -> str:
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


# ---------------------------------------------------------------------------
# Execution kill-switch disengage (persistent store) — real handler + admin dep
# ---------------------------------------------------------------------------

class TestExecutionKillSwitchDisengage:
    def _app(self) -> FastAPI:
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/execution/kill-switch/disengage",
            srv.v2_execution_kill_switch_disengage,
            methods=["POST"],
            dependencies=[Depends(srv._require_admin_dep)],
        )
        app.add_api_route(
            "/api/arbicore/execution/kill-switch/engage",
            srv.v2_execution_kill_switch_engage,
            methods=["POST"],
            dependencies=[Depends(srv._require_operator_dep)],
        )
        return app

    def _isolate_repo(self, monkeypatch):
        counters = {
            "disengage": 0,
            "engage": 0,
            "disengage_actors": [],
            "audit_fail": False,
        }

        async def fake_disengage(*, reason: str, actor: str = "operator"):
            if counters["audit_fail"]:
                raise RuntimeError("audit_write_failed")
            counters["disengage"] += 1
            counters["disengage_actors"].append(actor)
            return MagicMock(
                to_dict=lambda: {
                    "engaged": False,
                    "reason": None,
                    "actor": None,
                    "last_disengaged_at": "t",
                }
            )

        async def fake_engage(*, reason: str, actor: str = "operator"):
            counters["engage"] += 1
            return MagicMock(
                to_dict=lambda: {
                    "engaged": True,
                    "reason": reason,
                    "actor": actor,
                    "engaged_at": "t",
                }
            )

        monkeypatch.setattr(
            srv,
            "_KILL_SWITCH_REPO",
            MagicMock(
                disengage=AsyncMock(side_effect=fake_disengage),
                engage=AsyncMock(side_effect=fake_engage),
            ),
        )
        return counters

    def test_symbols_are_server_implementations(self):
        assert srv.v2_execution_kill_switch_disengage.__module__ == "server"
        assert srv._require_admin_dep.__module__ == "server"
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        assert (
            '@api_router.post("/arbicore/execution/kill-switch/disengage", '
            "dependencies=[Depends(_require_admin_dep)])"
        ) in text
        # Engage remains operator-accessible (emergency stop not weakened).
        assert (
            '@api_router.post("/arbicore/execution/kill-switch/engage", '
            "dependencies=[Depends(_require_operator_dep)])"
        ) in text

    def test_unauthenticated_disengage_401_no_mutation(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_repo(monkeypatch)
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/kill-switch/disengage",
            json={"reason": "clear"},
        )
        assert r.status_code == 401
        assert counters["disengage"] == 0

    def test_operator_disengage_403_no_mutation(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_repo(monkeypatch)
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        token = _issue("op1", "operator")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/kill-switch/disengage",
            json={"reason": "clear", "actor": "admin"},
            cookies={"access_token": token},
        )
        assert r.status_code == 403, r.text
        assert counters["disengage"] == 0

    def test_forged_token_disengage_401_no_mutation(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_repo(monkeypatch)
        forged = _issue("a1", "admin", secret="forged-secret-value-32chars-long!!")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/kill-switch/disengage",
            json={"reason": "clear"},
            cookies={"access_token": forged},
        )
        assert r.status_code == 401
        assert counters["disengage"] == 0

    def test_admin_disengage_ok_uses_session_actor_not_body(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_repo(monkeypatch)
        _stub_user(monkeypatch, user_id="a1", username="admin", role="admin")
        token = _issue("a1", "admin")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/kill-switch/disengage",
            json={"reason": "incident-cleared", "actor": "attacker-spoof"},
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("state", {}).get("engaged") is False
        assert counters["disengage"] == 1
        assert counters["disengage_actors"] == ["admin"]
        assert "attacker-spoof" not in counters["disengage_actors"]

    def test_audit_failure_fail_closed_no_success(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_repo(monkeypatch)
        counters["audit_fail"] = True
        _stub_user(monkeypatch, user_id="a1", username="admin", role="admin")
        token = _issue("a1", "admin")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/kill-switch/disengage",
            json={"reason": "clear"},
            cookies={"access_token": token},
        )
        assert r.status_code == 503, r.text
        assert counters["disengage"] == 0

    def test_operator_can_still_engage(self, monkeypatch):
        """Engage must remain available to authenticated operators."""
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        counters = self._isolate_repo(monkeypatch)
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        token = _issue("op1", "operator")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/kill-switch/engage",
            json={"reason": "emergency-stop"},
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True
        assert counters["engage"] == 1


# ---------------------------------------------------------------------------
# Repo-level fail-closed audit ordering (real KillSwitchRepo.disengage)
# ---------------------------------------------------------------------------

class TestKillSwitchRepoAuditFailClosed:
    def test_audit_failure_leaves_state_engaged(self):
        from arbicore.execution.kill_switch import KillSwitchRepo

        class _Coll:
            def __init__(self):
                self.doc = {
                    "key": "global",
                    "engaged": True,
                    "reason": "incident",
                    "actor": "op",
                    "engaged_at": "t0",
                    "last_disengaged_at": None,
                }
                self.updates = 0

            async def find_one(self, *_a, **_k):
                return dict(self.doc)

            async def update_one(self, *_a, **_k):
                self.updates += 1
                self.doc["engaged"] = False

            async def insert_one(self, *_a, **_k):
                raise AssertionError("state coll must not insert")

            async def create_index(self, *_a, **_k):
                return None

        class _Audit:
            async def insert_one(self, *_a, **_k):
                raise RuntimeError("audit_unavailable")

            async def create_index(self, *_a, **_k):
                return None

            def find(self, *_a, **_k):
                raise NotImplementedError

        class _DB(dict):
            pass

        db = _DB()
        coll = _Coll()
        audit = _Audit()
        db["kill_switch_state"] = coll
        db["kill_switch_audit"] = audit
        repo = KillSwitchRepo(db)

        with pytest.raises(RuntimeError, match="audit_unavailable"):
            asyncio.run(repo.disengage(reason="clear", actor="admin"))
        assert coll.updates == 0
        assert coll.doc["engaged"] is True


# ---------------------------------------------------------------------------
# Alternate safety kill disengage route — already admin-only; verify + actor
# ---------------------------------------------------------------------------

class TestSafetyKillDisengage:
    def test_source_requires_admin_role(self):
        text = (BACKEND / "server.py").read_text(encoding="utf-8")
        start = text.index("async def kill_disengage(")
        end = text.index("\n# ---------- paper engine endpoints ----------", start)
        body = text[start:end]
        assert 'ctx.get("role") != "admin"' in body
        assert "_resolve_current_user" in body
        assert "attacker" not in body

    def test_operator_rejected_no_mutation(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        if not getattr(srv, "_SAFETY_AVAILABLE", False):
            pytest.skip("safety module unavailable in this environment")

        class _FakeKill:
            def __init__(self):
                self.disengages = 0

            def disengage(self, *, by: str, reason: str):
                self.disengages += 1
                return {"action": "DISENGAGE", "by": by, "reason": reason}

            def to_dict(self):
                return {"engaged": False}

        fake = _FakeKill()
        monkeypatch.setattr(srv, "_KILL", fake)
        monkeypatch.setattr(srv, "_AUDIT", None)
        _stub_user(monkeypatch, user_id="op1", username="operator", role="operator")
        token = _issue("op1", "operator")

        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/safety/kill/disengage",
            srv.kill_disengage,
            methods=["POST"],
        )
        r = TestClient(app).post(
            "/api/arbicore/safety/kill/disengage",
            params={"reason": "clear"},
            cookies={"access_token": token},
        )
        assert r.status_code == 403, r.text
        assert fake.disengages == 0

    def test_admin_ok_actor_from_session(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        if not getattr(srv, "_SAFETY_AVAILABLE", False):
            pytest.skip("safety module unavailable in this environment")

        seen = {"by": None}

        class _FakeKill:
            def disengage(self, *, by: str, reason: str):
                seen["by"] = by
                return {"action": "DISENGAGE", "by": by, "reason": reason}

            def to_dict(self):
                return {"engaged": False}

        monkeypatch.setattr(srv, "_KILL", _FakeKill())
        monkeypatch.setattr(srv, "_AUDIT", None)
        _stub_user(monkeypatch, user_id="a1", username="admin", role="admin")
        token = _issue("a1", "admin")

        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/safety/kill/disengage",
            srv.kill_disengage,
            methods=["POST"],
        )
        r = TestClient(app).post(
            "/api/arbicore/safety/kill/disengage",
            params={"reason": "clear"},
            cookies={"access_token": token},
        )
        assert r.status_code == 200, r.text
        assert seen["by"] == "admin"

    def test_audit_failure_fail_closed(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        if not getattr(srv, "_SAFETY_AVAILABLE", False):
            pytest.skip("safety module unavailable in this environment")

        class _FakeKill:
            def __init__(self):
                self.disengages = 0

            def disengage(self, *, by: str, reason: str):
                self.disengages += 1
                return {"action": "DISENGAGE", "by": by, "reason": reason}

            def to_dict(self):
                return {"engaged": False}

        class _BadAudit:
            async def log(self, **_kw):
                raise RuntimeError("audit_down")

        fake = _FakeKill()
        monkeypatch.setattr(srv, "_KILL", fake)
        monkeypatch.setattr(srv, "_AUDIT", _BadAudit())
        _stub_user(monkeypatch, user_id="a1", username="admin", role="admin")
        token = _issue("a1", "admin")

        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/safety/kill/disengage",
            srv.kill_disengage,
            methods=["POST"],
        )
        r = TestClient(app).post(
            "/api/arbicore/safety/kill/disengage",
            params={"reason": "clear"},
            cookies={"access_token": token},
        )
        assert r.status_code == 503, r.text
        assert fake.disengages == 0
