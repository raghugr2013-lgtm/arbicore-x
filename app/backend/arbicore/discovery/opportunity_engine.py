"""Wide, parallel, fail-closed opportunity-surface engine (discovery + matrix).

Composes EXISTING pieces — chain registries, the multichain UniV3 pool resolver,
the multichain readiness gate and the QuoterRegistry — into:

  * ``enumerate_capabilities()`` — every registered chain × venue × strategy with
    DISTINCT capability states (never inferred from one another).
  * ``discover_pools_parallel()`` — bounded-concurrency, per-task-timeout pool
    resolution across many (chain, pair, fee) tasks; one failed chain/venue/RPC
    NEVER blocks the rest (``return_exceptions`` + fail-closed to None).
  * ``build_opportunity_matrix()`` — the CHAIN|VENUE|STRATEGY matrix showing
    exactly where a candidate is lost and why (explicit blocker).

REAL DATA ONLY: this module resolves real pools via an injected async
``eth_call`` and reports honest states. It NEVER fabricates pools, liquidity,
quotes, prices, gas, profitability or opportunities. Live economics/simulation
remain SEPARATE downstream gates — a pool being DISCOVERABLE never implies
QUOTABLE/ECONOMICALLY-VALID/SIMULATABLE/LIMITED-LIVE. No signing/broadcast.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..chains.registries import dexes_for
from .univ3_pool_resolver import EthCall, resolve_univ3_pool, univ3_factory_for
from ..runtime.multichain_readiness import (
    provider_registry_rpc_configured,
    rpc_explicitly_configured,
    supported_networks,
)

# Implemented arbitrage strategies (the canonical scanners in the repo). Kept
# as a documented constant so dormant strategies are never dropped from the
# surface; runtime readiness is reported per-cell, not inferred from existence.
IMPLEMENTED_STRATEGIES: Tuple[str, ...] = (
    "flash_loan_arbitrage",
    "dex_arbitrage",            # cross-DEX / intra-DEX / multi-hop
    "cross_chain_arbitrage",
    "cex_funding_arbitrage",
    "launch_arbitrage",
)

# Base's canonical venues (served by base_pool_registry / aero_resolver, not the
# generic multichain registry).
_BASE_VENUES: Tuple[str, ...] = ("uniswap_v3", "aerodrome_slipstream", "aerodrome")


def venues_for(chain: str) -> List[str]:
    c = (chain or "").lower()
    if c == "base":
        return list(_BASE_VENUES)
    return [d.get("dex") for d in dexes_for(c) if d.get("dex")]


def enumerate_capabilities() -> Dict[str, Any]:
    """Registered chains × venues × strategies, each an implemented capability.
    Availability/readiness is reported separately (see the matrix)."""
    chains = supported_networks()
    return {
        "chains": chains,
        "venues": {c: venues_for(c) for c in chains},
        "strategies": list(IMPLEMENTED_STRATEGIES),
        "note": ("Every entry is IMPLEMENTED. CONFIGURED/AVAILABLE/DISCOVERABLE/"
                 "QUOTABLE/ECONOMIC/SIMULATABLE/LIMITED-LIVE are distinct states "
                 "reported per cell and never inferred from IMPLEMENTED."),
    }


async def discover_pools_parallel(
    tasks: List[Dict[str, Any]], *,
    eth_call_for_chain: Callable[[str], Optional[EthCall]],
    max_concurrency: int = 8,
    per_task_timeout_s: Optional[float] = 5.0,
) -> List[Dict[str, Any]]:
    """Resolve many UniV3 pools concurrently, fail-closed and non-blocking.

    Each task = {chain, token_a, token_b, fee}. ``eth_call_for_chain(chain)``
    returns an async eth_call or None (⇒ that chain is unavailable/fail-closed;
    it does NOT stop other chains). A per-task timeout bounds a slow/hung RPC,
    classified as unresolved (never eligible). Returns one result row per task
    with ``resolved`` (bool) + ``pool`` (validated descriptor or None) + reason.
    """
    sem = asyncio.Semaphore(max(1, int(max_concurrency)))

    async def _one(task: Dict[str, Any]) -> Dict[str, Any]:
        chain = task.get("chain")
        base = {"chain": chain, "token_a": task.get("token_a"),
                "token_b": task.get("token_b"), "fee": task.get("fee")}
        eth_call = eth_call_for_chain(chain)
        if eth_call is None:
            return {**base, "resolved": False, "pool": None,
                    "reason": "chain_rpc_unavailable"}
        async with sem:
            try:
                coro = resolve_univ3_pool(
                    chain, task["token_a"], task["token_b"], task["fee"],
                    eth_call=eth_call)
                pool = (await asyncio.wait_for(coro, timeout=per_task_timeout_s)
                        if per_task_timeout_s else await coro)
            except Exception as exc:  # noqa: BLE001 — timeout/RPC fault fail-closed
                return {**base, "resolved": False, "pool": None,
                        "reason": f"resolve_error:{type(exc).__name__}"}
        if pool is None:
            # Base/base-sepolia are served by the canonical registry, not this
            # generic resolver — report that honestly rather than as invalid.
            reason = ("handled_by_canonical_registry"
                      if (chain or "").lower() in ("base", "base-sepolia")
                      else "pool_invalid_or_unreadable")
            return {**base, "resolved": False, "pool": None, "reason": reason}
        return {**base, "resolved": True, "pool": pool, "reason": "ok"}

    results = await asyncio.gather(*(_one(t) for t in tasks),
                                   return_exceptions=True)
    out: List[Dict[str, Any]] = []
    for t, r in zip(tasks, results):
        if isinstance(r, Exception):
            out.append({"chain": t.get("chain"), "resolved": False,
                        "pool": None, "reason": f"task_error:{type(r).__name__}"})
        else:
            out.append(r)
    return out


def _cell_state(chain: str, venue: str, *, quoter_supported: bool) -> Dict[str, Any]:
    implemented = True
    rpc = rpc_explicitly_configured(chain)              # discovery-level
    econ_rpc = provider_registry_rpc_configured(chain)  # economic gate
    is_univ3 = venue == "uniswap_v3"
    factory = univ3_factory_for(chain) if is_univ3 else None
    # DISCOVERABLE = a real resolution path exists. Base (canonical registry via
    # base_pool_registry/aero_resolver) resolves ALL its venues; other chains
    # resolve UniV3 via the registered factory. Non-UniV3 venue families on
    # non-Base chains have adapters but no generic pool-resolution seam here.
    if (chain or "").lower() in ("base", "base-sepolia"):
        discoverable = True
    elif is_univ3:
        discoverable = bool(factory)
    else:
        discoverable = False

    if not discoverable:
        blocker = ("univ3_factory_unregistered" if is_univ3
                   else "no_pool_resolver_for_venue_family")
    elif not rpc:
        blocker = "no_operator_configured_rpc"
    elif not quoter_supported:
        blocker = "no_quoter_adapter_for_venue"
    elif not econ_rpc:
        blocker = "economic_gate_rpc_not_configured"
    else:
        blocker = "requires_vps_runtime_proof"   # quote/liq/econ/sim/evidence

    # STRUCTURAL connectivity ONLY: the discovery → pool-resolution → quoter
    # adapter path is fully wired in code for this cell, so it CAN reach
    # QUOTABLE once a real RPC + runtime proof exist. This is NOT a runtime
    # claim — quote/liquidity/economic below stay ``requires_runtime`` and a
    # cell is never limited-live eligible from structural connectivity.
    quote_path_connected = bool(discoverable and quoter_supported)

    return {
        "implemented": implemented,
        "rpc_configured": rpc,
        "economic_rpc_configured": econ_rpc,
        "discoverable": discoverable,
        "quoter_supported": quoter_supported,
        # code-connectivity of discovery→resolver→quoter (offline-verifiable);
        # distinct from the runtime ``quote`` dimension which needs live RPC.
        "quote_path_connected": quote_path_connected,
        # live dimensions are never asserted from code/config alone
        "quote": "requires_runtime",
        "liquidity_tvl": "requires_runtime",
        "economic": "requires_runtime",
        "simulation": "requires_runtime",
        "evidence": "requires_runtime",
        "reached_state": "DISCOVERABLE" if discoverable else "IMPLEMENTED",
        "limited_live_eligible": False,
        "blocker": blocker,
    }


def build_opportunity_matrix(
    *, quoter_supported_dexes: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """CHAIN|VENUE|STRATEGY matrix with explicit per-cell state + blocker.
    ``quoter_supported_dexes`` defaults to the live QuoterRegistry's set."""
    if quoter_supported_dexes is None:
        from ..execution.quoter import QuoterRegistry
        quoter_supported_dexes = QuoterRegistry().supported_dexes
    supported = set(quoter_supported_dexes)

    rows: List[Dict[str, Any]] = []
    for chain in supported_networks():
        for venue in venues_for(chain):
            cell = _cell_state(chain, venue, quoter_supported=venue in supported)
            for strategy in IMPLEMENTED_STRATEGIES:
                rows.append({"chain": chain, "venue": venue,
                             "strategy": strategy, **cell})
    return {
        "safety": {"posture": "SHADOW / detection-only / fail-closed",
                   "signed": False, "broadcast": False,
                   "auto_execution": False, "full_live": False},
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "limited_live_eligible_count": sum(
                1 for r in rows if r["limited_live_eligible"]),
            "discoverable_count": sum(1 for r in rows if r["discoverable"]),
            # Cells whose discovery→resolver→quoter path is structurally wired
            # (CAN reach QUOTABLE with a real RPC + VPS runtime proof). This is
            # NOT a count of runtime-QUOTABLE cells — no cell is QUOTABLE or
            # limited-live eligible from code/config alone.
            "quote_path_connected_count": sum(
                1 for r in rows if r["quote_path_connected"]),
        },
        "note": ("No cell is limited-live eligible from code/config alone. A "
                 "candidate becomes LIMITED-LIVE ELIGIBLE only after a real "
                 "VPS/Base runtime proof passes every gate (quote→liquidity→"
                 "economics→simulation→evidence→safety) + admin approval."),
    }


__all__ = [
    "IMPLEMENTED_STRATEGIES", "venues_for", "enumerate_capabilities",
    "discover_pools_parallel", "build_opportunity_matrix",
]
