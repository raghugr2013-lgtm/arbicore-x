"""Multichain readiness gate — explicit, auditable per-network status.

Read-only. Never signs / broadcasts / enables anything. Deterministic + offline:
reports code availability, operator configuration and the EXACT blocker per
network. It NEVER represents a network as limited-live eligible merely because
its code exists or an RPC is configured — genuine limited-live eligibility
requires a real VPS runtime proof (live discovery → quote → liquidity/TVL →
economics → verification → simulation → evidence persistence/readback) plus
explicit administrator approval, none of which a static report can assert.

Capability-state vocabulary (never collapsed): IMPLEMENTED · CONFIGURED ·
DISCOVERABLE · QUOTABLE · ECONOMICALLY VALID · VERIFIABLE · SIMULATABLE ·
LIMITED-LIVE ELIGIBLE. Every live dimension is reported as
``implemented_unverified`` until proven on the VPS.
"""
from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

_LOG = logging.getLogger("arbicore.multichain_readiness")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def supported_networks() -> List[str]:
    """All networks with an implemented route universe: canonical Base plus the
    generic multi-chain discovery chains (deduped, deterministic order)."""
    from ..discovery.multichain_venues import supported_discovery_chains
    out: List[str] = ["base"]
    for c in supported_discovery_chains():
        if c not in out:
            out.append(c)
    return out


def rpc_explicitly_configured(chain: str) -> bool:
    """DISCOVERY-level: the operator configured ANY RPC for ``chain`` via a
    recognised operator key (``PROVIDER_RPC_URLS_<CHAIN>`` /
    ``PROVIDER_RPC_URL_<CHAIN>`` / ``ARBICORE_RPC_URL_<CHAIN>`` /
    ``<CHAIN>_RPC_URL``). A hardcoded public default does NOT count.

    NOTE: this is the looser discovery/quote notion. The safety-critical
    ALL-IN-COST (economic) gate uses the STRICTER registry contract below
    (`provider_registry_rpc_configured`) — the two are intentionally distinct
    so the readiness blocker is honest about which prerequisite is unmet."""
    c = (chain or "").upper()
    keys = [f"PROVIDER_RPC_URLS_{c}", f"PROVIDER_RPC_URL_{c}",
            f"ARBICORE_RPC_URL_{c}", f"{c}_RPC_URL"]
    return any((os.environ.get(k) or "").strip() for k in keys)


def provider_registry_rpc_configured(chain: str) -> bool:
    """ECONOMIC gate: only the endpoints the provider registry actually consumes
    (``PROVIDER_RPC_URLS_<CHAIN>`` / ``PROVIDER_RPC_URL_<CHAIN>``) back the
    all-in-cost estimator. ``ARBICORE_RPC_URL_*`` is NOT sufficient here (it is
    not synced into the registry), matching
    ``base_all_in_cost.base_rpc_explicitly_configured`` exactly for Base."""
    c = (chain or "").upper()
    return bool((os.environ.get(f"PROVIDER_RPC_URLS_{c}") or "").strip()
                or (os.environ.get(f"PROVIDER_RPC_URL_{c}") or "").strip())


def _discovery_universe_size(chain: str) -> int:
    c = (chain or "").lower()
    try:
        if c == "base":
            from ..discovery.base_pool_registry import build_canonical_pool_graph
            return len(build_canonical_pool_graph(resolved_only=True)[0])
        from ..discovery.multichain_venues import build_pool_graph
        return len(build_pool_graph(c))
    except Exception as exc:  # noqa: BLE001 — report 0 (fail-closed), but log why
        _LOG.warning("discovery universe unreadable for chain=%s: %s: %s",
                     chain, type(exc).__name__, exc)
        return 0


def _gas_model_object_exists(chain: str) -> bool:
    try:
        from ..chains.gas_model import get_chain_gas_model
        return get_chain_gas_model(chain) is not None
    except Exception:  # noqa: BLE001
        return False


def _network_readiness(chain: str) -> Dict[str, Any]:
    implemented = True
    rpc_configured = rpc_explicitly_configured(chain)          # discovery-level
    economic_rpc = provider_registry_rpc_configured(chain)     # all-in-cost gate
    universe = _discovery_universe_size(chain)
    gas_model = _gas_model_object_exists(chain)
    # Honest economic readiness: the all-in-cost estimator can only price when a
    # registry-backing RPC is configured AND a gas model exists. A gas-model
    # OBJECT existing is NOT sufficient (its estimator fails closed without RPC).
    economic_ready = bool(economic_rpc and gas_model)

    # Exact blocker (priority order). Limited-live is NEVER eligible from a
    # static report — the terminal blocker is always the runtime proof gate.
    if not implemented:
        blocker = "not_implemented"
    elif not rpc_configured:
        blocker = "no_operator_configured_rpc"
    elif not gas_model:
        blocker = "no_gas_model"
    elif not economic_ready:
        # Discovery RPC present but the registry-backing RPC the all-in-cost
        # gate needs (PROVIDER_RPC_URL[S]_<CHAIN>) is not configured.
        blocker = "economic_gate_rpc_not_configured"
    elif universe <= 0:
        blocker = "empty_route_universe"
    else:
        blocker = "requires_vps_runtime_proof_and_admin_approval"

    return {
        "implemented": implemented,
        "rpc_configured": rpc_configured,          # discovery-level (looser)
        "economic_rpc_configured": economic_rpc,   # registry-backing (stricter)
        "rpc_healthy": "unverified",               # requires a live probe (VPS)
        "discovery": {"status": "implemented",
                      "route_universe_size": universe},
        "quoting": {"status": "implemented_unverified"},
        "liquidity_tvl": {"status": "implemented_unverified"},
        "verification": {"status": "implemented_unverified"},
        "simulation": {"status": "implemented_unverified"},
        "economic_eligibility": {
            "status": "eligible_pending_runtime" if economic_ready else "blocked",
            "gas_model": gas_model,
            "economic_rpc_configured": economic_rpc,
        },
        "limited_live_eligible": False,            # never true from code/config alone
        "blocker": blocker,
    }


def build_multichain_readiness_report() -> Dict[str, Any]:
    """Machine-readable per-network readiness report. Pure/offline; safe to call
    per request (no RPC round-trips)."""
    networks = {c: _network_readiness(c) for c in supported_networks()}
    blocked_by: Dict[str, int] = {}
    for r in networks.values():
        blocked_by[r["blocker"]] = blocked_by.get(r["blocker"], 0) + 1
    # Derived from the per-network flags (never hardcoded) so a future edit that
    # flips a flag cannot silently leave the summary stale.
    eligible_count = sum(1 for r in networks.values()
                         if r["limited_live_eligible"])
    return {
        "generated_at": _iso_now(),
        "safety": {
            "posture": "SHADOW / detection-only / fail-closed",
            "signed": False,
            "broadcast": False,
            "limited_live_enabled": False,
        },
        "networks": networks,
        "summary": {
            "network_count": len(networks),
            "limited_live_eligible_count": eligible_count,
            "blocked_by": blocked_by,
        },
        "note": ("No network is limited-live eligible from implemented code or a "
                 "configured RPC alone. Limited-live requires a real VPS runtime "
                 "proof (live discovery→quote→liquidity→economics→verification→"
                 "simulation→evidence readback) plus explicit admin approval."),
    }


__all__ = [
    "supported_networks",
    "rpc_explicitly_configured",
    "provider_registry_rpc_configured",
    "build_multichain_readiness_report",
]
