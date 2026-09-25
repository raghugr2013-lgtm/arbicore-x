"""ArbiCore X — consolidated production-readiness COLLECTORS (read-only).

Composes the EXISTING probes into one ``ReadinessItem`` list, then hands them to
``readiness_core.aggregate``. Every collector is best-effort and fail-closed:
if a dependency is missing/unreadable it emits UNKNOWN/BLOCKED with the exact
reason + category, never a fabricated READY. Never signs/broadcasts, never
mutates config, never prints secrets (only counts/addresses/statuses).

Run via ``scripts/production_readiness.py``.
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Dict, List, Optional

from .readiness_core import Category, ReadinessItem, Status, aggregate

logger = logging.getLogger("arbicore.production_readiness")

SIX_CHAINS = ("base", "ethereum", "arbitrum", "optimism", "polygon", "bnb")


def _safe(fn: Callable[[], List[ReadinessItem]], domain: str) -> List[ReadinessItem]:
    try:
        return fn() or []
    except Exception as exc:  # noqa: BLE001 — a collector failure never READYs
        return [ReadinessItem(domain=domain, subject="collector",
                              status=Status.UNKNOWN, category=Category.CODE,
                              why_blocked=f"collector_error:{type(exc).__name__}:{exc}",
                              where_configured=domain)]


# --------------------------------------------------------------------------
# ENV — per-chain RPC presence (never prints the URL)
# --------------------------------------------------------------------------

def collect_rpc() -> List[ReadinessItem]:
    from ..config.persistent import resolve_rpc_url_from_env
    out: List[ReadinessItem] = []
    for c in SIX_CHAINS:
        url = None
        try:
            url = resolve_rpc_url_from_env(c)
        except Exception:  # noqa: BLE001
            url = None
        if url:
            out.append(ReadinessItem("RPC", c, Status.READY,
                                     detail={"configured": True}))
        else:
            out.append(ReadinessItem(
                "RPC", c, Status.BLOCKED, Category.ENVIRONMENT,
                what_missing=f"PROVIDER_RPC_URL(S)_{c.upper()}",
                why_blocked="no operator RPC configured for this chain",
                where_configured="env: PROVIDER_RPC_URLS_<CHAIN> (CSV) or PROVIDER_RPC_URL_<CHAIN>",
                required_value="one or more HTTPS RPC endpoints"))
    return out


# --------------------------------------------------------------------------
# CODE/ENV — provider × chain (catalog) + runtime-probe availability
# --------------------------------------------------------------------------

def collect_providers() -> List[ReadinessItem]:
    from ..scanners.flash_loan_arbitrage.economics import FLASH_LOAN_PROVIDERS
    try:
        from ..scanners.flash_loan_arbitrage.provider_liquidity import (
            RUNTIME_PROBE_PROVIDERS)
    except Exception:  # noqa: BLE001
        RUNTIME_PROBE_PROVIDERS = set()
    out: List[ReadinessItem] = []
    for name, meta in FLASH_LOAN_PROVIDERS.items():
        chains = meta.get("supports_chains", ())
        for c in SIX_CHAINS:
            subj = f"{c}/{name}"
            if c not in chains:
                continue  # not a gap — provider simply absent on this chain
            if name in RUNTIME_PROBE_PROVIDERS:
                out.append(ReadinessItem("PROVIDER", subj, Status.READY,
                                         detail={"fee_bps": meta.get("fee_bps_default")}))
            else:
                out.append(ReadinessItem(
                    "PROVIDER", subj, Status.DEGRADED, Category.CODE,
                    what_missing="runtime liquidity probe",
                    why_blocked=f"{name} is catalog-present but has no runtime "
                                "liquidity reader (fail-closed → never a live candidate)",
                    where_configured="scanners/flash_loan_arbitrage/provider_liquidity.py",
                    required_value="implement RUNTIME_PROBE_PROVIDERS entry or mark detection-only"))
    return out


# --------------------------------------------------------------------------
# CODE — DEX venue routability per chain (route probe graph vs registry)
# --------------------------------------------------------------------------

def collect_venues() -> List[ReadinessItem]:
    from ..chains import registries
    # Families the generic route probe graph can resolve on-chain AND quote
    # (live QuoterRegistry adapter present). V-2 added algebra (Camelot/QuickSwap).
    PROBED_ABIS = {"univ3", "univ2", "algebra"}
    # Families genuinely registered but with NO live quoter adapter yet → precise
    # CODE remainder (exact missing dependency stated per family).
    CODE_REMAINDER = {
        "solidly": "needs a dex='velodrome_v2' QuoterRegistry backend "
                   "(Router.getAmountsOut solidly ABI; pattern exists in "
                   "AerodromeClassicQuoter) + Velodrome router address (ENV/registry)",
        "curve": "needs a Curve stableswap get_dy QuoterRegistry adapter + "
                 "Curve registry/pool resolver",
    }
    out: List[ReadinessItem] = []
    for c in SIX_CHAINS:
        if c == "base":
            out.append(ReadinessItem("VENUE", "base/uniswap_v3", Status.READY,
                                     detail={"routable": True}))
            out.append(ReadinessItem("VENUE", "base/aerodrome", Status.READY,
                                     detail={"routable": True, "note": "quotable; exec gated by receiver version"}))
            out.append(ReadinessItem("VENUE", "base/aerodrome_slipstream", Status.READY,
                                     detail={"routable": True}))
            continue
        try:
            dexes = registries.dexes_for(c)
        except Exception:  # noqa: BLE001
            dexes = []
        for d in dexes:
            abi = d.get("abi")
            subj = f"{c}/{d.get('dex')}"
            if abi in PROBED_ABIS:
                out.append(ReadinessItem("VENUE", subj, Status.READY,
                                         detail={"abi": abi, "routable": True}))
            else:
                out.append(ReadinessItem(
                    "VENUE", subj, Status.DEGRADED, Category.CODE,
                    what_missing=f"live quoter adapter for '{abi}' family",
                    why_blocked=f"{d.get('dex')} ({abi}) is a registered venue with a real "
                                "factory but has no live quote adapter → not routed",
                    where_configured="execution/quoter.py + discovery/multichain_venues.py",
                    required_value=CODE_REMAINDER.get(abi, f"add {abi} quoter+resolver")))
    return out


def collect_exec_capability() -> List[ReadinessItem]:
    """EXEC-capability per venue, driven by the DEPLOYED receiver version (V-3).

    Reads ARBICORE_RECEIVER_VERSION (fail-closed default 'v1'). Only venues in the
    deployed version's profile are execution-capable; everything else is
    discovery/quote-only until Executor V2 (that version) is deployed + verified.
    """
    from ..scanners.flash_loan_arbitrage.executor_capability import (
        capability_profile_for, DEFAULT_RECEIVER_VERSION)
    version = os.environ.get("ARBICORE_RECEIVER_VERSION", DEFAULT_RECEIVER_VERSION)
    profile = capability_profile_for(version)
    exec_dexes = profile["dexes"]
    exec_heads = profile["flash_providers"]
    out = [ReadinessItem("EXEC", f"receiver_version={version}", Status.READY,
                         detail={"dexes": sorted(exec_dexes),
                                 "flash_providers": sorted(exec_heads)})]
    # Report the breadth gap explicitly: quotable venues not yet executable.
    quotable_not_exec = {"aerodrome", "aerodrome_slipstream", "camelot_v3",
                         "quickswap_v3", "sushiswap_v3", "pancakeswap_v3"} - exec_dexes
    for dex in sorted(quotable_not_exec):
        out.append(ReadinessItem(
            "EXEC", f"venue/{dex}", Status.DEGRADED, Category.INFRASTRUCTURE,
            what_missing="Executor V2 deployment supporting this swap venue",
            why_blocked=f"{dex} is quotable/routable but the deployed receiver "
                        f"(version={version}) settles only {sorted(exec_dexes)}",
            where_configured="contracts FlashLoanReceiver (Executor V2) + on-chain deploy",
            required_value="deploy+verify Executor V2, set ARBICORE_RECEIVER_VERSION"))
    return out


# --------------------------------------------------------------------------
# ENV/CODE — chain scan enablement (persisted config actually honoured?)
# --------------------------------------------------------------------------

def collect_scan_enablement(cfg_snapshot: Optional[Dict] = None) -> List[ReadinessItem]:
    """Reports which chains the flash-loan scanner will actually iterate.

    ``cfg_snapshot`` is the LIVE flash-loan config the running scanner uses
    (chains/providers/route_search) — passed in by the CLI from the running
    scanner instance when available so this reflects RUNTIME, not just the DB.
    """
    out: List[ReadinessItem] = []
    cfg = cfg_snapshot or {}
    chains_cfg = (cfg.get("chains") or {})
    rs = (cfg.get("route_search") or {})
    for c in SIX_CHAINS:
        enabled = bool((chains_cfg.get(c) or {}).get("enabled"))
        if enabled:
            out.append(ReadinessItem("SCAN", c, Status.READY,
                                     detail={"enabled": True}))
        else:
            out.append(ReadinessItem(
                "SCAN", c, Status.BLOCKED, Category.ENVIRONMENT,
                what_missing="chain enable flag",
                why_blocked="chain not enabled in the live flash-loan scanner config",
                where_configured="mongo: scanner.flash_loan_arb.chains.<chain>.enabled",
                required_value="apply {enabled: true} (and configure RPC)"))
    if rs:
        out.append(ReadinessItem("SCAN", "route_search", Status.READY,
                                 detail={"max_hops": rs.get("max_hops"),
                                         "min_pool_tvl_usd": rs.get("min_pool_tvl_usd")}))
    return out


# --------------------------------------------------------------------------
# MARKET — is there a genuine qualifying edge right now?
# --------------------------------------------------------------------------

def collect_market(latest_race_winner: Optional[dict] = None) -> List[ReadinessItem]:
    if latest_race_winner and float(latest_race_winner.get("net_profit_usd") or 0) >= 25.0:
        return [ReadinessItem("MARKET", "qualifying_edge", Status.READY,
                              detail={"net_profit_usd": latest_race_winner.get("net_profit_usd")})]
    return [ReadinessItem(
        "MARKET", "qualifying_edge", Status.BLOCKED, Category.MARKET,
        what_missing="a genuine >= $25 net (>= $35 conservative) atomic edge",
        why_blocked="no qualifying opportunity present in the latest race (correct fail-closed)",
        where_configured="opportunity race / live market",
        required_value="wait for market; never lower Gate-7 or fabricate")]


def build_report(*, head_sha: str = "",
                 flash_cfg_snapshot: Optional[Dict] = None,
                 latest_race_winner: Optional[dict] = None) -> Dict:
    items: List[ReadinessItem] = []
    items += _safe(collect_rpc, "RPC")
    items += _safe(collect_providers, "PROVIDER")
    items += _safe(collect_venues, "VENUE")
    items += _safe(collect_exec_capability, "EXEC")
    items += _safe(lambda: collect_scan_enablement(flash_cfg_snapshot), "SCAN")
    items += _safe(lambda: collect_market(latest_race_winner), "MARKET")
    return aggregate(items, head_sha=head_sha, generated_by="production_readiness")


__all__ = ["build_report", "SIX_CHAINS"]
