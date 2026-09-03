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

# Lifecycle states for an ingested candidate. It can NEVER reach an executable
# state from here — it must independently pass the existing downstream gates.
LIFECYCLE_INGESTED = "INGESTED"        # accepted as data; not yet evaluated
LIFECYCLE_REJECTED = "REJECTED"        # failed IR validation


async def ensure_indexes() -> None:
    await _registry.create_index([("strategy_fingerprint", 1), ("strategy_version", 1)],
                                 unique=True)
    await _registry.create_index("strategy_id")
    await _candidates.create_index("strategy_id")
    await _candidates.create_index([("strategy_fingerprint", 1), ("strategy_version", 1)])
    await _candidates.create_index("created_at")


async def register(ir: StrategyIR) -> Dict[str, Any]:
    """Persist a validated IR. Returns {registered, duplicate, candidate_id,
    strategy_fingerprint, strategy_version}. Duplicate (same fingerprint+version)
    is idempotent — not an error."""
    await ensure_indexes()
    doc = ir.to_registry_doc()
    reg_entry = {
        "strategy_id": doc["strategy_id"],
        "strategy_fingerprint": doc["strategy_fingerprint"],
        "strategy_version": doc["strategy_version"],
        "strategy_type": doc["strategy_type"],
        "source_class": doc["source_class"],
        "provenance": doc["provenance"],
        "lineage": doc["lineage"],
        "created_at": now_iso(),
    }
    duplicate = False
    try:
        await _registry.insert_one(dict(reg_entry))
    except DuplicateKeyError:
        duplicate = True

    candidate = {
        **doc,
        "lifecycle_state": LIFECYCLE_INGESTED,
        "executable": False,          # explicit, immutable at ingestion
        "ingested_at": now_iso(),
    }
    await _candidates.insert_one(dict(candidate))
    return {
        "registered": not duplicate,
        "duplicate": duplicate,
        "strategy_id": doc["strategy_id"],
        "strategy_fingerprint": doc["strategy_fingerprint"],
        "strategy_version": doc["strategy_version"],
        "lifecycle_state": LIFECYCLE_INGESTED,
    }


async def list_candidates(limit: int = 100) -> List[Dict[str, Any]]:
    cur = _candidates.find({}, {"_id": 0}).sort("created_at", -1).limit(int(limit))
    return [d async for d in cur]


async def get_registry_entry(strategy_id: str) -> Optional[Dict[str, Any]]:
    return await _registry.find_one({"strategy_id": strategy_id}, {"_id": 0})
