"""Venue Configuration Registry (E2) — configurable role assignment for the
execution venues. Single source of truth for Primary / Backup / Watch roles so
NO exchange is hardcoded in the execution layer; everything resolves here.

Roles:
  primary  — the venue the execution layer would target first (default Coinstore)
  backup   — fallback venue (default BitMart)
  watch    — monitored but not an execution target (default XT)
  disabled — excluded from execution consideration
"""
from core import registry as conn_registry
from core.models import new_id, now_iso
from services import db

ROLES = ["primary", "backup", "watch", "disabled"]

# Exchange-side automation capability surface, per the docs/20 readiness audit.
# Describes which API legs exist; live deposit-gate status is layered on top by
# the classification engine (which reads the live capability registry).
VENUE_AUTOMATION = {
    "coinstore": {"deposit_address_api": True, "deposit_history_api": True,
                  "trade_api": True, "withdraw_api": True, "verified_address_book": True,
                  "audit_score": 92,
                  "notes": "User-verified India loop; full API chain incl. doWithdraw to verified addresses."},
    "bitmart": {"deposit_address_api": True, "deposit_history_api": True,
                "trade_api": True, "withdraw_api": True, "verified_address_book": True,
                "audit_score": 90,
                "notes": "Full API surface; needs one ~$20 manual loop verification before promotion."},
    "xt": {"deposit_address_api": True, "deposit_history_api": True,
           "trade_api": True, "withdraw_api": True, "verified_address_book": True,
           "audit_score": 72,
           "notes": "Conditional — BDAG deposit gate currently CLOSED in reality."},
    "mexc": {"deposit_address_api": True, "deposit_history_api": True,
             "trade_api": True, "withdraw_api": True, "verified_address_book": False,
             "audit_score": None, "notes": "BDAG not listed — not an execution candidate."},
    "gate": {"deposit_address_api": True, "deposit_history_api": True,
             "trade_api": True, "withdraw_api": True, "verified_address_book": False,
             "audit_score": None, "notes": "BDAG not listed — not an execution candidate."},
}

DEFAULT_ROLES = {"coinstore": "primary", "bitmart": "backup", "xt": "watch",
                 "mexc": "disabled", "gate": "disabled"}


def _name(exchange: str) -> str:
    try:
        return conn_registry.resolve(exchange, "live").name
    except Exception:
        return exchange.upper()


async def ensure_seeded():
    for ex, role in DEFAULT_ROLES.items():
        existing = await db.venue_registry.find_one({"exchange": ex})
        if not existing:
            await db.venue_registry.insert_one({
                "id": new_id(), "exchange": ex, "name": _name(ex), "role": role,
                "automation": VENUE_AUTOMATION.get(ex, {}),
                "enabled": role != "disabled",
                "created_at": now_iso(), "updated_at": now_iso()})


_ROLE_ORDER = {"primary": 0, "backup": 1, "watch": 2, "disabled": 3}


async def list_venues():
    docs = await db.venue_registry.find({}, {"_id": 0}).to_list(100)
    docs.sort(key=lambda d: _ROLE_ORDER.get(d.get("role"), 9))
    return docs


async def get_role_map() -> dict:
    docs = await db.venue_registry.find({}, {"_id": 0, "exchange": 1, "role": 1}).to_list(100)
    return {d["exchange"]: d["role"] for d in docs}


async def primary():
    doc = await db.venue_registry.find_one({"role": "primary"}, {"_id": 0})
    return doc["exchange"] if doc else None


async def set_role(exchange: str, role: str):
    if role not in ROLES:
        raise ValueError(f"invalid role '{role}'; allowed: {ROLES}")
    if role == "primary":  # only one primary at a time — demote any existing primary to backup
        await db.venue_registry.update_many(
            {"role": "primary", "exchange": {"$ne": exchange}},
            {"$set": {"role": "backup", "updated_at": now_iso()}})
    await db.venue_registry.update_one(
        {"exchange": exchange},
        {"$set": {"role": role, "enabled": role != "disabled", "updated_at": now_iso()},
         "$setOnInsert": {"id": new_id(), "exchange": exchange, "name": _name(exchange),
                          "automation": VENUE_AUTOMATION.get(exchange, {}),
                          "created_at": now_iso()}},
        upsert=True)
    return await db.venue_registry.find_one({"exchange": exchange}, {"_id": 0})
