"""Reusable, CHAIN-SCOPED execution-readiness evaluator (fail-closed).

The Base broadcaster (``runtime.composition.build_controlled_live_safety``) is
Base-only. This module generalises the *pre-broadcast execution gate* into a
single, chain-scoped ladder that any of the six required chains can walk
INDEPENDENTLY — Base never has to succeed first, and NO Base RPC/address/
liquidity is ever used for a non-Base chain (every seam is bound to the
requested chain).

Ladder (each stage fails closed on its OWN missing evidence):

    RPC → CHAIN_VERIFICATION → MARKET_COMPOSITION → LIQUIDITY_PROVIDER
        → QUOTE → ECONOMICS → ROUTE → SIMULATION → EXECUTION_CAPABILITY

Status vocabulary (never collapsed):
    PASS      positive, chain-scoped evidence present
    BLOCKED   a definitive prerequisite is absent (fail-closed)
    UNKNOWN   requires a live VPS read not performed here (fail-closed)

Hard invariants (asserted by tests):
  * NEVER signs, broadcasts, deploys, or enables any live mode. The result
    always carries ``signed=False`` / ``broadcast=False``.
  * ``limited_live_eligible`` is ALWAYS False — this evaluator can only report
    the pre-broadcast gate; Limited-Live stays hard-gated in ``control.readiness``.
  * A registry entry / configured RPC is NEVER treated as runtime activation.
  * ``execution_capable`` is True ONLY when every stage is PASS (which requires
    a verified chain, a deployed+declared receiver and a resolvable executor).

Lives under ``arbicore.control`` (not ``arbicore.runtime``) intentionally so it
imports WITHOUT the Mongo-coupled runtime composition; all chain seams are
imported lazily and are read-only.
"""
from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Dict, List, Optional

PASS = "PASS"
BLOCKED = "BLOCKED"
UNKNOWN = "UNKNOWN"

STAGE_ORDER = (
    "RPC", "CHAIN_VERIFICATION", "MARKET_COMPOSITION", "LIQUIDITY_PROVIDER",
    "QUOTE", "ECONOMICS", "ROUTE", "SIMULATION", "EXECUTION_CAPABILITY",
)

# Canonical EVM chain-ids for the six required networks (public, verifiable).
EXPECTED_CHAIN_IDS: Dict[str, int] = {
    "ethereum": 1, "optimism": 10, "bnb": 56, "polygon": 137,
    "base": 8453, "arbitrum": 42161,
}


def _stage(status: str, reason: str, **evidence: Any) -> Dict[str, Any]:
    return {"status": status, "reason": reason, "evidence": evidence}


def _economic_rpc_configured(chain: str) -> bool:
    """ECONOMIC gate: only the endpoints the provider registry actually consumes
    (``PROVIDER_RPC_URLS_<CHAIN>`` / ``PROVIDER_RPC_URL_<CHAIN>``) back the
    all-in-cost estimator. Mirrors ``runtime.multichain_readiness`` without
    importing that (Mongo-coupled) package."""
    c = (chain or "").upper()
    return bool((os.environ.get(f"PROVIDER_RPC_URLS_{c}") or "").strip()
                or (os.environ.get(f"PROVIDER_RPC_URL_{c}") or "").strip())


def _default_pool_graph(chain: str) -> List[Any]:
    """Chain-scoped venue universe for ALL six networks: Base uses its own
    canonical (resolved) registry graph; every other chain uses the generic
    multichain venue builder. Fail-closed empty on any error."""
    c = (chain or "").lower()
    try:
        if c == "base":
            from ..discovery.base_pool_registry import build_canonical_pool_graph
            return list(build_canonical_pool_graph(resolved_only=True)[0])
        from ..discovery.multichain_venues import build_pool_graph
        return list(build_pool_graph(c))
    except Exception:  # noqa: BLE001 — fail-closed
        return []


def _executor_supported_venues(pools: List[Any]) -> List[str]:
    from ..scanners.flash_loan_arbitrage.executor_capability import SUPPORTED_DEXES
    # Base canonical nodes expose ``dex_protocol``; multichain nodes too. Base
    # PoolNode uses ``dex_protocol`` == e.g. "uniswap_v3"/"aerodrome".
    return sorted({getattr(p, "dex_protocol", None) for p in pools
                   if getattr(p, "dex_protocol", None) in SUPPORTED_DEXES})


def _runtime_flash_heads_for_chain(chain: str) -> List[str]:
    """Flash heads that are BOTH in the economics catalog for this chain AND
    have a genuine runtime liquidity probe (never inferred from the catalog
    alone)."""
    from ..scanners.flash_loan_arbitrage.economics import FLASH_LOAN_PROVIDERS
    from ..scanners.flash_loan_arbitrage.provider_liquidity import (
        RUNTIME_PROBE_PROVIDERS)
    c = (chain or "").lower()
    out = []
    for name, meta in FLASH_LOAN_PROVIDERS.items():
        if name in RUNTIME_PROBE_PROVIDERS and c in meta.get("supports_chains", ()):
            out.append(name)
    return sorted(out)


def _borrow_token_for_chain(chain: str) -> Optional[Dict[str, Any]]:
    """A canonical, verified borrow token (address + decimals) for a chain's
    live liquidity probe. Prefers USDC (listed on Aave + widely held), then
    WETH. Base uses its dedicated ``base_venues`` token table; every other chain
    uses the verified public ``chains.registries``. None if unavailable
    (fail-closed — never fabricated)."""
    c = (chain or "").lower()
    try:
        if c == "base":
            from ..discovery.base_venues import TOKENS
            for sym in ("USDC", "USDbC", "WETH"):
                t = TOKENS.get(sym)
                if t and t.get("address"):
                    return {"symbol": sym, "address": t["address"],
                            "decimals": int(t.get("decimals", 18))}
            return None
        from ..chains import registries
        toks = (registries.registry_for(c) or {}).get("tokens") or {}
        for sym in ("USDC", "USDC.e", "USDT", "WETH"):
            t = toks.get(sym)
            if t and t.get("address"):
                return {"symbol": sym, "address": t["address"],
                        "decimals": int(t.get("decimals", 18))}
    except Exception:  # noqa: BLE001
        return None
    return None


async def _default_liquidity_probe(chain: str, eth_call: Any) -> Dict[str, Any]:
    """GENUINE, chain-scoped live liquidity probe (fail-closed). For every
    runtime flash head on ``chain``, read the REAL on-chain flash-loanable
    balance (token units) of a verified borrow token via the chain-bound
    ``eth_call``. NEVER fabricates: a missing token / failed read is simply
    absent from the result. No USD price is used or invented here."""
    from ..scanners.flash_loan_arbitrage.provider_liquidity import (
        runtime_flash_liquidity_tokens)
    heads = _runtime_flash_heads_for_chain(chain)
    token = _borrow_token_for_chain(chain)
    out: Dict[str, Any] = {}
    if not heads or token is None or eth_call is None:
        return out
    for provider in heads:
        tokens = await runtime_flash_liquidity_tokens(
            eth_call, provider=provider, chain=chain,
            token_address=token["address"], token_decimals=token["decimals"])
        if tokens is not None:
            out[provider] = {
                "liquidity_tokens": tokens,
                "borrow_token": token["symbol"],
                "token_address": token["address"],
            }
    return out


async def evaluate_chain_execution_readiness(
    chain: str,
    *,
    # Every dependency is injectable so this is unit-testable offline AND
    # reusable on the VPS with the real chain-scoped seams. Defaults are bound
    # to the genuine, chain-scoped infrastructure (NEVER Base fallbacks).
    eth_call_factory: Optional[Callable[[str], Any]] = None,
    chain_id_reader: Optional[Callable[[str], Awaitable[Optional[int]]]] = None,
    pool_graph_fn: Optional[Callable[[str], List[Any]]] = None,
    gas_model_fn: Optional[Callable[[str], Any]] = None,
    economic_rpc_fn: Optional[Callable[[str], bool]] = None,
    receiver_capability_fn: Optional[Callable[[str], Any]] = None,
    executor_address_fn: Optional[Callable[[str], Optional[str]]] = None,
    price_feed_factory: Optional[Callable[[str], Any]] = None,
    liquidity_probe_fn: Optional[Callable[[str, Any], Awaitable[Dict[str, Any]]]] = None,
) -> Dict[str, Any]:
    """Walk the chain-scoped execution ladder. Live chain-verification and
    liquidity reads run ONLY when an operator RPC is configured for the chain
    (else fail-closed); every other live dimension (quote/economics/sim) stays
    fail-closed until proven on the VPS. NEVER Base-first, no Base fallback."""
    c = (chain or "").lower()

    # Resolve default seams lazily (avoid import cycles / import-time cost).
    if eth_call_factory is None:
        from ..searcher.runtime import make_eth_call_for_chain_from_env
        eth_call_factory = make_eth_call_for_chain_from_env
    if chain_id_reader is None:
        # LIVE by default: a chain-scoped eth_chainId read (fail-closed None
        # without an operator RPC). Never falls back to Base.
        chain_id_reader = make_registry_chain_id_reader()
    if pool_graph_fn is None:
        pool_graph_fn = _default_pool_graph
    if gas_model_fn is None:
        from ..chains.gas_model import get_chain_gas_model
        gas_model_fn = get_chain_gas_model
    if economic_rpc_fn is None:
        economic_rpc_fn = _economic_rpc_configured
    if receiver_capability_fn is None:
        from ..execution.receiver_capability import receiver_capability
        receiver_capability_fn = receiver_capability
    if executor_address_fn is None:
        from ..scanners.flash_loan_arbitrage.live_readiness_probes import (
            resolve_executor_address)
        executor_address_fn = resolve_executor_address
    if liquidity_probe_fn is None:
        liquidity_probe_fn = _default_liquidity_probe

    stages: Dict[str, Dict[str, Any]] = {}

    # 1) RPC — chain-scoped operator RPC ONLY (never Base fallback).
    eth_call = None
    try:
        eth_call = eth_call_factory(c)
    except Exception as exc:  # noqa: BLE001
        eth_call = None
        stages["RPC"] = _stage(BLOCKED, f"rpc_factory_error:{type(exc).__name__}")
    if "RPC" not in stages:
        if eth_call is None:
            stages["RPC"] = _stage(BLOCKED, "no_operator_configured_rpc")
        else:
            stages["RPC"] = _stage(PASS, "chain_scoped_rpc_configured")

    # 2) CHAIN_VERIFICATION — the RPC MUST be bound to THIS chain (a real guard
    #    against silently pointing a non-Base request at Base's endpoint).
    expected_id = EXPECTED_CHAIN_IDS.get(c)
    if expected_id is None:
        stages["CHAIN_VERIFICATION"] = _stage(BLOCKED, "unknown_chain", chain=c)
    elif eth_call is None:
        stages["CHAIN_VERIFICATION"] = _stage(
            BLOCKED, "no_rpc_to_verify_chain", expected_chain_id=expected_id)
    elif chain_id_reader is None:
        stages["CHAIN_VERIFICATION"] = _stage(
            UNKNOWN, "chain_id_unverified_offline", expected_chain_id=expected_id)
    else:
        try:
            observed = await chain_id_reader(c)
        except Exception as exc:  # noqa: BLE001
            observed = None
            stages["CHAIN_VERIFICATION"] = _stage(
                UNKNOWN, f"chain_id_read_error:{type(exc).__name__}",
                expected_chain_id=expected_id)
        if "CHAIN_VERIFICATION" not in stages:
            if observed is None:
                stages["CHAIN_VERIFICATION"] = _stage(
                    UNKNOWN, "chain_id_unreadable", expected_chain_id=expected_id)
            elif int(observed) != int(expected_id):
                stages["CHAIN_VERIFICATION"] = _stage(
                    BLOCKED, "chain_id_mismatch_rpc_bound_to_wrong_chain",
                    expected_chain_id=expected_id, observed_chain_id=int(observed))
            else:
                stages["CHAIN_VERIFICATION"] = _stage(
                    PASS, "rpc_confirmed_on_expected_chain", chain_id=int(observed))

    # 3) MARKET_COMPOSITION — chain-scoped venue universe with at least one
    #    executor-supported (Uniswap V3) swap venue.
    try:
        pools = pool_graph_fn(c) or []
    except Exception as exc:  # noqa: BLE001
        pools = []
        stages["MARKET_COMPOSITION"] = _stage(
            BLOCKED, f"pool_graph_error:{type(exc).__name__}")
    if "MARKET_COMPOSITION" not in stages:
        supported_venues = _executor_supported_venues(pools)
        if not pools:
            stages["MARKET_COMPOSITION"] = _stage(BLOCKED, "empty_route_universe")
        elif not supported_venues:
            stages["MARKET_COMPOSITION"] = _stage(
                BLOCKED, "no_executor_supported_venue",
                route_universe_size=len(pools))
        else:
            stages["MARKET_COMPOSITION"] = _stage(
                PASS, "executor_supported_venues_present",
                route_universe_size=len(pools),
                executor_supported_venues=supported_venues)

    # 4) LIQUIDITY_PROVIDER — flash heads with a genuine runtime probe on this
    #    chain. With an operator RPC we perform a REAL on-chain read of the
    #    provider's flash-loanable balance (token units — RUNTIME-PROVEN, no
    #    USD price fabricated). Without RPC / on read failure → fail closed.
    heads = _runtime_flash_heads_for_chain(c)
    if not heads:
        stages["LIQUIDITY_PROVIDER"] = _stage(
            BLOCKED, "no_runtime_flash_provider_on_chain")
    elif eth_call is None:
        stages["LIQUIDITY_PROVIDER"] = _stage(
            UNKNOWN, "liquidity_unverified_no_operator_rpc",
            runtime_flash_heads=heads)
    else:
        try:
            probed = await liquidity_probe_fn(c, eth_call) or {}
        except Exception as exc:  # noqa: BLE001 — never fabricate liquidity
            probed = {}
            stages["LIQUIDITY_PROVIDER"] = _stage(
                UNKNOWN, f"liquidity_probe_error:{type(exc).__name__}",
                runtime_flash_heads=heads)
        if "LIQUIDITY_PROVIDER" not in stages:
            proven = {p: v for p, v in probed.items()
                      if isinstance(v, dict) and v.get("liquidity_tokens") is not None}
            if proven:
                stages["LIQUIDITY_PROVIDER"] = _stage(
                    PASS, "runtime_liquidity_proven_onchain",
                    runtime_flash_heads=heads, proven_providers=sorted(proven),
                    liquidity=proven)
            else:
                stages["LIQUIDITY_PROVIDER"] = _stage(
                    UNKNOWN, "liquidity_read_returned_no_provider_balance",
                    runtime_flash_heads=heads)

    # 5) QUOTE — a live per-chain quote proof is required; not performed here.
    stages["QUOTE"] = _stage(
        UNKNOWN, ("quote_unverified_no_live_quote_proof" if eth_call is not None
                  else "quote_blocked_no_rpc"))

    # 6) ECONOMICS — gas model object + registry-backing RPC for all-in cost.
    try:
        gas_model = gas_model_fn(c)
    except Exception:  # noqa: BLE001
        gas_model = None
    try:
        econ_rpc = bool(economic_rpc_fn(c))
    except Exception:  # noqa: BLE001
        econ_rpc = False
    if gas_model is None:
        stages["ECONOMICS"] = _stage(BLOCKED, "no_gas_model")
    elif not econ_rpc:
        stages["ECONOMICS"] = _stage(
            BLOCKED, "economic_gate_rpc_not_configured",
            gas_model=type(gas_model).__name__)
    else:
        stages["ECONOMICS"] = _stage(
            UNKNOWN, "economics_ready_pending_live_inputs",
            gas_model=type(gas_model).__name__)

    # 7) ROUTE — route construction is pure/deterministic once an
    #    executor-supported venue universe exists.
    mc = stages.get("MARKET_COMPOSITION", {})
    if mc.get("status") == PASS:
        stages["ROUTE"] = _stage(
            PASS, "route_constructible",
            route_universe_size=mc["evidence"].get("route_universe_size"))
    else:
        stages["ROUTE"] = _stage(
            BLOCKED, "route_blocked_no_executor_supported_universe")

    # 8) SIMULATION — needs chain-scoped RPC AND a resolvable executor address;
    #    the exact candidate-bound atomic sim is only provable on the VPS.
    try:
        executor_addr = executor_address_fn(c)
    except Exception:  # noqa: BLE001
        executor_addr = None
    if eth_call is None:
        stages["SIMULATION"] = _stage(BLOCKED, "no_rpc_for_simulation")
    elif not executor_addr:
        stages["SIMULATION"] = _stage(BLOCKED, "no_executor_address")
    else:
        stages["SIMULATION"] = _stage(
            UNKNOWN, "simulation_requires_candidate_bound_calldata")

    # 9) EXECUTION_CAPABILITY — deployed receiver that EXPLICITLY supports a
    #    runtime flash head + a resolvable executor address. Fail-closed.
    try:
        cap = receiver_capability_fn(c)
    except Exception:  # noqa: BLE001
        cap = None
    if cap is None or not getattr(cap, "deployed", False):
        stages["EXECUTION_CAPABILITY"] = _stage(BLOCKED, "no_deployed_receiver")
    else:
        exec_heads = [h for h in heads if cap.supports(h)]
        if not exec_heads:
            stages["EXECUTION_CAPABILITY"] = _stage(
                BLOCKED, "receiver_declares_no_supported_runtime_flash_head")
        elif not executor_addr:
            stages["EXECUTION_CAPABILITY"] = _stage(BLOCKED, "no_executor_address")
        else:
            stages["EXECUTION_CAPABILITY"] = _stage(
                PASS, "receiver_and_executor_present",
                executable_flash_heads=exec_heads, executor_address=executor_addr)

    reached = None
    terminal_blocker = None
    for name in STAGE_ORDER:
        if stages[name]["status"] != PASS:
            reached = name
            terminal_blocker = stages[name]["reason"]
            break
    execution_capable = all(stages[n]["status"] == PASS for n in STAGE_ORDER)

    return {
        "chain": c,
        "expected_chain_id": expected_id,
        "stages": {n: stages[n] for n in STAGE_ORDER},
        "reached_stage": reached,
        "terminal_blocker": terminal_blocker,
        "execution_capable": execution_capable,
        "limited_live_eligible": False,   # ALWAYS — hard-gated elsewhere
        "signed": False,
        "broadcast": False,
    }


def make_registry_chain_id_reader() -> Callable[[str], Awaitable[Optional[int]]]:
    """VPS-usable, chain-scoped ``eth_chainId`` reader (read-only). Returns None
    when the chain has no operator RPC / the read fails (fail-closed). Bound to
    the requested chain — NEVER falls back to Base."""
    async def _reader(chain: str) -> Optional[int]:
        try:
            from ..providers.rpc_failover import get_registry_rpc_provider
            provider = get_registry_rpc_provider((chain or "").lower())
            if provider is None:
                return None
            return int(await provider.eth_chain_id())
        except Exception:  # noqa: BLE001 — fail-closed
            return None
    return _reader


async def build_chain_execution_readiness_report(
    chains: Optional[List[str]] = None, **kw: Any) -> Dict[str, Any]:
    """Per-chain execution-readiness for all six required networks (or a subset).
    Offline/pure by default; each chain evaluated INDEPENDENTLY (no Base-first)."""
    if chains is None:
        chains = ["base", "ethereum", "arbitrum", "optimism", "polygon", "bnb"]
    networks = {}
    for c in chains:
        networks[c] = await evaluate_chain_execution_readiness(c, **kw)
    return {
        "safety": {"posture": "SHADOW / pre-broadcast gate / fail-closed",
                   "signed": False, "broadcast": False,
                   "limited_live_enabled": False},
        "networks": networks,
        "execution_capable_count": sum(
            1 for r in networks.values() if r["execution_capable"]),
        "note": ("execution_capable reflects the pre-broadcast gate only; "
                 "Limited-Live remains hard-gated (RED) and requires explicit "
                 "operator approval + VPS runtime proof."),
    }


__all__ = [
    "PASS", "BLOCKED", "UNKNOWN", "STAGE_ORDER", "EXPECTED_CHAIN_IDS",
    "evaluate_chain_execution_readiness",
    "build_chain_execution_readiness_report",
    "make_registry_chain_id_reader",
]
