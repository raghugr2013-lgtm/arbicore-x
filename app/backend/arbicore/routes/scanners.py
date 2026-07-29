"""ArbiCore X — Phase D D-1: scanners + discovery + venues HTTP routes."""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..runtime.composition import (
    get_cex_arb_scanner, get_discovery_queue,
    get_discovery_source_metrics, get_funding_arb_scanner,
    get_dex_arb_scanner, get_launch_arb_scanner,
    get_cross_chain_arb_scanner,
    get_flash_loan_arb_scanner,
    get_scanner_config_repo,
    get_scanner_state_repo, get_venue_capability_repo,
)
from .arbicore import require_auth

router = APIRouter(prefix="/api/arbicore", tags=["arbicore-d1"])


# ---- Scanner endpoints ----------------------------------------------------

@router.get("/scanners/cex_arb/status", dependencies=[Depends(require_auth)])
async def scanner_status():
    scanner = get_cex_arb_scanner()
    cfg = await get_scanner_config_repo().get("cex_arb")
    state = await get_scanner_state_repo().get("cex_arb")
    caps_repo = get_venue_capability_repo()
    venues_live = await caps_repo.all_live()
    return {
        "wave": "D-1.0",
        "scanner_id": "cex_arb",
        "enabled": state.get("enabled", False),
        "config": {
            "interval_s": cfg.get("interval_s"),
            "tier_a_pairs": cfg.get("tier_a_pairs"),
            "tier_b_pairs": cfg.get("tier_b_pairs"),
        },
        "scanner_stats": scanner.stats,
        "sources_registered": scanner.source_registry.ids(),
        "verifiers_registered": scanner.verifier_registry.types(),
        "venues": [
            {"venue_id": v.get("venue_id"),
             "venue_status": v.get("venue_status"),
             "api_healthy": v.get("api_healthy"),
             "latency_ms": v.get("latency_ms"),
             "data_quality": v.get("data_quality")}
            for v in venues_live
        ],
    }


@router.post("/scanners/cex_arb/kill", dependencies=[Depends(require_auth)])
async def scanner_kill():
    return await get_scanner_state_repo().set_enabled("cex_arb", False)


@router.post("/scanners/cex_arb/resume", dependencies=[Depends(require_auth)])
async def scanner_resume():
    return await get_scanner_state_repo().set_enabled("cex_arb", True)


# ---- Phase D D-2.0 funding-arb scanner endpoints ----

@router.get("/scanners/funding_arb/status", dependencies=[Depends(require_auth)])
async def funding_scanner_status():
    scanner = get_funding_arb_scanner()
    cfg = await get_scanner_config_repo().get("funding_arb")
    state = await get_scanner_state_repo().get("funding_arb")
    return {
        "wave": "D-2.0",
        "scanner_id": "funding_arb",
        "primary_metric": "funding_diff_apr_pct",
        "enabled": state.get("enabled", False),
        "config": {
            "interval_s": cfg.get("interval_s"),
            "min_diff_apr_pct": cfg.get("min_diff_apr_pct"),
            "max_break_even_hours": cfg.get("max_break_even_hours"),
            "max_funding_age_s": cfg.get("max_funding_age_s"),
        },
        "scanner_stats": scanner.stats,
        "sources_registered": scanner.source_registry.ids(),
        "verifiers_registered": scanner.verifier_registry.types(),
    }


@router.post("/scanners/funding_arb/kill", dependencies=[Depends(require_auth)])
async def funding_scanner_kill():
    return await get_scanner_state_repo().set_enabled("funding_arb", False)


@router.post("/scanners/funding_arb/resume", dependencies=[Depends(require_auth)])
async def funding_scanner_resume():
    return await get_scanner_state_repo().set_enabled("funding_arb", True)


# ---- Phase D D-3.5 DEX-arb scanner endpoints ----
# Mirrors the D-1.0 / D-2.0 endpoint shape. Operator-controlled lifecycle
# preserved: scanner ships disabled, every discovery source ships disabled,
# the only state-mutating endpoints are the two below (kill / resume / config
# patch / source enable-disable through the universal discovery routes).

@router.get("/scanners/dex_arb/status", dependencies=[Depends(require_auth)])
async def dex_scanner_status():
    scanner = get_dex_arb_scanner()
    cfg = await get_scanner_config_repo().get("dex_arb")
    state = await get_scanner_state_repo().get("dex_arb")
    return {
        "wave": "D-3.4",
        "scanner_id": "dex_arb",
        "primary_metric": "mev_adjusted_net_pct",
        "enabled": state.get("enabled", False),
        "config": {
            "interval_s": cfg.get("interval_s"),
            "tier_a_pairs": cfg.get("tier_a_pairs"),
            "tier_b_pairs": cfg.get("tier_b_pairs"),
            "gate_thresholds": cfg.get("gate_thresholds"),
        },
        "scanner_stats": scanner.stats,
        "sources_registered": scanner.source_registry.ids(),
        "verifiers_registered": scanner.verifier_registry.types(),
    }


@router.post("/scanners/dex_arb/kill", dependencies=[Depends(require_auth)])
async def dex_scanner_kill():
    return await get_scanner_state_repo().set_enabled("dex_arb", False)


@router.post("/scanners/dex_arb/resume", dependencies=[Depends(require_auth)])
async def dex_scanner_resume():
    return await get_scanner_state_repo().set_enabled("dex_arb", True)


@router.put("/scanners/dex_arb/config", dependencies=[Depends(require_auth)])
async def dex_scanner_config_update(patch: "ConfigPatch"):
    patch_dict = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not patch_dict:
        raise HTTPException(400, "empty patch")
    return await get_scanner_config_repo().update("dex_arb", patch_dict)


@router.get("/scanners/dex_arb/gate-analysis", dependencies=[Depends(require_auth)])
async def dex_gate_analysis(window_minutes: int = 60,
                            pair: Optional[str] = None,
                            venue: Optional[str] = None):
    """Aggregation over arbicore_opportunities for D-3 gate telemetry.

    Mirrors the cex_arb / funding_arb gate-analysis shape exactly so existing
    operator tooling and dashboards work unchanged. The only differences:
    opportunity_type filter is DEX_ARBITRAGE and opportunity_id prefix is
    ``dexarb:`` (set by D-3.2 DEXQuoteVerifier).
    """
    from ..runtime.composition import get_db
    from datetime import datetime, timedelta, timezone
    db = get_db()
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    cutoff_iso = cutoff_dt.isoformat()
    q: Dict[str, Any] = {
        "opportunity_type": "DEX_ARBITRAGE",
        "opportunity_id": {"$regex": "^dexarb:"},
        "created_at": {"$gte": cutoff_iso},
    }
    if pair:
        q["asset"] = pair
    if venue:
        q["$or"] = [{"buy_venue": venue}, {"sell_venue": venue}]
    total = await db["arbicore_opportunities"].count_documents(q)
    validated_q = dict(q); validated_q["status"] = "validated"
    validated = await db["arbicore_opportunities"].count_documents(validated_q)
    # Rejections grouped by gate
    pipeline = [
        {"$match": {**q, "metadata.rejected_gate_name": {"$exists": True}}},
        {"$group": {"_id": "$metadata.rejected_gate_name",
                    "count": {"$sum": 1}}},
    ]
    rejections: Dict[str, int] = {}
    async for d in db["arbicore_opportunities"].aggregate(pipeline):
        rejections[str(d["_id"])] = int(d["count"])
    rejected = sum(rejections.values())
    pct = {k: round(100 * v / rejected, 1) if rejected else 0.0
           for k, v in rejections.items()}
    return {
        "wave": "D-3.4",
        "scanner_id": "dex_arb",
        "window_minutes": window_minutes,
        "primary_metric": "mev_adjusted_net_pct",
        "totals": {"observed": total, "validated": validated,
                   "rejected": rejected},
        "rejections_by_gate": rejections,
        "rejection_pct_by_gate": pct,
        "scanner_stats_live": get_dex_arb_scanner().stats,
    }


class ConfigPatch(BaseModel):
    tier_b_pairs: Optional[list] = None
    gate_thresholds: Optional[dict] = None
    rejected_capture_pct: Optional[float] = None
    discovery_sources: Optional[dict] = None
    interval_s: Optional[int] = None


@router.put("/scanners/cex_arb/config", dependencies=[Depends(require_auth)])
async def scanner_config_update(patch: ConfigPatch):
    patch_dict = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not patch_dict:
        raise HTTPException(400, "empty patch")
    return await get_scanner_config_repo().update("cex_arb", patch_dict)


@router.get("/scanners/cex_arb/gate-analysis", dependencies=[Depends(require_auth)])
async def gate_analysis(window_minutes: int = 60,
                        pair: Optional[str] = None,
                        venue: Optional[str] = None):
    """Aggregation over arbicore_opportunities for D-1 gate telemetry."""
    from ..runtime.composition import get_db
    from datetime import datetime, timedelta, timezone
    db = get_db()
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    cutoff_iso = cutoff_dt.isoformat()
    q: Dict[str, Any] = {
        "opportunity_type": "CEX_ARBITRAGE",
        "opportunity_id": {"$regex": "^cexarb:"},
        "created_at": {"$gte": cutoff_iso},
    }
    if pair:
        q["asset"] = pair
    if venue:
        q["$or"] = [{"buy_venue": venue}, {"sell_venue": venue}]
    total = await db["arbicore_opportunities"].count_documents(q)
    validated_q = dict(q); validated_q["status"] = "validated"
    validated = await db["arbicore_opportunities"].count_documents(validated_q)
    # Rejections grouped by gate
    pipeline = [
        {"$match": {**q, "metadata.rejected_gate_name": {"$exists": True}}},
        {"$group": {"_id": "$metadata.rejected_gate_name", "count": {"$sum": 1}}},
    ]
    rejections: Dict[str, int] = {}
    async for d in db["arbicore_opportunities"].aggregate(pipeline):
        rejections[str(d["_id"])] = int(d["count"])
    rejected = sum(rejections.values())
    pct = {k: round(100 * v / rejected, 1) if rejected else 0.0
           for k, v in rejections.items()}
    # Per-pair rejections
    per_pair_pipe = [
        {"$match": q},
        {"$group": {"_id": "$asset",
                    "rejected": {"$sum": {"$cond": [{"$eq": ["$status", "validated"]}, 0, 1]}},
                    "validated": {"$sum": {"$cond": [{"$eq": ["$status", "validated"]}, 1, 0]}}}},
        {"$sort": {"rejected": -1}}, {"$limit": 20},
    ]
    per_pair = []
    async for d in db["arbicore_opportunities"].aggregate(per_pair_pipe):
        per_pair.append({"pair": d["_id"], "rejected": d["rejected"],
                         "validated": d["validated"]})
    # D-1.5: per-discovery-source breakdown — distinguishes CG aggregator
    # hints from venue-originated candidates. Sources are HINTS only; the
    # CanonicalOpportunity provenance is set by the verifier from the venue
    # read's SOURCE_REGISTRY classification, not the hint source.
    per_source_pipe = [
        {"$match": q},
        {"$group": {
            "_id": "$metadata.discovery_source",
            "observed": {"$sum": 1},
            "validated": {"$sum": {"$cond": [{"$eq": ["$status", "validated"]}, 1, 0]}},
            "rejected_spread": {"$sum": {"$cond": [
                {"$eq": ["$metadata.rejected_gate_name", "spread"]}, 1, 0]}},
            "rejected_liquidity": {"$sum": {"$cond": [
                {"$eq": ["$metadata.rejected_gate_name", "liquidity"]}, 1, 0]}},
            "rejected_venue_capability": {"$sum": {"$cond": [
                {"$eq": ["$metadata.rejected_gate_name", "venue_capability"]}, 1, 0]}},
            "rejected_confidence": {"$sum": {"$cond": [
                {"$eq": ["$metadata.rejected_gate_name", "confidence"]}, 1, 0]}},
            "rejected_provenance": {"$sum": {"$cond": [
                {"$eq": ["$metadata.rejected_gate_name", "provenance"]}, 1, 0]}},
        }},
        {"$sort": {"observed": -1}},
    ]
    per_source = []
    async for d in db["arbicore_opportunities"].aggregate(per_source_pipe):
        per_source.append({
            "discovery_source": d["_id"],
            "observed": d["observed"],
            "validated": d["validated"],
            "rejections_by_gate": {
                "spread":            d["rejected_spread"],
                "liquidity":         d["rejected_liquidity"],
                "venue_capability":  d["rejected_venue_capability"],
                "confidence":        d["rejected_confidence"],
                "provenance":        d["rejected_provenance"],
            },
        })
    return {
        "window_minutes": window_minutes,
        "total_observed": total,
        "total_validated": validated,
        "total_rejected": rejected,
        "rejections_by_gate": {k: {"count": v, "pct": pct.get(k, 0.0)}
                                for k, v in rejections.items()},
        "rejections_by_pair": per_pair,
        "rejections_by_discovery_source": per_source,
    }


# ---- Venue endpoints ------------------------------------------------------

@router.get("/venues/capabilities", dependencies=[Depends(require_auth)])
async def venue_capabilities():
    return {"venues": await get_venue_capability_repo().all_live()}


@router.get("/venues/{venue_id}/capability-history",
            dependencies=[Depends(require_auth)])
async def venue_capability_history(venue_id: str, window_days: int = 7):
    return {"venue_id": venue_id,
            "history": await get_venue_capability_repo().history(
                venue_id, window_days=window_days)}


@router.post("/venues/{venue_id}/mute", dependencies=[Depends(require_auth)])
async def venue_mute(venue_id: str):
    await get_venue_capability_repo().set_status(
        venue_id, venue_status="disabled", reason="operator_mute")
    return await get_venue_capability_repo().get(venue_id)


@router.post("/venues/{venue_id}/unmute", dependencies=[Depends(require_auth)])
async def venue_unmute(venue_id: str):
    await get_venue_capability_repo().set_status(
        venue_id, venue_status="live", reason="operator_unmute")
    return await get_venue_capability_repo().get(venue_id)


# ---- Discovery endpoints --------------------------------------------------

@router.get("/discovery/queue/status", dependencies=[Depends(require_auth)])
async def discovery_queue_status():
    return await get_discovery_queue().queue_status()


@router.get("/discovery/sources/status", dependencies=[Depends(require_auth)])
async def discovery_sources_status():
    scanner = get_cex_arb_scanner()
    out = []
    for src in scanner.source_registry.all():
        h = await src.health()
        out.append({
            "source_id": src.source_id,
            "cadence_s": src.cadence_s,
            "tier": src.tier,
            "opportunity_types": sorted(t.value for t in src.opportunity_types),
            "ok": h.ok,
            "latency_ms": h.latency_ms,
            "last_emission_at": h.last_emission_at,
            "last_error": h.last_error,
        })
    return {"sources": out}


@router.get("/discovery/sources/hit-rates", dependencies=[Depends(require_auth)])
async def discovery_sources_hit_rates(window: str = "24h"):
    return {"window": window,
            "sources": await get_discovery_source_metrics().latest_per_source(window)}


@router.get("/discovery/candidates", dependencies=[Depends(require_auth)])
async def discovery_candidates(limit: int = 50, source_id: Optional[str] = None):
    return {"candidates": await get_discovery_queue().list_candidates(
        limit=limit, source_id=source_id)}


@router.get("/discovery/candidates/{candidate_id}",
            dependencies=[Depends(require_auth)])
async def discovery_candidate(candidate_id: str):
    doc = await get_discovery_queue().get_candidate(candidate_id)
    if doc is None:
        raise HTTPException(404, "candidate not found")
    return doc


@router.post("/discovery/sources/{source_id}/enable",
             dependencies=[Depends(require_auth)])
async def discovery_source_enable(source_id: str):
    cfg = await get_scanner_config_repo().get("cex_arb")
    ds = dict(cfg.get("discovery_sources", {}))
    src_cfg = dict(ds.get(source_id, {}))
    src_cfg["enabled"] = True
    ds[source_id] = src_cfg
    return await get_scanner_config_repo().update("cex_arb", {"discovery_sources": ds})


@router.post("/discovery/sources/{source_id}/disable",
             dependencies=[Depends(require_auth)])
async def discovery_source_disable(source_id: str):
    cfg = await get_scanner_config_repo().get("cex_arb")
    ds = dict(cfg.get("discovery_sources", {}))
    src_cfg = dict(ds.get(source_id, {}))
    src_cfg["enabled"] = False
    ds[source_id] = src_cfg
    return await get_scanner_config_repo().update("cex_arb", {"discovery_sources": ds})


# ---- Weekly digest --------------------------------------------------------

@router.get("/discovery/weekly-digest", dependencies=[Depends(require_auth)])
async def weekly_digest():
    return {"digests": await get_discovery_source_metrics().latest_weekly_digests(7)}


# ---- D-4.1 Launch Intelligence — read-only diagnostic preview ------------
# The launch_arb scanner orchestrator does NOT ship until D-4.5. This
# endpoint provides operator visibility into the substrate state seeded at
# D-4.0 + the discovery-source classes wired at D-4.1 without spawning
# any background work. Read-only: no state mutation, no emissions, no
# scanner activation.

@router.get("/scanners/launch_arb/preview",
            dependencies=[Depends(require_auth)])
async def launch_arb_preview():
    """Read-only diagnostic. Surfaces seeded config + source-registry
    classifications + per-source health + credential presence — never values.

    Wave: D-4.1 (substrate + DiscoverySources only; no orchestrator).
    """
    import os
    from ..data.provenance import SOURCE_REGISTRY
    from ..scanners.launch_arbitrage import (
        BitqueryWalletSource,
        DexScreenerFreshLaunchSource,
        HeliusWalletSource,
        JupiterTrendingSource,
        PumpfunLaunchesSource,
    )

    cfg = await get_scanner_config_repo().get("launch_arb")
    state = await get_scanner_state_repo().get("launch_arb")

    # Instantiate sources in-place (no network calls — discover() is not
    # invoked here; only health() which surfaces the last-known telemetry).
    config_loader = lambda: cfg
    empty_universe = lambda: []
    sources = [
        DexScreenerFreshLaunchSource(config_loader=config_loader),
        PumpfunLaunchesSource(config_loader=config_loader),
        JupiterTrendingSource(config_loader=config_loader),
        HeliusWalletSource(config_loader=config_loader,
                            token_universe_loader=empty_universe),
        BitqueryWalletSource(config_loader=config_loader),
    ]

    sources_view = []
    for s in sources:
        h = await s.health()
        per_src_cfg = (cfg.get("discovery_sources") or {}).get(s.source_id, {})
        registry_entry = SOURCE_REGISTRY.get(s.source_id)
        sources_view.append({
            "source_id": s.source_id,
            "tier": s.tier,
            "cadence_s": s.cadence_s,
            "provenance_of_hint": s.provenance_of_hint.value,
            "registry_provenance": (registry_entry.provenance.value
                                     if registry_entry else None),
            "registry_reason": registry_entry.reason if registry_entry else None,
            "enabled_in_config": bool(per_src_cfg.get("enabled", False)),
            "scaffolded_only": bool(per_src_cfg.get("scaffolded_only", False)),
            "credentials_env_var": getattr(s, "credentials_env_var", None),
            "credentials_present": s.credentials_available,
            "health_ok": h.ok,
            "health_last_error": h.last_error,
            "health_last_latency_ms": h.latency_ms,
            "health_last_emission_at": h.last_emission_at,
        })
        try:
            await s.close()
        except Exception:  # noqa: BLE001
            pass

    # Credential presence — never the value itself.
    credential_status = {
        "HELIUS_API_KEY": bool(os.environ.get("HELIUS_API_KEY", "").strip()),
        "BITQUERY_API_KEY": bool(os.environ.get("BITQUERY_API_KEY", "").strip()),
        # Listed for completeness; consumed by other scanners but visible here.
        "ALCHEMY_API_KEY": bool(os.environ.get("ALCHEMY_API_KEY", "").strip()),
        "GRAPH_GATEWAY_API_KEY": bool(os.environ.get("GRAPH_GATEWAY_API_KEY", "").strip()),
    }

    return {
        "wave": "D-4.1",
        "scanner_id": "launch_arb",
        "scanner_state": {
            "enabled": bool(state.get("enabled", False)),
            "dormant_reason": (
                "scanner_orchestrator_not_shipped_yet (lands D-4.5)"
                if not state.get("enabled", False)
                else "operator_enabled_but_orchestrator_not_shipped_yet"
            ),
        },
        "config_seeded": cfg,
        "sources": sources_view,
        "credential_status": credential_status,
        "invariants": {
            "INV_1_DiscoveryCandidate_not_Canonical": "preserved (sources emit DiscoveryCandidate only)",
            "INV_2_only_orchestrator_emits": "preserved (no orchestrator at D-4.1)",
            "INV_3_aggregators_are_hint_only": "preserved (registry markers + verifier override at D-4.4)",
        },
    }



# ============================================================================
# Phase D D-4.6 — Launch Arbitrage operator routes
#
# Mirrors the D-1.0 / D-2.0 / D-3.5 endpoint shape exactly so existing
# operator tooling, dashboards, and scanner-state-mutation patterns work
# unchanged. INV-1/INV-2/INV-3 are inherited from D-4.4 — these endpoints
# are read-only telemetry + a narrow state-mutation surface (kill, resume,
# config patch). The scanner ships disabled at boot; this surface is the
# only operator-controlled activation path (along with the boot env gate
# ``ARBICORE_SCANNER_LAUNCH_ARB``).
# ============================================================================


class LaunchConfigPatch(BaseModel):
    """Operator-tunable subset of ``scanner_config.launch_arb``.

    Only fields explicitly listed here are settable through the public route;
    everything else (e.g. the discovery_sources block's per-source enable
    flags) is mutated through dedicated endpoints to keep audit-log entries
    semantically targeted.
    """
    interval_s: Optional[int] = None
    gate_thresholds: Optional[dict] = None
    rug_gate: Optional[dict] = None
    wallet_intelligence: Optional[dict] = None
    phase_classifier: Optional[dict] = None
    roi_probability: Optional[dict] = None
    discovery_sources: Optional[dict] = None
    default_notional_usd: Optional[float] = None
    verifier_concurrency: Optional[int] = None


@router.get("/scanners/launch_arb/status", dependencies=[Depends(require_auth)])
async def launch_scanner_status():
    """D-4.6 read-only status surface. Mirrors funding_arb / dex_arb shape."""
    scanner = get_launch_arb_scanner()
    cfg = await get_scanner_config_repo().get("launch_arb")
    state = await get_scanner_state_repo().get("launch_arb")
    return {
        "wave": "D-4.5",
        "scanner_id": "launch_arb",
        "primary_metric": "composite_launch_score",
        "enabled": state.get("enabled", False),
        "venue_provider": (
            "default-noop" if scanner.venue_provider_is_default
            else "operator-provided"
        ),
        "config": {
            "interval_s": cfg.get("interval_s"),
            "default_notional_usd": cfg.get("default_notional_usd"),
            "gate_thresholds": cfg.get("gate_thresholds"),
            "rug_gate": cfg.get("rug_gate"),
            "roi_probability": cfg.get("roi_probability"),
            "wallet_intelligence": cfg.get("wallet_intelligence"),
        },
        "scanner_stats": scanner.stats,
        "sources_registered": scanner.source_registry.ids(),
        "verifiers_registered": scanner.verifier_registry.types(),
    }


@router.post("/scanners/launch_arb/kill", dependencies=[Depends(require_auth)])
async def launch_scanner_kill():
    """Operator hard-stop. Sets enabled=False; the orchestrator's next tick
    no-ops. No execution capability is involved (detection-only scanner)."""
    return await get_scanner_state_repo().set_enabled(
        "launch_arb", False, actor="operator_kill")


@router.post("/scanners/launch_arb/resume", dependencies=[Depends(require_auth)])
async def launch_scanner_resume():
    """Operator graduation. Flips enabled=True; the orchestrator starts on
    the next cache refresh cycle. Note: without an operator-wired
    ``LaunchVenueProvider``, every candidate ends as
    ``denied:venue_unreadable`` — visibly counted, never emitted.
    """
    res = await get_scanner_state_repo().set_enabled(
        "launch_arb", True, actor="operator_resume")
    # Best-effort start; safe to call when already running.
    try:
        await get_launch_arb_scanner().start()
    except Exception:  # noqa: BLE001
        pass
    return res


@router.put("/scanners/launch_arb/config",
            dependencies=[Depends(require_auth)])
async def launch_scanner_config_update(patch: LaunchConfigPatch):
    """Patch operator-tunable launch_arb config fields."""
    patch_dict = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not patch_dict:
        raise HTTPException(400, "empty patch")
    return await get_scanner_config_repo().update("launch_arb", patch_dict)


@router.get("/scanners/launch_arb/gate-analysis",
            dependencies=[Depends(require_auth)])
async def launch_gate_analysis(window_minutes: int = 60,
                                asset: Optional[str] = None,
                                launchpad: Optional[str] = None):
    """Aggregation over arbicore_opportunities for D-4 gate telemetry.

    Mirrors the cex_arb / funding_arb / dex_arb gate-analysis shape. The
    only differences: opportunity_type filter is LAUNCH_ARBITRAGE and
    opportunity_id prefix is ``launch_arb:`` (set by D-4.4 verifier).
    """
    from ..runtime.composition import get_db
    from datetime import datetime, timedelta, timezone
    db = get_db()
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    cutoff_iso = cutoff_dt.isoformat()
    q: Dict[str, Any] = {
        "opportunity_type": "LAUNCH_ARBITRAGE",
        "opportunity_id": {"$regex": "^launch_arb:"},
        "created_at": {"$gte": cutoff_iso},
    }
    if asset:
        q["asset"] = asset
    if launchpad:
        q["category_metadata.launchpad"] = launchpad
    total = await db["arbicore_opportunities"].count_documents(q)
    validated_q = dict(q)
    validated_q["status"] = "validated"
    validated = await db["arbicore_opportunities"].count_documents(validated_q)
    pipeline = [
        {"$match": {**q, "metadata.rejected_gate_name": {"$exists": True}}},
        {"$group": {"_id": "$metadata.rejected_gate_name",
                    "count": {"$sum": 1}}},
    ]
    rejections: Dict[str, int] = {}
    async for d in db["arbicore_opportunities"].aggregate(pipeline):
        rejections[str(d["_id"])] = int(d["count"])
    rejected = sum(rejections.values())
    pct = {k: round(100 * v / rejected, 1) if rejected else 0.0
           for k, v in rejections.items()}
    return {
        "wave": "D-4.5",
        "scanner_id": "launch_arb",
        "window_minutes": window_minutes,
        "primary_metric": "composite_launch_score",
        "totals": {"observed": total, "validated": validated,
                    "rejected": rejected},
        "rejections_by_gate": rejections,
        "rejection_pct_by_gate": pct,
        "scanner_stats_live": get_launch_arb_scanner().stats,
    }


@router.get("/scanners/launch_arb/source-health",
            dependencies=[Depends(require_auth)])
async def launch_source_health():
    """Per-source health snapshot. Read-only — calls each source's
    cached ``health()`` (no network I/O at request time).
    """
    scanner = get_launch_arb_scanner()
    out = []
    for src in scanner.source_registry.all():
        h = await src.health()
        out.append({
            "source_id": src.source_id,
            "tier": src.tier,
            "cadence_s": src.cadence_s,
            "credentials_env_var": getattr(src, "credentials_env_var", None),
            "credentials_present": getattr(src, "credentials_available", True),
            "ok": h.ok,
            "latency_ms": h.latency_ms,
            "last_emission_at": h.last_emission_at,
            "last_error": h.last_error,
        })
    return {"wave": "D-4.6", "scanner_id": "launch_arb", "sources": out}


@router.post("/scanners/launch_arb/sources/{source_id}/enable",
              dependencies=[Depends(require_auth)])
async def launch_source_enable(source_id: str):
    """Operator graduation of an individual launch_arb DiscoverySource."""
    cfg = await get_scanner_config_repo().get("launch_arb")
    ds = dict(cfg.get("discovery_sources", {}))
    src_cfg = dict(ds.get(source_id, {}))
    src_cfg["enabled"] = True
    ds[source_id] = src_cfg
    return await get_scanner_config_repo().update(
        "launch_arb", {"discovery_sources": ds})


@router.post("/scanners/launch_arb/sources/{source_id}/disable",
              dependencies=[Depends(require_auth)])
async def launch_source_disable(source_id: str):
    """Operator hard-stop of an individual launch_arb DiscoverySource."""
    cfg = await get_scanner_config_repo().get("launch_arb")
    ds = dict(cfg.get("discovery_sources", {}))
    src_cfg = dict(ds.get(source_id, {}))
    src_cfg["enabled"] = False
    ds[source_id] = src_cfg
    return await get_scanner_config_repo().update(
        "launch_arb", {"discovery_sources": ds})




# ============================================================================
# Phase D D-5.1 — Cross-Chain Arbitrage operator routes
#
# Mirrors the D-4.6 surface exactly with category-specific Pydantic patch
# model. Scanner ships disabled; per-bridge enable lives in bridges.{id}
# rather than discovery_sources.{id} — the dedicated bridge enable/disable
# endpoints below target the bridges block.
# ============================================================================


class CrossChainConfigPatch(BaseModel):
    """Operator-tunable subset of ``scanner_config.cross_chain_arb``."""
    interval_s: Optional[int] = None
    gate_thresholds: Optional[dict] = None
    bridges: Optional[dict] = None
    chains: Optional[dict] = None
    transfer_model: Optional[dict] = None
    roi_probability: Optional[dict] = None
    http_retry: Optional[dict] = None
    default_notional_usd: Optional[float] = None
    verifier_concurrency: Optional[int] = None


@router.get("/scanners/cross_chain_arb/status",
            dependencies=[Depends(require_auth)])
async def cross_chain_scanner_status():
    scanner = get_cross_chain_arb_scanner()
    cfg = await get_scanner_config_repo().get("cross_chain_arb")
    state = await get_scanner_state_repo().get("cross_chain_arb")
    return {
        "wave": "D-5.1",
        "scanner_id": "cross_chain_arb",
        "primary_metric": "total_round_trip_cost_pct",
        "enabled": state.get("enabled", False),
        "transfer_provider": (
            "default-noop" if scanner.transfer_provider_is_default
            else "operator-provided"
        ),
        "config": {
            "interval_s": cfg.get("interval_s"),
            "default_notional_usd": cfg.get("default_notional_usd"),
            "gate_thresholds": cfg.get("gate_thresholds"),
            "bridges": {b: {"enabled": v.get("enabled", False)}
                        for b, v in (cfg.get("bridges") or {}).items()},
            "chains": {c: {"enabled": v.get("enabled", False),
                            "chain_id": v.get("chain_id")}
                        for c, v in (cfg.get("chains") or {}).items()},
        },
        "scanner_stats": scanner.stats,
        "sources_registered": scanner.source_registry.ids(),
        "verifiers_registered": scanner.verifier_registry.types(),
    }


@router.post("/scanners/cross_chain_arb/kill",
             dependencies=[Depends(require_auth)])
async def cross_chain_scanner_kill():
    return await get_scanner_state_repo().set_enabled(
        "cross_chain_arb", False, actor="operator_kill")


@router.post("/scanners/cross_chain_arb/resume",
             dependencies=[Depends(require_auth)])
async def cross_chain_scanner_resume():
    res = await get_scanner_state_repo().set_enabled(
        "cross_chain_arb", True, actor="operator_resume")
    try:
        await get_cross_chain_arb_scanner().start()
    except Exception:  # noqa: BLE001
        pass
    return res


@router.put("/scanners/cross_chain_arb/config",
            dependencies=[Depends(require_auth)])
async def cross_chain_scanner_config_update(patch: CrossChainConfigPatch):
    patch_dict = {k: v for k, v in patch.model_dump().items()
                   if v is not None}
    if not patch_dict:
        raise HTTPException(400, "empty patch")
    return await get_scanner_config_repo().update(
        "cross_chain_arb", patch_dict)


@router.get("/scanners/cross_chain_arb/gate-analysis",
            dependencies=[Depends(require_auth)])
async def cross_chain_gate_analysis(window_minutes: int = 60,
                                     asset: Optional[str] = None,
                                     bridge: Optional[str] = None):
    """Aggregation over arbicore_opportunities for D-5 gate telemetry."""
    from ..runtime.composition import get_db
    from datetime import datetime, timedelta, timezone
    db = get_db()
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    cutoff_iso = cutoff_dt.isoformat()
    q: Dict[str, Any] = {
        "opportunity_type": "CROSS_CHAIN_ARBITRAGE",
        "opportunity_id": {"$regex": "^cross_chain_arb:"},
        "created_at": {"$gte": cutoff_iso},
    }
    if asset:
        q["asset"] = asset
    if bridge:
        q["category_metadata.bridge_provider"] = bridge
    total = await db["arbicore_opportunities"].count_documents(q)
    validated_q = dict(q)
    validated_q["status"] = "validated"
    validated = await db["arbicore_opportunities"].count_documents(validated_q)
    pipeline = [
        {"$match": {**q, "metadata.rejected_gate_name": {"$exists": True}}},
        {"$group": {"_id": "$metadata.rejected_gate_name",
                    "count": {"$sum": 1}}},
    ]
    rejections: Dict[str, int] = {}
    async for d in db["arbicore_opportunities"].aggregate(pipeline):
        rejections[str(d["_id"])] = int(d["count"])
    rejected = sum(rejections.values())
    pct = {k: round(100 * v / rejected, 1) if rejected else 0.0
           for k, v in rejections.items()}
    return {
        "wave": "D-5.1",
        "scanner_id": "cross_chain_arb",
        "window_minutes": window_minutes,
        "primary_metric": "total_round_trip_cost_pct",
        "totals": {"observed": total, "validated": validated,
                    "rejected": rejected},
        "rejections_by_gate": rejections,
        "rejection_pct_by_gate": pct,
        "scanner_stats_live": get_cross_chain_arb_scanner().stats,
    }


@router.get("/scanners/cross_chain_arb/source-health",
            dependencies=[Depends(require_auth)])
async def cross_chain_source_health():
    scanner = get_cross_chain_arb_scanner()
    out = []
    for src in scanner.source_registry.all():
        h = await src.health()
        out.append({
            "source_id": src.source_id,
            "tier": src.tier,
            "cadence_s": src.cadence_s,
            "credentials_env_var": getattr(src, "credentials_env_var", None),
            "credentials_present": getattr(src, "credentials_available", True),
            "ok": h.ok,
            "latency_ms": h.latency_ms,
            "last_emission_at": h.last_emission_at,
            "last_error": h.last_error,
        })
    chain_liveness = {
        chain: snap.to_dict()
        for chain, snap in scanner.chain_liveness.all_snapshots().items()
    }
    return {"wave": "D-5.1", "scanner_id": "cross_chain_arb",
            "sources": out,
            "chain_liveness": chain_liveness,
            "transfer_provider_is_default":
                scanner.transfer_provider_is_default}


@router.post("/scanners/cross_chain_arb/bridges/{bridge_id}/enable",
              dependencies=[Depends(require_auth)])
async def cross_chain_bridge_enable(bridge_id: str):
    cfg = await get_scanner_config_repo().get("cross_chain_arb")
    bridges = dict(cfg.get("bridges", {}))
    b_cfg = dict(bridges.get(bridge_id, {}))
    if not b_cfg:
        raise HTTPException(404, f"unknown bridge: {bridge_id}")
    b_cfg["enabled"] = True
    bridges[bridge_id] = b_cfg
    return await get_scanner_config_repo().update(
        "cross_chain_arb", {"bridges": bridges})


@router.post("/scanners/cross_chain_arb/bridges/{bridge_id}/disable",
              dependencies=[Depends(require_auth)])
async def cross_chain_bridge_disable(bridge_id: str):
    cfg = await get_scanner_config_repo().get("cross_chain_arb")
    bridges = dict(cfg.get("bridges", {}))
    b_cfg = dict(bridges.get(bridge_id, {}))
    if not b_cfg:
        raise HTTPException(404, f"unknown bridge: {bridge_id}")
    b_cfg["enabled"] = False
    bridges[bridge_id] = b_cfg
    return await get_scanner_config_repo().update(
        "cross_chain_arb", {"bridges": bridges})


@router.post("/scanners/cross_chain_arb/chains/{chain_id}/enable",
              dependencies=[Depends(require_auth)])
async def cross_chain_chain_enable(chain_id: str):
    cfg = await get_scanner_config_repo().get("cross_chain_arb")
    chains = dict(cfg.get("chains", {}))
    c_cfg = dict(chains.get(chain_id, {}))
    if not c_cfg:
        raise HTTPException(404, f"unknown chain: {chain_id}")
    c_cfg["enabled"] = True
    chains[chain_id] = c_cfg
    return await get_scanner_config_repo().update(
        "cross_chain_arb", {"chains": chains})


@router.post("/scanners/cross_chain_arb/chains/{chain_id}/disable",
              dependencies=[Depends(require_auth)])
async def cross_chain_chain_disable(chain_id: str):
    cfg = await get_scanner_config_repo().get("cross_chain_arb")
    chains = dict(cfg.get("chains", {}))
    c_cfg = dict(chains.get(chain_id, {}))
    if not c_cfg:
        raise HTTPException(404, f"unknown chain: {chain_id}")
    c_cfg["enabled"] = False
    chains[chain_id] = c_cfg
    return await get_scanner_config_repo().update(
        "cross_chain_arb", {"chains": chains})


@router.get("/scanners/cross_chain_arb/preview",
            dependencies=[Depends(require_auth)])
async def cross_chain_preview():
    """Read-only diagnostic surface mirroring /scanners/launch_arb/preview.

    Surfaces seeded config + per-source health + bridge enable + chain
    enable + chain-liveness snapshots + credential presence — never values.
    """
    import os as _os
    from ..data.provenance import SOURCE_REGISTRY
    scanner = get_cross_chain_arb_scanner()
    cfg = await get_scanner_config_repo().get("cross_chain_arb")
    state = await get_scanner_state_repo().get("cross_chain_arb")
    sources_view = []
    for s in scanner.source_registry.all():
        h = await s.health()
        sources_view.append({
            "source_id": s.source_id,
            "tier": s.tier,
            "cadence_s": s.cadence_s,
            "provenance_of_hint": s.provenance_of_hint.value,
            "credentials_env_var": getattr(s, "credentials_env_var", None),
            "credentials_present": s.credentials_available,
            "health_ok": h.ok,
            "health_last_error": h.last_error,
        })
    bridges_view = {b: {"enabled": v.get("enabled", False),
                         "credentials_env_var": v.get("credentials_env_var"),
                         "credentials_present": bool(_os.environ.get(
                             v.get("credentials_env_var", "_"), "").strip())}
                    for b, v in (cfg.get("bridges") or {}).items()}
    chains_view = {c: {"enabled": v.get("enabled", False),
                        "rpc_env_var": v.get("rpc_env_var"),
                        "rpc_present": bool(_os.environ.get(
                            v.get("rpc_env_var", "_"), "").strip())}
                   for c, v in (cfg.get("chains") or {}).items()}
    registry_view = {
        "lifi_quote_real": (SOURCE_REGISTRY["lifi_quote_real"].provenance.value
                              if "lifi_quote_real" in SOURCE_REGISTRY else None),
        "stargate_quote_real": (
            SOURCE_REGISTRY["stargate_quote_real"].provenance.value
            if "stargate_quote_real" in SOURCE_REGISTRY else None),
    }
    return {
        "wave": "D-5.1",
        "scanner_id": "cross_chain_arb",
        "scanner_state": {
            "enabled": bool(state.get("enabled", False)),
            "transfer_provider": (
                "default-noop" if scanner.transfer_provider_is_default
                else "operator-provided"),
        },
        "sources": sources_view,
        "bridges": bridges_view,
        "chains": chains_view,
        "registry_provenance": registry_view,
        "invariants": {
            "INV_1_DiscoveryCandidate_not_Canonical":
                "preserved (sources emit DiscoveryCandidate only)",
            "INV_2_only_orchestrator_emits":
                "preserved (CrossChainArbitrageScanner._tick is sole emit site)",
            "INV_3_canonical_provenance_from_legs":
                "preserved (verifier uses lifi_quote_real / stargate_quote_real)",
        },
    }


# ============================================================================
# Phase D D-6.1 — Flash-Loan Arbitrage operator routes
# ============================================================================


class FlashLoanConfigPatch(BaseModel):
    interval_s: Optional[int] = None
    gate_thresholds: Optional[dict] = None
    providers: Optional[dict] = None
    chains: Optional[dict] = None
    route_search: Optional[dict] = None
    roi_probability: Optional[dict] = None
    http_retry: Optional[dict] = None
    default_notional_usd: Optional[float] = None
    verifier_concurrency: Optional[int] = None


@router.get("/scanners/flash_loan_arb/status",
            dependencies=[Depends(require_auth)])
async def flash_loan_status():
    scanner = get_flash_loan_arb_scanner()
    cfg = await get_scanner_config_repo().get("flash_loan_arb")
    state = await get_scanner_state_repo().get("flash_loan_arb")
    return {
        "wave": "D-6.1",
        "scanner_id": "flash_loan_arb",
        "primary_metric": "atomic_profit_usd",
        "enabled": state.get("enabled", False),
        "quote_provider": (
            "default-noop" if scanner.quote_provider_is_default
            else "operator-provided"
        ),
        "config": {
            "interval_s": cfg.get("interval_s"),
            "default_notional_usd": cfg.get("default_notional_usd"),
            "gate_thresholds": cfg.get("gate_thresholds"),
            "route_search": cfg.get("route_search"),
            "providers": {p: {"enabled": v.get("enabled", False)}
                          for p, v in (cfg.get("providers") or {}).items()},
            "chains": {c: {"enabled": v.get("enabled", False)}
                       for c, v in (cfg.get("chains") or {}).items()},
        },
        "scanner_stats": scanner.stats,
        "sources_registered": scanner.source_registry.ids(),
        "verifiers_registered": scanner.verifier_registry.types(),
    }


@router.post("/scanners/flash_loan_arb/kill",
             dependencies=[Depends(require_auth)])
async def flash_loan_kill():
    return await get_scanner_state_repo().set_enabled(
        "flash_loan_arb", False, actor="operator_kill")


@router.post("/scanners/flash_loan_arb/resume",
             dependencies=[Depends(require_auth)])
async def flash_loan_resume():
    res = await get_scanner_state_repo().set_enabled(
        "flash_loan_arb", True, actor="operator_resume")
    try:
        await get_flash_loan_arb_scanner().start()
    except Exception:  # noqa: BLE001
        pass
    return res


@router.put("/scanners/flash_loan_arb/config",
            dependencies=[Depends(require_auth)])
async def flash_loan_config_update(patch: FlashLoanConfigPatch):
    p = {k: v for k, v in patch.model_dump().items() if v is not None}
    if not p:
        raise HTTPException(400, "empty patch")
    return await get_scanner_config_repo().update("flash_loan_arb", p)


@router.get("/scanners/flash_loan_arb/gate-analysis",
            dependencies=[Depends(require_auth)])
async def flash_loan_gate_analysis(window_minutes: int = 60,
                                    chain: Optional[str] = None,
                                    provider: Optional[str] = None):
    from ..runtime.composition import get_db
    from datetime import datetime, timedelta, timezone
    db = get_db()
    cutoff_dt = datetime.now(timezone.utc) - timedelta(minutes=window_minutes)
    cutoff_iso = cutoff_dt.isoformat()
    q: Dict[str, Any] = {
        "opportunity_type": "FLASH_LOAN_ARBITRAGE",
        "opportunity_id": {"$regex": "^flash_loan_arb:"},
        "created_at": {"$gte": cutoff_iso},
    }
    if chain:
        q["category_metadata.chain"] = chain
    if provider:
        q["category_metadata.flash_loan_provider"] = provider
    total = await db["arbicore_opportunities"].count_documents(q)
    validated_q = dict(q)
    validated_q["status"] = "validated"
    validated = await db["arbicore_opportunities"].count_documents(validated_q)
    pipeline = [
        {"$match": {**q, "metadata.rejected_gate_name": {"$exists": True}}},
        {"$group": {"_id": "$metadata.rejected_gate_name",
                    "count": {"$sum": 1}}},
    ]
    rejections: Dict[str, int] = {}
    async for d in db["arbicore_opportunities"].aggregate(pipeline):
        rejections[str(d["_id"])] = int(d["count"])
    rejected = sum(rejections.values())
    pct = {k: round(100 * v / rejected, 1) if rejected else 0.0
           for k, v in rejections.items()}
    return {
        "wave": "D-6.1",
        "scanner_id": "flash_loan_arb",
        "window_minutes": window_minutes,
        "primary_metric": "atomic_profit_usd",
        "totals": {"observed": total, "validated": validated,
                    "rejected": rejected},
        "rejections_by_gate": rejections,
        "rejection_pct_by_gate": pct,
        "scanner_stats_live": get_flash_loan_arb_scanner().stats,
    }


@router.get("/scanners/flash_loan_arb/source-health",
            dependencies=[Depends(require_auth)])
async def flash_loan_source_health():
    scanner = get_flash_loan_arb_scanner()
    out = []
    for src in scanner.source_registry.all():
        h = await src.health()
        out.append({
            "source_id": src.source_id,
            "tier": src.tier,
            "cadence_s": src.cadence_s,
            "credentials_env_var": getattr(src, "credentials_env_var", None),
            "credentials_present": getattr(src, "credentials_available", True),
            "ok": h.ok,
            "latency_ms": h.latency_ms,
            "last_emission_at": h.last_emission_at,
            "last_error": h.last_error,
        })
    return {
        "wave": "D-6.1",
        "scanner_id": "flash_loan_arb",
        "sources": out,
        "route_engine": {
            "max_hops": scanner.route_engine.max_hops,
            "wall_clock_cap_s": scanner.route_engine.wall_clock_cap_s,
            "candidate_cap": scanner.route_engine.candidate_cap,
            "min_pool_tvl_usd": scanner.route_engine.min_pool_tvl_usd,
            "last_wall_ms": scanner.route_engine.last_wall_ms,
            "last_explored": scanner.route_engine.last_explored,
        },
        "quote_provider_is_default": scanner.quote_provider_is_default,
    }


@router.post("/scanners/flash_loan_arb/providers/{provider_id}/enable",
              dependencies=[Depends(require_auth)])
async def flash_loan_provider_enable(provider_id: str):
    cfg = await get_scanner_config_repo().get("flash_loan_arb")
    providers = dict(cfg.get("providers", {}))
    p = dict(providers.get(provider_id, {}))
    if not p:
        raise HTTPException(404, f"unknown provider: {provider_id}")
    p["enabled"] = True
    providers[provider_id] = p
    return await get_scanner_config_repo().update(
        "flash_loan_arb", {"providers": providers})


@router.post("/scanners/flash_loan_arb/providers/{provider_id}/disable",
              dependencies=[Depends(require_auth)])
async def flash_loan_provider_disable(provider_id: str):
    cfg = await get_scanner_config_repo().get("flash_loan_arb")
    providers = dict(cfg.get("providers", {}))
    p = dict(providers.get(provider_id, {}))
    if not p:
        raise HTTPException(404, f"unknown provider: {provider_id}")
    p["enabled"] = False
    providers[provider_id] = p
    return await get_scanner_config_repo().update(
        "flash_loan_arb", {"providers": providers})


@router.post("/scanners/flash_loan_arb/chains/{chain_id}/enable",
              dependencies=[Depends(require_auth)])
async def flash_loan_chain_enable(chain_id: str):
    cfg = await get_scanner_config_repo().get("flash_loan_arb")
    chains = dict(cfg.get("chains", {}))
    c = dict(chains.get(chain_id, {}))
    if not c:
        raise HTTPException(404, f"unknown chain: {chain_id}")
    c["enabled"] = True
    chains[chain_id] = c
    return await get_scanner_config_repo().update(
        "flash_loan_arb", {"chains": chains})


@router.post("/scanners/flash_loan_arb/chains/{chain_id}/disable",
              dependencies=[Depends(require_auth)])
async def flash_loan_chain_disable(chain_id: str):
    cfg = await get_scanner_config_repo().get("flash_loan_arb")
    chains = dict(cfg.get("chains", {}))
    c = dict(chains.get(chain_id, {}))
    if not c:
        raise HTTPException(404, f"unknown chain: {chain_id}")
    c["enabled"] = False
    chains[chain_id] = c
    return await get_scanner_config_repo().update(
        "flash_loan_arb", {"chains": chains})


@router.get("/scanners/flash_loan_arb/preview",
            dependencies=[Depends(require_auth)])
async def flash_loan_preview():
    import os as _os
    from ..data.provenance import SOURCE_REGISTRY
    scanner = get_flash_loan_arb_scanner()
    cfg = await get_scanner_config_repo().get("flash_loan_arb")
    state = await get_scanner_state_repo().get("flash_loan_arb")
    sources_view = []
    for s in scanner.source_registry.all():
        h = await s.health()
        sources_view.append({
            "source_id": s.source_id,
            "tier": s.tier,
            "cadence_s": s.cadence_s,
            "provenance_of_hint": s.provenance_of_hint.value,
            "credentials_present": s.credentials_available,
            "health_ok": h.ok,
            "health_last_error": h.last_error,
        })
    providers_view = {p: {"enabled": v.get("enabled", False),
                            "fee_bps_default": v.get("fee_bps") or v.get(
                                "fee_bps_default")}
                       for p, v in (cfg.get("providers") or {}).items()}
    chains_view = {c: {"enabled": v.get("enabled", False),
                        "rpc_env_var": v.get("rpc_env_var"),
                        "rpc_present": bool(_os.environ.get(
                            v.get("rpc_env_var", "_"), "").strip())}
                   for c, v in (cfg.get("chains") or {}).items()}
    registry_view = {
        sid: (SOURCE_REGISTRY[sid].provenance.value
               if sid in SOURCE_REGISTRY else None)
        for sid in ("aave_v3_flashloan_real",
                     "balancer_v2_flashloan_real",
                     "uniswap_v3_flashloan_real")
    }
    return {
        "wave": "D-6.1",
        "scanner_id": "flash_loan_arb",
        "scanner_state": {
            "enabled": bool(state.get("enabled", False)),
            "quote_provider": (
                "default-noop" if scanner.quote_provider_is_default
                else "operator-provided"),
        },
        "sources": sources_view,
        "providers": providers_view,
        "chains": chains_view,
        "registry_provenance": registry_view,
        "invariants": {
            "INV_1_DiscoveryCandidate_not_Canonical":
                "preserved (sources emit DiscoveryCandidate only)",
            "INV_2_only_orchestrator_emits":
                "preserved (FlashLoanArbitrageScanner._tick is sole emit "
                "site; 6th and final across the tree)",
            "INV_3_canonical_provenance_from_legs":
                "preserved (verifier uses provider source_ids: "
                "aave_v3_flashloan_real / balancer_v2_flashloan_real / "
                "uniswap_v3_flashloan_real)",
        },
    }

