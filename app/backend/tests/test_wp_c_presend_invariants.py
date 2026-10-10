"""WP-C adversarial offline tests for pre-send invariants C1–C7.

No live RPC, signing, or broadcast. Synthetic data only.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from arbicore.execution.kill_switch import (  # noqa: E402
    KillSwitchEngagedError,
    KillSwitchRepo,
)
from arbicore.execution.presend_invariants import (  # noqa: E402
    DurableBudgetStore,
    NonceCoordinator,
    SendCriticalSection,
    TxByteBinding,
    assert_chain_allowed,
    assert_chain_ceiling,
    cleanup_failed_technical_validation,
    read_authoritative_kill,
    ChainPolicyError,
)


class _MemColl:
    def __init__(self):
        self.docs: Dict[str, Dict[str, Any]] = {}
        self.audit: list = []

    async def create_index(self, *_a, **_k):
        return None

    async def find_one(self, q, *_a, **_k):
        key = q.get("key")
        return dict(self.docs[key]) if key in self.docs else None

    async def insert_one(self, doc):
        if "action" in doc:  # audit
            self.audit.append(doc)
            return
        self.docs[doc["key"]] = dict(doc)

    async def update_one(self, q, update, upsert=False):
        key = q.get("key")
        doc = self.docs.get(key, {"key": key})
        if "$set" in update:
            doc.update(update["$set"])
        if "$setOnInsert" in update and key not in self.docs:
            for k, v in update["$setOnInsert"].items():
                doc.setdefault(k, v)
        if "$inc" in update:
            for k, v in update["$inc"].items():
                doc[k] = float(doc.get(k) or 0) + float(v)
        self.docs[key] = doc

    async def find_one_and_update(self, q, update, upsert=False, return_document=None):
        await self.update_one(q, update, upsert=upsert)
        return await self.find_one(q)

    async def delete_many(self, q):
        before = len(self.docs)
        # simplistic filter
        if "opportunity_id" in q:
            self.docs = {
                k: v for k, v in self.docs.items()
                if v.get("opportunity_id") != q["opportunity_id"]
            }
        class R:
            deleted_count = before - len(self.docs)
        return R()

    async def update_many(self, q, update):
        for doc in self.docs.values():
            if q.get("opportunity_id") and doc.get("opportunity_id") != q["opportunity_id"]:
                continue
            if "$set" in update:
                doc.update(update["$set"])

    def find(self, *_a, **_k):
        class C:
            def sort(self, *_a, **_k):
                return self

            def limit(self, n):
                return self

            async def to_list(self, n):
                return []
        return C()


class _MemDB:
    def __init__(self):
        self._cols: Dict[str, _MemColl] = {}

    def __getitem__(self, name: str) -> _MemColl:
        if name not in self._cols:
            self._cols[name] = _MemColl()
        return self._cols[name]


class TestC1AuthoritativeKillSwitch:
    def test_engage_reflected_on_guard_and_mirror(self):
        async def _run():
            db = _MemDB()
            repo = KillSwitchRepo(db)
            await repo.ensure_default()

            class Mirror:
                def __init__(self):
                    self.engaged = False

                def engage(self, *, by, reason):
                    self.engaged = True

                def disengage(self, *, by, reason):
                    self.engaged = False

                def is_engaged(self):
                    return self.engaged

            m = Mirror()
            repo.bind_memory_mirror(m)
            await repo.engage("incident", actor="op")
            assert m.is_engaged() is True
            with pytest.raises(KillSwitchEngagedError):
                await repo.guard()
            auth = await read_authoritative_kill(repo)
            assert auth.engaged is True
            assert auth.source == "persistent"
            await repo.disengage("clear", actor="admin")
            assert m.is_engaged() is False
            await repo.guard()  # must not raise

        asyncio.run(_run())

    def test_unavailable_state_fail_closed(self):
        async def _run():
            class Boom:
                async def state(self):
                    raise RuntimeError("db_down")

            auth = await read_authoritative_kill(Boom())
            assert auth.engaged is True
            assert auth.source == "fail_closed_unavailable"

        asyncio.run(_run())


class TestC2KillVsSend:
    def test_engage_during_critical_section_denies_send(self):
        async def _run():
            db = _MemDB()
            repo = KillSwitchRepo(db)
            await repo.ensure_default()
            section = SendCriticalSection()
            sent = {"n": 0}

            async def send():
                sent["n"] += 1
                return "0xabc"

            # First: disengaged — send proceeds
            out = await section.run_send(kill_switch=repo, send_coro_factory=send)
            assert out == "0xabc"
            assert sent["n"] == 1

            await repo.engage("race", actor="op")
            with pytest.raises(KillSwitchEngagedError):
                await section.run_send(kill_switch=repo, send_coro_factory=send)
            assert sent["n"] == 1  # not incremented

        asyncio.run(_run())


class TestC3TxByteImmutability:
    def test_mutation_after_validate_denied(self):
        tx = {
            "to": "0xabc",
            "data": "0xdead",
            "value": 0,
            "chainId": 8453,
            "nonce": 1,
            "gas": 21000,
            "gasPrice": 1,
        }
        binding = TxByteBinding.from_tx(tx)
        mutated = dict(tx)
        mutated["data"] = "0xbeef"
        with pytest.raises(PermissionError, match="tx_byte_immutability"):
            binding.assert_matches(mutated)
        binding.assert_matches(tx)  # original still ok


class TestC4ChainAllowlist:
    def test_base_allowed_foreign_denied(self):
        assert assert_chain_allowed("base", 8453) == 8453
        with pytest.raises(ChainPolicyError):
            assert_chain_allowed("ethereum", 1)
        with pytest.raises(ChainPolicyError):
            assert_chain_allowed("base", 1)  # wrong id
        with pytest.raises(ChainPolicyError):
            assert_chain_ceiling("base", 10_000.0)
        assert_chain_ceiling("base", 100.0)


class TestC5DurableBudgets:
    def test_ceiling_blocks_and_preserves_total(self):
        async def _run():
            db = _MemDB()
            store = DurableBudgetStore(db)
            ok, total = await store.add_and_check("daily_loss:flash", 40.0, ceiling=100.0)
            assert ok and total == 40.0
            ok2, total2 = await store.add_and_check("daily_loss:flash", 70.0, ceiling=100.0)
            assert ok2 is False
            # Reverted — still 40
            assert abs(await store.get("daily_loss:flash") - 40.0) < 1e-9

        asyncio.run(_run())


class TestC6NonceCoordination:
    def test_concurrent_allocate_serialized(self):
        async def _run():
            coord = NonceCoordinator()
            coord.claim_writer("inst-a")
            with pytest.raises(PermissionError, match="single-writer"):
                coord.claim_writer("inst-b")

            n1 = await coord.allocate("0xabc", 5)
            n2 = await coord.allocate("0xabc", 5)
            assert n1 == 5
            assert n2 == 6  # serialized next

        asyncio.run(_run())


class TestC7TvCleanup:
    def test_failed_tv_clears_allowances(self):
        async def _run():
            db = _MemDB()
            db["arbicore_tv_allowances"].docs["a1"] = {
                "key": "a1",
                "opportunity_id": "opp-1",
                "status": "FAILED",
            }
            db["arbicore_technical_validations"].docs["r1"] = {
                "key": "r1",
                "opportunity_id": "opp-1",
                "engine_ready": False,
                "live_eligible": True,
            }
            out = await cleanup_failed_technical_validation(
                db, opportunity_id="opp-1",
            )
            assert out["ok"] is True
            assert out["allowances_deleted"] >= 1
            row = db["arbicore_technical_validations"].docs["r1"]
            assert row.get("live_eligible") is False
            assert row.get("cleanup") == "expired"

        asyncio.run(_run())
