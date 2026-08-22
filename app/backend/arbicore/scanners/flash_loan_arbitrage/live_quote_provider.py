"""Live flash-loan route quote provider (canonical, honest).

Bridges the real ``FlashLoanArbitrageScanner`` verifier to the SAME live Base
quoter (``QuoterRegistry``) the OpportunityEngine uses. Given a discovered route
cycle (from ``RouteSearchEngine`` over the real Base pool universe), it quotes
every hop live and returns the ``facts`` dict the ``FlashLoanOpportunityVerifier``
consumes (``hop_legs`` + ``gross_profit_pct`` + gas + tvl).

Honesty guarantees:
  * No fabricated profit — ``gross_profit_pct`` is computed from real on-chain
    quotes. A losing route yields a negative/zero value and is denied by Gate 7.
  * No signing / no broadcast — quoting is read-only ``eth_call``.
  * If the RPC/quoter cannot price the route, returns ``None`` →
    ``denied:venue_unreadable`` (never a false confirm).
"""
from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, Awaitable

from ...discovery.base_venues import (
    CHAIN, PROBE_AMOUNT, TOKENS, build_pool_graph, token_address,
)


def _tvl_by_pool() -> Dict[str, float]:
    pools, _specs = build_pool_graph()
    return {p.pool_address: float(getattr(p, "tvl_usd", 0.0) or 0.0) for p in pools}


def make_live_quote_provider(
    quoter_registry,
) -> Callable[[Dict[str, Any], float], Awaitable[Optional[Dict[str, Any]]]]:
    """Return an async ``QuoteProvider`` bound to a live ``QuoterRegistry``."""
    _pools, specs = build_pool_graph()
    tvl_map = {p.pool_address: float(getattr(p, "tvl_usd", 0.0) or 0.0) for p in _pools}

    async def _provider(cycle_metadata: Dict[str, Any],
                        borrow_amount_usd: float) -> Optional[Dict[str, Any]]:
        hm = cycle_metadata or {}
        route_pools: List[str] = list(hm.get("route_pools") or [])
        token_path: List[str] = [str(t).upper() for t in (hm.get("cycle_token_path") or [])]
        borrow_token = (hm.get("borrow_token") or (token_path[0] if token_path else "")).upper()
        if len(route_pools) < 2 or len(token_path) != len(route_pools) + 1:
            return None  # malformed route → unreadable (honest)

        # Build the live hop plan (mirrors OpportunityEngine._route_to_hops).
        hops: List[Dict[str, Any]] = []
        for i, pool_addr in enumerate(route_pools):
            spec = dict(specs.get(pool_addr) or {})
            tin, tout = token_path[i], token_path[i + 1]
            addr_in, addr_out = token_address(tin), token_address(tout)
            if not addr_in or not addr_out:
                return None
            hop: Dict[str, Any] = {
                "dex": spec.get("dex") or "uniswap_v3",
                "token_in": addr_in,
                "token_out": addr_out,
            }
            if i == 0:
                hop["amount_in_wei"] = int(PROBE_AMOUNT.get(borrow_token, 10 ** 16))
            if "fee" in spec:
                hop["fee"] = spec["fee"]
            hops.append(hop)

        try:
            rq = await quoter_registry.quote_route(chain=CHAIN, hops=hops)
        except Exception:  # noqa: BLE001
            return None
        if rq is None or rq.status == "fallback:break_even":
            return None  # could not price the route on-chain

        amount_in = int(hops[0].get("amount_in_wei") or 0)
        final_out = int(rq.final_amount_out_wei or 0)
        if amount_in <= 0:
            return None
        # Cycle closes on the borrow token → in/out share decimals, so a raw
        # wei ratio is the honest gross round-trip result (before flash fee,
        # swap fees, slippage, gas and MEV, which the economics layer applies).
        gross_profit_pct = 100.0 * (final_out - amount_in) / amount_in

        hop_legs: List[Dict[str, Any]] = []
        for h in rq.hops:
            fee_bps = 0
            # HopQuote has no fee; recover from spec by matching addresses.
            hop_legs.append({
                "venue_id": f"{getattr(h, 'dex', 'dex')}:{CHAIN}",
                "source_id": ("uniswap_v3_quote_real"
                              if getattr(h, "dex", "") == "uniswap_v3"
                              else f"{getattr(h, 'dex', 'dex')}_quote_real"),
                "price": None,
                "depth_usd": 0.0,
                "fee_bps": fee_bps,
                "dex_protocol": getattr(h, "dex", None),
                "status": getattr(h, "status", None),
            })
        # attach real fee_bps + depth from specs/tvl per hop
        for leg, pool_addr in zip(hop_legs, route_pools):
            spec = specs.get(pool_addr) or {}
            leg["fee_bps"] = int(spec.get("fee", 3000)) // 100
            leg["depth_usd"] = float(tvl_map.get(pool_addr, 0.0))

        min_tvl = min((float(tvl_map.get(p, 0.0)) for p in route_pools), default=0.0)

        return {
            "hop_legs": hop_legs,
            "gross_profit_pct": gross_profit_pct,
            "tx_gas_units": rq.aggregate_gas_estimate_units,
            "min_pool_tvl_usd_in_route": min_tvl,
            "flash_loan_pool_address": "",
            "route_quote_status": rq.status,
            "verified_at_ts": time.time(),
        }

    return _provider
