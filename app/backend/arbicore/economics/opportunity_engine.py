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


def categorize_quote_failure(route_quote: Dict[str, Any]) -> Optional[str]:
    """Bucket the reason a route did not produce a usable REAL quote.

    Returns None for a fully-ok route. Categories:
    rate_limited · revert_no_pool · no_adapter · rpc_error · other."""
    hops = route_quote.get("hops") or []
    for h in hops:
        st = str(h.get("status") or "")
        if st == "ok":
            continue
        err = str(h.get("error") or "").lower()
        if "rate limit" in err or "-32016" in err or "429" in err or st == "fallback:rate_limited":
            return "rate_limited"
        if st == "fallback:revert" or "revert" in err or "spl" in err:
            return "revert_no_pool"
        if st == "fallback:no_adapter":
            return "no_adapter"
        if st == "fallback:rpc_error":
            return "rpc_error"
        return "other"
    return None


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
        # Dynamic-sizing depth probe: measure real liquidity from the quote
        # curve for routes whose marginal spread is within striking distance.
        self._impact_k = float(cfg.get("impact_k", 0.15))
        self._depth_probe_threshold_bps = float(cfg.get("depth_probe_threshold_bps", -25.0))
        self._depth_probe_multiplier = float(cfg.get("depth_probe_multiplier", 4.0))

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

    async def _measure_liquidity(self, hops: List[Dict[str, Any]], *,
                                 borrow_token: str, eth_usd: Optional[float],
                                 marginal_spread_bps: float):
        """Derive EFFECTIVE pool liquidity (USD) from the live quote curve.

        Quotes the route again at a larger notional and reads how much the
        realized spread degrades. The optimizer models slippage as
        ``impact_k * (notional/liq) * 1e4`` — so the measured slope
        (bps per USD) inverts to ``liq = impact_k * 1e4 / slope``. This is a
        LIVE, on-chain-derived depth input, not a static default. Returns
        ``(liquidity_usd, source)``; falls back to the conservative default
        when the probe is not informative."""
        if marginal_spread_bps < self._depth_probe_threshold_bps:
            return self._pool_liquidity_default, "default:below_threshold"
        token_usd = eth_usd if borrow_token in ("WETH", "cbETH") else 1.0
        if not token_usd:
            return self._pool_liquidity_default, "default:no_price"
        dec = TOKENS[borrow_token]["decimals"]
        in1 = int(hops[0]["amount_in_wei"])
        mult = self._depth_probe_multiplier
        hops2 = [dict(h) for h in hops]
        hops2[0]["amount_in_wei"] = int(in1 * mult)
        rqd2 = await self._quote_with_freshness(hops2)
        if rqd2.get("status") != "ok":
            return self._pool_liquidity_default, "default:probe_unavailable"
        in2 = int(in1 * mult)
        out2 = int(rqd2.get("final_amount_out_wei") or 0)
        if out2 <= 0:
            return self._pool_liquidity_default, "default:probe_zero"
        spread2_bps = (out2 - in2) / in2 * 10_000.0
        n1_usd = in1 / 10**dec * token_usd
        n2_usd = in2 / 10**dec * token_usd
        slope = (marginal_spread_bps - spread2_bps) / max(n2_usd - n1_usd, 1e-9)
        if slope <= 1e-9:
            # No measurable degradation at 4x → very deep pool.
            return max(self._pool_liquidity_default, n2_usd * 50.0), "live_probe:deep"
        liq = self._impact_k * 10_000.0 / slope
        liq = max(50_000.0, min(liq, 500_000_000.0))
        return liq, "live_probe"

    async def evaluate_route(self, route: RouteCycle, *,
                             eth_usd: Optional[float] = None) -> Dict[str, Any]:
        hops = self._route_to_hops(route)
        rqd = await self._quote_with_freshness(hops)
        gas_usd = await self._gas_cost_usd(route.hop_count, eth_usd)
        native_price = eth_usd if route.borrow_token in ("WETH", "cbETH") else 1.0

        # Marginal spread from the first (probe) quote → decide whether to run
        # the live depth probe for dynamic sizing.
        from .quote_provider import classify_quote_status
        qs = classify_quote_status(rqd, max_age_sec=self._quote_max_age_sec)["quote_status"]
        marginal_spread_bps = 0.0
        in0 = int(hops[0].get("amount_in_wei") or 0)
        out0 = int(rqd.get("final_amount_out_wei") or 0)
        if qs == "REAL" and in0 > 0:
            marginal_spread_bps = (out0 - in0) / in0 * 10_000.0
        if qs == "REAL":
            pool_liq_usd, liq_source = await self._measure_liquidity(
                hops, borrow_token=route.borrow_token, eth_usd=eth_usd,
                marginal_spread_bps=marginal_spread_bps)
        else:
            pool_liq_usd, liq_source = self._pool_liquidity_default, "default:quote_unavailable"

        built = build_opportunity_from_route(
            rqd, input_hops=hops, max_age_sec=self._quote_max_age_sec,
            economics={
                "opportunity_id": route.route_id,
                "pool_liquidity_usd": pool_liq_usd,
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
            "quote_failure_category": categorize_quote_failure(rqd),
            "liquidity_usd": round(pool_liq_usd, 2),
            "liquidity_source": liq_source,
            "marginal_spread_bps": round(marginal_spread_bps, 4),
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

    def candidate_universe_size(self) -> int:
        return len(self.enumerate_routes())

    async def scan_once(self, *, limit: Optional[int] = None,
                        offset: int = 0) -> Dict[str, Any]:
        t0 = time.time()
        all_routes = self.enumerate_routes()
        cap = int(limit or self._max_routes)
        n = len(all_routes)
        if n and offset:
            off = offset % n
            routes = (all_routes + all_routes)[off:off + cap]
        else:
            routes = all_routes[:cap]
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

        # ---- market-coverage funnel -------------------------------------
        def _qs(x):
            return (x.get("quote_provenance") or {}).get("quote_status")
        real = [r for r in results if _qs(r) == "REAL"]
        # categorize why non-REAL routes failed to quote
        failure_reasons: Dict[str, int] = {}
        for r in results:
            cat = r.get("quote_failure_category")
            if cat:
                failure_reasons[cat] = failure_reasons.get(cat, 0) + 1
        funnel = {
            "candidate_universe": len(all_routes),
            "routes_quoted": len(results),
            "real_quotes": len(real),
            "quote_failures": sum(1 for r in results if _qs(r) == "UNAVAILABLE"),
            "quote_failure_reasons": failure_reasons,
            "stale_quotes": sum(1 for r in results if _qs(r) == "STALE"),
            "liquidity_measured": sum(1 for r in results
                                      if str(r.get("liquidity_source", "")).startswith("live_probe")),
            "negative_economics": sum(1 for r in real if float(r.get("net_profit_usd") or 0) <= 0),
            "positive_net": sum(1 for r in real if float(r.get("net_profit_usd") or 0) > 0),
            "positive_ev": sum(1 for r in results if float(r.get("expected_value_usd") or 0) > 0),
            "simulation_candidates": len(real),
            "simulation_passes": sum(1 for r in results
                                     if (r.get("simulation") or {}).get("passed")),
            "executable": sum(1 for r in results if r.get("would_execute")),
        }
        return {
            "scan_id": f"scan-{int(t0*1000)}",
            "eth_price_usd": eth_usd,
            "routes_enumerated": len(all_routes),
            "routes_evaluated": len(results),
            "executable_count": funnel["executable"],
            "funnel": funnel,
            "opportunities": results,
            "scan_ms": int((time.time() - t0) * 1000),
            "generated_at": _now_iso(),
        }


__all__ = ["OpportunityEngine", "classify_route", "TOKEN_ALLOWLIST",
           "ContinuousScanner"]


class ContinuousScanner:
    """Operator-controllable background loop that runs the OpportunityEngine
    against real Base market data on an interval and persists all evidence.

    SHADOW/PAPER-safe: read-only discovery + analysis + persistence only.
    """

    def __init__(self, *, engine: "OpportunityEngine", history_repo,
                 recurrence_repo, alert_repo=None, interval_s: float = 90.0,
                 routes_per_scan: int = 12):
        import asyncio
        self._engine = engine
        self._history = history_repo
        self._recurrence = recurrence_repo
        self._alerts = alert_repo
        self._interval = float(interval_s)
        self._routes_per_scan = int(routes_per_scan)
        self._task: Optional["asyncio.Task"] = None
        self._stop = asyncio.Event()
        self._running = False
        self._offset = 0
        self._last_scan: Optional[Dict[str, Any]] = None
        self._cumulative = {"scans": 0, "routes_evaluated": 0,
                            "executable_found": 0, "errors": 0,
                            "started_at": None, "last_scan_at": None,
                            "last_error": None}
        self._funnel_cumulative = {
            "candidate_universe": 0, "routes_quoted": 0, "real_quotes": 0,
            "quote_failures": 0, "stale_quotes": 0, "liquidity_measured": 0,
            "negative_economics": 0, "positive_net": 0, "positive_ev": 0,
            "simulation_candidates": 0, "simulation_passes": 0, "executable": 0,
            "quote_failure_reasons": {}}

    @property
    def running(self) -> bool:
        return self._running

    def status(self) -> Dict[str, Any]:
        last = self._last_scan or {}
        return {
            "running": self._running,
            "interval_s": self._interval,
            "routes_per_scan": self._routes_per_scan,
            "candidate_universe": self._engine.candidate_universe_size(),
            "cumulative": dict(self._cumulative),
            "funnel_cumulative": dict(self._funnel_cumulative),
            "last_scan_summary": {
                "scan_id": last.get("scan_id"),
                "eth_price_usd": last.get("eth_price_usd"),
                "routes_enumerated": last.get("routes_enumerated"),
                "routes_evaluated": last.get("routes_evaluated"),
                "executable_count": last.get("executable_count"),
                "funnel": last.get("funnel"),
                "scan_ms": last.get("scan_ms"),
                "generated_at": last.get("generated_at"),
            } if last else None,
            "next_scan_in_s": (self._interval if self._running else None),
            "generated_at": _now_iso(),
        }

    async def _persist(self, scan: Dict[str, Any]) -> None:
        opps = scan.get("opportunities") or []
        try:
            await self._history.record_many(scan["scan_id"], opps)
            await self._recurrence.record_many(opps)
            if self._alerts is not None:
                await self._alerts.record_qualified(scan["scan_id"], opps)
        except Exception as exc:  # noqa: BLE001
            self._cumulative["last_error"] = f"persist: {exc!r}"

    async def scan_and_persist(self, *, limit: Optional[int] = None) -> Dict[str, Any]:
        scan = await self._engine.scan_once(limit=limit or self._routes_per_scan,
                                            offset=self._offset)
        await self._persist(scan)
        self._last_scan = scan
        self._cumulative["scans"] += 1
        self._cumulative["routes_evaluated"] += int(scan.get("routes_evaluated") or 0)
        self._cumulative["executable_found"] += int(scan.get("executable_count") or 0)
        self._cumulative["last_scan_at"] = _now_iso()
        fn = scan.get("funnel") or {}
        for k in self._funnel_cumulative:
            if k == "candidate_universe":
                self._funnel_cumulative[k] = fn.get(k, self._funnel_cumulative[k])
            elif k == "quote_failure_reasons":
                for cat, cnt in (fn.get(k) or {}).items():
                    self._funnel_cumulative[k][cat] = \
                        self._funnel_cumulative[k].get(cat, 0) + int(cnt)
            else:
                self._funnel_cumulative[k] += int(fn.get(k) or 0)
        # advance the rotating window so successive scans cover the universe
        universe = int(fn.get("candidate_universe") or 0)
        if universe:
            self._offset = (self._offset + (limit or self._routes_per_scan)) % universe
        return scan

    async def _run(self) -> None:
        import asyncio
        while not self._stop.is_set():
            try:
                await self.scan_and_persist()
            except Exception as exc:  # noqa: BLE001
                self._cumulative["errors"] += 1
                self._cumulative["last_error"] = f"scan: {exc!r}"
                logger.warning("continuous scan failed: %r", exc)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._interval)
            except asyncio.TimeoutError:
                pass

    async def start(self) -> Dict[str, Any]:
        import asyncio
        if self._running:
            return self.status()
        self._stop.clear()
        self._running = True
        self._cumulative["started_at"] = _now_iso()
        self._task = asyncio.create_task(self._run())
        logger.info("ContinuousScanner started (interval=%.0fs)", self._interval)
        return self.status()

    async def stop(self) -> Dict[str, Any]:
        import asyncio
        self._stop.set()
        self._running = False
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except (asyncio.TimeoutError, Exception):  # noqa: BLE001
                self._task.cancel()
        logger.info("ContinuousScanner stopped")
        return self.status()
