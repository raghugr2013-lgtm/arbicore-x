"""v2.11.8 hotfix — Regression test for the IndexOptionsConflict on
``arbicore_opportunities``.

Before this fix, ``MongoOpportunityRepository.ensure_indexes()`` called
``create_index`` without an explicit ``name`` kwarg on a collection that
the canonical boot indexer had already populated with named indexes.
Mongo raised ``IndexOptionsConflict`` because the *auto-generated name*
differed from the existing name — even though every other option
matched.

This test spins up a Motor-backed collection with the exact live-index
set reported by the VPS audit and then exercises
:meth:`MongoOpportunityRepository.ensure_indexes` to prove it now
tolerates the pre-existing indexes.
"""
from __future__ import annotations

import asyncio
import os
import uuid

import pytest


pytestmark = pytest.mark.asyncio


def _mongo_url() -> str:
    return (os.environ.get("MONGO_URL") or "").strip()


def _db_name() -> str:
    return (os.environ.get("DB_NAME") or "").strip()


@pytest.mark.skipif(not (_mongo_url() and _db_name()),
                     reason="requires MONGO_URL + DB_NAME in env")
def test_ensure_indexes_is_idempotent_against_named_indexes():
    """Reproduce the VPS state, then ensure the fixed repo is happy."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mongo.opportunity_repo_mongo import MongoOpportunityRepository

    class _RepoBoundToTestCol(MongoOpportunityRepository):
        """Subclass with ``_col`` bound to a throwaway collection."""
        def __init__(self, db, col):
            super().__init__(db)
            self.__col_override = col
        @property
        def _col(self):
            return self.__col_override

    async def _run():
        client = AsyncIOMotorClient(_mongo_url())
        db = client[_db_name()]
        coll_name = f"arbicore_opportunities_test_{uuid.uuid4().hex[:8]}"
        col = db[coll_name]
        try:
            # 1. Recreate the EXACT live-index state from the VPS audit.
            await col.create_index("opportunity_id",
                                    unique=True, name="opportunity_id_unique")
            await col.create_index("subject_id", name="subject_id_idx")
            await col.create_index([("opportunity_type", 1), ("status", 1)],
                                    name="type_status_idx")
            await col.create_index([("created_at", -1)], name="created_at_desc")

            pre = [dict(i) async for i in col.list_indexes()]
            pre_names = {i["name"] for i in pre}
            assert {"opportunity_id_unique", "subject_id_idx",
                     "type_status_idx", "created_at_desc"} <= pre_names

            # 2. Call ensure_indexes(). Must NOT raise IndexOptionsConflict.
            repo = _RepoBoundToTestCol(db, col)
            await repo.ensure_indexes()

            # 3. No auto-named duplicates leaked; no drops.
            post = [dict(i) async for i in col.list_indexes()]
            post_names = {i["name"] for i in post}
            assert {"opportunity_id_unique", "subject_id_idx",
                     "type_status_idx", "created_at_desc"} <= post_names
            for auto in ("opportunity_id_1", "subject_id_1",
                          "opportunity_type_1_status_1",
                          "created_at_-1"):
                assert auto not in post_names, (
                    f"idempotent path leaked auto-named index {auto!r}"
                )
            assert len(post) == len(pre)
        finally:
            try:
                await col.drop()
            except Exception:
                pass
            client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not (_mongo_url() and _db_name()),
                     reason="requires MONGO_URL + DB_NAME in env")
def test_ensure_indexes_creates_on_empty_collection():
    """When the collection is brand new the repo must actually create
    the four canonical indexes with the canonical names."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mongo.opportunity_repo_mongo import MongoOpportunityRepository

    class _RepoBoundToTestCol(MongoOpportunityRepository):
        def __init__(self, db, col):
            super().__init__(db)
            self.__col_override = col
        @property
        def _col(self):
            return self.__col_override

    async def _run():
        client = AsyncIOMotorClient(_mongo_url())
        db = client[_db_name()]
        coll_name = f"arbicore_opportunities_empty_{uuid.uuid4().hex[:8]}"
        col = db[coll_name]
        try:
            repo = _RepoBoundToTestCol(db, col)
            await repo.ensure_indexes()
            indexes = [dict(i) async for i in col.list_indexes()]
            names = {i["name"] for i in indexes}
            assert "_id_" in names
            assert "opportunity_id_unique" in names
            assert "subject_id_idx" in names
            assert "type_status_idx" in names
            assert "created_at_desc" in names
        finally:
            try:
                await col.drop()
            except Exception:
                pass
            client.close()

    asyncio.run(_run())


@pytest.mark.skipif(not (_mongo_url() and _db_name()),
                     reason="requires MONGO_URL + DB_NAME in env")
def test_ensure_indexes_tolerates_legacy_auto_named_indexes():
    """Simulate the OPPOSITE of the VPS state — a DB where a previous
    process created the four indexes with auto-generated names
    (opportunity_id_1, subject_id_1, …).  The repo must still not raise:
    the auto-named index already covers the key spec, so the repo
    correctly skips the create call rather than layering a differently-
    named duplicate on top."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from arbicore.data.mongo.opportunity_repo_mongo import MongoOpportunityRepository

    class _RepoBoundToTestCol(MongoOpportunityRepository):
        def __init__(self, db, col):
            super().__init__(db)
            self.__col_override = col
        @property
        def _col(self):
            return self.__col_override

    async def _run():
        client = AsyncIOMotorClient(_mongo_url())
        db = client[_db_name()]
        coll_name = f"arbicore_opportunities_legacy_{uuid.uuid4().hex[:8]}"
        col = db[coll_name]
        try:
            # Legacy auto-named indexes (what the pre-fix repo would have
            # created).
            await col.create_index("opportunity_id", unique=True)
            await col.create_index("subject_id")
            await col.create_index([("opportunity_type", 1), ("status", 1)])
            await col.create_index([("created_at", -1)])
            pre = {i["name"] async for i in col.list_indexes()}
            assert "opportunity_id_1" in pre

            # Must complete without raising.
            repo = _RepoBoundToTestCol(db, col)
            await repo.ensure_indexes()

            post = {i["name"] async for i in col.list_indexes()}
            # No canonical duplicates layered on top.
            assert "opportunity_id_unique" not in post
            assert "subject_id_idx" not in post
            # Original auto-named indexes still cover the key specs.
            assert "opportunity_id_1" in post
            assert "subject_id_1" in post
        finally:
            try:
                await col.drop()
            except Exception:
                pass
            client.close()

    asyncio.run(_run())
