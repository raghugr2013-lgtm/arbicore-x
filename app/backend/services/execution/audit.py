"""Append-only execution audit log (E2 scaffold).

One immutable entry per state transition / side-effect intent + result. The
source of truth for "what happened, in what order, with which idempotency key".
In E2 every entry is flagged simulated=True (no real side effects).
"""
from core.models import new_id, now_iso
from services import db


async def record(cycle_id: str, step: str, phase: str, idempotency_key=None,
                 external_ref=None, amounts=None, actor: str = "system", note=None):
    """phase: 'intent' | 'result' | 'recovery'. Append-only — never updated/deleted."""
    try:
        await db.execution_audit.insert_one({
            "id": new_id(), "ts": now_iso(), "created_at": now_iso(),
            "cycle_id": cycle_id, "step": step, "phase": phase,
            "idempotency_key": idempotency_key, "external_ref": external_ref,
            "amounts": amounts, "actor": actor, "note": note, "simulated": True})
    except Exception:
        pass


async def trail(cycle_id: str, limit: int = 300):
    return await db.execution_audit.find({"cycle_id": cycle_id}, {"_id": 0},
                                         sort=[("ts", 1)]).to_list(limit)
