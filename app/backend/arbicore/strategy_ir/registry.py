"""Strategy IR registry + candidate store — additive Mongo collections only.

Collections (created lazily, never migrated/reset):
  * strategy_registry   — canonical identity keyed by (fingerprint, version)
  * strategy_candidates — ingested IR + validation/lifecycle status
No existing collection is touched.
"""
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from core.models import now_iso
from services import db as _dbmod
from .schema import StrategyIR

_registry = _dbmod.db["strategy_registry"]
_candidates = _dbmod.db["strategy_candidates"]
_indexes_ready = False

# Lifecycle states for an ingested candidate. It can NEVER reach an executable
# state from here — it must independently pass the existing downstream gates.
LIFECYCLE_INGESTED = "INGESTED"        # accepted as data; not yet evaluated
LIFECYCLE_REJECTED = "REJECTED"        # failed IR validation


async def ensure_indexes() -> None:
    global _indexes_ready
    if _indexes_ready:
        return
    await _registry.create_index([("strategy_fingerprint", 1), ("strategy_version", 1)],
                                 unique=True)
    await _registry.create_index("strategy_id")
    try:
        await _candidates.create_index(
            [("strategy_fingerprint", 1), ("strategy_version", 1)], unique=True)
    except Exception:  # noqa: BLE001 — pre-existing non-unique index of same keys
        try:
            await _candidates.drop_index("strategy_fingerprint_1_strategy_version_1")
        except Exception:  # noqa: BLE001
            pass
        await _candidates.create_index(
            [("strategy_fingerprint", 1), ("strategy_version", 1)], unique=True)
    await _candidates.create_index("strategy_id")
    await _candidates.create_index("created_at")
    _indexes_ready = True


async def register(ir: StrategyIR) -> Dict[str, Any]:
    """Persist a validated IR. Returns {registered, duplicate, strategy_id,
    strategy_fingerprint, strategy_version, lifecycle_state}. Duplicate (same
    fingerprint+version) is idempotent — the CANONICAL already-registered
    strategy_id is returned (never a fresh, unresolvable id)."""
    await ensure_indexes()
    doc = ir.to_registry_doc()
    fp, ver = doc["strategy_fingerprint"], doc["strategy_version"]
    reg_entry = {
        "strategy_id": doc["strategy_id"],
        "strategy_fingerprint": fp,
        "strategy_version": ver,
        "strategy_type": doc["strategy_type"],
        "source_class": doc["source_class"],
        "provenance": doc["provenance"],
        "lineage": doc["lineage"],
        "created_at": now_iso(),
    }
    duplicate = False
    try:
        await _registry.insert_one(dict(reg_entry))
        canonical_id = doc["strategy_id"]
    except DuplicateKeyError:
        duplicate = True
        existing = await _registry.find_one({"strategy_fingerprint": fp,
                                             "strategy_version": ver}, {"_id": 0})
        canonical_id = (existing or {}).get("strategy_id", doc["strategy_id"])

    # One candidate row per (fingerprint, version); dedup via upsert + counter.
    candidate = {**doc, "strategy_id": canonical_id,
                 "lifecycle_state": LIFECYCLE_INGESTED, "executable": False}
    await _candidates.update_one(
        {"strategy_fingerprint": fp, "strategy_version": ver},
        {"$setOnInsert": {**candidate, "ingested_at": now_iso()},
         "$set": {"last_ingested_at": now_iso()},
         "$inc": {"ingest_count": 1}},
        upsert=True)
    return {
        "registered": not duplicate,
        "duplicate": duplicate,
        "strategy_id": canonical_id,
        "strategy_fingerprint": fp,
        "strategy_version": ver,
        "lifecycle_state": LIFECYCLE_INGESTED,
    }


async def list_candidates(limit: int = 100) -> List[Dict[str, Any]]:
    cur = _candidates.find({}, {"_id": 0}).sort("created_at", -1).limit(int(limit))
    return [d async for d in cur]


async def get_registry_entry(strategy_id: str) -> Optional[Dict[str, Any]]:
    return await _registry.find_one({"strategy_id": strategy_id}, {"_id": 0})


async def get_candidate(strategy_id: str) -> Optional[Dict[str, Any]]:
    return await _candidates.find_one({"strategy_id": strategy_id}, {"_id": 0})
