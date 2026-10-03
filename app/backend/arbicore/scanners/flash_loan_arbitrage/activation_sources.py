"""M5 Canonical Activation — DiscoverySources for GENERIC_DEX / Triangular /
Balancer P1+P1b.

INV-1: emit ``DiscoveryCandidate`` only (never CanonicalOpportunity).
INV-2: no EmissionBus; candidates feed FlashLoanArbitrageScanner → verifier →
       sole ``_tick`` emit site.
INV-3: REAL provenance for on-chain / configured sources.

All sources are dormant unless scanner_config enables the relevant chains +
flash-loan providers (same gate as RouteSearchDiscoverySource). Optional
per-source toggles live under ``discovery_sources.<id>.enabled`` (default True
once wired — chains/providers remain the capacity control).
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from ...models.discovery import (
    DiscoveryCandidate, SourceHealth, make_candidate_id,
)
from ...models.enums import DataProvenance, OpportunityType
from ...chains.registries import probe_amount_wei, tokens_for
from ..discovery_source import DiscoverySource
from .economics import providers_for_chain
from .route_search import PoolNode, RouteSearchEngine
from .triangular import enumerate_cycles

logger = logging.getLogger(
    "arbicore.scanners.flash_loan_arbitrage.activation_sources")

_IN_SCOPE_CHAINS = frozenset({
    "ethereum", "arbitrum", "base", "optimism", "polygon", "bnb",
})
_DEFAULT_BORROW = ("USDC", "USDT", "WETH", "DAI")
_DEFAULT_INTERMEDIATES = ("USDC", "USDT", "WETH", "DAI", "WBTC", "ARB", "OP")


def _now() -> float:
    return time.time()


def _ds_enabled(cfg: Dict[str, Any], key: str, *, default: bool = True) -> bool:
    block = (cfg.get("discovery_sources") or {}).get(key) or {}
    return bool(block.get("enabled", default))


def _enabled_chains_providers(cfg: Dict[str, Any]
                              ) -> Tuple[List[str], List[str]]:
    chains_cfg = cfg.get("chains") or {}
    providers_cfg = cfg.get("providers") or {}
    enabled_chains = [c for c, v in chains_cfg.items()
                      if (v or {}).get("enabled", False)
                      and c in _IN_SCOPE_CHAINS]
    enabled_providers = [p for p, v in providers_cfg.items()
                         if (v or {}).get("enabled", False)]
    return enabled_chains, enabled_providers


def _fee_ppm(pool: PoolNode) -> int:
    tail = str(pool.pool_address).rsplit(":", 1)[-1]
    try:
        return int(tail)
    except (TypeError, ValueError):
        return int(pool.fee_bps) * 100


def _hop_from_pool(pool: PoolNode, token_in: str, token_out: str
                   ) -> Dict[str, Any]:
    h: Dict[str, Any] = {
        "dex": pool.dex_protocol,
        "token_in": token_in,
        "token_out": token_out,
        "fee": _fee_ppm(pool),
        "pool": pool.pool_address,
        "fee_bps": int(pool.fee_bps),
    }
    return h


def _candidate(
    *,
    source_id: str,
    provider: str,
    chain: str,
    borrow_token: str,
    route_id: str,
    venues: List[str],
    hint_metric: Dict[str, Any],
    reason: str,
) -> DiscoveryCandidate:
    subject = f"flash_loan:{provider}:{chain}:{borrow_token}:{route_id}"
    observed = _now()
    cid = make_candidate_id(
        hint_source=source_id,
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        subject_id=subject, asset=borrow_token,
        candidate_venues=venues, hint_observed_at=observed,
    )
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
        hint_source=source_id,
        hint_observed_at=observed,
        subject_id=subject,
        asset=borrow_token,
        candidate_venues=venues,
        hint_metric=hint_metric,
        reason=reason,
    )


def _pick_quotable_pool(
    chain: str,
    cands: List[PoolNode],
    predicate: Callable[[str, PoolNode], bool],
) -> Optional[PoolNode]:
    """Smallest pool id among hops the predicate accepts.

    Alphabetical order is kept, but only after incapable DEXes are removed.
    An empty capable set returns None so the cycle is not emitted.
    """
    capable = [p for p in cands if predicate(chain, p)]
    if not capable:
        return None
    return min(capable, key=lambda p: p.pool_address)


def _attach_probe(chain: str, borrow_token: str,
                  hint_metric: Dict[str, Any]) -> None:
    amt = probe_amount_wei(chain, borrow_token)
    if amt is not None:
        hint_metric["borrow_amount_wei"] = int(amt)
        hint_metric["borrow_amount_provenance"] = "deterministic_probe"


# ============================================================================
# GENERIC_DEX — 2-venue cross-DEX cycles from the pool graph
# ============================================================================

class GenericDexDiscoverySource(DiscoverySource):
    """Emits 2-hop cross-venue cycles (buy venue A / sell venue B).

    Reuses ``RouteSearchEngine`` inventory; does NOT call
    ``GenericDexRouteEngine.evaluate_route`` (economics stay in the verifier
    + Gate 7 at $25). No EmissionBus.
    """

    source_id = "flash_loan_generic_dex"
    cadence_s = 60
    opportunity_types: Set[OpportunityType] = {
        OpportunityType.FLASH_LOAN_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None

    def __init__(
        self,
        *,
        route_engine: RouteSearchEngine,
        config_loader: Callable[[], Dict[str, Any]],
        borrow_token_set: Optional[List[str]] = None,
    ) -> None:
        self._engine = route_engine
        self._cfg = config_loader
        self._borrow_tokens = list(borrow_token_set or _DEFAULT_BORROW)
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._cfg() or {}
        if not _ds_enabled(cfg, "generic_dex"):
            return []
        enabled_chains, enabled_providers = _enabled_chains_providers(cfg)
        if not enabled_chains or not enabled_providers:
            return []
        t0 = _now()
        out: List[DiscoveryCandidate] = []
        for chain in enabled_chains:
            for borrow in self._borrow_tokens:
                try:
                    cycles = self._engine.search(
                        chain=chain, borrow_token=borrow)
                except Exception as exc:  # noqa: BLE001
                    self._last_error = (
                        f"generic_dex[{chain}:{borrow}]: "
                        f"{type(exc).__name__}: {exc}")
                    continue
                for cycle in cycles:
                    if cycle.hop_count != 2:
                        continue
                    dexes = [p.dex_protocol for p in cycle.pools]
                    # Cross-venue (or distinct fee-tier venues) GENERIC_DEX shape.
                    if len(set(dexes)) < 2 and len(set(
                            p.pool_address for p in cycle.pools)) < 2:
                        continue
                    pred = getattr(self._engine, "hop_predicate", None)
                    if pred is not None and not all(
                            pred(chain, p) for p in cycle.pools):
                        continue
                    hops = [
                        _hop_from_pool(cycle.pools[i],
                                       cycle.token_path[i],
                                       cycle.token_path[i + 1])
                        for i in range(2)
                    ]
                    for provider in providers_for_chain(chain, enabled_providers):
                        hm: Dict[str, Any] = {
                            "chain": chain,
                            "provider": provider,
                            "borrow_token": cycle.borrow_token,
                            "hop_count": 2,
                            "min_tvl_usd": cycle.min_tvl_usd,
                            "estimated_total_fee_pct":
                                cycle.estimated_total_fee_pct,
                            "route_pools": [p.pool_address for p in cycle.pools],
                            "route_dex_protocols": dexes,
                            "cycle_token_path": list(cycle.token_path),
                            "route_hops": hops,
                            "strategy_hint": "GENERIC_DEX",
                            "activation_source": self.source_id,
                        }
                        _attach_probe(chain, cycle.borrow_token, hm)
                        out.append(_candidate(
                            source_id=self.source_id, provider=provider,
                            chain=chain, borrow_token=cycle.borrow_token,
                            route_id=f"gdx:{cycle.route_id}",
                            venues=[p.pool_address for p in cycle.pools],
                            hint_metric=hm,
                            reason=f"{self.source_id}:{cycle.route_id}",
                        ))
        self._last_latency_ms = int((_now() - t0) * 1000)
        if out:
            self._last_emission_at = _now()
        return out

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )


# ============================================================================
# Triangular — A→B→C→A DiscoveryCandidates (Gate 7 authoritative)
# ============================================================================

class TriangularDiscoverySource(DiscoverySource):
    """Enumerates triangular cycles and emits DiscoveryCandidates.

    Uses ``enumerate_cycles`` only — does NOT apply the library
    ``discover_triangular`` profit prefilter / ``emit_flash_candidate`` path.
    Canonical Gate 7 ($25) remains authoritative in the verifier.
    """

    source_id = "flash_loan_triangular"
    cadence_s = 60
    opportunity_types: Set[OpportunityType] = {
        OpportunityType.FLASH_LOAN_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None

    def __init__(
        self,
        *,
        route_engine: RouteSearchEngine,
        config_loader: Callable[[], Dict[str, Any]],
        borrow_token_set: Optional[List[str]] = None,
        intermediates: Optional[List[str]] = None,
        hop_predicate: Optional[Callable[[str, PoolNode], bool]] = None,
    ) -> None:
        self._engine = route_engine
        self._cfg = config_loader
        self._borrow_tokens = list(borrow_token_set or _DEFAULT_BORROW)
        self._intermediates = list(intermediates or _DEFAULT_INTERMEDIATES)
        self._hop_predicate = hop_predicate
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def _predicate(self):
        if self._hop_predicate is not None:
            return self._hop_predicate
        from .live_quote_provider import hop_quote_capable
        return hop_quote_capable

    def _pools_for_leg(self, pools: List[PoolNode], a: str, b: str
                       ) -> List[PoolNode]:
        a_u, b_u = a.upper(), b.upper()
        return [p for p in pools
                if {p.token_a.upper(), p.token_b.upper()} == {a_u, b_u}]

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._cfg() or {}
        if not _ds_enabled(cfg, "triangular"):
            return []
        enabled_chains, enabled_providers = _enabled_chains_providers(cfg)
        if not enabled_chains or not enabled_providers:
            return []
        t0 = _now()
        out: List[DiscoveryCandidate] = []
        loader = self._engine._pool_loader
        for chain in enabled_chains:
            try:
                pools = list(loader(chain) or [])
            except Exception as exc:  # noqa: BLE001
                self._last_error = (
                    f"triangular_pools[{chain}]: {type(exc).__name__}: {exc}")
                continue
            if not pools:
                continue
            present = {p.token_a.upper() for p in pools} | {
                p.token_b.upper() for p in pools}
            for base in self._borrow_tokens:
                if base.upper() not in present:
                    continue
                inter = [t for t in self._intermediates
                         if t.upper() != base.upper() and t.upper() in present]
                for cyc in enumerate_cycles(base, inter):
                    # cyc = (A, B, C, A)
                    legs = [(cyc[0], cyc[1]), (cyc[1], cyc[2]), (cyc[2], cyc[3])]
                    leg_pools: List[Optional[PoolNode]] = []
                    ok = True
                    for a, b in legs:
                        cands = self._pools_for_leg(pools, a, b)
                        chosen_leg = _pick_quotable_pool(
                            chain, cands, self._predicate())
                        if chosen_leg is None:
                            ok = False
                            break
                        leg_pools.append(chosen_leg)
                    if not ok or any(p is None for p in leg_pools):
                        continue
                    chosen: List[PoolNode] = [p for p in leg_pools if p]
                    hops = [
                        _hop_from_pool(chosen[i], legs[i][0], legs[i][1])
                        for i in range(3)
                    ]
                    venues = [p.pool_address for p in chosen]
                    route_id = f"tri:{chain}:{':'.join(cyc)}:{':'.join(venues)}"
                    for provider in providers_for_chain(chain, enabled_providers):
                        hm: Dict[str, Any] = {
                            "chain": chain,
                            "provider": provider,
                            "borrow_token": base.upper(),
                            "hop_count": 3,
                            "min_tvl_usd": min(p.tvl_usd for p in chosen),
                            "estimated_total_fee_pct":
                                sum(p.fee_bps for p in chosen) / 100.0,
                            "route_pools": venues,
                            "route_dex_protocols": [
                                p.dex_protocol for p in chosen],
                            "cycle_token_path": list(cyc),
                            "route_hops": hops,
                            "strategy_hint": "TRIANGULAR",
                            "activation_source": self.source_id,
                            # Gate 7 ($25) is authoritative — no library $35
                            # prefilter on this DiscoverySource path.
                            "canonical_gate7_floor_usd": 25.0,
                        }
                        _attach_probe(chain, base.upper(), hm)
                        out.append(_candidate(
                            source_id=self.source_id, provider=provider,
                            chain=chain, borrow_token=base.upper(),
                            route_id=route_id, venues=venues, hint_metric=hm,
                            reason=f"{self.source_id}:{route_id}",
                        ))
        self._last_latency_ms = int((_now() - t0) * 1000)
        if out:
            self._last_emission_at = _now()
        return out

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )


# ============================================================================
# Balancer P1 (subgraph) + P1b (on-chain PoolRegistered)
# ============================================================================

class BalancerV2DiscoverySource(DiscoverySource):
    """Injects Balancer V2 pool identities into the canonical discovery path.

    * P1 subgraph: config-aware fail-closed when
      ``ARBICORE_BALANCER_SUBGRAPH_URL_<CHAIN>`` is absent
      (``DISCOVERY_UNAVAILABLE`` → no fabricated pools).
    * P1b on-chain: uses injected / registry-failover ``eth_getLogs``; transport
      failures remain ``DISCOVERY_UNAVAILABLE`` (preserve fail-closed).

    Candidates are paired with a complementary UniV3 (or other) venue from the
    pool graph when available so the verifier can quote a closed 2-hop cycle
    via existing ``BalancerV2Quoter`` + UniV3 backends. No new EmissionBus site.
    """

    source_id = "flash_loan_balancer_v2"
    cadence_s = 120
    opportunity_types: Set[OpportunityType] = {
        OpportunityType.FLASH_LOAN_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None

    def __init__(
        self,
        *,
        route_engine: RouteSearchEngine,
        config_loader: Callable[[], Dict[str, Any]],
        borrow_token_set: Optional[List[str]] = None,
        intermediates: Optional[List[str]] = None,
        eth_get_logs_factory: Optional[Callable[[str], Optional[Any]]] = None,
        subgraph_source: Optional[Any] = None,
        onchain_source_factory: Optional[Callable[..., Any]] = None,
        max_pools_per_pair: int = 4,
    ) -> None:
        self._engine = route_engine
        self._cfg = config_loader
        self._borrow_tokens = list(borrow_token_set or _DEFAULT_BORROW)
        self._intermediates = list(intermediates or ("WETH", "USDC", "USDT"))
        self._eth_get_logs_factory = eth_get_logs_factory
        self._subgraph = subgraph_source
        self._onchain_factory = onchain_source_factory
        self._max_pools = max(1, int(max_pools_per_pair))
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return True

    async def close(self) -> None:
        return None

    def _ensure_subgraph(self):
        if self._subgraph is not None:
            return self._subgraph
        from ...discovery.balancer_v2_pool_enumeration import (
            SubgraphBalancerV2PoolSource)
        self._subgraph = SubgraphBalancerV2PoolSource()
        return self._subgraph

    def _onchain_for(self, chain: str):
        from ...discovery.balancer_v2_onchain_source import (
            OnChainPoolRegisteredSource)
        get_logs = None
        block_fn = None
        if self._eth_get_logs_factory is not None:
            get_logs = self._eth_get_logs_factory(chain)
            if get_logs is not None:
                block_fn = getattr(get_logs, "eth_block_number", None)
        if self._onchain_factory is not None:
            return self._onchain_factory(
                eth_get_logs_fn=get_logs, eth_block_number_fn=block_fn)
        return OnChainPoolRegisteredSource(
            eth_get_logs_fn=get_logs, eth_block_number_fn=block_fn)

    def _token_addr(self, chain: str, sym: str) -> Optional[str]:
        toks = tokens_for(chain) or {}
        t = toks.get(sym.upper())
        return t.get("address") if t else None

    def _complement_venue(self, chain: str, pools: List[PoolNode],
                          a: str, b: str) -> Optional[PoolNode]:
        a_u, b_u = a.upper(), b.upper()
        cands = [p for p in pools
                 if {p.token_a.upper(), p.token_b.upper()} == {a_u, b_u}
                 and str(p.dex_protocol).lower() != "balancer_v2"]
        from .live_quote_provider import hop_quote_capable
        return _pick_quotable_pool(chain, cands, hop_quote_capable)

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._cfg() or {}
        if not _ds_enabled(cfg, "balancer_v2"):
            return []
        enabled_chains, enabled_providers = _enabled_chains_providers(cfg)
        if not enabled_chains or not enabled_providers:
            return []
        from ...discovery.balancer_v2_pool_discovery import (
            BALANCER_V2_VAULT_BY_CHAIN)
        from ...discovery.balancer_v2_pool_enumeration import (
            SRC_DISCOVERY_UNAVAILABLE, SRC_OK, SRC_UNSUPPORTED_CHAIN)

        t0 = _now()
        out: List[DiscoveryCandidate] = []
        errors: List[str] = []
        loader = self._engine._pool_loader
        subgraph = self._ensure_subgraph()

        for chain in enabled_chains:
            if chain not in BALANCER_V2_VAULT_BY_CHAIN:
                continue
            try:
                graph_pools = list(loader(chain) or [])
            except Exception as exc:  # noqa: BLE001
                errors.append(f"pools[{chain}]: {type(exc).__name__}")
                graph_pools = []

            pairs: List[Tuple[str, str]] = []
            for bt in self._borrow_tokens:
                for it in self._intermediates:
                    if bt.upper() == it.upper():
                        continue
                    if self._token_addr(chain, bt) and self._token_addr(chain, it):
                        pairs.append((bt.upper(), it.upper()))

            for token_a, token_b in pairs:
                addr_a = self._token_addr(chain, token_a)
                addr_b = self._token_addr(chain, token_b)
                if not addr_a or not addr_b:
                    continue
                bal_cands = []
                # P1 subgraph — fail-closed when URL absent.
                try:
                    src_res = await subgraph.find_pools(chain, addr_a, addr_b)
                except Exception as exc:  # noqa: BLE001
                    src_res = None
                    errors.append(
                        f"subgraph[{chain}]: {type(exc).__name__}: {exc}")
                if src_res is not None:
                    if src_res.status == SRC_DISCOVERY_UNAVAILABLE:
                        errors.append(
                            f"subgraph[{chain}]: {src_res.error or 'unavailable'}")
                    elif src_res.status == SRC_OK:
                        bal_cands.extend(list(src_res.candidates or []))
                    elif src_res.status == SRC_UNSUPPORTED_CHAIN:
                        pass

                # P1b on-chain — fail-closed on getLogs infra errors.
                try:
                    onchain = self._onchain_for(chain)
                    oc_res = await onchain.find_pools(chain, addr_a, addr_b)
                except Exception as exc:  # noqa: BLE001
                    oc_res = None
                    errors.append(
                        f"onchain[{chain}]: {type(exc).__name__}: {exc}")
                if oc_res is not None:
                    if oc_res.status == SRC_DISCOVERY_UNAVAILABLE:
                        errors.append(
                            f"onchain[{chain}]: {oc_res.error or 'unavailable'}")
                    elif oc_res.status == SRC_OK:
                        bal_cands.extend(list(oc_res.candidates or []))

                if not bal_cands:
                    continue
                complement = self._complement_venue(
                    chain, graph_pools, token_a, token_b)
                if complement is None:
                    # No second venue → cannot form a closed flash cycle; skip
                    # (do not fabricate a complementary pool).
                    continue

                seen = set()
                for cand in bal_cands:
                    key = cand.identity_key()
                    if not key or key in seen:
                        continue
                    seen.add(key)
                    if len(seen) > self._max_pools:
                        break
                    if not (cand.pool_id or cand.pool_address):
                        continue  # never fabricate identity
                    bal_hop_fwd = {
                        "dex": "balancer_v2",
                        "token_in": token_a,
                        "token_out": token_b,
                        "pool_id": cand.pool_id,
                        "pool_address": cand.pool_address,
                        "fee_bps": 0,
                    }
                    univ_hop_back = _hop_from_pool(
                        complement, token_b, token_a)
                    venues = [
                        cand.pool_id or cand.pool_address or "balancer",
                        complement.pool_address,
                    ]
                    route_id = (
                        f"bal:{chain}:{token_a}:{token_b}:"
                        f"{cand.pool_id or cand.pool_address}:"
                        f"{complement.pool_address}")
                    for provider in providers_for_chain(chain, enabled_providers):
                        hm: Dict[str, Any] = {
                            "chain": chain,
                            "provider": provider,
                            "borrow_token": token_a,
                            "hop_count": 2,
                            "min_tvl_usd": float(complement.tvl_usd or 0.0),
                            "estimated_total_fee_pct":
                                float(complement.fee_bps) / 100.0,
                            "route_pools": venues,
                            "route_dex_protocols": [
                                "balancer_v2", complement.dex_protocol],
                            "cycle_token_path": [token_a, token_b, token_a],
                            "route_hops": [bal_hop_fwd, univ_hop_back],
                            "strategy_hint": "GENERIC_DEX",
                            "activation_source": self.source_id,
                            "balancer_source": cand.source,
                        }
                        _attach_probe(chain, token_a, hm)
                        out.append(_candidate(
                            source_id=self.source_id, provider=provider,
                            chain=chain, borrow_token=token_a,
                            route_id=route_id, venues=venues, hint_metric=hm,
                            reason=f"{self.source_id}:{route_id}",
                        ))

        self._last_latency_ms = int((_now() - t0) * 1000)
        if errors:
            # Keep the most recent / informative error for health — fail-closed
            # posture is preserved (we may still emit candidates from other
            # chains that succeeded).
            self._last_error = errors[-1][:300]
        else:
            self._last_error = None
        if out:
            self._last_emission_at = _now()
        return out

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )


__all__ = [
    "GenericDexDiscoverySource",
    "TriangularDiscoverySource",
    "BalancerV2DiscoverySource",
]
