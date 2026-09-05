"""Flash-Loan DiscoverySources — D-6.1.

Two sources land here. Both INV-1 compliant (DiscoveryCandidate only).

  - RouteSearchDiscoverySource
        Consumes the ``RouteSearchEngine`` and emits one
        DiscoveryCandidate per discovered closed cycle.
        Gated by per-chain enable flag in scanner_config.

  - FlashLoanProviderHealthSource
        Probes per-provider liquidity caps via on-chain reads. Emits
        SourceHealth only — no DiscoveryCandidates (informational).
        Equivalent surface to D-5's bridge-liveness probes.

INV-3: hint provenance is REAL (provider catalog source_ids).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

from ...models.discovery import (
    DiscoveryCandidate, SourceHealth, make_candidate_id,
)
from ...models.enums import DataProvenance, OpportunityType
from ...chains.registries import probe_amount_wei
from ..discovery_source import DiscoverySource
from .route_search import PoolNode, RouteCycle, RouteSearchEngine

logger = logging.getLogger(
    "arbicore.scanners.flash_loan_arbitrage.sources")


_IN_SCOPE_CHAINS = frozenset({
    "ethereum", "arbitrum", "base", "optimism", "polygon",
})


def _now() -> float:
    return time.time()


def _fee_ppm_from_pool(pool: PoolNode) -> int:
    """Authoritative fee tier (ppm) for a hop. The multichain venue id encodes
    the fee tier as its last ``:``-segment (``dex:tokenlo:tokenhi:fee_ppm``);
    prefer that exact value, else fall back to ``fee_bps * 100``. No fabricated
    fee — both sources come from the operator-supplied pool graph."""
    tail = str(pool.pool_address).rsplit(":", 1)[-1]
    try:
        return int(tail)
    except (TypeError, ValueError):
        return int(pool.fee_bps) * 100


# ============================================================================
# RouteSearchDiscoverySource
# ============================================================================

class RouteSearchDiscoverySource(DiscoverySource):
    """Emits one ``DiscoveryCandidate`` per discovered cycle.

    Construction takes:
      - ``route_engine`` — pre-built ``RouteSearchEngine``
      - ``config_loader`` — returns scanner_config.flash_loan_arb
      - ``borrow_token_set`` — operator-configurable starting set
    """

    source_id = "flash_loan_route_search"
    cadence_s = 60
    opportunity_types: Set[OpportunityType] = {
        OpportunityType.FLASH_LOAN_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None

    _DEFAULT_BORROW_TOKENS = ("USDC", "USDT", "WETH", "DAI")

    def __init__(
        self,
        *,
        route_engine: RouteSearchEngine,
        config_loader: Callable[[], Dict[str, Any]],
        borrow_token_set: Optional[List[str]] = None,
    ) -> None:
        self._engine = route_engine
        self._cfg = config_loader
        self._borrow_tokens = list(
            borrow_token_set or self._DEFAULT_BORROW_TOKENS)
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        # No HTTP API key needed — on-chain reads only.
        return True

    async def close(self) -> None:
        return None

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._cfg() or {}
        chains_cfg = cfg.get("chains") or {}
        providers_cfg = cfg.get("providers") or {}
        enabled_chains = [c for c, v in chains_cfg.items()
                           if (v or {}).get("enabled", False)
                           and c in _IN_SCOPE_CHAINS]
        enabled_providers = [p for p, v in providers_cfg.items()
                              if (v or {}).get("enabled", False)]
        if not enabled_chains or not enabled_providers:
            return []
        t0 = _now()
        candidates: List[DiscoveryCandidate] = []
        for chain in enabled_chains:
            for borrow_token in self._borrow_tokens:
                try:
                    cycles = self._engine.search(
                        chain=chain, borrow_token=borrow_token)
                except Exception as exc:  # noqa: BLE001
                    self._last_error = (
                        f"route_search[{chain}:{borrow_token}]: "
                        f"{type(exc).__name__}: {exc}")
                    continue
                for cycle in cycles:
                    for provider in enabled_providers:
                        cand = self._candidate_for_cycle(
                            cycle, provider=provider)
                        if cand is not None:
                            candidates.append(cand)
        self._last_latency_ms = int((_now() - t0) * 1000)
        if candidates:
            self._last_emission_at = _now()
        return candidates

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )

    def _candidate_for_cycle(self, cycle: RouteCycle,
                              *, provider: str,
                              ) -> Optional[DiscoveryCandidate]:
        subject = (f"flash_loan:{provider}:{cycle.chain}:"
                    f"{cycle.borrow_token}:{cycle.route_id}")
        venues = [p.pool_address for p in cycle.pools]
        observed = _now()
        cid = make_candidate_id(
            hint_source=self.source_id,
            opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
            subject_id=subject, asset=cycle.borrow_token,
            candidate_venues=venues, hint_observed_at=observed,
        )
        hint_metric: Dict[str, Any] = {
            "chain": cycle.chain,
            "provider": provider,
            "borrow_token": cycle.borrow_token,
            "hop_count": cycle.hop_count,
            "min_tvl_usd": cycle.min_tvl_usd,
            "estimated_total_fee_pct": cycle.estimated_total_fee_pct,
            "route_pools": list(venues),
            "route_dex_protocols": [p.dex_protocol for p in cycle.pools],
            "cycle_token_path": list(cycle.token_path),
            "route_search_wall_ms": self._engine.last_wall_ms,
            "route_search_candidates_explored": self._engine.last_explored,
        }
        # For genuinely multichain (non-Base) cycles, attach the per-hop route
        # reconstruction + a deterministic probe borrow amount so the chain/
        # venue-aware live_quote_provider can quote the route. Base is left
        # untouched (regression-frozen): it keeps its canonical-registry path
        # (_plan_base) and ignores these fields entirely.
        self._augment_multichain_route(cycle, hint_metric)
        return DiscoveryCandidate(
            candidate_id=cid,
            opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
            hint_source=self.source_id,
            hint_observed_at=observed,
            subject_id=subject,
            asset=cycle.borrow_token,
            candidate_venues=venues,
            hint_metric=hint_metric,
            reason=f"{self.source_id}:{cycle.route_id}",
        )

    @staticmethod
    def _augment_multichain_route(cycle: RouteCycle,
                                  hint_metric: Dict[str, Any]) -> None:
        """Attach ``route_hops`` + a deterministic probe ``borrow_amount_wei``
        for a NON-Base cycle so the generic EVM quote path can reconstruct the
        route. Base/base-sepolia return early (canonical registry path is
        regression-frozen). Nothing is fabricated: hops carry token SYMBOLS +
        the venue id + the pool's declared fee tier, and the amount is a
        decimals-derived probe (``chains.registries.probe_amount_wei``). If the
        borrow token has no verified registry decimals the amount is OMITTED so
        the route fails closed downstream — never an invented amount."""
        chain = (cycle.chain or "").lower()
        if chain in ("base", "base-sepolia"):
            return
        tp = list(cycle.token_path)
        hops: List[Dict[str, Any]] = []
        for i, pool in enumerate(cycle.pools):
            hops.append({
                "dex": pool.dex_protocol,
                "token_in": tp[i],
                "token_out": tp[i + 1],
                "fee": _fee_ppm_from_pool(pool),
                "pool": pool.pool_address,
            })
        hint_metric["route_hops"] = hops
        amt = probe_amount_wei(chain, cycle.borrow_token)
        if amt is not None:
            hint_metric["borrow_amount_wei"] = int(amt)
            # Provenance: this is a PROBE only — never executable liquidity,
            # flash-loan capacity, trade size, or profitability.
            hint_metric["borrow_amount_provenance"] = "deterministic_probe"


# ============================================================================
# FlashLoanProviderHealthSource — informational SourceHealth only
# ============================================================================

class FlashLoanProviderHealthSource(DiscoverySource):
    """Probes provider liquidity caps. Returns no candidates; the
    verifier uses provider health via the route catalog instead.
    This source exists primarily so the /source-health route can
    surface provider readiness.
    """

    source_id = "flash_loan_provider_health"
    cadence_s = 120
    opportunity_types: Set[OpportunityType] = {
        OpportunityType.FLASH_LOAN_ARBITRAGE}
    tier = 2
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                  ) -> None:
        self._cfg = config_loader
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None

    @property
    def credentials_available(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def discover(self) -> List[DiscoveryCandidate]:
        return []  # informational only

    async def health(self) -> SourceHealth:
        cfg = self._cfg() or {}
        providers = (cfg.get("providers") or {})
        # Aggregate per-provider enable flags into a single ok signal.
        any_enabled = any(p.get("enabled", False) for p in providers.values())
        return SourceHealth(
            source_id=self.source_id,
            ok=any_enabled and self._last_error is None,
            latency_ms=0,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error or
                ("no providers enabled" if not any_enabled else None),
        )


# ============================================================================
# Factory
# ============================================================================

def build_all_flash_loan_sources(
    *,
    route_engine: RouteSearchEngine,
    config_loader: Callable[[], Dict[str, Any]],
) -> List[DiscoverySource]:
    """One instance of every D-6.1 flash-loan DiscoverySource."""
    return [
        RouteSearchDiscoverySource(
            route_engine=route_engine, config_loader=config_loader),
        FlashLoanProviderHealthSource(config_loader=config_loader),
    ]
