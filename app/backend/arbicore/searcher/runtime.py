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

from .pool_cache import PoolStateCache, PoolState
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

    def pool_addresses(self) -> List[str]:
        """Real pool contract addresses seeded into the cache (for WSS subs)."""
        return self.cache.pools()


# ── Canonical registry-driven composition (M1→M4 wiring) ────────────────────
def _load_canonical_base_pools():
    from ..discovery import base_pool_registry as reg
    return reg.get_canonical_pools()


def populate_from_registry(cache: PoolStateCache, graph: RouteGraph,
                           pools=None, *, seed_block: int = 0) -> int:
    """Seed the route graph + empty PoolState skeletons from the canonical Base
    pool registry (M1). Needs NO RPC — only pools with a resolved real address
    are added (deterministic-verified UniV3 today; runtime-resolved Aerodrome on
    the VPS). Keyed by REAL contract address so WSS logs land in the cache.
    Skeletons hold sqrt_p/liquidity=0 → cache.quote returns None (honest) until
    real V3 state arrives via slot0 bootstrap / Swap events."""
    if pools is None:
        pools = _load_canonical_base_pools()
    added = 0
    for p in pools:
        if not p.address:
            continue                            # runtime_getpool → resolve on VPS
        key = p.address.lower()
        graph.add_pool(key, p.token0_symbol, p.token1_symbol)
        fee_bps = p.fee_bps if p.fee_bps is not None else (5 if p.kind == "v3" else 30)
        cache.upsert(PoolState(pool=key, kind=p.kind,
                               token0=p.token0_symbol, token1=p.token1_symbol,
                               fee_bps=int(fee_bps), block=seed_block))
        added += 1
    return added


def build_base_tvl_provider(eth_call, price_source, pools=None):
    """Build the REAL, fail-closed Gate-8 TVL provider by REUSING the existing
    OnChainReserveTVLProvider + CachedTVLProvider, fed by a V3-aware on-chain
    reserves fn (balanceOf — NOT V2 getReserves) and a genuine USD price source.
    Unknown price/reserves → None → Gate 8 fails closed (never fabricated)."""
    from ..scanners.flash_loan_arbitrage.tvl_provider import (
        OnChainReserveTVLProvider, CachedTVLProvider)
    from .live_base import make_base_price_fn
    from .v3_state import make_base_v3_reserves_fn, build_pool_meta_for_reserves
    if pools is None:
        pools = _load_canonical_base_pools()
    meta = build_pool_meta_for_reserves(pools)
    reserves_fn = make_base_v3_reserves_fn(eth_call, meta)
    price_fn = make_base_price_fn(price_source)
    return CachedTVLProvider(OnChainReserveTVLProvider(reserves_fn, price_fn))


def build_base_searcher_runtime(*, eth_call=None, price_source=None,
                                pools=None, **kw) -> BaseSearcherRuntime:
    """Full canonical Base searcher composition (SHADOW-only):
      registry → route graph + cache skeletons → (real TVL provider when a
      genuine eth_call + price source are supplied). tvl_provider stays None
      (Gate 8 fail-closed) if either is absent — never fabricated."""
    cache = PoolStateCache()
    graph = RouteGraph()
    populate_from_registry(cache, graph, pools)
    tvl = None
    if eth_call is not None and price_source is not None:
        tvl = build_base_tvl_provider(eth_call, price_source, pools)
    return BaseSearcherRuntime(cache=cache, graph=graph, tvl_provider=tvl, **kw)


# ── Env-driven real-infra adapters (VPS); all fail-closed to None ───────────
def make_base_eth_call_from_env():
    """Return ``async (to, data) -> hex`` over the configured Base RPC, or None
    when no RPC is configured. Reuses the canonical EthJsonRpcProvider (no new
    network abstraction)."""
    from ..config.persistent import resolve_rpc_url_from_env
    url = resolve_rpc_url_from_env("base")
    if not url:
        return None
    from ..providers.rpc import EthJsonRpcProvider
    provider = EthJsonRpcProvider(chain="base", url=url)

    async def eth_call(to: str, data: str):
        try:
            return await provider.eth_call({"to": to, "data": data})
        except Exception:  # noqa: BLE001 — fail-closed
            return None
    return eth_call


def make_base_price_source_from_env():
    """Return ``async (token) -> usd|None`` from GENUINE operator-provided price
    config. Only the native asset price (ARBICORE_NATIVE_PRICE_USD, operator
    config — NOT a hardcoded constant) is served; every other token → None so
    Gate 8 fails closed until a full multi-token price feed is wired on the VPS.
    Returns None (→ no TVL provider) when no price config exists."""
    raw = os.environ.get("ARBICORE_NATIVE_PRICE_USD")
    if not raw:
        return None
    try:
        native = float(raw)
    except (TypeError, ValueError):
        return None
    if native <= 0:
        return None
    native_syms = {"WETH", "ETH"}

    async def price_source(token: str):
        return native if str(token).upper() in native_syms else None
    return price_source


def make_base_v3_state_initializer_from_env():
    """Return the real slot0()/liquidity() V3 state initializer over env RPC, or
    None when no RPC is configured."""
    eth_call = make_base_eth_call_from_env()
    if eth_call is None:
        return None
    from .v3_state import make_v3_state_initializer

    async def _get_block():
        from ..config.persistent import resolve_rpc_url_from_env
        from ..providers.rpc import EthJsonRpcProvider
        url = resolve_rpc_url_from_env("base")
        return await EthJsonRpcProvider(chain="base", url=url).eth_get_block_number()
    return make_v3_state_initializer(eth_call, get_block=_get_block)


def maybe_build_base_searcher() -> Optional[BaseSearcherRuntime]:
    """Flag-gated factory (SHADOW-only; never broadcasts/promotes).

    Now performs the FULL canonical composition: registry → graph + cache +
    real (fail-closed) TVL provider when Base RPC + a genuine price source are
    configured. Eliminates the previous empty-graph / tvl_provider=None blocker
    through genuine wiring; Gate 8 remains fail-closed."""
    if not searcher_enabled():
        return None
    try:
        eth_call = make_base_eth_call_from_env()
    except Exception:  # noqa: BLE001
        eth_call = None
    try:
        price_source = make_base_price_source_from_env()
    except Exception:  # noqa: BLE001
        price_source = None
    return build_base_searcher_runtime(eth_call=eth_call, price_source=price_source)


__all__ = ["BaseSearcherRuntime", "ScanMetrics", "searcher_enabled",
           "maybe_build_base_searcher", "build_base_searcher_runtime",
           "populate_from_registry", "build_base_tvl_provider",
           "make_base_eth_call_from_env", "make_base_price_source_from_env",
           "make_base_v3_state_initializer_from_env", "STRATEGY", "MODE"]
