"""ArbiCore X — Mongo collection bindings + ensure_indexes() (Phase B).

All collection names are NEW and live in the ``arbicore_*`` namespace. They
do not collide with any existing ArbiCore collection (master P10).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, Optional, Tuple

from pymongo.errors import OperationFailure

from services import db as _db


logger = logging.getLogger(__name__)


# Canonical collection name registry. Keep this dict as the single source
# of truth; never reference collection names by string elsewhere.
COLLECTION_NAMES: Dict[str, str] = {
    "opportunities":      "arbicore_opportunities",
    "outcomes":           "arbicore_outcomes",
    "state_snapshots":    "arbicore_state_snapshots",
    "audit_log":          "arbicore_audit_log",
    "route_stats":        "arbicore_route_stats",
    "provenance_audit":   "arbicore_provenance_audit",
    "signal_metrics":     "arbicore_signal_metrics",
    "wallet_metrics":     "arbicore_wallet_metrics",
    "temporal_sequences": "arbicore_temporal_sequences",
    "sequence_patterns":  "arbicore_sequence_patterns",
    "regime_snapshots":   "arbicore_regime_snapshots",
    # Phase C Wave 4 — Universal Entity Intelligence
    "entities":           "arbicore_entities",
    "entity_refs":        "arbicore_entity_refs",
    "entity_clusters":    "arbicore_entity_clusters",
}


def _col(name_key: str) -> Any:
    return _db.db[COLLECTION_NAMES[name_key]]


def get_collection(name_key: str) -> Any:
    """Return the Motor collection object for a logical name."""
    return _col(name_key)


def _keyspec_from_arg(key_arg) -> Tuple[Tuple[str, int], ...]:
    """Normalise ``create_index`` key argument into a hashable tuple."""
    if isinstance(key_arg, str):
        return ((key_arg, 1),)
    if isinstance(key_arg, list):
        return tuple((k, v) for k, v in key_arg)
    return ()


async def _safe_create_index(col, key, **kwargs) -> Optional[str]:
    """Idempotent index creation.

    * If an index with the same key spec already exists (regardless of
      the auto-generated name), skip creation entirely to avoid
      ``IndexOptionsConflict``.
    * Any residual server-side conflict is logged and swallowed — the
      canonical boot indexer is best-effort.
    """
    wanted = _keyspec_from_arg(key)
    try:
        existing = await col.index_information()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "index_information(%s) failed: %s", col.name, exc
        )
        existing = {}
    for _name, info in existing.items():
        if tuple(tuple(k) for k in (info.get("key") or [])) == wanted:
            return None  # compatible index already present
    try:
        return await col.create_index(key, **kwargs)
    except OperationFailure as exc:
        if exc.code == 85:  # IndexOptionsConflict
            logger.info(
                "create_index(%s, %s) → conflict (already exists with "
                "different name), skipping",
                col.name, key,
            )
            return None
        raise


async def ensure_indexes() -> Dict[str, Any]:
    """Idempotent index creation for every arbicore_* collection.

    Returns a report dict consumed by /api/arbicore/health.
    """
    report: Dict[str, Any] = {"collections": [], "ttl_indexes": []}

    # arbicore_opportunities
    c = _col("opportunities")
    await _safe_create_index(c, "opportunity_id", unique=True, name="opportunity_id_unique")
    await _safe_create_index(c, "subject_id", name="subject_id_idx")
    await _safe_create_index(c, [("opportunity_type", 1), ("status", 1)], name="type_status_idx")
    await _safe_create_index(c, [("created_at", -1)], name="created_at_desc")
    report["collections"].append("arbicore_opportunities")

    # arbicore_outcomes
    c = _col("outcomes")
    await _safe_create_index(c, "id", unique=True, name="outcome_id_unique")
    await _safe_create_index(c, "opportunity_id", name="opp_id_idx")
    await _safe_create_index(c, "due_at", sparse=True, name="due_at_sparse")
    await _safe_create_index(c, "evaluated", name="evaluated_idx")
    await _safe_create_index(c, "subject_id", name="subject_id_idx")
    report["collections"].append("arbicore_outcomes")

    # arbicore_state_snapshots — TTL 30 days via captured_at_dt
    c = _col("state_snapshots")
    await _safe_create_index(c, [("subject_id", 1), ("captured_at_ts", -1)], name="subject_time_idx")
    await _safe_create_index(c, "opportunity_type", name="opp_type_idx")
    await _safe_create_index(c, "captured_at_dt", expireAfterSeconds=30 * 86400, name="ttl_30d")
    report["collections"].append("arbicore_state_snapshots")
    report["ttl_indexes"].append({"collection": "arbicore_state_snapshots", "ttl_days": 30})

    # arbicore_audit_log — TTL 90 days via ts_dt
    c = _col("audit_log")
    await _safe_create_index(c, "ts", name="ts_idx")
    await _safe_create_index(c, "opportunity_id", name="opp_id_idx")
    await _safe_create_index(c, "actor", name="actor_idx")
    await _safe_create_index(c, "ts_dt", expireAfterSeconds=90 * 86400, name="ttl_90d")
    report["collections"].append("arbicore_audit_log")
    report["ttl_indexes"].append({"collection": "arbicore_audit_log", "ttl_days": 90})

    # arbicore_route_stats
    c = _col("route_stats")
    await _safe_create_index(c, "route_key", unique=True, name="route_key_unique")
    await _safe_create_index(c, [("updated_at", -1)], name="updated_at_desc")
    report["collections"].append("arbicore_route_stats")

    # arbicore_provenance_audit
    c = _col("provenance_audit")
    await _safe_create_index(c, "source", name="source_idx")
    await _safe_create_index(c, [("updated_at", -1)], name="updated_at_desc")
    report["collections"].append("arbicore_provenance_audit")

    # arbicore_signal_metrics
    c = _col("signal_metrics")
    await _safe_create_index(c, "signal_id", name="signal_id_idx")
    await _safe_create_index(c, "subject_id", name="subject_id_idx")
    await _safe_create_index(c, [("aggregated_at", -1)], name="aggregated_at_desc")
    report["collections"].append("arbicore_signal_metrics")

    # arbicore_wallet_metrics
    c = _col("wallet_metrics")
    await _safe_create_index(c, "wallet_id", unique=True, name="wallet_id_unique")
    await _safe_create_index(c, "entity_id", name="entity_id_idx")
    await _safe_create_index(c, [("updated_at", -1)], name="updated_at_desc")
    report["collections"].append("arbicore_wallet_metrics")

    # arbicore_temporal_sequences — TTL 90d via discovered_at_dt
    c = _col("temporal_sequences")
    await _safe_create_index(c, "subject_id", name="subject_id_idx")
    await _safe_create_index(c, [("discovered_at", -1)], name="discovered_at_desc")
    await _safe_create_index(c, "discovered_at_dt", expireAfterSeconds=90 * 86400, name="ttl_90d")
    report["collections"].append("arbicore_temporal_sequences")
    report["ttl_indexes"].append({"collection": "arbicore_temporal_sequences", "ttl_days": 90})

    # arbicore_sequence_patterns
    c = _col("sequence_patterns")
    await _safe_create_index(c, "pattern_id", unique=True, name="pattern_id_unique")
    await _safe_create_index(c, "support", name="support_idx")
    await _safe_create_index(c, "confidence", name="confidence_idx")
    report["collections"].append("arbicore_sequence_patterns")

    # arbicore_regime_snapshots — TTL 90d via captured_at_dt
    c = _col("regime_snapshots")
    await _safe_create_index(c, [("captured_at", -1)], name="captured_at_desc")
    await _safe_create_index(c, "dominant_regime", name="dominant_regime_idx")
    await _safe_create_index(c, "captured_at_dt", expireAfterSeconds=90 * 86400, name="ttl_90d")
    report["collections"].append("arbicore_regime_snapshots")
    report["ttl_indexes"].append({"collection": "arbicore_regime_snapshots", "ttl_days": 90})

    # arbicore_entities (W4)
    c = _col("entities")
    await _safe_create_index(c, "entity_id", unique=True, name="entity_id_unique")
    await _safe_create_index(c, "entity_type", name="entity_type_idx")
    await _safe_create_index(c, [("last_seen_at", -1)], name="last_seen_desc")
    report["collections"].append("arbicore_entities")

    # arbicore_entity_refs (W4)
    c = _col("entity_refs")
    await _safe_create_index(c, [("ref_type", 1), ("external_ref", 1)],
                             unique=True, name="ref_unique")
    await _safe_create_index(c, "entity_id", name="entity_id_idx")
    report["collections"].append("arbicore_entity_refs")

    # arbicore_entity_clusters (W4)
    c = _col("entity_clusters")
    await _safe_create_index(c, "cluster_id", unique=True, name="cluster_id_unique")
    await _safe_create_index(c, [("cluster_score", -1)], name="score_desc")
    await _safe_create_index(c, [("detected_at", -1)], name="detected_desc")
    report["collections"].append("arbicore_entity_clusters")

    return report
