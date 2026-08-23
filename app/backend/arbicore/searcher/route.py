"""Universal route graph + closed-cycle enumeration + cheap spot fast-filter.

Stage 1 of the two-stage searcher pipeline: enumerate token cycles and screen
them with a cheap local spot-price product (no sizing, no sim). Only cycles
whose spot round-trip exceeds a threshold survive to stage 2 (simulation).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .pool_cache import PoolStateCache


@dataclass
class Edge:
    pool: str
    token_in: str
    token_out: str


@dataclass
class RouteGraph:
    adjacency: Dict[str, List[Edge]] = field(default_factory=dict)

    def add_pool(self, pool: str, token0: str, token1: str) -> None:
        self.adjacency.setdefault(token0, []).append(Edge(pool, token0, token1))
        self.adjacency.setdefault(token1, []).append(Edge(pool, token1, token0))


def enumerate_cycles(graph: RouteGraph, start: str, max_hops: int = 3,
                     cap: int = 5000) -> List[List[Edge]]:
    """Closed cycles start→…→start with 2..max_hops edges (no pool reused)."""
    out: List[List[Edge]] = []

    def dfs(token: str, path: List[Edge], used_pools: set):
        if len(out) >= cap:
            return
        if path and token == start and len(path) >= 2:
            out.append(list(path))
            return
        if len(path) >= max_hops:
            return
        for e in graph.adjacency.get(token, ()):  # noqa: B007
            if e.pool in used_pools:
                continue
            dfs(e.token_out, path + [e], used_pools | {e.pool})

    dfs(start, [], set())
    return out


def spot_roundtrip(cache: PoolStateCache, cycle: List[Edge],
                   probe_amount: float = 1.0) -> Optional[float]:
    """Cheap output/input ratio for a tiny probe. None if any hop unpriceable."""
    amt = probe_amount
    for e in cycle:
        out = cache.quote(e.pool, e.token_in, amt)
        if out is None or out <= 0:
            return None
        amt = out
    return amt / probe_amount if probe_amount > 0 else None


def fast_filter(cache: PoolStateCache, cycles: List[List[Edge]], *,
                min_ratio: float = 1.0005,
                probe_amount: float = 1.0) -> List[Tuple[List[Edge], float]]:
    """Stage-1: keep cycles whose spot round-trip ratio > min_ratio.

    min_ratio is a *screening* pre-filter (find candidates worth simulating),
    NOT a profitability gate — the $25 economic floor and full economics are
    applied later at the verifier. Never fabricates: unpriceable → dropped.
    """
    survivors: List[Tuple[List[Edge], float]] = []
    for cyc in cycles:
        r = spot_roundtrip(cache, cyc, probe_amount)
        if r is not None and r > min_ratio:
            survivors.append((cyc, r))
    survivors.sort(key=lambda t: t[1], reverse=True)
    return survivors


__all__ = ["Edge", "RouteGraph", "enumerate_cycles", "spot_roundtrip",
           "fast_filter"]
