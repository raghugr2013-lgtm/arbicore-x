"""RouteSearchEngine — graph + bounded cycle enumeration.

The single piece of D-6 substrate that does NOT have a direct ancestor
elsewhere in ArbiCore X. It builds a token→pool graph from an
operator-supplied pool registry and emits *closed cycles* (starting
and ending at the borrow token) within a hop budget.

Algorithm: depth-bounded DFS with a wall-clock cap and a candidate cap.
Pruning rules:
  - Visited-pool set (no pool reused inside a single cycle)
  - Minimum-TVL gate per hop (configurable)
  - Cycle must close on the borrow token

INV-1/2/3 preserved:
  - Pure computation. No HTTP, no DB, no EmissionBus, no canonical
    construction. Returns ordered ``RouteCycle`` value objects.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


# ============================================================================
# Pool graph value objects
# ============================================================================

@dataclass(frozen=True)
class PoolNode:
    """One DEX pool as a graph node.

    Pools are bidirectional: a swap can go ``token_a → token_b`` or the
    reverse. The ``RouteSearchEngine`` traverses both directions.
    """
    pool_address: str
    dex_protocol: str           # 'uniswap_v3' | 'aerodrome' | ...
    chain: str
    token_a: str                # symbol (e.g. 'USDC')
    token_b: str
    tvl_usd: float
    fee_bps: int                # pool swap fee in basis points

    def other_token(self, token: str) -> Optional[str]:
        if token == self.token_a:
            return self.token_b
        if token == self.token_b:
            return self.token_a
        return None


@dataclass
class RouteCycle:
    """A discovered closed cycle starting & ending on ``borrow_token``."""
    chain: str
    borrow_token: str
    pools: List[PoolNode]                # ordered
    token_path: List[str]                # ordered (len = len(pools) + 1)
    min_tvl_usd: float
    hop_count: int
    estimated_total_fee_pct: float       # Σ pool fees in pct

    @property
    def route_id(self) -> str:
        return ":".join([self.chain, self.borrow_token,
                          *(p.pool_address for p in self.pools)])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "borrow_token": self.borrow_token,
            "route_pools": [p.pool_address for p in self.pools],
            "route_dex_protocols": [p.dex_protocol for p in self.pools],
            "cycle_token_path": list(self.token_path),
            "hop_count": self.hop_count,
            "min_tvl_usd": self.min_tvl_usd,
            "estimated_total_fee_pct": self.estimated_total_fee_pct,
            "route_id": self.route_id,
        }


# ============================================================================
# RouteSearchEngine
# ============================================================================

class RouteSearchEngine:
    """Depth-bounded DFS cycle enumerator over a token→pool graph.

    Construction takes a callable that returns the per-chain pool
    inventory; the engine builds the adjacency map lazily on each
    ``search()`` call (operator may update the inventory between calls).

    Caps (all operator-tunable via scanner_config.flash_loan_arb.route_search):
      - ``max_hops``       — default 4
      - ``wall_clock_cap_s`` — default 5.0
      - ``candidate_cap``  — default 64
      - ``min_pool_tvl_usd`` — default 100_000
    """

    def __init__(
        self,
        *,
        pool_loader,
        max_hops: int = 4,
        wall_clock_cap_s: float = 5.0,
        candidate_cap: int = 64,
        min_pool_tvl_usd: float = 100_000.0,
    ) -> None:
        self._pool_loader = pool_loader
        self.max_hops = int(max_hops)
        self.wall_clock_cap_s = float(wall_clock_cap_s)
        self.candidate_cap = int(candidate_cap)
        self.min_pool_tvl_usd = float(min_pool_tvl_usd)
        self._last_wall_ms: int = 0
        self._last_explored: int = 0

    @property
    def last_wall_ms(self) -> int:
        return self._last_wall_ms

    @property
    def last_explored(self) -> int:
        return self._last_explored

    def search(self, *, chain: str, borrow_token: str) -> List[RouteCycle]:
        """Enumerate cycles starting & ending on ``borrow_token``."""
        t0 = time.time()
        pools = list(self._pool_loader(chain) or [])
        pools = [p for p in pools if p.tvl_usd >= self.min_pool_tvl_usd]
        adjacency = _build_adjacency(pools)

        cycles: List[RouteCycle] = []
        explored = 0
        deadline = t0 + self.wall_clock_cap_s

        def dfs(token: str, path_pools: List[PoolNode],
                token_path: List[str], visited: Set[str],
                ) -> None:
            nonlocal explored
            if len(cycles) >= self.candidate_cap:
                return
            if time.time() >= deadline:
                return
            if len(path_pools) > self.max_hops:
                return
            for pool in adjacency.get(token, ()):
                if pool.pool_address in visited:
                    continue
                next_token = pool.other_token(token)
                if next_token is None:
                    continue
                explored += 1
                new_visited = visited | {pool.pool_address}
                new_pools = path_pools + [pool]
                new_path = token_path + [next_token]
                if next_token == borrow_token and len(new_pools) >= 2:
                    cycles.append(_finalise_cycle(
                        chain, borrow_token, new_pools, new_path))
                    if len(cycles) >= self.candidate_cap:
                        return
                else:
                    # Continue search only if budget remains.
                    if len(new_pools) < self.max_hops:
                        dfs(next_token, new_pools, new_path, new_visited)

        dfs(borrow_token, [], [borrow_token], set())
        self._last_wall_ms = int((time.time() - t0) * 1000)
        self._last_explored = explored
        return cycles


# ============================================================================
# Helpers
# ============================================================================

def _build_adjacency(pools: Iterable[PoolNode]) -> Dict[str, List[PoolNode]]:
    adj: Dict[str, List[PoolNode]] = {}
    for p in pools:
        adj.setdefault(p.token_a, []).append(p)
        adj.setdefault(p.token_b, []).append(p)
    return adj


def _finalise_cycle(chain: str, borrow_token: str,
                     pools: List[PoolNode], path: List[str]) -> RouteCycle:
    min_tvl = min((p.tvl_usd for p in pools), default=0.0)
    total_fee_pct = sum((p.fee_bps for p in pools), 0) / 100.0
    return RouteCycle(
        chain=chain, borrow_token=borrow_token, pools=list(pools),
        token_path=list(path), min_tvl_usd=min_tvl,
        hop_count=len(pools), estimated_total_fee_pct=total_fee_pct,
    )
