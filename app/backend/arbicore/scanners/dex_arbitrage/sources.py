"""ArbiCore X — Phase D D-3.1 DEX pool discovery sources.

Each source class subclasses DiscoverySource. Sources poll a per-DEX hint
provider (subgraph / DexScreener pair-state proxy / aggregator) for a
mid-price on each configured pair, push into a shared DEXQuoteCache, and
emit a DiscoveryCandidate when cross-DEX cross-chain mid divergence
exceeds a configurable threshold.

INV-1 preserved: every source returns ``List[DiscoveryCandidate]`` only.
Sources never drive the EmissionBus emit method — that's the scanner's job
(D-3.4). INV-3 preserved: sources tag candidates with provenance_of_hint
matching the SOURCE_REGISTRY entry that classified them. The verifier
(D-3.2) will re-derive provenance from the per-leg on-chain quoter, not
from any hint.

Live integration — subgraph / DexScreener proxy HTTP calls — lands in
D-3.6 when an API key is wired. D-3.1 ships graceful-disable stubs that
respect the same `credentials_available` discipline as the quoter layer.
Source.discover() returns [] cleanly when credentials are missing, with
SourceHealth.last_error reflecting the disable reason.
"""
from __future__ import annotations

import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

from ...models.discovery import DiscoveryCandidate, SourceHealth, make_candidate_id
from ...models.enums import DataProvenance, OpportunityType
from ..discovery_source import DiscoverySource
from .quote_cache import DEXQuoteCache

logger = logging.getLogger("arbicore.scanners.dex_arb.sources")


# ============================================================================
# Base class for per-DEX × chain pool sources
# ============================================================================

class BaseDEXPoolSource(DiscoverySource, ABC):
    """Common pool-state poller shared by all D-3 venue sources.

    Subclasses MUST set ``dex`` and ``chain`` (class-level) and implement
    ``_poll_pool_mids(active_pairs)`` returning a list of
    ``(pair_canonical, mid, pool_liquidity_usd, pool_address)`` tuples.

    Graceful disable: if the source's ``credentials_env_var`` is non-empty
    but absent from os.environ, discover() returns [] without touching the
    network and health() reports ok=False with reason='credentials_missing'.
    """

    dex: str = ""
    chain: str = ""
    credentials_env_var: Optional[str] = None
    provenance_of_hint = DataProvenance.REAL
    opportunity_types: Set[OpportunityType] = {OpportunityType.DEX_ARBITRAGE}
    cadence_s = 60
    tier = 1
    pool_divergence_threshold_bps_default = 30.0

    def __init__(self, *, quote_cache: DEXQuoteCache,
                 config_loader: Callable[[], Dict[str, Any]]) -> None:
        if not self.dex or not self.chain:
            raise TypeError(
                f"{type(self).__name__} must set dex and chain at class scope"
            )
        # source_id format mirrors D-1: "venue_dex_pool:<dex>:<chain>"
        self.source_id = f"venue_dex_pool:{self.dex}:{self.chain}"
        # SOURCE_REGISTRY id for INV-3 attribution — verifier reads this
        # when re-deriving CanonicalOpportunity.source_data_quality.
        self.registry_source_id = f"{self.dex}_quoter_{self.chain}"
        self._quote_cache = quote_cache
        self._config_loader = config_loader
        self._client = httpx.AsyncClient(timeout=10.0)
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms: int = 0

    # ----- public DiscoverySource API --------------------------------------

    @property
    def credentials_available(self) -> bool:
        if not self.credentials_env_var:
            return True
        return bool(os.environ.get(self.credentials_env_var, "").strip())

    async def close(self) -> None:
        await self._client.aclose()

    async def discover(self) -> List[DiscoveryCandidate]:
        """Poll, update cache, emit DiscoveryCandidate per divergent pool."""
        if not self.credentials_available:
            self._last_error = f"credentials_missing:{self.credentials_env_var}"
            return []
        cfg = self._config_loader() or {}
        active_pairs = self._active_pairs_for_self(cfg)
        if not active_pairs:
            return []
        t0 = time.time()
        try:
            observations = await self._poll_pool_mids(active_pairs)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_latency_ms = int((time.time() - t0) * 1000)
            return []
        self._last_latency_ms = int((time.time() - t0) * 1000)
        self._last_error = None
        if not observations:
            return []
        # Update shared cache with this source's observations
        for obs in observations:
            self._quote_cache.put(
                chain=self.chain, dex=self.dex,
                pair_canonical=obs["pair_canonical"],
                mid=obs["mid"],
                pool_liquidity_usd=obs.get("pool_liquidity_usd"),
                source_id=self.registry_source_id,
            )
        # Build candidates per pair whose divergence exceeds threshold
        out: List[DiscoveryCandidate] = []
        threshold_bps = self._divergence_threshold_bps(cfg)
        now = time.time()
        for obs in observations:
            pair_canonical = obs["pair_canonical"]
            div = self._quote_cache.divergence_bps(
                chain=self.chain, dex=self.dex, pair_canonical=pair_canonical,
            )
            if div is None or abs(div) < threshold_bps:
                continue
            # Refuse to emit a candidate if we're the only observer
            if len(self._quote_cache.quotes_for(pair_canonical=pair_canonical)) < 2:
                continue
            venues = sorted({
                f"{cq.dex}:{cq.chain}"
                for cq in self._quote_cache.quotes_for(pair_canonical=pair_canonical)
            })
            candidate_id = make_candidate_id(
                hint_source=self.source_id,
                opportunity_type=OpportunityType.DEX_ARBITRAGE,
                subject_id=pair_canonical,
                asset=pair_canonical.split("/")[0],
                candidate_venues=venues,
                hint_observed_at=now,
            )
            out.append(DiscoveryCandidate(
                candidate_id=candidate_id,
                opportunity_type=OpportunityType.DEX_ARBITRAGE,
                hint_source=self.source_id,
                hint_observed_at=now,
                subject_id=pair_canonical,
                asset=pair_canonical.split("/")[0],
                candidate_venues=venues,
                hint_metric={
                    "divergence_bps": float(div),
                    "self_mid": obs["mid"],
                    "reference_mid": self._quote_cache.reference_mid(
                        pair_canonical=pair_canonical),
                    "pool_address": obs.get("pool_address"),
                    "pool_liquidity_usd": obs.get("pool_liquidity_usd"),
                    "self_chain": self.chain,
                    "self_dex": self.dex,
                },
                reason=f"pool_divergence:{abs(div):.1f}bps@{self.dex}:{self.chain}",
            ))
        if out:
            self._last_emission_at = now
        return out

    async def health(self) -> SourceHealth:
        ok = self._last_error is None and self.credentials_available
        last_error = self._last_error
        if not self.credentials_available and last_error is None:
            last_error = f"credentials_missing:{self.credentials_env_var}"
        return SourceHealth(
            source_id=self.source_id,
            ok=ok,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=last_error,
        )

    # ----- helpers ----------------------------------------------------------

    def _active_pairs_for_self(self, cfg: Dict[str, Any]) -> List[str]:
        """Filter the scanner-config pair universe down to pairs whose
        chain qualifier matches our chain. Pairs are stored canonically as
        ``BASE/QUOTE@CHAIN`` (see DEFAULT_DEX_ARB_CONFIG.tier_a_pairs)."""
        tier_a = cfg.get("tier_a_pairs", []) or []
        tier_b = cfg.get("tier_b_pairs", []) or []
        pairs = tier_a + tier_b
        suffix = f"@{self.chain}"
        return [p for p in pairs if p.endswith(suffix)]

    def _divergence_threshold_bps(self, cfg: Dict[str, Any]) -> float:
        per_source = (cfg.get("discovery_sources") or {}).get(self.source_id, {})
        return float(per_source.get(
            "pool_divergence_threshold_bps",
            self.pool_divergence_threshold_bps_default,
        ))

    # ----- subclass contract -----------------------------------------------

    @abstractmethod
    async def _poll_pool_mids(self, active_pairs: List[str]
                              ) -> List[Dict[str, Any]]:
        """Return [{pair_canonical, mid, pool_liquidity_usd?, pool_address?}, ...].

        Subclasses implement live integration here. Live wiring lands in
        D-3.6. For D-3.1 each concrete subclass returns [] (graceful-disable
        when credentials_env_var unset; otherwise stub-empty).
        """


# ============================================================================
# Concrete EVM V3 sources (Uniswap V3 / PancakeSwap V3 / Aerodrome)
# ============================================================================

class _EVMV3PoolSourceBase(BaseDEXPoolSource):
    """Common stub poller for the seven EVM V3 sources.

    D-3.1 keeps _poll_pool_mids returning [] — the live subgraph wiring
    lands at D-3.6. Until then sources are inert and graceful-disabled.
    All other behaviour (divergence-vs-reference math, candidate shape,
    SourceHealth, INV-1 typing) is fully exercised by tests today.
    """

    credentials_env_var = "GRAPH_GATEWAY_API_KEY"

    async def _poll_pool_mids(self, active_pairs: List[str]
                              ) -> List[Dict[str, Any]]:
        # D-3.6 will wire The Graph gateway subgraph queries per DEX.
        # The contract is honoured here so that downstream divergence
        # math, candidate emission, and INV-1 typing are testable today.
        return []


class UniswapV3PoolSource(_EVMV3PoolSourceBase):
    dex = "uniswap_v3"

    def __init__(self, *, chain: str, **kwargs: Any) -> None:
        self.chain = chain
        super().__init__(**kwargs)


class PancakeV3PoolSource(_EVMV3PoolSourceBase):
    dex = "pancake_v3"

    def __init__(self, *, chain: str, **kwargs: Any) -> None:
        self.chain = chain
        super().__init__(**kwargs)


class AerodromePoolSource(_EVMV3PoolSourceBase):
    dex = "aerodrome"
    chain = "base"
    # Aerodrome ships with a heritage REAL DexScreener-proxy entry — no
    # Graph gateway key required. Override credentials_env_var to None
    # so the source is graceful-disable-free at D-3.1.
    credentials_env_var = None

    async def _poll_pool_mids(self, active_pairs: List[str]
                              ) -> List[Dict[str, Any]]:
        # D-3.6 will wire DexScreener pair-state proxy here. Stub returns [].
        return []


# ============================================================================
# Solana / Raydium source
# ============================================================================

class RaydiumPoolSource(BaseDEXPoolSource):
    dex = "raydium"
    chain = "solana"
    credentials_env_var = "HELIUS_API_KEY"
    # Solana pools tend to drift wider before arb closes; bump default.
    pool_divergence_threshold_bps_default = 50.0

    async def _poll_pool_mids(self, active_pairs: List[str]
                              ) -> List[Dict[str, Any]]:
        # D-3.6 will wire Helius getMultipleAccounts pool-state reads here.
        return []


# ============================================================================
# Factory
# ============================================================================

def build_all_dex_sources(*, quote_cache: DEXQuoteCache,
                          config_loader: Callable[[], Dict[str, Any]],
                          ) -> List[BaseDEXPoolSource]:
    """Instantiate the full D-3 venue-tier source universe (8 sources):

      Uniswap V3 on ethereum, arbitrum, base                  (3)
      PancakeSwap V3 on bnb, arbitrum, base                   (3)
      Aerodrome on base                                       (1)
      Raydium on solana                                       (1)

    Each source is independently graceful-disabled when its
    credentials_env_var is missing. The DexScreener aggregator HINT source
    is registered separately by build_aggregator_hint_sources()
    (see arbicore.scanners.discovery.dexscreener_hint).
    """
    out: List[BaseDEXPoolSource] = []
    for chain in ("ethereum", "arbitrum", "base"):
        out.append(UniswapV3PoolSource(
            chain=chain, quote_cache=quote_cache, config_loader=config_loader,
        ))
    for chain in ("bnb", "arbitrum", "base"):
        out.append(PancakeV3PoolSource(
            chain=chain, quote_cache=quote_cache, config_loader=config_loader,
        ))
    out.append(AerodromePoolSource(
        quote_cache=quote_cache, config_loader=config_loader,
    ))
    out.append(RaydiumPoolSource(
        quote_cache=quote_cache, config_loader=config_loader,
    ))
    return out
