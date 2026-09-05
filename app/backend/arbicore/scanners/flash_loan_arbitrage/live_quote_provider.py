"""Live flash-loan route quote provider (canonical, honest, chain/venue-aware).

Bridges the real ``FlashLoanArbitrageScanner`` verifier to the SAME live
``QuoterRegistry`` the OpportunityEngine uses. Given a discovered route cycle it
quotes every hop live and returns the ``facts`` dict the
``FlashLoanOpportunityVerifier`` consumes (``hop_legs`` + ``gross_profit_pct`` +
gas + tvl).

Chain/venue-aware (no longer Base-hardwired):
  * The chain is resolved from the route/candidate context (``chain`` in the
    cycle metadata), defaulting to ``base`` for full backward compatibility.
  * BASE path is behaviour-identical to the certified P0-3 implementation: it
    uses the canonical Base registry (base_venues + base_pool_registry).
  * OTHER registered EVM chains (ethereum/arbitrum/optimism/polygon/bnb) resolve
    token addresses from the chain registry and validate each UniV3 pool
    on-chain via ``univ3_pool_resolver`` before quoting through the correct
    chain in ``QuoterRegistry``. A venue family with no generic pool resolver,
    or a missing/failed RPC, fails CLOSED (returns ``None`` →
    ``denied:venue_unreadable``) — never a fabricated quote/pool/liquidity.

Honesty guarantees (unchanged):
  * No fabricated profit — gross is computed from real on-chain quotes.
  * No signing / no broadcast — quoting is read-only ``eth_call``.
  * Any unreadable hop / partial route / non-closed cycle → ``None``.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

_LOG = logging.getLogger("arbicore.live_quote_provider")


def _dex_source_id(dex: str, chain: str) -> str:
    m = {
        "uniswap_v3": f"uniswap_v3_quoter_{chain}",
        "aerodrome_slipstream": f"aerodrome_quoter_{chain}",
        "aerodrome": f"aerodrome_quoter_{chain}",
    }
    return m.get(dex, f"{dex}_quoter_{chain}")


async def _resolve_pool_tvls(route_pools: List[str], tvl_provider,
                             chain: str = "base") -> Dict[str, float]:
    """REAL on-chain pool depth per Base route pool (canonical-registry path,
    behaviour-compatible with P0-3). Missing provider/address/error/non-positive
    read → ABSENT (Gate 8 fails closed). Non-Base plans resolve depth inline."""
    out: Dict[str, float] = {}
    if tvl_provider is None:
        return out
    from ...discovery.base_pool_registry import canonical_pool_by_id
    for pid in route_pools:
        cp = canonical_pool_by_id(pid)
        addr = getattr(cp, "address", None) if cp else None
        if not addr:
            continue
        try:
            v = await tvl_provider.get_pool_tvl_usd(chain, addr)
        except Exception:  # noqa: BLE001 — provider never fabricates
            v = None
        if v is not None and float(v) > 0.0:
            out[pid] = float(v)
    return out


def _route_min_tvl(pool_tvls: Dict[str, float], route_pools: List[str]) -> float:
    """Min measured TVL over the route. FAIL CLOSED (0.0) unless EVERY pool on
    the route has a positive, verified on-chain TVL — never a partial pass."""
    if not route_pools:
        return 0.0
    vals: List[float] = []
    for pid in route_pools:
        v = pool_tvls.get(pid)
        if v is None or v <= 0.0:
            return 0.0
        vals.append(v)
    return min(vals)


# ── per-hop plan: (dex, token_in_addr, token_out_addr, fee, tick_spacing,
#    stable, tvl_key, tvl_addr, fee_bps) ──────────────────────────────────────
class _HopPlan:
    __slots__ = ("dex", "token_in", "token_out", "fee", "tick_spacing",
                 "stable", "tvl_key", "tvl_addr", "fee_bps")

    def __init__(self, dex, token_in, token_out, fee, tick_spacing, stable,
                 tvl_key, tvl_addr, fee_bps):
        self.dex, self.token_in, self.token_out = dex, token_in, token_out
        self.fee, self.tick_spacing, self.stable = fee, tick_spacing, stable
        self.tvl_key, self.tvl_addr, self.fee_bps = tvl_key, tvl_addr, fee_bps


def _plan_base(hm: Dict[str, Any]) -> Optional[Tuple[List[_HopPlan], List[str], int]]:
    """Behaviour-identical Base plan from the canonical registry."""
    from ...discovery.base_venues import token_address, probe_amount
    from ...discovery.base_pool_registry import (
        canonical_pool_specs, canonical_pool_by_id)
    specs = canonical_pool_specs()
    route_pools: List[str] = list(hm.get("route_pools") or [])
    token_path: List[str] = [str(t).upper() for t in (hm.get("cycle_token_path") or [])]
    borrow_token = (hm.get("borrow_token") or (token_path[0] if token_path else "")).upper()
    if len(route_pools) < 2 or len(token_path) != len(route_pools) + 1:
        return None
    plans: List[_HopPlan] = []
    for i, pool_addr in enumerate(route_pools):
        spec = dict(specs.get(pool_addr) or {})
        addr_in, addr_out = token_address(token_path[i]), token_address(token_path[i + 1])
        if not addr_in or not addr_out:
            return None
        cp = canonical_pool_by_id(pool_addr)
        plans.append(_HopPlan(
            dex=spec.get("dex") or "uniswap_v3",
            token_in=addr_in, token_out=addr_out,
            fee=spec.get("fee"), tick_spacing=spec.get("tick_spacing"),
            stable=spec.get("stable"),
            tvl_key=pool_addr,
            tvl_addr=(getattr(cp, "address", None) if cp else None),
            fee_bps=int(spec.get("fee", 3000)) // 100))
    return plans, token_path, int(probe_amount(borrow_token))


async def _plan_generic_evm(
    chain: str, hm: Dict[str, Any], eth_call,
) -> Optional[Tuple[List[_HopPlan], List[str], int]]:
    """Chain/venue-aware plan for a non-Base EVM chain. Requires per-hop venue
    specs in ``route_hops`` and an explicit borrow ``amount_in_wei``. UniV3 hops
    are validated on-chain via the resolver; anything unsupported/unreadable
    fails closed (returns None)."""
    from ...chains.registries import tokens_for
    from ...discovery.univ3_pool_resolver import resolve_univ3_pool

    route_hops: List[Dict[str, Any]] = list(hm.get("route_hops") or [])
    token_path: List[str] = [str(t).upper() for t in (hm.get("cycle_token_path") or [])]
    amount_in_wei = int(hm.get("borrow_amount_wei") or 0)
    if len(route_hops) < 2 or len(token_path) != len(route_hops) + 1:
        return None
    if amount_in_wei <= 0:                      # no fabricated probe amount
        return None
    if eth_call is None:                        # no RPC → fail closed
        _LOG.debug("no eth_call for chain=%s → venue_unreadable", chain)
        return None

    toks = tokens_for(chain)

    def _addr(sym_or_addr: str) -> Optional[str]:
        s = str(sym_or_addr)
        if s.startswith("0x") and len(s) == 42:
            return s
        t = toks.get(s.upper())
        return t.get("address") if t else None

    plans: List[_HopPlan] = []
    for i, rh in enumerate(route_hops):
        dex = rh.get("dex")
        addr_in = _addr(rh.get("token_in") or token_path[i])
        addr_out = _addr(rh.get("token_out") or token_path[i + 1])
        fee = rh.get("fee")
        if not dex or not addr_in or not addr_out:
            return None
        if dex != "uniswap_v3":
            # Implemented/discoverable but no generic resolver yet → fail closed.
            _LOG.debug("no_pool_resolver_for_venue_family chain=%s dex=%s", chain, dex)
            return None
        if fee is None:
            return None
        pool = await resolve_univ3_pool(chain, addr_in, addr_out, int(fee),
                                        eth_call=eth_call)
        if pool is None:                        # invalid/unreadable/nonexistent
            return None
        plans.append(_HopPlan(
            dex=dex, token_in=addr_in, token_out=addr_out, fee=int(fee),
            tick_spacing=rh.get("tick_spacing"), stable=rh.get("stable"),
            tvl_key=pool["pool_address"], tvl_addr=pool["pool_address"],
            fee_bps=int(fee) // 100))
    return plans, token_path, amount_in_wei


def make_live_quote_provider(
    quoter_registry,
    *,
    tvl_provider=None,
    eth_call_for_chain: Optional[Callable[[str], Optional[Any]]] = None,
) -> Callable[[Dict[str, Any], float], Awaitable[Optional[Dict[str, Any]]]]:
    """Return an async ``QuoteProvider`` bound to a live ``QuoterRegistry``.

    ``tvl_provider`` (M2.2, optional) supplies REAL measured on-chain pool depth
    for Gate 8 (fail-closed when absent). ``eth_call_for_chain(chain)`` supplies
    an async ``eth_call`` for NON-Base chains' on-chain pool validation; when it
    is ``None`` (or returns ``None`` for a chain), non-Base routes fail closed.
    Base is unaffected and uses the canonical registry.
    """

    async def _provider(cycle_metadata: Dict[str, Any],
                        borrow_amount_usd: float) -> Optional[Dict[str, Any]]:
        hm = cycle_metadata or {}
        chain = str(hm.get("chain") or "base").lower()

        if chain in ("base", "base-sepolia"):
            planned = _plan_base(hm)
        else:
            eth_call = eth_call_for_chain(chain) if eth_call_for_chain else None
            planned = await _plan_generic_evm(chain, hm, eth_call)
        if planned is None:
            return None
        plans, token_path, amount_in_wei = planned

        hops: List[Dict[str, Any]] = []
        for i, p in enumerate(plans):
            hop: Dict[str, Any] = {"dex": p.dex, "token_in": p.token_in,
                                   "token_out": p.token_out}
            if i == 0:
                hop["amount_in_wei"] = amount_in_wei
            if p.fee is not None:
                hop["fee"] = p.fee
            if p.tick_spacing is not None:
                hop["tick_spacing"] = p.tick_spacing
            if p.stable is not None:
                hop["stable"] = p.stable
            hops.append(hop)

        try:
            rq = await quoter_registry.quote_route(chain=chain, hops=hops)
        except Exception:  # noqa: BLE001
            return None

        # QUOTE INTEGRITY — FAIL CLOSED (partial-quote defect, audit 2026-06).
        if rq is None or rq.status != "ok":
            return None
        if any(getattr(h, "status", None) not in (None, "ok") for h in rq.hops):
            return None
        if token_path[0] != token_path[-1]:
            return None  # not a closed cycle → wei ratio meaningless
        final_out = int(rq.final_amount_out_wei or 0)
        if amount_in_wei <= 0 or final_out <= 0:
            return None
        gross_profit_pct = 100.0 * (final_out - amount_in_wei) / amount_in_wei

        # REAL measured on-chain depth (M2.2), keyed per hop via the plan.
        tvl_keys = [p.tvl_key for p in plans]
        pool_tvls: Dict[str, float] = {}
        if tvl_provider is not None:
            for p in plans:
                if not p.tvl_addr:
                    continue
                try:
                    v = await tvl_provider.get_pool_tvl_usd(chain, p.tvl_addr)
                except Exception:  # noqa: BLE001 — provider never fabricates
                    v = None
                if v is not None and float(v) > 0.0:
                    pool_tvls[p.tvl_key] = float(v)

        hop_legs: List[Dict[str, Any]] = []
        for idx, h in enumerate(rq.hops):
            p = plans[idx] if idx < len(plans) else None
            hop_legs.append({
                "venue_id": f"{getattr(h, 'dex', 'dex')}:{chain}",
                "source_id": _dex_source_id(getattr(h, "dex", ""), chain),
                "price": None,
                "depth_usd": float(pool_tvls.get(p.tvl_key, 0.0)) if p else 0.0,
                "fee_bps": int(p.fee_bps) if p else 0,
                "dex_protocol": getattr(h, "dex", None),
                "status": getattr(h, "status", None),
                "block_number": getattr(h, "block_number", None),
            })

        min_tvl = _route_min_tvl(pool_tvls, tvl_keys)
        quote_blocks = [int(h.get("block_number")) for h in hop_legs
                        if isinstance(h.get("block_number"), int)]

        return {
            "hop_legs": hop_legs,
            "gross_profit_pct": gross_profit_pct,
            "tx_gas_units": rq.aggregate_gas_estimate_units,
            "min_pool_tvl_usd_in_route": min_tvl,
            "tvl_provenance": ("onchain_reserves" if tvl_provider is not None
                               else "unverified"),
            "flash_loan_pool_address": "",
            "route_quote_status": rq.status,
            "chain": chain,
            "quote_block": max(quote_blocks) if quote_blocks else None,
            "verified_at_ts": time.time(),
        }

    return _provider
