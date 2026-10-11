"""Trusted-RPC stuck-send recovery — adversarial offline tests.

No live RPC / signing / broadcast. Injected RecoveryRpcVerifier fakes
provide authoritative observations.
"""
from __future__ import annotations

import asyncio
import copy
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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
os.environ.setdefault("ARBICORE_RECOVERY_ABSENT_MIN_AGE_S", "0")
os.environ.setdefault("ARBICORE_RECOVERY_ABSENT_REQUERY_DELAY_S", "0")

from arbicore.execution.durable_broadcast_coordination import (  # noqa: E402
    BroadcastCoordinator,
    CoordinationError,
)
from arbicore.execution.presend_invariants import TxByteBinding  # noqa: E402
from arbicore.execution.recovery_rpc_evidence import (  # noqa: E402
    TrustedChainObservation,
    TrustedNonceObservation,
    TrustedTxObservation,
)
import server as srv  # noqa: E402
from services import auth as sauth  # noqa: E402

_TEST_SECRET = "wp-c-send-recovery-jwt-secret-32ch!!"
_SIGNER = "0xabc0000000000000000000000000000000000001"
_TO = "0xdef0000000000000000000000000000000000002"
_HASH_OK = "0x" + "ab" * 32
_HASH_OTHER = "0x" + "cd" * 32


def _tx_fields(*, nonce=5, chain_id=8453, data="0xdeadbeef"):
    return {
        "to": _TO,
        "data": data,
        "value": 0,
        "chainId": chain_id,
        "nonce": nonce,
        "gas": 21000,
        "gasPrice": 1_000_000_000,
    }


def _digest_for(**kw) -> str:
    return TxByteBinding.from_tx(_tx_fields(**kw)).digest


def _rpc_tx(*, nonce=5, chain_id=8453, data="0xdeadbeef",
            sender=_SIGNER, tx_hash=_HASH_OK) -> Dict[str, Any]:
    f = _tx_fields(nonce=nonce, chain_id=chain_id, data=data)
    return {
        "hash": tx_hash,
        "from": sender,
        "to": f["to"],
        "input": f["data"],
        "value": hex(f["value"]),
        "nonce": hex(f["nonce"]),
        "gas": hex(f["gas"]),
        "gasPrice": hex(f["gasPrice"]),
        "chainId": hex(f["chainId"]),
    }


# ----- Fake Mongo -----

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


class FakeVerifier:
    """Injectable trusted RPC stand-in."""

    def __init__(self):
        self.observed_chain_id = 8453
        self.txs: Dict[str, Optional[Dict[str, Any]]] = {}
        self.pending = 5
        self.latest = 5
        self.fail_chain = False
        self.fail_nonce = False
        self.unstable = False
        self.tx_error_hashes: set = set()
        self.absent_min_age_s = 0.0
        self.absent_requery_delay_s = 0.0
        self._ncalls = 0

    async def observe_chain_id(self, expected_chain_id: int) -> TrustedChainObservation:
        if self.fail_chain:
            raise RuntimeError("rpc_chain_down")
        return TrustedChainObservation(
            observed_chain_id=int(self.observed_chain_id),
            expected_chain_id=int(expected_chain_id),
            observed_at=datetime.now(timezone.utc).isoformat(),
            provider_label="rpc:injected",
        )

    async def observe_transaction(
        self, expected_chain_id: int, tx_hash: str
    ) -> TrustedTxObservation:
        h = tx_hash.lower()
        at = datetime.now(timezone.utc).isoformat()
        if h in self.tx_error_hashes:
            return TrustedTxObservation(
                tx_hash=h, status="error", tx=None, observed_at=at,
                provider_label="rpc:injected",
                observed_chain_id=int(expected_chain_id), detail="timeout",
            )
        if h not in self.txs:
            return TrustedTxObservation(
                tx_hash=h, status="not_found", tx=None, observed_at=at,
                provider_label="rpc:injected",
                observed_chain_id=int(expected_chain_id),
            )
        tx = self.txs[h]
        if tx is None:
            return TrustedTxObservation(
                tx_hash=h, status="not_found", tx=None, observed_at=at,
                provider_label="rpc:injected",
                observed_chain_id=int(expected_chain_id),
            )
        return TrustedTxObservation(
            tx_hash=h, status="found", tx=tx, observed_at=at,
            provider_label="rpc:injected",
            observed_chain_id=int(expected_chain_id),
        )

    async def observe_nonces(
        self, expected_chain_id: int, signer: str
    ) -> TrustedNonceObservation:
        if self.fail_nonce:
            raise RuntimeError("rpc_nonce_down")
        return TrustedNonceObservation(
            pending_nonce=int(self.pending),
            latest_nonce=int(self.latest),
            observed_at=datetime.now(timezone.utc).isoformat(),
            provider_label="rpc:injected",
            observed_chain_id=int(expected_chain_id),
        )

    async def observe_nonces_consistent(
        self, expected_chain_id: int, signer: str
    ) -> TrustedNonceObservation:
        self._ncalls += 1
        first = await self.observe_nonces(expected_chain_id, signer)
        if self.unstable:
            self.pending += 1
            raise RuntimeError(
                "rpc_nonce_unstable: pending/latest changed between observations"
            )
        return first


async def _stuck_rpc_submitted(
    db,
    *,
    signer=_SIGNER,
    nonce=5,
    chain_id=8453,
    data="0xdeadbeef",
    verifier: Optional[FakeVerifier] = None,
):
    v = verifier or FakeVerifier()
    c = BroadcastCoordinator(db, instance_id="crashed-worker", rpc_verifier=v)
    auth = await c.authorize_send()
    digest = _digest_for(nonce=nonce, chain_id=chain_id, data=data)
    await c.mark_entering_rpc(
        auth, signer=signer, nonce=nonce, chain_id=chain_id,
        tx_binding_digest=digest,
    )
    from arbicore.execution.durable_broadcast_coordination import NonceLease
    await c.claim_writer()
    lease = await c.allocate_nonce(signer, nonce)
    await c.mark_nonce_ambiguous(lease, reason="process_crash_after_boundary")
    # Backdate rpc_entered_at so absent min-age does not block by default.
    db["arbicore_send_coordination"].docs["global"]["active_send"][
        "rpc_entered_at"
    ] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    return c, auth, v, digest


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
            c, auth, v, digest = await _stuck_rpc_submitted(db)
            v.txs[_HASH_OK] = _rpc_tx()
            v.pending = 6
            v.latest = 6
            out = await c.recover_stuck_send(
                operator="admin",
                reason="crash recovery — tx mined",
                decision="tx_found",
                evidence={"candidate_tx_hash": _HASH_OK},
                send_id=auth.send_id,
            )
            assert out["ok"] is True
            assert out["resend_forbidden"] is True
            assert out["action"] == "completed_on_chain_no_resend"
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "completed"
            assert st["active_send"]["resend_forbidden"] is True
            out2 = await c.recover_stuck_send(
                operator="admin", reason="retry", decision="tx_found",
                evidence={"candidate_tx_hash": _HASH_OK},
                send_id=auth.send_id,
            )
            assert out2["action"] == "idempotent_already_resolved"
            assert out2["resend_forbidden"] is True

        asyncio.run(_run())

    def test_recovery_when_submission_never_occurred(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db, nonce=5)
            v.pending = 5
            v.latest = 5
            out = await c.recover_stuck_send(
                operator="admin",
                reason="RPC never accepted",
                decision="tx_absent",
                evidence={},
                send_id=auth.send_id,
            )
            assert out["ok"] is True
            assert out["action"] == "released_unused"
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "recovered_unused"
            await c.claim_writer()
            n = await c.allocate_nonce(_SIGNER, 5)
            assert n.nonce == 5

        asyncio.run(_run())

    def test_fabricated_tx_absent_operator_json_ignored(self):
        """Handoff-6 probe: operator proof fields must not release nonce."""
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db, nonce=5)
            # Trusted RPC says nonce was consumed — fabricated absent proof ignored.
            v.pending = 9
            v.latest = 9
            with pytest.raises(CoordinationError, match="advanced|blocked|contradict"):
                await c.recover_stuck_send(
                    operator="admin",
                    reason="fabricated",
                    decision="tx_absent",
                    evidence={
                        "tx_found_on_chain": False,
                        "rpc_get_transaction_result": "not_found",
                        "chain_pending_nonce": 5,
                        "observed_at": "2099-01-01T00:00:00+00:00",
                        "chain_id": 8453,
                    },
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_unbound_tx_hash_rejected(self):
        """Handoff-6 probe: hash accepted only if digest-bound to stuck send."""
        async def _run():
            db = _FakeDB()
            c, auth, v, digest = await _stuck_rpc_submitted(db)
            # Different calldata → different digest
            v.txs[_HASH_OTHER] = _rpc_tx(data="0xother", tx_hash=_HASH_OTHER)
            v.pending = 6
            v.latest = 6
            with pytest.raises(CoordinationError, match="binding|digest|mismatch"):
                await c.recover_stuck_send(
                    operator="admin", reason="unbound", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OTHER},
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"
            assert st["active_send"]["tx_binding_digest"] == digest

        asyncio.run(_run())

    def test_wrong_chain_id_rejected(self):
        """Handoff-6 probe: evidence/RPC chain must match stuck send."""
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db, chain_id=8453)
            v.observed_chain_id = 1  # ethereum
            v.txs[_HASH_OK] = _rpc_tx(chain_id=8453)
            with pytest.raises(CoordinationError, match="chain_id"):
                await c.recover_stuck_send(
                    operator="admin", reason="wrong chain", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK, "chain_id": 1},
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_wrong_sender_rejected(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.txs[_HASH_OK] = _rpc_tx(
                sender="0x9999999999999999999999999999999999999999"
            )
            v.pending = 6
            v.latest = 6
            with pytest.raises(CoordinationError, match="signer_mismatch|binding"):
                await c.recover_stuck_send(
                    operator="admin", reason="wrong from", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_wrong_nonce_rejected(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db, nonce=5)
            # Same digest fields but RPC reports different nonce → bind fail
            bad = _rpc_tx(nonce=7)
            # Force digest of stuck to be for nonce 5; RPC nonce 7 mismatches
            v.txs[_HASH_OK] = bad
            v.pending = 8
            v.latest = 8
            with pytest.raises(CoordinationError, match="nonce_mismatch|binding"):
                await c.recover_stuck_send(
                    operator="admin", reason="wrong nonce", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_stale_absent_min_age_blocks(self):
        async def _run():
            db = _FakeDB()
            v = FakeVerifier()
            v.absent_min_age_s = 3600.0
            c, auth, v, _ = await _stuck_rpc_submitted(db, verifier=v)
            # Fresh rpc_entered_at
            db["arbicore_send_coordination"].docs["global"]["active_send"][
                "rpc_entered_at"
            ] = datetime.now(timezone.utc).isoformat()
            v.pending = 5
            v.latest = 5
            with pytest.raises(CoordinationError, match="too recent|stale|blocked"):
                await c.recover_stuck_send(
                    operator="admin", reason="too fresh", decision="tx_absent",
                    evidence={}, send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_pending_ne_latest_ambiguous(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.pending = 6
            v.latest = 5
            with pytest.raises(CoordinationError, match="diverge|inconclusive|blocked"):
                await c.recover_stuck_send(
                    operator="admin", reason="mempool", decision="tx_absent",
                    evidence={}, send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_unstable_nonce_observations_fail_closed(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.pending = 5
            v.latest = 5
            v.unstable = True
            with pytest.raises(CoordinationError, match="unavailable|unstable|blocked"):
                await c.recover_stuck_send(
                    operator="admin", reason="race", decision="tx_absent",
                    evidence={}, send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_rpc_failure_fail_closed(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.fail_chain = True
            with pytest.raises(CoordinationError, match="RPC unavailable|rpc"):
                await c.recover_stuck_send(
                    operator="admin", reason="rpc down", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_ambiguous_rpc_timeout_stays_blocked(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.tx_error_hashes.add(_HASH_OK)
            with pytest.raises(CoordinationError, match="blocked|not find|error"):
                await c.recover_stuck_send(
                    operator="admin",
                    reason="timeout — unknown",
                    decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_stale_contradictory_evidence_rejected(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db, nonce=5)
            v.pending = 9
            v.latest = 9
            with pytest.raises(CoordinationError, match="advanced|contradict|blocked"):
                await c.recover_stuck_send(
                    operator="admin",
                    reason="weird state",
                    decision="tx_absent",
                    evidence={},
                    send_id=auth.send_id,
                )
            # candidate still present → cannot claim absent
            v.pending = 5
            v.latest = 5
            v.txs[_HASH_OK] = _rpc_tx()
            with pytest.raises(CoordinationError, match="still present|tx_found"):
                await c.recover_stuck_send(
                    operator="admin",
                    reason="bad",
                    decision="tx_absent",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_concurrent_recovery_attempts(self):
        async def _run():
            db = _FakeDB()
            v = FakeVerifier()
            v.txs[_HASH_OK] = _rpc_tx()
            v.pending = 6
            v.latest = 6
            c1 = BroadcastCoordinator(db, instance_id="op1", rpc_verifier=v)
            c2 = BroadcastCoordinator(db, instance_id="op2", rpc_verifier=v)
            _, auth, _, _ = await _stuck_rpc_submitted(db, verifier=v)

            async def recover(coord, label):
                return await coord.recover_stuck_send(
                    operator=label,
                    reason="concurrent",
                    decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )

            results = await asyncio.gather(
                recover(c1, "admin-a"),
                recover(c2, "admin-b"),
                return_exceptions=True,
            )
            oks = [r for r in results if isinstance(r, dict) and r.get("ok")]
            errs = [r for r in results if isinstance(r, CoordinationError)]
            assert len(oks) >= 1
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
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.txs[_HASH_OK] = _rpc_tx(tx_hash=_HASH_OK)
            # use matching hash constant
            h = _HASH_OK
            v.txs[h] = _rpc_tx(tx_hash=h)
            v.pending = 6
            v.latest = 6
            out = await c.recover_stuck_send(
                operator="admin", reason="r1", decision="tx_found",
                evidence={"candidate_tx_hash": h},
                send_id=auth.send_id,
            )
            assert out["ok"]
            c2 = BroadcastCoordinator(db, instance_id="after-restart", rpc_verifier=v)
            out2 = await c2.recover_stuck_send(
                operator="admin", reason="r2", decision="tx_found",
                evidence={"candidate_tx_hash": h},
                send_id=auth.send_id,
            )
            assert out2["action"] == "idempotent_already_resolved"

        asyncio.run(_run())

    def test_crash_after_commit_intent_before_finish_resumable(self):
        """Terminal mutation + unfinished audit must not unlock ambiguous resend."""
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.txs[_HASH_OK] = _rpc_tx()
            v.pending = 6
            v.latest = 6

            real_finish = c._audit_finish
            calls = {"n": 0}

            async def flaky_finish(*a, **k):
                calls["n"] += 1
                if calls["n"] == 1 and k.get("ok") is True:
                    # Simulate crash: durable state already committed; audit finish dies.
                    raise CoordinationError("recovery_audit_finish_failed")
                return await real_finish(*a, **k)

            c._audit_finish = flaky_finish  # type: ignore[method-assign]
            with pytest.raises(CoordinationError, match="audit_finish"):
                await c.recover_stuck_send(
                    operator="admin", reason="crash mid", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            # Durable terminal state committed before finish — resend forbidden.
            assert st["active_send"]["status"] == "completed"
            assert st["active_send"]["resend_forbidden"] is True
            # Restart completes idempotently
            c._audit_finish = real_finish  # type: ignore[method-assign]
            c2 = BroadcastCoordinator(db, instance_id="resume", rpc_verifier=v)
            out = await c2.recover_stuck_send(
                operator="admin", reason="resume", decision="tx_found",
                evidence={"candidate_tx_hash": _HASH_OK},
                send_id=auth.send_id,
            )
            assert out["action"] == "idempotent_already_resolved"
            assert out["resend_forbidden"] is True

        asyncio.run(_run())

    def test_commit_intent_audit_failure_fail_closed(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.txs[_HASH_OK] = _rpc_tx()
            v.pending = 6
            v.latest = 6
            # Fail updates after insert (commit_intent uses update_one)
            db["arbicore_send_recovery_audit"].fail_update = True
            with pytest.raises(CoordinationError, match="audit"):
                await c.recover_stuck_send(
                    operator="admin", reason="x", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_audit_store_failure_fail_closed(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            db["arbicore_send_recovery_audit"].fail_insert = True
            with pytest.raises(CoordinationError, match="audit"):
                await c.recover_stuck_send(
                    operator="admin", reason="x", decision="tx_found",
                    evidence={"candidate_tx_hash": _HASH_OK},
                    send_id=auth.send_id,
                )
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_ttl_does_not_clear_rpc_submitted(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
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
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            out = await c.recover_stuck_send(
                operator="admin", reason="need more data",
                decision="investigate",
                evidence={},
                send_id=auth.send_id,
            )
            assert out["blocked"] is True
            st = await c.get_coordination_status()
            assert st["active_send"]["status"] == "rpc_submitted"

        asyncio.run(_run())

    def test_forbidden_evidence_fields_rejected(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            with pytest.raises(CoordinationError, match="not allowed"):
                await c.recover_stuck_send(
                    operator="admin", reason="x", decision="tx_found",
                    evidence={
                        "candidate_tx_hash": _HASH_OK,
                        "private_key": "0xdead",
                    },
                    send_id=auth.send_id,
                )

        asyncio.run(_run())

    def test_replayed_fabricated_evidence_still_requires_rpc(self):
        async def _run():
            db = _FakeDB()
            c, auth, v, _ = await _stuck_rpc_submitted(db)
            v.fail_chain = True
            with pytest.raises(CoordinationError, match="RPC unavailable|rpc"):
                await c.recover_stuck_send(
                    operator="admin", reason="replay", decision="tx_absent",
                    evidence={
                        "tx_found_on_chain": False,
                        "rpc_get_transaction_result": "not_found",
                        "chain_pending_nonce": 5,
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
        v = FakeVerifier()
        monkeypatch.setattr(
            srv, "_BROADCAST_COORDINATOR",
            BroadcastCoordinator(db, instance_id="http", rpc_verifier=v),
        )
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/broadcast/recover-stuck-send",
            json={"decision": "tx_found"},  # missing reason
            cookies={"access_token": _issue("a1", "admin")},
        )
        assert r.status_code == 200
        assert r.json().get("ok") is False

    def test_admin_recovery_ok(self, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", _TEST_SECRET)
        _stub(monkeypatch)
        db = _FakeDB()
        v = FakeVerifier()
        v.txs[_HASH_OK] = _rpc_tx()
        v.pending = 6
        v.latest = 6
        coord = BroadcastCoordinator(db, instance_id="http", rpc_verifier=v)
        monkeypatch.setattr(srv, "_BROADCAST_COORDINATOR", coord)

        async def setup():
            return await _stuck_rpc_submitted(db, verifier=v)
        _, auth, _, _ = asyncio.run(setup())
        r = TestClient(self._app()).post(
            "/api/arbicore/execution/broadcast/recover-stuck-send",
            json={
                "reason": "ops recovery",
                "decision": "tx_found",
                "send_id": auth.send_id,
                "evidence": {"candidate_tx_hash": _HASH_OK},
            },
            cookies={"access_token": _issue("a1", "admin")},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        assert body.get("resend_forbidden") is True
        assert "private_key" not in r.text.lower()
        assert "rpc_url" not in r.text.lower()
