"""Approval Proposer — background worker.

Every 15 s:
  1. Rebuilds the ranked proposal snapshot (`approval_workflow.build_proposals`).
  2. Persists the snapshot into `proposed_cycles_snapshots` (TTL 1 h)
     so the Approval Console + audit can replay recent state.
  3. Marks the current best PRIMARY (if any) in `proposed_cycles_current`
     (single-doc upsert) — used as the canonical "what would Auto Mode do".

Read-only, never signs, never moves funds. Independent of operator activity:
this is the autonomous pipeline that drives Approval Required Mode.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

from services import db
from services.execution import approval_workflow as approval_wf

logger = logging.getLogger("approval_proposer")

PROPOSER_INTERVAL_S = 15


class ApprovalProposer:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self.last_run_at: str | None = None
        self.last_run_status: str = "idle"
        self.last_error: str | None = None
        self.iterations: int = 0
        self.last_primary_id: str | None = None
        # ArbiCore X Phase C Wave 5 (Shadow Binding): optional async hook
        # invoked after every successful proposal-build cycle with the
        # snapshot dict. Failures in the hook MUST NOT impact this loop.
        self.post_run_hook = None  # type: ignore[assignment]

    async def ensure_indexes(self):
        c = db.db.proposed_cycles_snapshots
        # TTL: snapshots auto-expire after 1 h
        await c.create_index("created_at_dt", expireAfterSeconds=3600)
        await c.create_index([("created_at_ts", -1)])

    async def _run_once(self):
        snap = await approval_wf.build_proposals()
        now_ts = int(time.time())
        now_dt = datetime.now(timezone.utc)
        primary = snap.get("primary")
        doc = {
            "created_at": now_dt.isoformat(),
            "created_at_ts": now_ts,
            "created_at_dt": now_dt,
            "primary": primary,
            "secondary": snap.get("secondary") or [],
            "ranked_count": snap.get("ranked_count", 0),
            "actionable_count": snap.get("actionable_count", 0),
            "blockers": snap.get("blockers") or [],
            "min_roi_threshold_pct": snap.get("min_roi_threshold_pct"),
            "staleness_threshold_s": snap.get("staleness_threshold_s"),
        }
        await db.db.proposed_cycles_snapshots.insert_one(dict(doc))
        # Upsert "current" — single doc, easy fetch
        await db.db.proposed_cycles_current.update_one(
            {"_key": "current"}, {"$set": {**doc, "_key": "current"}}, upsert=True)

        self.last_primary_id = primary["proposal_id"] if primary else None
        self.last_run_at = now_dt.isoformat()
        self.last_run_status = "ok"
        self.iterations += 1

        # ArbiCore X Phase C Wave 5: shadow-binding hook. Strict zero-impact
        # rule: any exception is swallowed; the legacy loop continues
        # untouched.
        hook = getattr(self, "post_run_hook", None)
        if hook is not None:
            try:
                await hook(snap)
            except Exception as exc:  # noqa: BLE001
                logger.warning("approval_proposer.post_run_hook failed: %s", exc)

    async def _loop(self):
        await self.ensure_indexes()
        await asyncio.sleep(2)  # let other services boot
        while not self._stop.is_set():
            try:
                await self._run_once()
                self.last_error = None
            except Exception as e:  # noqa: BLE001
                self.last_run_status = "error"
                self.last_error = repr(e)
                logger.warning("approval_proposer iteration failed: %s", e)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=PROPOSER_INTERVAL_S)
            except asyncio.TimeoutError:
                pass

    async def start(self):
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop())
        logger.info("approval_proposer started (interval=%ss)", PROPOSER_INTERVAL_S)

    async def stop(self):
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=3)
            except asyncio.TimeoutError:
                self._task.cancel()
        self._task = None

    async def status(self) -> dict:
        return {
            "running": bool(self._task and not self._task.done()),
            "interval_s": PROPOSER_INTERVAL_S,
            "iterations": self.iterations,
            "last_run_at": self.last_run_at,
            "last_run_status": self.last_run_status,
            "last_error": self.last_error,
            "last_primary_id": self.last_primary_id,
        }


approval_proposer = ApprovalProposer()


async def current_snapshot() -> dict | None:
    doc = await db.db.proposed_cycles_current.find_one({"_key": "current"}, {"_id": 0, "_key": 0, "created_at_dt": 0})
    return doc


async def recent_snapshots(limit: int = 20) -> list[dict]:
    cur = db.db.proposed_cycles_snapshots.find(
        {}, {"_id": 0, "created_at_dt": 0}).sort("created_at_ts", -1).limit(limit)
    return await cur.to_list(limit)
