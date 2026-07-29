"""ArbiCore X — Opportunity Center read-only routes.

These endpoints power the new Opportunity Center operator UI (separate
artefact from the frozen UIC). All routes are GET-only (one POST is a pure
read query — no DB mutation), all are gated by ``require_auth``, and none
of them touch verifier logic, gates, thresholds, economics, scanner config,
D-6.2, D-4.7, or watchdog state.

Routes added (per UI blueprint §4):
  GET  /api/arbicore/wallets
  POST /api/arbicore/wallets/get_many       (read-only batch lookup)
  GET  /api/arbicore/audit_log
  GET  /api/arbicore/system/collections
  GET  /api/arbicore/discovery_candidates/stats
  GET  /api/arbicore/analytics/timeseries
  GET  /api/arbicore/analytics/funnel

Plus packaging convenience (read-only file send):
  GET  /api/arbicore/release/manifest
  GET  /api/arbicore/release/bundle
"""
from __future__ import annotations

import os as _os
import time as _time
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from services.auth import require_auth

from ..runtime.composition import get_db, get_wallet_profile_repo


router = APIRouter(prefix="/api/arbicore", tags=["arbicore-opportunity-center"])


# ---------------------------------------------------------------------------
# Wallet endpoints
# ---------------------------------------------------------------------------

@router.get("/wallets", dependencies=[Depends(require_auth)])
async def list_wallets(
    label: Optional[str] = Query(None, description="Filter by label (smart_money, whale, influencer, sniper, …)"),
    label_source: Optional[str] = Query(None, description="curated | algorithmic | None"),
    chain: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """Read-only listing of wallet profiles from ``arbicore_wallet_metrics``."""
    db = get_db()
    coll = db["arbicore_wallet_metrics"]

    filt: Dict[str, Any] = {}
    if label is not None:
        filt["label"] = label
    if label_source is not None:
        filt["label_source"] = label_source
    if chain is not None:
        filt["chain"] = chain

    total = await coll.count_documents(filt)
    cursor = coll.find(filt, {"_id": 0}).skip(offset).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"count": len(items), "total": total, "items": items}


class WalletGetManyRequest(BaseModel):
    addresses: List[str] = Field(..., min_length=1, max_length=200)


@router.post("/wallets/get_many", dependencies=[Depends(require_auth)])
async def wallets_get_many(payload: WalletGetManyRequest):
    """Batch wallet-profile lookup. **Read-only** — no DB mutation.

    Mirrors the existing repository ``get_many`` helper for UI enrichment
    (e.g., buyer-wallet badges on the Opportunity Detail page).
    """
    db = get_db()
    coll = db["arbicore_wallet_metrics"]
    addrs = list({a for a in payload.addresses if a})
    cursor = coll.find({"wallet_id": {"$in": addrs}}, {"_id": 0})
    docs = await cursor.to_list(length=len(addrs))
    out = {d.get("wallet_id"): d for d in docs}
    return {"count": len(out), "items": out}


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------

@router.get("/audit_log", dependencies=[Depends(require_auth)])
async def audit_log_tail(
    limit: int = Query(50, ge=1, le=500),
    since: Optional[float] = Query(None, description="Epoch seconds; only return entries after this ts"),
):
    """Read-only tail of ``arbicore_audit_log``."""
    db = get_db()
    coll = db["arbicore_audit_log"]
    filt: Dict[str, Any] = {}
    if since is not None:
        filt["timestamp"] = {"$gt": float(since)}
    cursor = coll.find(filt, {"_id": 0}).sort("timestamp", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return {"count": len(items), "items": items}


# ---------------------------------------------------------------------------
# System / collections census
# ---------------------------------------------------------------------------

@router.get("/system/collections", dependencies=[Depends(require_auth)])
async def system_collections():
    """Mongo `arbicore_*` collection census — counts only, no contents."""
    db = get_db()
    names = sorted([n for n in await db.list_collection_names() if n.startswith("arbicore_")])
    out: List[Dict[str, Any]] = []
    for n in names:
        try:
            count = await db[n].estimated_document_count()
        except Exception:  # noqa: BLE001
            count = 0
        out.append({"name": n, "count": int(count)})
    return {"count": len(out), "items": out}


# ---------------------------------------------------------------------------
# Discovery candidates aggregate
# ---------------------------------------------------------------------------

_WINDOW_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
    "7d": 7 * 24 * 60 * 60,
}


def _window_start(window: str) -> float:
    secs = _WINDOW_SECONDS.get(window)
    if secs is None:
        raise HTTPException(status_code=400, detail=f"Invalid window: {window}. Allowed: {list(_WINDOW_SECONDS)}")
    return _time.time() - secs


@router.get("/discovery_candidates/stats", dependencies=[Depends(require_auth)])
async def discovery_candidate_stats(
    window: str = Query("1h"),
):
    """Aggregate counts of discovery candidates by source within a window."""
    since = _window_start(window)
    db = get_db()
    coll = db["arbicore_discovery_candidates"]
    pipeline = [
        {"$match": {"hint_observed_at": {"$gte": since}}},
        {"$group": {"_id": "$hint_source", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}},
    ]
    rows = await coll.aggregate(pipeline).to_list(length=200)
    total = sum(int(r.get("n", 0)) for r in rows)
    return {
        "window": window,
        "since_ts": since,
        "total": total,
        "by_source": [{"source": (r["_id"] or "unknown"), "count": int(r["n"])} for r in rows],
    }


# ---------------------------------------------------------------------------
# Analytics — timeseries + funnel
# ---------------------------------------------------------------------------

_BUCKET_SECONDS = {
    "5m": 5 * 60,
    "15m": 15 * 60,
    "1h": 60 * 60,
    "6h": 6 * 60 * 60,
    "24h": 24 * 60 * 60,
}

_METRIC_TO_COLLECTION = {
    "candidates": ("arbicore_discovery_candidates", "hint_observed_at"),
    "outcomes": ("arbicore_outcomes", "created_at"),
    "opportunities": ("arbicore_opportunities", "created_at"),
}


@router.get("/analytics/timeseries", dependencies=[Depends(require_auth)])
async def analytics_timeseries(
    metric: str = Query(..., description="candidates | outcomes | opportunities"),
    window: str = Query("24h"),
    bucket: str = Query("1h"),
):
    """Read-only bucketed counts for a chosen metric over a chosen window."""
    if metric not in _METRIC_TO_COLLECTION:
        raise HTTPException(status_code=400, detail=f"Invalid metric: {metric}. Allowed: {list(_METRIC_TO_COLLECTION)}")
    bucket_secs = _BUCKET_SECONDS.get(bucket)
    if bucket_secs is None:
        raise HTTPException(status_code=400, detail=f"Invalid bucket: {bucket}. Allowed: {list(_BUCKET_SECONDS)}")
    since = _window_start(window)
    coll_name, ts_field = _METRIC_TO_COLLECTION[metric]
    coll = get_db()[coll_name]

    pipeline = [
        {"$match": {ts_field: {"$gte": since}}},
        {"$project": {
            "bucket_ts": {
                "$multiply": [
                    {"$floor": {"$divide": [f"${ts_field}", bucket_secs]}},
                    bucket_secs,
                ]
            }
        }},
        {"$group": {"_id": "$bucket_ts", "n": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
    ]
    rows = await coll.aggregate(pipeline).to_list(length=10_000)
    return {
        "metric": metric,
        "window": window,
        "bucket": bucket,
        "since_ts": since,
        "points": [{"ts": float(r["_id"]), "count": int(r["n"])} for r in rows],
    }


@router.get("/analytics/funnel", dependencies=[Depends(require_auth)])
async def analytics_funnel(window: str = Query("24h")):
    """Verification funnel: candidates → claimed → verified → confirmed.

    Each stage is counted independently from its source collection within
    the same window. This matches the read-only verifier-loop semantics
    documented in the master architecture (no write-paths, no aggregation
    against verifier internals).
    """
    since = _window_start(window)
    db = get_db()

    candidates = await db["arbicore_discovery_candidates"].count_documents({"hint_observed_at": {"$gte": since}})
    opportunities = await db["arbicore_opportunities"].count_documents({"created_at": {"$gte": since}})

    outcomes_coll = db["arbicore_outcomes"]
    verified = await outcomes_coll.count_documents({"created_at": {"$gte": since}})
    confirmed = await outcomes_coll.count_documents({"created_at": {"$gte": since}, "decision": "confirmed"})

    return {
        "window": window,
        "since_ts": since,
        "stages": [
            {"stage": "candidate",   "count": int(candidates)},
            {"stage": "claimed",     "count": int(opportunities)},
            {"stage": "verified",    "count": int(verified)},
            {"stage": "confirmed",   "count": int(confirmed)},
        ],
    }


# ---------------------------------------------------------------------------
# Release bundle endpoints — RETIRED in v1.0.0
# ---------------------------------------------------------------------------
# In legacy releases these endpoints streamed a pre-built deployment ZIP
# (`arbicore-x-deployment-bundle.zip`) to authenticated operators. That
# distribution model is deprecated: as of v1.0.0 the canonical repository
# is deployed via `git clone` + `scripts/install.sh`, and no per-release
# bundle is produced or shipped.
#
# The routes are preserved for backward compatibility with any UI or
# tooling that still calls them. They now return a structured, informative
# response instead of streaming a file or 404-ing silently. The routes
# can be removed in a future major version once no consumers remain.


_RETIRED_RELEASE_BUNDLE_RESPONSE = {
    "status": "retired",
    "message": "Release bundles are no longer distributed separately. "
               "Deploy directly from the canonical repository "
               "(https://github.com/raghugr2013-lgtm/arbicore-x).",
    "since_version": "1.0.0",
}


@router.get("/release/manifest", dependencies=[Depends(require_auth)])
async def release_manifest():
    """RETIRED. Historically returned metadata about a staged deployment ZIP;
    now returns a structured retirement notice. See docstring above."""
    return _RETIRED_RELEASE_BUNDLE_RESPONSE


@router.get("/release/bundle", dependencies=[Depends(require_auth)])
async def release_bundle():
    """RETIRED. Historically streamed a deployment ZIP; now returns a
    structured retirement notice. See docstring above."""
    return _RETIRED_RELEASE_BUNDLE_RESPONSE
