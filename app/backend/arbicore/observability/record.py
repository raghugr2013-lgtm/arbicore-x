"""Assemble a persistable Phase 0 strategy-intelligence record.

The return value is JSON-serializable observation. It is not written to a
database and it is not attached to the live verifier.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .economics_observation import observe_economics
from .fields import CLASSIFIER_VERSION, as_dict
from .taxonomy import build_route_view, classify_route


def observe_strategy_intelligence(
    bundle: Optional[Dict[str, Any]] = None,
    candidate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify stored route evidence and read stored economics.

    ``bundle`` is an m2.3 verifier evidence dict. ``candidate`` is an optional
    discovery-candidate dict (``hint_metric``, ``verified_outcome``). Neither
    input is mutated. Missing economics stay missing.
    """
    bundle_in = as_dict(bundle)
    candidate_in = as_dict(candidate)
    economics = observe_economics(bundle_in, candidate_in)
    view = build_route_view(
        bundle_in, candidate_in, timestamp=economics.get("timestamp"),
    )
    strategy = classify_route(view)
    schema = None
    created_at = None
    if bundle_in is not None:
        raw_schema = bundle_in.get("schema_version")
        if isinstance(raw_schema, str) and raw_schema.strip():
            schema = raw_schema.strip()
        raw_created = bundle_in.get("created_at")
        if isinstance(raw_created, str) and raw_created.strip():
            created_at = raw_created.strip()

    strategy_out = {
        "primary_family": strategy["primary_family"],
        "secondary_tags": list(strategy["secondary_tags"]),
        "classification_state": strategy["classification_state"],
        "confidence": strategy["confidence"],
        "strategy_completeness": strategy["strategy_completeness"],
        "evidence": list(strategy["evidence"]),
        "unresolved_fields": list(strategy["unresolved_fields"]),
        "classifier_version": CLASSIFIER_VERSION,
    }
    return {
        "classifier_version": CLASSIFIER_VERSION,
        "evidence_schema_version": schema,
        "bundle_created_at": created_at,
        "bundle_presence": economics["bundle_presence"],
        "strategy": strategy_out,
        "legs": view["legs"],
        "economics": {
            "completeness": economics["completeness"],
            "fields": economics["fields"],
            "unresolved_fields": economics["unresolved_fields"],
            "calculator_version": economics["calculator_version"],
            "timestamp": economics["timestamp"],
        },
        "provenance_notes": [
            "Protocol is read only from dex_protocol, route_dex_protocols, "
            "or route_hops[].dex.",
            "Venue ids, pool ids, and pool addresses are not parsed into a protocol.",
            "The flash-loan provider is not a route protocol.",
            "Missing economics fields stay null. Stored numeric zero stays zero.",
            "No economics formula is evaluated by this record.",
        ],
    }
