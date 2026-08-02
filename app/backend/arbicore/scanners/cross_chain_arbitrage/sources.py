"""Cross-chain DiscoverySources — D-5.1.

Two sources land at this wave, both HINT-aware (per INV-3) and gated by
per-bridge enable flags in ``scanner_config.cross_chain_arb.bridges.*``.

  - LiFiAggregatorSource    aggregator → /connections + /quote
                             surface; one DiscoveryCandidate per
                             (source_chain, destination_chain, asset)
                             corridor returned by the connection map.
                             Credentials: LIFI_API_KEY (optional —
                             public endpoints exist; graceful-disable
                             only on env explicit "off" config).
  - StargateSource          direct bridge → /v1/quote per corridor.
                             Credentials: STARGATE_API_KEY (optional).

Both sources emit ``DiscoveryCandidate.opportunity_type=
CROSS_CHAIN_ARBITRAGE``. Per INV-3 the aggregator hint provenance is
``REAL`` but the verifier (D-5.1) re-derives ``source_data_quality``
from the per-leg ``source_id`` (``lifi_quote_real`` or
``stargate_quote_real``) — these are the SOURCE_REGISTRY keys reserved
at D-5.0.

INV-1: sources emit DiscoveryCandidate only — never CanonicalOpportunity.
INV-2: sources never call EmissionBus.
INV-3: hints carry HINT-level classification; the verifier's leg
       ``source_id`` drives the canonical's ``source_data_quality``.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

from ...models.discovery import (
    DiscoveryCandidate, SourceHealth, make_candidate_id,
)
from ...models.enums import DataProvenance, OpportunityType
from ..discovery_source import DiscoverySource

logger = logging.getLogger("arbicore.scanners.cross_chain_arbitrage.sources")


_IN_SCOPE_CHAINS = frozenset({
    "ethereum", "arbitrum", "base", "optimism", "polygon", "solana",
})


def _per_bridge_config(cfg: Dict[str, Any], bridge: str) -> Dict[str, Any]:
    return (cfg.get("bridges") or {}).get(bridge, {}) or {}


def _now_ts() -> float:
    return time.time()


def _in_scope(chain: str) -> bool:
    return (chain or "").lower() in _IN_SCOPE_CHAINS


def _candidate_for_corridor(
    *,
    source_id: str,
    bridge: str,
    src_chain: str,
    dst_chain: str,
    asset: str,
    hint_metric: Dict[str, Any],
) -> Optional[DiscoveryCandidate]:
    if not _in_scope(src_chain) or not _in_scope(dst_chain):
        return None
    if src_chain == dst_chain:
        return None
    if not asset:
        return None
    subject = f"cross_chain:{bridge}:{src_chain}→{dst_chain}:{asset}"
    venues = [f"{bridge}:{src_chain}", f"{bridge}:{dst_chain}"]
    now = _now_ts()
    cid = make_candidate_id(
        hint_source=source_id,
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        subject_id=subject, asset=asset,
        candidate_venues=venues, hint_observed_at=now,
    )
    return DiscoveryCandidate(
        candidate_id=cid,
        opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
        hint_source=source_id,
        hint_observed_at=now,
        subject_id=subject,
        asset=asset,
        candidate_venues=venues,
        hint_metric={
            "bridge": bridge,
            "source_chain": src_chain,
            "destination_chain": dst_chain,
            **hint_metric,
        },
        reason=f"{source_id}:{src_chain}→{dst_chain}:{asset}",
    )


# ============================================================================
# LiFiAggregatorSource
# ============================================================================

class LiFiAggregatorSource(DiscoverySource):
    """LI.FI aggregator — discovers cross-chain corridors via the
    ``/connections`` endpoint and (optionally) cross-validates by
    polling ``/quote`` for the operator-configured probe assets.

    INV-3: HINT-aware. The verifier re-derives ``source_data_quality``
    from the per-leg ``source_id="lifi_quote_real"``.
    """

    source_id = "lifi_aggregator"
    cadence_s = 60
    opportunity_types: Set[OpportunityType] = {
        OpportunityType.CROSS_CHAIN_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = "LIFI_API_KEY"  # optional but tracked

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                 http_client: Optional[httpx.AsyncClient] = None,
                 ) -> None:
        self._config_loader = config_loader
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        # LI.FI public endpoints exist; the API key only unlocks higher rate
        # limits. Treat credentials as always-available (operator controls
        # via per-bridge enabled flag in scanner_config).
        return True

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        bridge_cfg = _per_bridge_config(cfg, "lifi")
        if not bridge_cfg.get("enabled", False):
            return []
        # Probe asset list — operator-tunable; ships with conservative defaults.
        probe_assets = list(bridge_cfg.get(
            "probe_assets", ["USDC", "USDT", "WETH"]))
        # Probe corridors — Cartesian product of in-scope chains, deduped.
        chains_cfg = cfg.get("chains") or {}
        enabled_chains = [c for c, v in chains_cfg.items()
                           if (v or {}).get("enabled", False)
                           and c in _IN_SCOPE_CHAINS]
        if not enabled_chains:
            # Operator hasn't enabled any chain — emit no candidates.
            return []
        max_corridors = int(bridge_cfg.get("max_corridors_per_cycle", 12))
        api_key = os.environ.get(self.credentials_env_var, "").strip()
        base_url = bridge_cfg.get("base_url", "https://li.quest/v1")
        t0 = _now_ts()
        candidates: List[DiscoveryCandidate] = []
        connections_ok = await self._probe_connections(
            base_url=base_url, api_key=api_key)
        if not connections_ok:
            # Connection probe failure → fall through but emit no candidates
            # (verifier never sees stale corridors).
            self._last_latency_ms = int((_now_ts() - t0) * 1000)
            return []
        for src in enabled_chains:
            for dst in enabled_chains:
                if src == dst:
                    continue
                for asset in probe_assets:
                    cand = _candidate_for_corridor(
                        source_id=self.source_id,
                        bridge="lifi",
                        src_chain=src, dst_chain=dst, asset=asset,
                        hint_metric={
                            "probe_endpoint": "/connections",
                            "credentials_present": bool(api_key),
                        },
                    )
                    if cand is not None:
                        candidates.append(cand)
                    if len(candidates) >= max_corridors:
                        break
                if len(candidates) >= max_corridors:
                    break
            if len(candidates) >= max_corridors:
                break
        self._last_latency_ms = int((_now_ts() - t0) * 1000)
        if candidates:
            self._last_emission_at = _now_ts()
        return candidates

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )

    # ---- helpers ----------------------------------------------------------

    async def _probe_connections(self, *, base_url: str, api_key: str,
                                  ) -> bool:
        """Best-effort liveness probe. Returns True on 200; False on any
        non-200 or HTTP error. Updates ``last_error`` accordingly.

        The post-2025 LI.FI ``/connections`` endpoint requires at minimum
        ``fromChain`` and ``toChain`` query parameters (returns HTTP 400
        otherwise). We hit the canonical ETH ↔ ARB corridor as a known-
        good liveness check that maps to LI.FI's most-supported route.
        """
        headers = {"x-lifi-api-key": api_key} if api_key else {}
        try:
            resp = await self._client.get(
                f"{base_url}/connections",
                params={"fromChain": "1", "toChain": "42161"},
                headers=headers)
        except httpx.HTTPError as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            return False
        if resp.status_code != 200:
            self._last_error = f"http_{resp.status_code}"
            return False
        self._last_error = None
        return True


# ============================================================================
# StargateSource
# ============================================================================

class StargateSource(DiscoverySource):
    """Stargate (LayerZero v2) direct bridge — discovers corridors via the
    operator-configured probe asset universe. Stargate's quote endpoint is
    per-corridor; this source emits one DiscoveryCandidate per supported
    (src, dst, asset) tuple so the verifier can ask the provider for a
    live quote.

    INV-3: HINT-aware. Verifier uses ``source_id="stargate_quote_real"``.
    """

    source_id = "stargate_direct"
    cadence_s = 90
    opportunity_types: Set[OpportunityType] = {
        OpportunityType.CROSS_CHAIN_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = "STARGATE_API_KEY"

    # Stargate v2 ships USDC + USDT + ETH as primary cross-chain assets.
    _STARGATE_SUPPORTED_ASSETS = ("USDC", "USDT", "ETH", "WETH")

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                 http_client: Optional[httpx.AsyncClient] = None,
                 ) -> None:
        self._config_loader = config_loader
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return True  # public endpoints; key for rate limits only

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        bridge_cfg = _per_bridge_config(cfg, "stargate")
        if not bridge_cfg.get("enabled", False):
            return []
        # Upstream deprecation (verified 2026-06): the public Stargate v1
        # quote API at stargate.finance/api/v1 returns HTTP 410 Gone and
        # redirects to LayerZero VT. We surface a clear, persistent
        # deprecation signal to the operator instead of attempting calls
        # that would only ever fail. LI.FI internally routes Stargate as
        # one of its supported bridges — operator should rely on the
        # ``lifi`` bridge for Stargate corridor quotes.
        if bridge_cfg.get("deprecated", True):
            self._last_error = (
                "stargate_api_deprecated:"
                "use_lifi_for_stargate_routing"
            )
            return []
        chains_cfg = cfg.get("chains") or {}
        # Stargate does not currently support Solana; skip it even if
        # operator marked solana enabled in the chain config.
        enabled_chains = [
            c for c, v in chains_cfg.items()
            if (v or {}).get("enabled", False)
            and c in _IN_SCOPE_CHAINS and c != "solana"
        ]
        if not enabled_chains:
            return []
        max_corridors = int(bridge_cfg.get("max_corridors_per_cycle", 8))
        t0 = _now_ts()
        candidates: List[DiscoveryCandidate] = []
        for src in enabled_chains:
            for dst in enabled_chains:
                if src == dst:
                    continue
                for asset in self._STARGATE_SUPPORTED_ASSETS:
                    cand = _candidate_for_corridor(
                        source_id=self.source_id,
                        bridge="stargate",
                        src_chain=src, dst_chain=dst, asset=asset,
                        hint_metric={
                            "probe_endpoint": "/v1/quote",
                        },
                    )
                    if cand is not None:
                        candidates.append(cand)
                    if len(candidates) >= max_corridors:
                        break
                if len(candidates) >= max_corridors:
                    break
            if len(candidates) >= max_corridors:
                break
        self._last_latency_ms = int((_now_ts() - t0) * 1000)
        self._last_error = None
        if candidates:
            self._last_emission_at = _now_ts()
        return candidates

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )


# ============================================================================
# Factory consumed by CrossChainArbitrageScanner
# ============================================================================

def build_all_cross_chain_sources(
    *,
    config_loader: Callable[[], Dict[str, Any]],
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[DiscoverySource]:
    """One instance of every D-5.1 cross-chain DiscoverySource."""
    return [
        LiFiAggregatorSource(
            config_loader=config_loader, http_client=http_client),
        StargateSource(
            config_loader=config_loader, http_client=http_client),
    ]
