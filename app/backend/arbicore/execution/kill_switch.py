"""Wave 6D · Kill Switch.

Global emergency stop.  When engaged:

    * ``guard()`` raises ``KillSwitchEngagedError`` for any live-signing
      or broadcast call.  Wave 6C simulation, plan building, and
      read-only endpoints remain functional (operators may need to
      inspect the state during an incident).
    * Every trading strategy is automatically pinned to at most
      ``SHADOW`` for the purposes of the broadcast gate (the mode
      ladder itself is unchanged; the kill switch is a *stronger*
      overlay that is checked before the ladder).

Engagement / disengagement is fully audited to
``db.kill_switch_audit`` with actor, reason, and timestamp.  A
Wave-5 signed evidence bundle is emitted for every transition when
signing is configured (this happens through the existing signing
worker via a lightweight source-component tap; see Wave 6E wiring).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class KillSwitchEngagedError(PermissionError):
    """Raised by ``KillSwitchRepo.guard()`` when the switch is engaged."""


@dataclass(frozen=True)
class KillSwitchState:
    engaged: bool
    reason: Optional[str]
    actor: Optional[str]
    engaged_at: Optional[str]
    last_disengaged_at: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class KillSwitchRepo:
    """Singleton-ish: one row per environment.  ``key`` fixed to ``global``."""

    KEY = "global"

    def __init__(self, db,
                 collection: str = "kill_switch_state",
                 audit_collection: str = "kill_switch_audit"):
        self._db = db
        self._coll = db[collection]
        self._audit = db[audit_collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._coll.create_index("key", unique=True)
        await self._audit.create_index([("at", -1)])
        self._indexes_ready = True

    async def ensure_default(self) -> None:
        """Seed the disengaged state.  Idempotent."""
        existing = await self._coll.find_one({"key": self.KEY}, {"_id": 0})
        if existing:
            return
        now = _now_iso()
        await self._coll.insert_one({
            "key": self.KEY, "engaged": False, "reason": None, "actor": None,
            "engaged_at": None, "last_disengaged_at": now, "updated_at": now,
        })

    async def state(self) -> KillSwitchState:
        doc = await self._coll.find_one({"key": self.KEY}, {"_id": 0}) or {}
        return KillSwitchState(
            engaged=bool(doc.get("engaged")),
            reason=doc.get("reason"),
            actor=doc.get("actor"),
            engaged_at=doc.get("engaged_at"),
            last_disengaged_at=doc.get("last_disengaged_at"),
        )

    # Optional sync hook for in-memory mirrors (WP-C / C1). Set by server boot.
    _memory_mirror = None  # type: ignore[var-annotated]

    def bind_memory_mirror(self, mirror) -> None:
        """Bind an in-memory KillSwitch-like object (``engage``/``disengage``/``is_engaged``).

        Persistent store remains the sole source of truth; the mirror is updated
        after successful persistent transitions so sync callers see the same flag.
        """
        self._memory_mirror = mirror

    def _sync_mirror_engaged(self, *, engaged: bool, actor: str, reason: str) -> None:
        mirror = self._memory_mirror
        if mirror is None:
            return
        try:
            if engaged and hasattr(mirror, "engage"):
                mirror.engage(by=actor, reason=reason)
            elif (not engaged) and hasattr(mirror, "disengage"):
                mirror.disengage(by=actor, reason=reason)
        except Exception:  # noqa: BLE001 — mirror must never block authoritative path
            pass

    async def engage(self, reason: str, actor: str = "operator") -> KillSwitchState:
        now = _now_iso()
        await self._coll.update_one(
            {"key": self.KEY},
            {"$set": {"engaged": True, "reason": reason, "actor": actor,
                      "engaged_at": now, "updated_at": now},
             "$setOnInsert": {"key": self.KEY}},
            upsert=True,
        )
        await self._audit.insert_one({
            "action": "engage", "reason": reason, "actor": actor, "at": now,
        })
        self._sync_mirror_engaged(engaged=True, actor=actor, reason=reason)
        return await self.state()

    async def disengage(self, reason: str, actor: str = "operator") -> KillSwitchState:
        """Disengage the persistent kill switch (fail-closed on audit write).

        WP-B / F-AUTH-03: audit is written *before* clearing engaged state so an
        audit persistence failure cannot leave the switch silently disengaged
        without a record. ``actor`` must be the server-derived identity — never
        a client-supplied body field.
        """
        now = _now_iso()
        # Audit first — if this fails, state remains unchanged (fail-closed).
        await self._audit.insert_one({
            "action": "disengage", "reason": reason, "actor": actor, "at": now,
        })
        await self._coll.update_one(
            {"key": self.KEY},
            {"$set": {"engaged": False, "reason": None, "actor": None,
                      "engaged_at": None, "last_disengaged_at": now,
                      "updated_at": now},
             "$setOnInsert": {"key": self.KEY}},
            upsert=True,
        )
        self._sync_mirror_engaged(engaged=False, actor=actor, reason=reason)
        return await self.state()

    async def guard(self) -> None:
        """Called by every live-signer / broadcast path before signing.

        WP-C: re-reads persistent state every call (no sticky cache). Unavailable
        state fails closed as engaged.
        """
        try:
            st = await self.state()
        except Exception as exc:  # noqa: BLE001
            raise KillSwitchEngagedError(
                f"kill switch state unavailable (fail-closed): {type(exc).__name__}"
            ) from exc
        if st.engaged:
            raise KillSwitchEngagedError(
                f"kill switch engaged (reason: {st.reason or 'n/a'}); "
                f"actor: {st.actor or 'n/a'}; at: {st.engaged_at or 'n/a'}"
            )

    async def audit_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        cur = self._audit.find({}, {"_id": 0}).sort("at", -1).limit(limit)
        return await cur.to_list(limit)
