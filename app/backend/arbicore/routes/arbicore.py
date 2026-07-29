"""ArbiCore X — Phase B read-only routes (admin-gated).

Endpoints:
  GET /api/arbicore/health
  GET /api/arbicore/opportunities
  GET /api/arbicore/opportunities/{id}
  GET /api/arbicore/provenance

All routes require admin authentication via services.auth.require_auth.
NO write endpoints — Phase B is read-only (master architecture §9.5).
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from services.auth import require_auth

from ..data.provenance import (
    SOURCE_REGISTRY,
    PHASE_B_NATIVE_SOURCES,
    coverage_pct,
    list_sources_by_provenance,
    native_coverage_pct,
    registry_counts_by_provenance,
)
from ..models.category_metadata import unknown_key_warnings
from ..models.enums import DataProvenance, OpportunityStatus, OpportunityType
from ..runtime.composition import (
    get_adaptive_weights,
    get_audit_log,
    get_confidence_engine,
    get_metrics_aggregator,
    get_metrics_repo,
    get_opportunity_repo,
    get_outcome_evaluator,
    get_outcome_repo,
    get_outcome_tracker,
    get_regime_classifier,
    get_regime_snapshot_repo,
    get_regime_worker,
    get_route_tracker,
    get_sequence_miner,
    get_state_observer_registry,
    get_survival_analytics,
)

router = APIRouter(prefix="/api/arbicore", tags=["arbicore"])


def _parse_opportunity_type(value: Optional[str]) -> Optional[OpportunityType]:
    if value is None:
        return None
    try:
        return OpportunityType(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid opportunity_type: {value}")


def _parse_status(value: Optional[str]) -> Optional[OpportunityStatus]:
    if value is None:
        return None
    try:
        return OpportunityStatus(value)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {value}")


def _parse_provenance_filter(values: Optional[list]) -> Optional[frozenset]:
    if not values:
        return None
    out = set()
    for v in values:
        try:
            out.add(DataProvenance(v))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid provenance: {v}")
    return frozenset(out)


@router.get("/health", dependencies=[Depends(require_auth)])
async def arbicore_health():
    opp_repo = get_opportunity_repo()
    outcome_repo = get_outcome_repo()
    metrics_repo = get_metrics_repo()
    regime_repo = get_regime_snapshot_repo()
    observer_registry = get_state_observer_registry()
    audit_log = get_audit_log()
    route_tracker = get_route_tracker()
    outcome_tracker = get_outcome_tracker()
    evaluator = get_outcome_evaluator()

    # Provenance coverage — over the universe of all REGISTERED sources today.
    universe = list(SOURCE_REGISTRY.keys())
    counts = registry_counts_by_provenance()

    # Learning-eligibility ratio per source (1.0 if REAL/VERIFIED_REAL, else 0)
    learning_ratio = {
        name: 1.0 if SOURCE_REGISTRY[name].learning_eligible else 0.0
        for name in universe
    }

    try:
        opp_counts = await opp_repo.count_by_type_status()
    except Exception as e:
        opp_counts = {"_error": str(e)}
    try:
        outcome_counts = await outcome_repo.count_outcomes_by_evaluated()
    except Exception as e:
        outcome_counts = {"_error": str(e)}
    try:
        metric_counts = await metrics_repo.counts()
    except Exception as e:
        metric_counts = {"_error": str(e)}
    try:
        regime_count = await regime_repo.count()
    except Exception as e:
        regime_count = {"_error": str(e)}

    return {
        "phase": "B",
        "status": "ok",
        "provenance": {
            "coverage_pct": native_coverage_pct(),
            "coverage_pct_full_registry": coverage_pct(universe),
            "native_sources_total": len(PHASE_B_NATIVE_SOURCES),
            "counts": counts,
        },
        "opportunities": {
            "counts_by_type_status": opp_counts,
        },
        "outcomes": {
            "counts_by_evaluated": outcome_counts,
        },
        "metrics": {
            "counts": metric_counts,
        },
        "regime_snapshots": {
            "count": regime_count,
        },
        "audit_log": {
            "size": await audit_log.count(),
        },
        "learning_eligibility": {
            "ratio_per_source": learning_ratio,
        },
        "wiring": {
            "opportunity_repo_alive": opp_repo is not None,
            "outcome_repo_alive": outcome_repo is not None,
            "metrics_repo_alive": metrics_repo is not None,
            "regime_snapshot_repo_alive": regime_repo is not None,
            "state_observer_registry_alive": observer_registry is not None,
            "registered_observer_types": observer_registry.registered_types(),
            # Wave 1
            "audit_log_alive": audit_log is not None,
            "route_tracker_alive": route_tracker is not None,
            "outcome_tracker_alive": outcome_tracker is not None,
            "outcome_evaluator": evaluator.status,
        },
        "learning_wave_1": {
            "outcome_tracker_stats": outcome_tracker.stats,
            "route_stats_count": await route_tracker.count(),
        },
        "category_metadata": {
            "unknown_key_warnings": unknown_key_warnings(),
        },
    }


@router.get("/outcomes", dependencies=[Depends(require_auth)])
async def list_outcomes(
    subject_id: Optional[str] = Query(None),
    evaluated: Optional[bool] = Query(None),
    provenance: Optional[list] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """Read-only outcome rows. Filter by subject + evaluated state."""
    prov_filter = _parse_provenance_filter(provenance)
    repo = get_outcome_repo()
    if subject_id is None:
        # No subject filter — list_due is the cheapest sample for ops view.
        import time
        rows = await repo.list_due(now_ts=time.time() + 86400, limit=limit)
    else:
        rows = await repo.list_for_subject(
            subject_id, evaluated=evaluated, provenance_filter=prov_filter,
        )
    return {
        "count": len(rows),
        "items": [r.to_dict() for r in rows],
    }


@router.get("/route-stats", dependencies=[Depends(require_auth)])
async def list_route_stats(limit: int = Query(50, ge=1, le=500)):
    tracker = get_route_tracker()
    rows = await tracker.list_top(limit=limit)
    return {
        "count": len(rows),
        "items": [r.to_dict() for r in rows],
    }


@router.get("/learning-status", dependencies=[Depends(require_auth)])
async def learning_status():
    """Wave 1 + 2 + 3 readiness — single panel showing trackers + workers + audit + weights + regime."""
    outcome_tracker = get_outcome_tracker()
    evaluator = get_outcome_evaluator()
    audit = get_audit_log()
    route_tracker = get_route_tracker()
    aggregator = get_metrics_aggregator()
    weights = get_adaptive_weights()
    regime_worker = get_regime_worker()
    regime_repo = get_regime_snapshot_repo()
    miner = get_sequence_miner()
    binder = get_shadow_binder()
    try:
        from services.execution.approval_proposer import approval_proposer as _proposer
        hook_attached = getattr(_proposer, "post_run_hook", None) is not None
    except Exception:  # noqa: BLE001
        hook_attached = False
    return {
        "wave": "C-5",
        "outcome_tracker": outcome_tracker.stats,
        "outcome_evaluator": evaluator.status,
        "audit_log_count": await audit.count(),
        "route_stats_count": await route_tracker.count(),
        "metrics_aggregator": await aggregator.stats(),
        "adaptive_weights": {
            "current": weights.get_weights({}),
            "cache_age_s": weights.cache_age_s,
        },
        "registered_observer_types": get_state_observer_registry().registered_types(),
        # Wave 3
        "regime_worker": regime_worker.status,
        "regime_snapshot_count": await regime_repo.count(),
        "sequence_pattern_count": await miner.count(),
        # Wave 5 — Shadow Binding
        "shadow_binder": {
            "hook_attached": hook_attached,
            "stats": binder.stats,
        },
    }


@router.get("/weights/current", dependencies=[Depends(require_auth)])
async def current_weights():
    weights = get_adaptive_weights()
    await weights.refresh()
    snapshot = weights.get_weights({})
    return {
        "count": len(snapshot),
        "weights": snapshot,
        "cache_age_s": weights.cache_age_s,
        "neutral_default": 1.0,
        "min": 0.1,
        "max": 2.0,
    }


@router.get("/confidence/score", dependencies=[Depends(require_auth)])
async def confidence_score(opportunity_id: str = Query(...)):
    """Score the confidence of an opportunity that already lives in
    arbicore_opportunities. Read-only — does not mutate the opportunity."""
    opp = await get_opportunity_repo().get(opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    engine = get_confidence_engine()
    bd = await engine.score_with_breakdown(opp)
    return {
        "opportunity_id": opportunity_id,
        "confidence": bd.final,
        "breakdown": bd.to_dict(),
    }


# ---- Wave 3 endpoints -------------------------------------------------------

@router.get("/survival/{subject_id}", dependencies=[Depends(require_auth)])
async def survival_for_subject(subject_id: str,
                               tolerance: Optional[float] = Query(None),
                               horizon_s: Optional[int] = Query(None)):
    """Per-subject survival analytics — read-only."""
    analytics = get_survival_analytics()
    row = await analytics.for_subject(subject_id, tolerance=tolerance,
                                      horizon_s=horizon_s)
    if row is None:
        return {"subject_id": subject_id, "survival": None,
                "reason": "insufficient_state_snapshots"}
    return {"subject_id": subject_id, "survival": row.to_dict()}


@router.get("/regime/latest", dependencies=[Depends(require_auth)])
async def regime_latest():
    snap = await get_regime_snapshot_repo().latest()
    if snap is None:
        return {"regime": None, "reason": "no_snapshots_yet"}
    from dataclasses import asdict
    return {"regime": asdict(snap)}


@router.get("/regime/history", dependencies=[Depends(require_auth)])
async def regime_history(limit: int = Query(50, ge=1, le=500),
                         since: float = Query(0.0)):
    from dataclasses import asdict
    rows = await get_regime_snapshot_repo().list_since(t0=float(since), limit=limit)
    return {"count": len(rows), "items": [asdict(r) for r in rows]}


@router.get("/sequences/patterns", dependencies=[Depends(require_auth)])
async def sequence_patterns(limit: int = Query(50, ge=1, le=500),
                            min_support: int = Query(2, ge=1)):
    miner = get_sequence_miner()
    rows = await miner.list_patterns(limit=limit, min_support=min_support)
    return {
        "count": len(rows),
        "total_patterns": await miner.count(),
        "items": [r.to_dict() for r in rows],
    }


# ---- Wave 4 endpoints -------------------------------------------------------

from ..runtime.composition import (  # noqa: E402
    get_entity_cluster_detector,
    get_entity_repo,
    get_entity_resolver,
    get_entity_scorer,
)
from ..intel.entity_types import EntityType  # noqa: E402


@router.get("/entities", dependencies=[Depends(require_auth)])
async def list_entities(entity_type: Optional[str] = Query(None),
                        limit: int = Query(100, ge=1, le=500)):
    repo = get_entity_repo()
    if entity_type is not None:
        try:
            et = EntityType(entity_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid entity_type: {entity_type}")
        rows = await repo.list_by_type(et, limit=limit)
    else:
        # No filter — pick across all types
        rows = []
        for et in EntityType:
            rows.extend(await repo.list_by_type(et, limit=limit))
            if len(rows) >= limit:
                break
        rows = rows[:limit]
    return {
        "count": len(rows),
        "total_entities": await repo.count(),
        "items": [e.to_dict() for e in rows],
    }


@router.get("/entities/clusters", dependencies=[Depends(require_auth)])
async def list_clusters(limit: int = Query(50, ge=1, le=500)):
    det = get_entity_cluster_detector()
    rows = await det.list_top(limit=limit)
    return {"count": len(rows), "total_clusters": await det.count(),
            "items": rows}


@router.get("/entities/scores/top", dependencies=[Depends(require_auth)])
async def top_entity_scores(limit: int = Query(50, ge=1, le=500)):
    scorer = get_entity_scorer()
    rows = await scorer.top(limit=limit)
    return {"count": len(rows), "items": [r.to_dict() for r in rows]}


@router.get("/entities/resolve", dependencies=[Depends(require_auth)])
async def resolve_entity(ref_type: str = Query(...),
                         external_ref: str = Query(...)):
    resolver = get_entity_resolver()
    eid = await resolver.lookup_by_ref(ref_type, external_ref)
    return {"ref_type": ref_type, "external_ref": external_ref,
            "entity_id": eid}


@router.get("/entities/{entity_id}", dependencies=[Depends(require_auth)])
async def get_entity(entity_id: str):
    repo = get_entity_repo()
    e = await repo.get(entity_id)
    if e is None:
        raise HTTPException(status_code=404, detail="Entity not found")
    return e.to_dict()


@router.get("/opportunities", dependencies=[Depends(require_auth)])
async def list_opportunities(
    type: Optional[str] = Query(None, alias="type"),
    status: Optional[str] = Query(None),
    subject_id: Optional[str] = Query(None),
    since: Optional[float] = Query(None, description="Epoch seconds"),
    provenance: Optional[list] = Query(None, description="DataProvenance filter (repeatable)"),
    limit: int = Query(100, ge=1, le=500),
):
    opp_type = _parse_opportunity_type(type)
    opp_status = _parse_status(status)
    prov_filter = _parse_provenance_filter(provenance)

    filt = {}
    if opp_type is not None:
        filt["opportunity_type"] = opp_type
    if opp_status is not None:
        filt["status"] = opp_status
    if subject_id is not None:
        filt["subject_id"] = subject_id
    if since is not None:
        filt["since"] = since

    repo = get_opportunity_repo()
    items = await repo.find(filt, limit=limit, provenance_filter=prov_filter)
    return {
        "count": len(items),
        "items": [o.model_dump(mode="json") for o in items],
    }


@router.get("/opportunities/{opportunity_id}", dependencies=[Depends(require_auth)])
async def get_opportunity(opportunity_id: str):
    repo = get_opportunity_repo()
    opp = await repo.get(opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opp.model_dump(mode="json")


# ---- Wave 5 endpoints — Shadow Binding ------------------------------------

from ..runtime.composition import get_shadow_binder  # noqa: E402


@router.get("/shadow/status", dependencies=[Depends(require_auth)])
async def shadow_status():
    """Shadow Binding observability — counters + last error.

    Read-only. Reflects the per-process state of the
    ``ShadowBindingObserver`` that converts legacy ``build_proposals()``
    snapshots into ``CanonicalOpportunity`` objects.
    """
    binder = get_shadow_binder()
    try:
        from services.execution.approval_proposer import approval_proposer as _proposer
        hook_attached = getattr(_proposer, "post_run_hook", None) is not None
        proposer_iterations = int(getattr(_proposer, "iterations", 0) or 0)
    except Exception:  # noqa: BLE001
        hook_attached = False
        proposer_iterations = 0
    return {
        "wave": "C-5",
        "mode": "SHADOW",
        "hook_attached": hook_attached,
        "proposer_iterations": proposer_iterations,
        "binder": binder.stats,
    }


@router.get("/provenance", dependencies=[Depends(require_auth)])
async def provenance_dump():
    counts = registry_counts_by_provenance()
    return {
        "registry": {
            name: {
                "source": entry.source,
                "provenance": entry.provenance.value,
                "reason": entry.reason,
                "learning_eligible": entry.learning_eligible,
            }
            for name, entry in SOURCE_REGISTRY.items()
        },
        "counts": counts,
        "by_provenance": {
            tier.value: list_sources_by_provenance(tier) for tier in DataProvenance
        },
        "total_sources": len(SOURCE_REGISTRY),
    }
