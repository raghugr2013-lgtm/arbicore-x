"""Universal simulation interface + backends.

Stage 2 of the two-stage pipeline. A ``SimulationBackend`` takes a route +
input size and returns a realized-output/net result. Two backends:

  * LocalMathSimulationBackend — deterministic, RPC-free; recomputes the
    route through the local pool cache (amm_math). Used for fast candidate
    validation before the (expensive) fork sim.
  * RevmForkBackend — REAL atomic simulation via a REVM/Anvil fork. It is an
    honest stub here: it REFUSES to return a result unless a real backend is
    wired (VPS), rather than fabricating a passing simulation.

Chain-specific behavior lives behind the backend, not in the caller.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol, runtime_checkable

from .pool_cache import PoolStateCache
from .route import Edge


@dataclass
class SimResult:
    ok: bool
    amount_in: float
    amount_out: float
    net_native: float                 # amount_out - amount_in (repay basis)
    backend: str
    reason: str = ""
    hops: List[float] = field(default_factory=list)


@runtime_checkable
class SimulationBackend(Protocol):
    backend_id: str
    async def simulate(self, cycle: List[Edge], amount_in: float) -> SimResult: ...


class LocalMathSimulationBackend:
    backend_id = "local_math"

    def __init__(self, cache: PoolStateCache) -> None:
        self._cache = cache

    async def simulate(self, cycle: List[Edge], amount_in: float) -> SimResult:
        amt = float(amount_in)
        hops: List[float] = []
        for e in cycle:
            out = self._cache.quote(e.pool, e.token_in, amt)
            if out is None or out <= 0:
                return SimResult(False, amount_in, 0.0, -amount_in,
                                 self.backend_id, reason="unpriceable_hop",
                                 hops=hops)
            amt = out
            hops.append(out)
        return SimResult(True, amount_in, amt, amt - amount_in,
                         self.backend_id, reason="ok", hops=hops)


class RevmForkBackend:
    """Real atomic fork simulation. Honest stub: refuses to fabricate."""

    backend_id = "revm_fork"

    def __init__(self, runner=None) -> None:
        self._runner = runner       # injected real REVM/Anvil runner on VPS

    async def simulate(self, cycle: List[Edge], amount_in: float) -> SimResult:
        if self._runner is None:
            return SimResult(
                False, amount_in, 0.0, -amount_in, self.backend_id,
                reason="revm/anvil backend not wired (VPS-only); refusing to "
                       "fabricate a simulation result")
        return await self._runner.simulate(cycle, amount_in)


async def two_stage_pipeline(
    cache: PoolStateCache, survivors, *, amount_in: float,
    backend: Optional[SimulationBackend] = None,
) -> list:
    """Stage-1 survivors → stage-2 simulate. Returns simulated positive-net
    routes sorted by net (screening only; economic gate applied downstream)."""
    backend = backend or LocalMathSimulationBackend(cache)
    results = []
    for cyc, ratio in survivors:
        res = await backend.simulate(cyc, amount_in)
        if res.ok and res.net_native > 0:
            results.append((cyc, ratio, res))
    results.sort(key=lambda t: t[2].net_native, reverse=True)
    return results


__all__ = ["SimResult", "SimulationBackend", "LocalMathSimulationBackend",
           "RevmForkBackend", "two_stage_pipeline"]
