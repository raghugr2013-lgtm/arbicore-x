"""Capability Registry persistence (Sprint 3) — current deposit/withdraw gates
per exchange+asset in `capabilities`, with every flip appended to
`capability_history` for historical route-feasibility analysis."""
from core.models import new_id, now_iso

from services import db

TRACKED_FIELDS = ("deposit_enabled", "withdraw_enabled")
STATE_FIELDS = ("chain", "deposit_enabled", "withdraw_enabled", "withdraw_fee",
                "withdraw_min", "deposit_confirmations")


async def record(exchange: str, currency: str, fee: dict, route_id: str = None):
    """Upsert current capability state; returns the list of flips detected."""
    currency = currency.upper()
    state = {f: fee.get(f) for f in STATE_FIELDS}
    cur = await db.capabilities_col.find_one({"exchange": exchange, "currency": currency}, {"_id": 0})
    if cur is None:
        await db.capabilities_col.insert_one({
            "id": new_id(), "exchange": exchange, "currency": currency, **state,
            "first_seen": now_iso(), "last_changed": None, "updated_at": now_iso()})
        return []
    flips = []
    for f in TRACKED_FIELDS:
        if cur.get(f) != state.get(f):
            flips.append({"id": new_id(), "exchange": exchange, "currency": currency,
                          "field": f, "from": cur.get(f), "to": state.get(f),
                          "ts": now_iso(), "route_id": route_id})
    if flips:
        await db.capability_history.insert_many([dict(f) for f in flips])
    updates = {**state, "updated_at": now_iso()}
    if flips:
        updates["last_changed"] = now_iso()
    await db.capabilities_col.update_one(
        {"exchange": exchange, "currency": currency}, {"$set": updates})
    return flips
