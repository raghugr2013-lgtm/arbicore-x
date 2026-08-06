"""Shadow Certification repositories (v2.11.9).

Two implementations that share the same async surface:

* :class:`InMemoryShadowCertificationRepository` — deterministic,
  used by unit tests and for fail-open bring-up (never depends on Mongo
  being reachable at import time).
* :class:`MongoShadowCertificationRepository` — production surface;
  writes to the ``arbicore_shadow_certifications`` collection.

Persistence contract:

* Insert-then-replace under the same ``run_id``.  A finalise operation
  ships a completed run; append operations ship a new intermediate.
  The repo never mutates in-place — the caller feeds a NEW run instance
  each time and the repo replaces the mongo doc keyed on ``run_id``.
* ``run_id`` unique index.
* ``status + started_at`` compound index for listing.

Fail-open reads: every read method that raises returns ``None`` /
``[]`` so a Mongo hiccup can never crash the certification endpoints.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .models import ShadowCertificationRun

logger = logging.getLogger(__name__)


class InMemoryShadowCertificationRepository:
    """Volatile Shadow Certification store."""

    def __init__(self) -> None:
        self._runs: Dict[str, ShadowCertificationRun] = {}

    async def ensure_indexes(self) -> None:  # parity with Mongo repo
        return None

    async def upsert(self, run: ShadowCertificationRun) -> str:
        self._runs[run.run_id] = run
        return run.run_id

    async def get(self, run_id: str) -> Optional[ShadowCertificationRun]:
        return self._runs.get(run_id)

    async def current_running(self) -> Optional[ShadowCertificationRun]:
        for r in self._runs.values():
            if r.status == "RUNNING":
                return r
        return None

    async def list_recent(
        self, *, limit: int = 50, status: Optional[str] = None
    ) -> List[ShadowCertificationRun]:
        items = list(self._runs.values())
        if status:
            items = [r for r in items if r.status == status]
        items.sort(key=lambda r: r.started_at or "", reverse=True)
        return items[: int(limit)]

    async def count(self, *, status: Optional[str] = None) -> int:
        if status is None:
            return len(self._runs)
        return sum(1 for r in self._runs.values() if r.status == status)


class MongoShadowCertificationRepository:
    """Mongo-backed Shadow Certification repository.

    Collection: ``arbicore_shadow_certifications``.

    Idempotent index creation — matches the Paper Validation and
    ArbiCore-opportunity repos' pattern.  Existing indexes with the same
    key spec are left untouched to avoid ``IndexOptionsConflict``.
    """

    COLLECTION = "arbicore_shadow_certifications"

    def __init__(self, db) -> None:
        if db is None:
            raise ValueError(
                "MongoShadowCertificationRepository requires a Mongo db handle"
            )
        self._db = db
        self._col = db[self.COLLECTION]

    async def ensure_indexes(self) -> None:
        wanted = [
            {"key": [("run_id", 1)], "name": "uniq_run_id", "unique": True},
            {
                "key": [("status", 1), ("started_at", -1)],
                "name": "status_recent",
            },
            {"key": [("started_at", -1)], "name": "recent"},
        ]
        try:
            existing = await self._col.index_information()
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "MongoShadowCertificationRepository index_information failed: %s",
                exc,
            )
            existing = {}
        existing_key_specs = {
            tuple(v.get("key") or []) for v in existing.values()
        }
        for spec in wanted:
            key_tuple = tuple(spec["key"])
            if key_tuple in existing_key_specs:
                continue
            try:
                await self._col.create_index(
                    spec["key"],
                    name=spec["name"],
                    unique=spec.get("unique", False),
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "MongoShadowCertificationRepository create_index(%s) failed: %s",
                    spec["name"],
                    exc,
                )

    async def upsert(self, run: ShadowCertificationRun) -> str:
        doc = run.to_mongo()
        await self._col.update_one(
            {"run_id": run.run_id},
            {"$set": doc},
            upsert=True,
        )
        return run.run_id

    async def get(self, run_id: str) -> Optional[ShadowCertificationRun]:
        try:
            doc = await self._col.find_one({"run_id": run_id})
        except Exception as exc:  # noqa: BLE001
            logger.warning("shadow_cert.get(%s) failed: %s", run_id, exc)
            return None
        if not doc:
            return None
        doc.pop("_id", None)
        return ShadowCertificationRun.from_mongo(doc)

    async def current_running(self) -> Optional[ShadowCertificationRun]:
        try:
            doc = await self._col.find_one(
                {"status": "RUNNING"}, sort=[("started_at", -1)]
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("shadow_cert.current_running failed: %s", exc)
            return None
        if not doc:
            return None
        doc.pop("_id", None)
        return ShadowCertificationRun.from_mongo(doc)

    async def list_recent(
        self, *, limit: int = 50, status: Optional[str] = None
    ) -> List[ShadowCertificationRun]:
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        try:
            cur = self._col.find(q, sort=[("started_at", -1)]).limit(int(limit))
            out: List[ShadowCertificationRun] = []
            async for doc in cur:
                doc.pop("_id", None)
                out.append(ShadowCertificationRun.from_mongo(doc))
            return out
        except Exception as exc:  # noqa: BLE001
            logger.warning("shadow_cert.list_recent failed: %s", exc)
            return []

    async def count(self, *, status: Optional[str] = None) -> int:
        q: Dict[str, Any] = {}
        if status:
            q["status"] = status
        try:
            return await self._col.count_documents(q)
        except Exception as exc:  # noqa: BLE001
            logger.warning("shadow_cert.count failed: %s", exc)
            return 0
