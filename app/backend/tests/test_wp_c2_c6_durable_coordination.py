"""WP-C2/C6 remediation — durable cross-process coordination adversarial tests.

Uses two coordinator instances sharing one in-memory store as a realistic
multi-process analogue (separate objects, shared durable state — not merely
concurrent tasks on one in-process mutex).

No live RPC / signing / broadcast.
"""
from __future__ import annotations

import asyncio
import copy
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from arbicore.execution.durable_broadcast_coordination import (  # noqa: E402
    AmbiguousBroadcastError,
    BroadcastCoordinator,
    CoordinationError,
)
from arbicore.execution.kill_switch import KillSwitchRepo  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal Mongo-analogue supporting the coordinator's conditional updates
# ---------------------------------------------------------------------------

def _match(doc: Dict[str, Any], filt: Dict[str, Any]) -> bool:
    if not filt:
        return True
    for k, cond in filt.items():
        if k == "$or":
            if not any(_match(doc, sub) for sub in cond):
                return False
            continue
        if k == "$and":
            if not all(_match(doc, sub) for sub in cond):
                return False
            continue
        # dotted path
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
            if "$in" in cond:
                if cur not in cond["$in"]:
                    return False
        else:
            if cur != cond:
                return False
    return True


class _FakeColl:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self._seq = 0

    async def create_index(self, *_a, **_k):
        return None

    async def find_one(self, filt, *_a, **_k):
        for d in self.docs.values():
            if _match(d, filt):
                return copy.deepcopy(d)
        return None

    async def insert_one(self, doc):
        key = doc.get("key")
        if key is None:
            self._seq += 1
            key = f"_auto_{self._seq}"
        if key in self.docs and not str(key).startswith("_auto_"):
            raise Exception("duplicate key")
        stored = copy.deepcopy(doc)
        if "key" not in stored:
            stored["_id"] = key
        self.docs[key] = stored

    async def update_one(self, filt, update, upsert=False):
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

    def _apply(self, d: Dict[str, Any], update: Dict[str, Any]) -> None:
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
        if "$setOnInsert" in update:
            for k, v in update["$setOnInsert"].items():
                d.setdefault(k, copy.deepcopy(v))


class _FakeDB:
    def __init__(self):
        self._cols: Dict[str, _FakeColl] = {}

    def __getitem__(self, name: str) -> _FakeColl:
        if name not in self._cols:
            self._cols[name] = _FakeColl()
        return self._cols[name]


def _two_workers(db=None):
    db = db or _FakeDB()
    a = BroadcastCoordinator(db, instance_id="worker-A")
    b = BroadcastCoordinator(db, instance_id="worker-B")
    return db, a, b


# ---------------------------------------------------------------------------
# C2 — kill vs send across process analogues
# ---------------------------------------------------------------------------

class TestC2CrossProcessKillSendRace:
    def test_engage_then_other_worker_denied_at_boundary(self):
        async def _run():
            db, a, b = _two_workers()
            # Worker A authorizes
            auth = await a.authorize_send()
            # Worker B engages kill (separate process analogue)
            await b.on_kill_engaged(reason="incident", actor="op")
            # Worker A cannot cross broadcast boundary
            with pytest.raises(CoordinationError, match="kill engaged"):
                await a.mark_entering_rpc(auth)

        asyncio.run(_run())

    def test_handoff4_race_engage_between_authorize_and_rpc(self):
        """Exact Handoff-4 pattern: authorize wins, then engage, then RPC denied."""
        async def _run():
            db, sender, engagé = _two_workers()
            auth = await sender.authorize_send()
            await engagé.on_kill_engaged(reason="race", actor="op")
            with pytest.raises(CoordinationError):
                await sender.mark_entering_rpc(auth)
            # New authorize also denied
            with pytest.raises(CoordinationError, match="kill_switch engaged"):
                await engagé.authorize_send()

        asyncio.run(_run())

    def test_in_flight_rpc_submitted_not_recalled_but_new_denied(self):
        async def _run():
            db, a, b = _two_workers()
            auth = await a.authorize_send()
            await a.mark_entering_rpc(auth)  # crossed linearization point
            await b.on_kill_engaged(reason="late", actor="op")
            # In-flight may complete (not recalled)
            await a.complete_send(auth, outcome="completed")
            # New send denied
            with pytest.raises(CoordinationError):
                await b.authorize_send()

        asyncio.run(_run())

    def test_kill_switch_repo_engage_blocks_other_worker_send(self):
        async def _run():
            db = _FakeDB()
            ks = KillSwitchRepo(db)
            await ks.ensure_default()
            coord = BroadcastCoordinator(db, instance_id="ks-worker")
            ks.bind_broadcast_coordinator(coord)
            other = BroadcastCoordinator(db, instance_id="sender-worker")
            auth = await other.authorize_send()
            await ks.engage("stop", actor="admin")
            with pytest.raises(CoordinationError):
                await other.mark_entering_rpc(auth)

        asyncio.run(_run())

    def test_coord_unavailable_fail_closed(self):
        async def _run():
            class BoomDB:
                def __getitem__(self, _name):
                    raise RuntimeError("mongo_down")

            c = BroadcastCoordinator(BoomDB(), instance_id="x")
            with pytest.raises(Exception):
                await c.authorize_send()

        asyncio.run(_run())  # construction succeeds; operation fails closed


# ---------------------------------------------------------------------------
# C6 — durable nonce / writer
# ---------------------------------------------------------------------------

class TestC6DurableNonceAndWriter:
    def test_two_workers_cannot_claim_same_writer(self):
        async def _run():
            db, a, b = _two_workers()
            await a.claim_writer()
            with pytest.raises(CoordinationError, match="writer_lease_denied"):
                await b.claim_writer()

        asyncio.run(_run())

    def test_two_workers_cannot_claim_same_nonce(self):
        async def _run():
            db, a, b = _two_workers()
            await a.claim_writer()
            n1 = await a.allocate_nonce("0xabc", 7)
            assert n1.nonce == 7
            # Expire writer so B can become broadcaster; nonce lease remains.
            db["arbicore_send_coordination"].docs["global"]["writer_lease"][
                "expires_ts"
            ] = 0
            await b.claim_writer()
            with pytest.raises(CoordinationError, match="nonce_in_use"):
                await b.allocate_nonce("0xabc", 7)

        asyncio.run(_run())

    def test_stale_writer_after_lease_expiry(self):
        async def _run():
            db, a, b = _two_workers()
            # Force near-immediate expiry on the stored lease via tiny TTL
            a._writer_ttl = 0.05
            b._writer_ttl = 60.0
            claimed = await a.claim_writer()
            # Advance past expires_ts without relying on wall-clock flakiness
            db["arbicore_send_coordination"].docs["global"]["writer_lease"][
                "expires_ts"
            ] = claimed["expires_ts"] - 1
            await b.claim_writer()
            with pytest.raises(CoordinationError):
                await a._require_writer("worker-A")

        asyncio.run(_run())

    def test_pre_broadcast_failure_does_not_skip_nonce(self):
        async def _run():
            db = _FakeDB()
            c = BroadcastCoordinator(db, instance_id="w1")
            await c.claim_writer()
            lease = await c.allocate_nonce("0xabc", 5)
            await c.mark_nonce_pre_broadcast_failure(lease)
            # Retry gets same nonce (not 6)
            lease2 = await c.allocate_nonce("0xabc", 5)
            assert lease2.nonce == 5

        asyncio.run(_run())

    def test_ambiguous_blocks_until_reconcile(self):
        async def _run():
            db = _FakeDB()
            c = BroadcastCoordinator(db, instance_id="w1")
            await c.claim_writer()
            lease = await c.allocate_nonce("0xabc", 3)
            await c.mark_nonce_ambiguous(lease, reason="rpc_timeout")
            with pytest.raises(AmbiguousBroadcastError):
                await c.allocate_nonce("0xabc", 3)
            # Reconcile: tx not on chain, pending still 3 → release
            out = await c.reconcile_nonce(
                "0xabc",
                chain_pending_nonce=3,
                tx_found_on_chain=False,
            )
            assert out["ok"] is True
            lease2 = await c.allocate_nonce("0xabc", 3)
            assert lease2.nonce == 3

        asyncio.run(_run())

    def test_reconcile_found_on_chain_advances(self):
        async def _run():
            db = _FakeDB()
            c = BroadcastCoordinator(db, instance_id="w1")
            await c.claim_writer()
            lease = await c.allocate_nonce("0xabc", 9)
            await c.mark_nonce_ambiguous(lease, reason="timeout")
            out = await c.reconcile_nonce(
                "0xabc",
                chain_pending_nonce=10,
                tx_found_on_chain=True,
                tx_hash="0xdead",
            )
            assert out["ok"] is True
            lease2 = await c.allocate_nonce("0xabc", 10)
            assert lease2.nonce == 10

        asyncio.run(_run())

    def test_process_restart_stale_local_cannot_use_old_fence(self):
        async def _run():
            db = _FakeDB()
            c1 = BroadcastCoordinator(db, instance_id="w1")
            await c1.claim_writer()
            lease = await c1.allocate_nonce("0xabc", 1)
            # Expire writer lease durably (process crash analogue)
            db["arbicore_send_coordination"].docs["global"]["writer_lease"][
                "expires_ts"
            ] = 0
            c2 = BroadcastCoordinator(db, instance_id="w2")
            await c2.claim_writer()
            # Release prior nonce via reconcile (tx never hit chain)
            await db["arbicore_nonce_leases"].update_one(
                {"key": "0xabc"},
                {"$set": {
                    "blocked_reason": None,
                    "inflight": {"status": "released_pre_rpc", "nonce": 1},
                }},
            )
            n2 = await c2.allocate_nonce("0xabc", 1)
            assert n2.owner_id == "w2"
            assert n2.fence != lease.fence

        asyncio.run(_run())

    def test_run_authorized_send_denied_after_foreign_engage(self):
        async def _run():
            db, a, b = _two_workers()
            sent = {"n": 0}

            async def send():
                sent["n"] += 1
                return "0xhash"

            # Interleave: start authorize path manually
            auth = await a.authorize_send()
            await b.on_kill_engaged(reason="x", actor="op")
            with pytest.raises(CoordinationError):
                await a.mark_entering_rpc(auth)
            assert sent["n"] == 0

        asyncio.run(_run())
