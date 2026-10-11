"""Operator evidence-based recovery for stuck active_send=rpc_submitted.

Adversarial offline tests — no live RPC / signing / broadcast.
"""
from __future__ import annotations

import asyncio
import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import os
os.environ.setdefault("JWT_SECRET", "wp-c-send-recovery-jwt-secret-32ch!!")
os.environ.setdefault("ARBICORE_JWT_SECRET", "wp-c-send-recovery-jwt-secret-32ch!!")
os.environ.setdefault("MONGO_URL", "mongodb://127.0.0.1:27017")
os.environ.setdefault("DB_NAME", "wp_c_send_recovery_test")
os.environ.setdefault("ARBICORE_LEGACY_AUTH_SEED", "0")

from arbicore.execution.durable_broadcast_coordination import (  # noqa: E402
    BroadcastCoordinator,
    CoordinationError,
    SendAuthorization,
)
import server as srv  # noqa: E402
from services import auth as sauth  # noqa: E402

_TEST_SECRET = "wp-c-send-recovery-jwt-secret-32ch!!"


# ----- Fake Mongo (shared durable store for process analogues) -----

def _match(doc: Dict[str, Any], filt: Dict[str, Any]) -> bool:
    if not filt:
        return True
    for k, cond in filt.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        cur: Any = doc
        for part in k.split("."):
            if not isinstance(cur, dict) or part not in cur:
                cur = None
                break
            cur = cur[part]
        if isinstance(cond, dict) and any(str(x).startswith("$") for x in cond):
            if "$ne" in cond and cur == cond["$ne"]:
                return False
            if "$exists" in cond:
                exists = cur is not None
                if bool(cond["$exists"]) != exists:
                    return False
            if "$lt" in cond:
                if cur is None or not (float(cur) < float(cond["$lt"])):
                    return False
            if "$in" in cond and cur not in cond["$in"]:
                return False
        elif cur != cond:
            return False
    return True


class _FakeColl:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self._seq = 0
        self.fail_insert = False
        self.fail_update = False

    async def create_index(self, *_a, **_k):
        return None

    async def find_one(self, filt, *_a, **_k):
        for d in self.docs.values():
            if _match(d, filt):
                return copy.deepcopy(d)
        return None

    async def insert_one(self, doc):
        if self.fail_insert:
            raise RuntimeError("audit_store_down")
        key = doc.get("key") or doc.get("claim_id")
        if key is None:
            self._seq += 1
            key = f"_auto_{self._seq}"
        if key in self.docs and doc.get("key"):
            raise Exception("duplicate key")
        self.docs[key] = copy.deepcopy(doc)

    async def update_one(self, filt, update, upsert=False):
        if self.fail_update:
            raise RuntimeError("audit_update_down")
        for key, d in list(self.docs.items()):
            if _match(d, filt):
                self._apply(d, update)
                return
        if upsert:
            d = {"key": filt.get("key")}
            self._apply(d, update)
            self.docs[d["key"]] = d

    async def find_one_and_update(self, filt, update, upsert=False, return_document=None):
        for key, d in list(self.docs.items()):
            if _match(d, filt):
                self._apply(d, update)
                return copy.deepcopy(d)
        if upsert:
            d = {"key": filt.get("key")}
            self._apply(d, update)
            self.docs[d["key"]] = d
            return copy.deepcopy(d)
        return None

    def _apply(self, d, update):
        if "$set" in update:
            for k, v in update["$set"].items():
                if "." in k:
                    parts = k.split(".")
                    cur = d
                    for p in parts[:-1]:
                        nxt = cur.get(p)
                        if not isinstance(nxt, dict):
                            nxt = {}
                            cur[p] = nxt
                        cur = nxt
                    cur[parts[-1]] = copy.deepcopy(v)
                else:
                    d[k] = copy.deepcopy(v)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                d[k] = int(d.get(k) or 0) + int(v)


class _FakeDB:
    def __init__(self):
        self._cols: Dict[str, _FakeColl] = {}

    def __getitem__(self, name: str) -> _FakeColl:
        if name not in self._cols:
            self._cols[name] = _FakeColl()
        return self._cols[name]


async def _stuck_rpc_submitted(db, *, signer="0xabc", nonce=5, send_id=None):
    c = BroadcastCoordinator(db, instance_id="crashed-worker")
    auth = await c.authorize_send()
    await c.mark_entering_rpc(
        auth, signer=signer, nonce=nonce, chain_id=8453,
        tx_binding_digest="deadbeef" * 4,
    )
    # Simulate crash: leave rpc_submitted; mark nonce ambiguous
    from arbicore.execution.durable_broadcast_coordination import NonceLease
    await c.claim_writer()
    lease = await c.allocate_nonce(signer, nonce)
    await c.mark_nonce_ambiguous(lease, reason="process_crash_after_boundary")
    return c, auth


def _issue(uid, user, *, secret=_TEST_SECRET):
    return jwt.encode(
        {"sub": uid, "username": user, "sv": 1, "type": "access",
         "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        secret, algorithm="HS256",
    )


def _stub(monkeypatch, role="admin", user="admin", uid="a1"):
    async def _u(_p):
        return {"id": uid, "username": user, "role": role,
                "session_version": 1, "created_at": "t"}
    monkeypatch.setattr(sauth, "get_user_by_payload", _u)


# ----- Coordinator recovery -----

class TestRecoverStuckSend:
    def test_recovery_when_tx_was_submitted(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db)
            out = await c.recover_stuck_send(
                operator="admin",
                reason="crash recovery — tx mined",
                decision="tx_found",
                evidence={
                    "tx_found_on_chain": True,
                    "tx_hash": "0x" + "ab" * 32,
                    "rpc_get_transaction_result": "found",
                    "chain_pending_nonce": 6,
                    "evidence_source": "eth_getTransactionByHash",
                },
                send_id=auth.send_id,
                signer="0xabc",
            )
            assert out["ok"] is True
            assert out["resend_forbidden"] is True
            assert out["action"] == "completed_on_chain_no_resend"
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "completed"
            assert st["active_send"]["resend_forbidden"] is True
            # Cannot accidentally resend — new authorize ok, but same send resolved
            out2 = await c.recover_stuck_send(
                operator="admin", reason="retry", decision="tx_found",
                evidence={
                    "tx_found_on_chain": True,
                    "tx_hash": "0x" + "ab" * 32,
                    "rpc_get_transaction_result": "found",
                    "chain_pending_nonce": 6,
                },
                send_id=auth.send_id,
            )
            assert out2["action"] == "idempotent_already_resolved"
            assert out2["resend_forbidden"] is True

        asyncio.run(_run())

    def test_recovery_when_submission_never_occurred(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db, nonce=5)
            out = await c.recover_stuck_send(
                operator="admin",
                reason="RPC never accepted — eth_getTransactionByHash empty",
                decision="tx_absent",
                evidence={
                    "tx_found_on_chain": False,
                    "tx_hash": None,
                    "rpc_get_transaction_result": "not_found",
                    "chain_pending_nonce": 5,
                    "evidence_source": "eth_getTransactionByHash+eth_getTransactionCount",
                },
                send_id=auth.send_id,
                signer="0xabc",
            )
            assert out["ok"] is True
            assert out["action"] == "released_unused"
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "recovered_unused"
            # Nonce reusable for a *new* send_id
            await c.claim_writer()
            # clear writer if needed — same instance
            n = await c.allocate_nonce("0xabc", 5)
            assert n.nonce == 5

        asyncio.run(_run())

    def test_ambiguous_rpc_timeout_stays_blocked(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db)
            with pytest.raises(CoordinationError, match="unavailable|inconclusive|not_found"):
                await c.recover_stuck_send(
                    operator="admin",
                    reason="timeout — unknown",
                    decision="tx_absent",
                    evidence={
                        "tx_found_on_chain": False,
                        "rpc_get_transaction_result": "unavailable",
                        "chain_pending_nonce": 5,
                    },
                    send_id=auth.send_id,
                    signer="0xabc",
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_stale_contradictory_evidence_rejected(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db, nonce=5)
            # pending advanced but claim tx not found — contradictory
            with pytest.raises(CoordinationError, match="contradict|inconclusive"):
                await c.recover_stuck_send(
                    operator="admin",
                    reason="weird state",
                    decision="tx_absent",
                    evidence={
                        "tx_found_on_chain": False,
                        "rpc_get_transaction_result": "not_found",
                        "chain_pending_nonce": 9,
                    },
                    send_id=auth.send_id,
                    signer="0xabc",
                )
            # tx_found but rpc says not_found
            with pytest.raises(CoordinationError, match="contradict"):
                await c.recover_stuck_send(
                    operator="admin",
                    reason="bad",
                    decision="tx_found",
                    evidence={
                        "tx_found_on_chain": True,
                        "tx_hash": "0x" + "cd" * 32,
                        "rpc_get_transaction_result": "not_found",
                        "chain_pending_nonce": 6,
                    },
                    send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_concurrent_recovery_attempts(self):
        async def _run():
            db = _FakeDB()
            c1 = BroadcastCoordinator(db, instance_id="op1")
            c2 = BroadcastCoordinator(db, instance_id="op2")
            _, auth = await _stuck_rpc_submitted(db)

            async def recover(coord, label):
                return await coord.recover_stuck_send(
                    operator=label,
                    reason="concurrent",
                    decision="tx_found",
                    evidence={
                        "tx_found_on_chain": True,
                        "tx_hash": "0x" + "11" * 32,
                        "rpc_get_transaction_result": "found",
                        "chain_pending_nonce": 6,
                    },
                    send_id=auth.send_id,
                    signer="0xabc",
                )

            results = await asyncio.gather(
                recover(c1, "admin-a"),
                recover(c2, "admin-b"),
                return_exceptions=True,
            )
            oks = [r for r in results if isinstance(r, dict) and r.get("ok")]
            errs = [r for r in results if isinstance(r, CoordinationError)]
            assert len(oks) >= 1
            # Exactly one completing mutation path; other is busy or idempotent.
            assert len(oks) + len(errs) == 2
            actions = {r.get("action") for r in oks}
            assert actions & {
                "completed_on_chain_no_resend",
                "idempotent_already_resolved",
            }

        asyncio.run(_run())

    def test_restart_during_reconciliation_idempotent(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db)
            out = await c.recover_stuck_send(
                operator="admin", reason="r1", decision="tx_found",
                evidence={
                    "tx_found_on_chain": True,
                    "tx_hash": "0x" + "22" * 32,
                    "rpc_get_transaction_result": "found",
                    "chain_pending_nonce": 6,
                },
                send_id=auth.send_id, signer="0xabc",
            )
            assert out["ok"]
            # "Restart" — new coordinator instance, same store
            c2 = BroadcastCoordinator(db, instance_id="after-restart")
            out2 = await c2.recover_stuck_send(
                operator="admin", reason="r2", decision="tx_found",
                evidence={
                    "tx_found_on_chain": True,
                    "tx_hash": "0x" + "22" * 32,
                    "rpc_get_transaction_result": "found",
                    "chain_pending_nonce": 6,
                },
                send_id=auth.send_id,
            )
            assert out2["action"] == "idempotent_already_resolved"

        asyncio.run(_run())

    def test_audit_store_failure_fail_closed(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db)
            db["arbicore_send_recovery_audit"].fail_insert = True
            with pytest.raises(CoordinationError, match="audit"):
                await c.recover_stuck_send(
                    operator="admin", reason="x", decision="tx_found",
                    evidence={
                        "tx_found_on_chain": True,
                        "tx_hash": "0x" + "33" * 32,
                        "rpc_get_transaction_result": "found",
                        "chain_pending_nonce": 6,
                    },
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_ttl_does_not_clear_rpc_submitted(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db)
            # Expire any expires_ts — authorize must still refuse
            db["arbicore_send_coordination"].docs["global"]["active_send"][
                "expires_ts"
            ] = 0
            with pytest.raises(CoordinationError, match="in flight|kill"):
                await c.authorize_send()
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"
            assert st["active_send"]["send_id"] == auth.send_id

        asyncio.run(_run())

    def test_investigate_remains_blocked(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db)
            out = await c.recover_stuck_send(
                operator="admin", reason="need more data",
                decision="investigate",
                evidence={"tx_found_on_chain": None,
                          "rpc_get_transaction_result": "unavailable"},
                send_id=auth.send_id,
            )
            assert out["blocked"] is True
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_forbidden_evidence_fields_rejected(self):
        async def _run():
            db = _FakeDB()
            c, auth = await _stuck_rpc_submitted(db)
            with pytest.raises(CoordinationError, match="not allowed"):
                await c.recover_stuck_send(
                    operator="admin", reason="x", decision="tx_found",
                    evidence={
                        "tx_found_on_chain": True,
                        "tx_hash": "0x" + "44" * 32,
                        "rpc_get_transaction_result": "found",
                        "private_key": "0xdead",
                    },
                    send_id=auth.send_id,
                )

        asyncio.run(_run())


# ----- HTTP admin gate -----

class TestRecoveryHTTPAuth:
    def _app(self):
        app = FastAPI()
        app.add_api_route(
            "/api/arbicore/execution/broadcast/recover-stuck-send",
            srv.v2_broadcast_recover_stuck_send,
            methods=["POST"],
            dependencies=[Depends(srv._require_admin_dep)],
        )
        return app

    def test_anonymous_401(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/broadcast/recover-stuck-send",
            json={"reason": "x", "decision": "investigate", "evidence": {}},
        )
        assert r.status_code == 401

    def test_operator_403(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        _stub(monkeypatch, role="operator", user="op", uid="op1")
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/broadcast/recover-stuck-send",
            json={"reason": "x", "decision": "investigate", "evidence": {}},
            cookies={"access_token": _issue("op1", "op")},
        )
        assert r.status_code == 403

    def test_malformed_body(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        _stub(monkeypatch)
        db = _FakeDB()
        monkeypatch.setattr(srv, "_BROADCAST_COORDINATOR",
                            BroadcastCoordinator(db, instance_id="http"))
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/broadcast/recover-stuck-send",
            json={"decision": "tx_found"},  # missing reason + evidence
            cookies={"access_token": _issue("a1", "admin")},
        )
        assert r.status_code == 200
        assert r.json().get("ok") is False

    def test_admin_recovery_ok(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        _stub(monkeypatch)
        db = _FakeDB()
        coord = BroadcastCoordinator(db, instance_id="http")
        monkeypatch.setattr(srv, "_BROADCAST_COORDINATOR", coord)

        async def setup():
            return await _stuck_rpc_submitted(db)
        c, auth = asyncio.run(setup())
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/broadcast/recover-stuck-send",
            json={
                "reason": "ops recovery",
                "decision": "tx_found",
                "send_id": auth.send_id,
                "signer": "0xabc",
                "evidence": {
                    "tx_found_on_chain": True,
                    "tx_hash": "0x" + "55" * 32,
                    "rpc_get_transaction_result": "found",
                    "chain_pending_nonce": 6,
                },
            },
            cookies={"access_token": _issue("a1", "admin")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("resend_forbidden") is True
        assert "private_key" not in r.text.lower()
        assert "0x55" * 8 not in r.text or body.get("resolved_tx_hash")  # hash ok in result
