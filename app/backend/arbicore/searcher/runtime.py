"""Base searcher runtime orchestrator (SHADOW-only; no broadcasting).

Real-data path (flag-gated: ARBICORE_T2_SEARCHER_ENABLED):
  Base WSS/logs → PoolStateCache → local AMM/CL math → route discovery →
  fast filter → T1 sizing/economics/ranking → LocalMathSimulation →
  Gate 7 ($25) / Gate 8 (real TVL, fail-closed) / REAL provenance →
  candidate output.  (RevmForkBackend = optional stage-2b, fail-closed.)

INVARIANTS: never broadcasts; never promotes; $25 Gate 7 unchanged; Gate 8
fails closed without verifiable TVL; only REAL/VERIFIED_REAL provenance;
never fabricates liquidity/quotes/sims.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .pool_cache import PoolStateCache
from .route import RouteGraph, enumerate_cycles, fast_filter
from .simulation import LocalMathSimulationBackend, SimulationBackend
from ..scanners.flash_loan_arbitrage.ranking import rank_opportunities
from ..scanners.flash_loan_arbitrage.filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
)

STRATEGY = "flash_loan_arbitrage"
MODE = "SHADOW"


def searcher_enabled() -> bool:
    return (os.environ.get("ARBICORE_T2_SEARCHER_ENABLED") or "").strip().lower() \
        in {"1", "true", "yes", "on"}


@dataclass
class ScanMetrics:
    block: int = 0
    cycles: int = 0
    survivors: int = 0
    sim_ok: int = 0
    gate7_rejected: int = 0
    gate8_rejected: int = 0
    stale_hops: int = 0
    candidates: int = 0
    scan_latency_ms: float = 0.0
    broadcasts: int = 0            # MUST always be 0 (SHADOW)


class BaseSearcherRuntime:
    def __init__(self, *, cache: PoolStateCache, graph: RouteGraph,
                 tvl_provider=None, sim_backend: Optional[SimulationBackend] = None,
                 max_hops: int = 3, min_ratio: float = 1.0005,
                 g7_floor_usd: float = 25.0):
        self.cache = cache
        self.graph = graph
        self.tvl_provider = tvl_provider
        self.sim = sim_backend or LocalMathSimulationBackend(cache)
        self.max_hops = max_hops
        self.min_ratio = min_ratio
        # $25 Gate 7 floor is NOT lowerable via this path.
        self.gate7 = FlashLoanGate7AtomicProfit(thresholds={})
        self.gate8 = FlashLoanGate8LiquidityDepth(thresholds={})
        self._g7_floor = g7_floor_usd
        self.mode = MODE

    def ingest_log(self, log: Dict[str, Any]) -> None:
        self.cache.apply_log(log)

    async def scan_block(self, block: int, start_tokens: List[str],
                         *, amount_in: float = 1.0) -> Dict[str, Any]:
        assert self.mode == "SHADOW", "runtime must be SHADOW"
        t0 = time.perf_counter()
        self.cache.set_head_block(block)
        m = ScanMetrics(block=block)
        candidates: List[Dict[str, Any]] = []

        all_cycles = []
        for tok in start_tokens:
            all_cycles += enumerate_cycles(self.graph, tok, self.max_hops)
        m.cycles = len(all_cycles)
        survivors = fast_filter(self.cache, all_cycles, min_ratio=self.min_ratio)
        m.survivors = len(survivors)

        for cyc, ratio in survivors:
            sim = await self.sim.simulate(cyc, amount_in)
            if not sim.ok or sim.net_native <= 0:
                if sim.reason == "unpriceable_hop":
                    m.stale_hops += 1
                continue
            m.sim_ok += 1
            # Economics (native-unit net → treat as USD-normalised proxy here;
            # real USD pricing is applied by the verifier on the VPS).
            atomic_profit_usd = float(sim.net_native)
            g7 = self.gate7.evaluate(atomic_profit_usd=atomic_profit_usd,
                                     borrow_amount_usd=amount_in)
            if not g7.passed:
                m.gate7_rejected += 1
                continue
            # Gate 8: real verifiable liquidity or FAIL CLOSED.
            min_tvl = await self._route_min_tvl(cyc)
            g8 = self.gate8.evaluate(min_pool_tvl_usd_in_route=(min_tvl or 0.0))
            if not g8.passed:
                m.gate8_rejected += 1
                continue
            candidates.append({
                "strategy": STRATEGY, "mode": MODE,
                "provenance": "REAL",            # live-quoted from cache state
                "route": [e.pool for e in cyc],
                "spot_ratio": round(ratio, 6),
                "sim_net": round(sim.net_native, 8),
                "atomic_profit_usd": round(atomic_profit_usd, 6),
                "min_route_tvl_usd": min_tvl,
                "expected_net_profit_usd": atomic_profit_usd,
                "execution_probability": 0.7, "confidence": 0.7,
                "block": block,
            })
        m.candidates = len(candidates)
        ranked = rank_opportunities([
            {"opportunity_id": ",".join(c["route"]),
             "expected_net_profit_usd": c["expected_net_profit_usd"],
             "execution_probability": c["execution_probability"],
             "confidence": c["confidence"],
             "min_route_tvl_usd": c["min_route_tvl_usd"]} for c in candidates])
        m.scan_latency_ms = (time.perf_counter() - t0) * 1e3
        return {"metrics": m.__dict__,
                "candidates": candidates,
                "ranking": [(r.opportunity_id, r.score) for r in ranked],
                "broadcast": False}

    async def _route_min_tvl(self, cyc) -> Optional[float]:
        if self.tvl_provider is None:
            return None                        # → Gate 8 fails closed
        vals = []
        for e in cyc:
            v = await self.tvl_provider.get_pool_tvl_usd("base", e.pool)
            if v is None:
                return None                    # unverifiable → fail closed
            vals.append(v)
        return min(vals) if vals else None


def maybe_build_base_searcher() -> Optional[BaseSearcherRuntime]:
    """Flag-gated factory. Returns None unless ARBICORE_T2_SEARCHER_ENABLED.
    Construction only — never starts broadcasting; SHADOW-only."""
    if not searcher_enabled():
        return None
    return BaseSearcherRuntime(cache=PoolStateCache(), graph=RouteGraph())


__all__ = ["BaseSearcherRuntime", "ScanMetrics", "searcher_enabled",
           "maybe_build_base_searcher", "STRATEGY", "MODE"]
