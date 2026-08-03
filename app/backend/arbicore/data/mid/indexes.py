"""MID index + TTL policy definitions.

Called at startup by ``ensure_indexes(db)``. Idempotent; safe on every boot.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .schemas import DOMAINS, MID_COLLECTION_MAP


# Per-domain TTL (in seconds).  ``None`` = permanent.
DEFAULT_TTL_SECONDS: Dict[str, Optional[int]] = {
    "market_state":  90 * 24 * 3600,
    "quotes":        30 * 24 * 3600,
    "liquidity":     90 * 24 * 3600,
    "gas":          180 * 24 * 3600,
    "providers":    365 * 24 * 3600,
    "routes":        None,   # permanent — route history is never dropped
    "opportunities": None,   # permanent — every opportunity is retained
    "confidence":    90 * 24 * 3600,
    "decisions":     None,   # permanent — full audit surface
    "outcomes":      None,   # permanent — training data
    "replay":        30 * 24 * 3600,   # recomputable
}

# Standard metadata-block index set (shared by every collection).
_METADATA_INDEXES: List[List[tuple]] = [
    [("meta.strategy_type", 1), ("ts", -1)],
    [("meta.chain", 1), ("ts", -1)],
    [("meta.execution_mode", 1), ("ts", -1)],
    [("meta.opportunity_type", 1), ("ts", -1)],
    [("meta.capital_source", 1), ("ts", -1)],
    [("meta.market_regime", 1), ("ts", -1)],
    [("ts", -1)],
]

# Domain-specific extra indexes (in addition to metadata + mid_id).
_DOMAIN_INDEXES: Dict[str, List[List[tuple]]] = {
    "market_state":  [[("market_snapshot_id", 1)], [("dex", 1), ("pair", 1), ("ts", -1)]],
    "quotes":        [[("route_id", 1), ("ts", -1)]],
    "liquidity":     [[("dex", 1), ("pool", 1), ("ts", -1)]],
    "gas":           [[("meta.chain", 1), ("ts", -1)]],
    "providers":     [[("provider_id", 1), ("ts", -1)]],
    "routes":        [[("route_id", 1)]],   # UPSERT key
    "opportunities": [[("opp_id", 1), ("event_ordinal", 1)], [("event_id", 1)]],
    "confidence":    [[("opp_id", 1), ("ts", -1)]],
    "decisions":     [[("opp_id", 1), ("gate", 1), ("ts", -1)]],
    "outcomes":      [[("opp_id", 1)], [("terminal", 1), ("ts", -1)]],
    "replay":        [[("opp_id", 1), ("variant_id", 1)]],
}


async def ensure_indexes(db: Any, ttl_overrides: Optional[Dict[str, Optional[int]]] = None) -> Dict[str, Any]:
    """Create all MID indexes + TTL policies.  Idempotent.

    Returns a summary dict {collection: [index_names]} for logging / diagnostics.
    """
    ttl = dict(DEFAULT_TTL_SECONDS)
    if ttl_overrides:
        ttl.update(ttl_overrides)

    summary: Dict[str, Any] = {}

    for domain in DOMAINS:
        coll_name = MID_COLLECTION_MAP[domain]
        coll = db[coll_name]
        idx_created: List[str] = []

        # 1) unique mid_id
        try:
            name = await coll.create_index([("mid_id", 1)], unique=True, name="mid_id_uniq")
            idx_created.append(name)
        except Exception:
            pass  # already exists

        # 2) metadata indexes
        for spec in _METADATA_INDEXES:
            try:
                name = await coll.create_index(spec)
                idx_created.append(name)
            except Exception:
                pass

        # 3) domain-specific
        for spec in _DOMAIN_INDEXES.get(domain, []):
            try:
                unique = (domain == "routes" and spec == [("route_id", 1)])
                if unique:
                    name = await coll.create_index(spec, unique=True, name="route_id_uniq")
                else:
                    name = await coll.create_index(spec)
                idx_created.append(name)
            except Exception:
                pass

        # 4) TTL index on `ts` if applicable
        ttl_s = ttl.get(domain)
        if ttl_s is not None:
            try:
                name = await coll.create_index(
                    [("ts", 1)], expireAfterSeconds=ttl_s, name="ttl_ts"
                )
                idx_created.append(name)
            except Exception:
                # If TTL was previously created with a different expireAfterSeconds,
                # Mongo requires collMod — skip silently (operator adjusts via Settings UI).
                pass

        summary[coll_name] = idx_created

    # enum-warnings audit collection: TTL 30 d
    try:
        await db["mid_enum_warnings"].create_index(
            [("ts", 1)], expireAfterSeconds=30 * 24 * 3600, name="ttl_ts"
        )
    except Exception:
        pass

    return summary
