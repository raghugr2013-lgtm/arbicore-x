"""ArbiCore X — Autonomous Flash-Loan Opportunity Engine (P0 orchestrator).

Connects DISCOVERY → REAL QUOTE → decision chain, REUSING the already-built
components (never rebuilding them):

    RouteSearchEngine (cycle enumeration)
      → QuoterRegistry (read-only Base eth_call quotes)
      → quote_provider.build_opportunity_from_route (realized spread + freshness)
      → opportunity_decision.decide_opportunity
          (net_profit → confidence v2 → EV → size optimizer → HARD sim gate)

Discovery covers: same-DEX different fee tiers, cross-DEX, multi-hop,
triangular and stablecoin-triangular cycles (the DFS enumerates all closed
cycles on each borrow token across the curated venue graph).

Quote freshness is a HARD condition:
    REAL → continue ·  STALE → re-quote once ·  UNAVAILABLE → reject.

SHADOW/PAPER-safe: pure analysis + persistence. No signing/broadcast/deploy.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from ..scanners.flash_loan_arbitrage.route_search import RouteSearchEngine, RouteCycle
from ..discovery.base_venues import (
    CHAIN, TOKENS, BORROW_TOKENS, PROBE_AMOUNT, ROUTER_ALLOWLIST,
    token_address, is_stable, build_pool_graph,
)
from .quote_provider import build_opportunity_from_route
from .opportunity_decision import decide_opportunity

logger = logging.getLogger("arbicore.economics.opportunity_engine")

TOKEN_ALLOWLIST = [t["address"] for t in TOKENS.values()]

# Gas model (Base): flash-loan overhead + per-swap units.
_GAS_FLASH_OVERHEAD = 120_000
_GAS_PER_SWAP = 150_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def classify_route(route: RouteCycle) -> str:
    hops = route.hop_count
    dexes = {p.dex_protocol for p in route.pools}
    tokens = route.token_path[:-1]           # drop the closing repeat
    uniq = set(tokens)
    if hops == 2:
        return "same_dex_fee_tier" if len(dexes) == 1 else "cross_dex"
    if len(uniq) >= 3 and all(is_stable(t) for t in uniq):
        return "stablecoin_triangular"
    if hops == 3 and len(uniq) == 3:
        return "triangular"
    return "multi_hop"


class OpportunityEngine:
    """Autonomous discovery + evaluation over the read-only Base quote layer."""

    def __init__(self, *, quoter_registry, config: Optional[Dict[str, Any]] = None):
        self._quoter = quoter_registry
        cfg = config or {}
        self._pools, self._specs = build_pool_graph()
        self._route_engine = RouteSearchEngine(
            pool_loader=lambda chain: self._pools if chain == CHAIN else [],
            max_hops=int(cfg.get("max_hops", 3)),
            wall_clock_cap_s=float(cfg.get("route_wall_clock_cap_s", 3.0)),
            candidate_cap=int(cfg.get("candidate_cap", 48)),
            min_pool_tvl_usd=0.0,
        )
        self._max_routes = int(cfg.get("max_routes_per_scan", 16))
        self._pool_liquidity_default = float(cfg.get("pool_liquidity_usd_default", 1_500_000.0))
        self._max_slippage_bps = float(cfg.get("max_slippage_bps", 150.0))
        self._max_gas_usd = float(cfg.get("max_gas_usd", 50.0))
        self._mev_risk = float(cfg.get("mev_risk", 0.15))
        self._quote_max_age_sec = float(cfg.get("quote_max_age_sec", 12.0))

    # ---- discovery ------------------------------------------------------
    def enumerate_routes(self) -> List[RouteCycle]:
        routes: List[RouteCycle] = []
        seen: set = set()
        for bt in BORROW_TOKENS:
            for cyc in self._route_engine.search(chain=CHAIN, borrow_token=bt):
                if cyc.route_id not in seen:
                    seen.add(cyc.route_id)
                    routes.append(cyc)
        return routes

    def _route_to_hops(self, route: RouteCycle) -> List[Dict[str, Any]]:
        hops: List[Dict[str, Any]] = []
        path = route.token_path
        borrow = route.borrow_token
        for i, pool in enumerate(route.pools):
            tin, tout = path[i], path[i + 1]
            spec = dict(self._specs.get(pool.pool_address, {}))
            h: Dict[str, Any] = {
                "dex": spec.get("dex"),
                "token_in": token_address(tin),
                "token_out": token_address(tout),
            }
            if i == 0:
                h["amount_in_wei"] = PROBE_AMOUNT.get(borrow, 10**16)
            if "fee" in spec:
                h["fee"] = spec["fee"]
            if "tick_spacing" in spec:
                h["tick_spacing"] = spec["tick_spacing"]
            if "stable" in spec:
                h["stable"] = spec["stable"]
            hops.append(h)
        return hops

    # ---- live market context -------------------------------------------
    async def _eth_price_usd(self) -> Optional[float]:
        try:
            rq = await self._quoter.quote_route(chain=CHAIN, hops=[{
                "dex": "uniswap_v3",
                "token_in": token_address("WETH"),
                "token_out": token_address("USDC"),
                "amount_in_wei": 10**18, "fee": 500}])
            if rq.status == "ok" and rq.final_amount_out_wei > 0:
                return rq.final_amount_out_wei / 10**6      # USDC has 6 decimals
        except Exception:  # noqa: BLE001
            return None
        return None

    async def _gas_price_wei(self) -> Optional[int]:
        rpc = self._quoter._rpc_url()  # noqa: SLF001 — same read-only RPC
        if not rpc:
            return None
        try:
            async with httpx.AsyncClient(timeout=8.0) as c:
                r = await c.post(rpc, json={"jsonrpc": "2.0", "id": 1,
                                            "method": "eth_gasPrice", "params": []})
                r.raise_for_status()
                res = r.json().get("result")
                return int(res, 16) if res else None
        except Exception:  # noqa: BLE001
            return None

    async def _gas_cost_usd(self, hop_count: int, eth_usd: Optional[float]) -> float:
        gas_price = await self._gas_price_wei()
        if gas_price is None or eth_usd is None:
            return 0.0
        units = _GAS_FLASH_OVERHEAD + _GAS_PER_SWAP * hop_count
        return gas_price * units / 1e18 * eth_usd

    # ---- evaluation -----------------------------------------------------
    async def _quote_with_freshness(self, hops: List[Dict[str, Any]]):
        """Quote once; on STALE re-quote once; return (route_quote_dict)."""
        from .quote_provider import classify_quote_status
        rq = await self._quoter.quote_route(chain=CHAIN, hops=hops)
        rqd = rq.to_dict()
        status = classify_quote_status(rqd, max_age_sec=self._quote_max_age_sec)["quote_status"]
        if status == "STALE":
            rq = await self._quoter.quote_route(chain=CHAIN, hops=hops)
            rqd = rq.to_dict()
        return rqd

    async def evaluate_route(self, route: RouteCycle, *,
                             eth_usd: Optional[float] = None) -> Dict[str, Any]:
        hops = self._route_to_hops(route)
        rqd = await self._quote_with_freshness(hops)
        gas_usd = await self._gas_cost_usd(route.hop_count, eth_usd)
        native_price = eth_usd if route.borrow_token in ("WETH", "cbETH") else 1.0
        built = build_opportunity_from_route(
            rqd, input_hops=hops, max_age_sec=self._quote_max_age_sec,
            economics={
                "opportunity_id": route.route_id,
                "pool_liquidity_usd": self._pool_liquidity_default,
                "gas_cost_usd": gas_usd,
                "flash_loan_fee_bps": 0.0,
                "flash_loan_provider": "balancer_v2",
                "native_price_usd": native_price,
                "gas_certainty": 0.9, "mev_risk": self._mev_risk,
                "buy_venue_fee_bps": 0.0, "sell_venue_fee_bps": 0.0,  # realized spread is net of DEX fees
                "max_hops": 4,
            })
        opp = built["opportunity"]
        decision = decide_opportunity(
            opp, router_allowlist=ROUTER_ALLOWLIST, token_allowlist=TOKEN_ALLOWLIST,
            max_slippage_bps=self._max_slippage_bps, max_gas_usd=self._max_gas_usd)
        d = decision.to_dict()
        return {
            "route_id": route.route_id,
            "opportunity_type": classify_route(route),
            "chain": CHAIN,
            "borrow_token": route.borrow_token,
            "token_path": route.token_path,
            "dex_path": [p.dex_protocol for p in route.pools],
            "hop_count": route.hop_count,
            "quote_provenance": built["quote_provenance"],
            "gas_cost_usd": round(gas_usd, 6),
            "would_execute": d["would_execute"],
            "reason": d["reason"],
            "gross_spread_bps": opp["gross_spread_bps"],
            "net_profit_usd": d["net_profit_usd"],
            "confidence": d["confidence"],
            "expected_value_usd": d["expected_value_usd"],
            "optimal_notional_usd": d["optimal_notional_usd"],
            "simulation": d["simulation"],
            "decision": d,
            "evaluated_at": _now_iso(),
        }

    async def scan_once(self, *, limit: Optional[int] = None) -> Dict[str, Any]:
        t0 = time.time()
        routes = self.enumerate_routes()
        cap = int(limit or self._max_routes)
        routes = routes[:cap]
        eth_usd = await self._eth_price_usd()
        results: List[Dict[str, Any]] = []
        for r in routes:
            try:
                results.append(await self.evaluate_route(r, eth_usd=eth_usd))
            except Exception as exc:  # noqa: BLE001
                logger.warning("evaluate_route failed for %s: %r", r.route_id, exc)
        # Rank: executable first, then by EV desc.
        results.sort(key=lambda x: (x["would_execute"], x["expected_value_usd"]),
                     reverse=True)
        executable = [r for r in results if r["would_execute"]]
        return {
            "scan_id": f"scan-{int(t0)}",
            "eth_price_usd": eth_usd,
            "routes_enumerated": len(self.enumerate_routes()),
            "routes_evaluated": len(results),
            "executable_count": len(executable),
            "opportunities": results,
            "scan_ms": int((time.time() - t0) * 1000),
            "generated_at": _now_iso(),
        }


__all__ = ["OpportunityEngine", "classify_route", "TOKEN_ALLOWLIST"]
