"""ArbiCore X — Phase D D-3.1 DexScreener aggregator HINT source.

Second aggregator DiscoverySource (after D-1.5 CoinGecko). Polls DexScreener
public REST for cross-DEX, cross-chain pair-state divergence and emits
DiscoveryCandidate rows for any pair whose max-vs-min DEX mid divergence
exceeds the configured threshold (default 40 bps).

Hard contract:
  - INV-1: emits DiscoveryCandidate ONLY; never CanonicalOpportunity.
  - INV-2: D-3.4 DEXArbitrageScanner is the only emit caller for DEX_ARBITRAGE.
  - INV-3: ``dexscreener_hint`` provenance is TELEMETRY ONLY. When this source's
           candidate is later confirmed by the D-3.2 DEXQuoteVerifier, the emitted
           CanonicalOpportunity's source_data_quality is set from the per-leg
           on-chain quoter's SOURCE_REGISTRY classification, NEVER from this hint.

D-3.1 ships the source with full divergence-detection plumbing but a stub
HTTP call (no live DexScreener requests are issued at this wave — live wiring
lands at D-3.6 alongside the venue sources). The contract, candidate shape,
round-robin pair selection, INV-1 typing, and graceful-disable on network
error are all testable today.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

from ...models.discovery import DiscoveryCandidate, SourceHealth, make_candidate_id
from ...models.enums import DataProvenance, OpportunityType
from ..discovery_source import DiscoverySource

logger = logging.getLogger("arbicore.scanners.discovery.dexscreener_hint")


class DexScreenerHintSource(DiscoverySource):
    """Cross-DEX / cross-chain pair-state aggregator HINT source."""

    source_id = "dexscreener_hint"
    cadence_s = 120                                       # gentle: 1 pair / 2 min
    opportunity_types: Set[OpportunityType] = {OpportunityType.DEX_ARBITRAGE}
    tier = 2                                              # aggregator tier
    provenance_of_hint = DataProvenance.REAL              # telemetry only (INV-3)

    # No credentials required — DexScreener public endpoint.
    credentials_env_var: Optional[str] = None
    base_url: str = "https://api.dexscreener.com/latest/dex/tokens"

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                 http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._config_loader = config_loader
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None
        self._cursor = 0
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms: int = 0
        # D-3.7 sanity-gate telemetry — cumulative count of hints suppressed
        # because their divergence exceeded the symbol-collision ceiling.
        self._last_sanity_rejections: int = 0

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ----- DiscoverySource public API --------------------------------------

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        pair_universe = self._pair_universe(cfg)
        if not pair_universe:
            return []
        # Round-robin one pair per cycle to respect aggregator rate limits.
        pair_canonical = pair_universe[self._cursor % len(pair_universe)]
        self._cursor += 1
        threshold_bps = self._divergence_threshold_bps(cfg)
        volume_floor = self._volume_floor_usd(cfg)
        t0 = time.time()
        try:
            observations = await self._fetch_pair_dex_quotes(pair_canonical)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_latency_ms = int((time.time() - t0) * 1000)
            return []
        self._last_latency_ms = int((time.time() - t0) * 1000)
        self._last_error = None
        if len(observations) < 2:
            return []
        # Filter by volume floor
        observations = [o for o in observations
                        if (o.get("h24_volume_usd") or 0) >= volume_floor]
        if len(observations) < 2:
            return []
        mids = [o["mid"] for o in observations if o.get("mid", 0) > 0]
        if len(mids) < 2:
            return []
        mid_max, mid_min = max(mids), min(mids)
        if mid_min <= 0:
            return []
        divergence_bps = (mid_max - mid_min) / mid_min * 10_000.0
        if divergence_bps < threshold_bps:
            return []
        # D-3.7 sanity gate: reject implausible divergence as symbol-collision noise.
        # DexScreener free-text search occasionally returns rows with the same
        # base/quote symbol pair but on a different chain belonging to an
        # unrelated impostor token (e.g. sub-cent pseudo-WETH on a long-tail
        # chain). Those produce divergence in the thousands-of-bps range and
        # would waste verifier cycles. INV-3 already prevents propagation to
        # canonical, but suppressing the hint avoids the wasted on-chain quote.
        sanity_ceiling_bps = self._divergence_sanity_ceiling_bps(cfg)
        if divergence_bps > sanity_ceiling_bps:
            self._last_sanity_rejections += 1
            return []
        venues = sorted({
            f"{o.get('dex','?')}:{o.get('chain','?')}" for o in observations
        })
        now = time.time()
        candidate_id = make_candidate_id(
            hint_source=self.source_id,
            opportunity_type=OpportunityType.DEX_ARBITRAGE,
            subject_id=pair_canonical,
            asset=pair_canonical.split("/")[0],
            candidate_venues=venues,
            hint_observed_at=now,
        )
        self._last_emission_at = now
        return [DiscoveryCandidate(
            candidate_id=candidate_id,
            opportunity_type=OpportunityType.DEX_ARBITRAGE,
            hint_source=self.source_id,
            hint_observed_at=now,
            subject_id=pair_canonical,
            asset=pair_canonical.split("/")[0],
            candidate_venues=venues,
            hint_metric={
                "divergence_bps": divergence_bps,
                "mid_max": mid_max, "mid_min": mid_min,
                "observation_count": len(observations),
            },
            reason=(
                f"dexscreener_divergence:{divergence_bps:.1f}bps "
                f"across {len(venues)} DEX×chain"
            ),
        )]

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )

    # ----- helpers ----------------------------------------------------------

    def _pair_universe(self, cfg: Dict[str, Any]) -> List[str]:
        tier_a = cfg.get("tier_a_pairs", []) or []
        tier_b = cfg.get("tier_b_pairs", []) or []
        # Strip the @chain suffix and dedupe — DexScreener crosses chains.
        return sorted({
            p.split("@", 1)[0] for p in (tier_a + tier_b) if p
        })

    def _divergence_threshold_bps(self, cfg: Dict[str, Any]) -> float:
        per_source = (cfg.get("discovery_sources") or {}).get(self.source_id, {})
        return float(per_source.get("ds_divergence_threshold_bps", 40.0))

    def _divergence_sanity_ceiling_bps(self, cfg: Dict[str, Any]) -> float:
        """D-3.7 sanity gate ceiling. Hints with divergence above this value
        are assumed to be symbol-collision artefacts (impostor tokens sharing
        symbol with the real asset on a long-tail chain) and are dropped.
        Default 1000 bps (10%) was chosen from the D-3.6 live probe data —
        every legitimate cross-DEX divergence observed was well under 200 bps,
        and every above-1000-bps observation traced back to an impostor pool.
        """
        per_source = (cfg.get("discovery_sources") or {}).get(self.source_id, {})
        return float(per_source.get("ds_divergence_sanity_ceiling_bps", 1000.0))

    def _volume_floor_usd(self, cfg: Dict[str, Any]) -> float:
        per_source = (cfg.get("discovery_sources") or {}).get(self.source_id, {})
        return float(per_source.get("volume_floor_usd", 50_000.0))

    async def _fetch_pair_dex_quotes(self, pair_canonical: str
                                     ) -> List[Dict[str, Any]]:
        """Live DexScreener pair-state fetch (D-3.6).

        Queries the public ``/latest/dex/search`` endpoint. No credentials
        required. Returns a normalized list of observations:
        ``{dex, chain, mid, h24_volume_usd, pool_address, liquidity_usd}``.

        Filters: only observations whose ``baseToken.symbol == BASE`` and
        ``quoteToken.symbol == QUOTE`` are accepted; this avoids reverse-pair
        and synthetic noise. INV-3 telemetry-only — the verifier always
        re-derives provenance from the on-chain quoter per leg.
        """
        if "/" not in pair_canonical:
            return []
        base = pair_canonical.split("/", 1)[0].upper()
        quote = pair_canonical.split("/", 1)[1].upper()
        url = "https://api.dexscreener.com/latest/dex/search"
        try:
            resp = await self._client.get(url, params={"q": f"{base} {quote}"})
        except Exception:  # noqa: BLE001
            raise
        if resp.status_code != 200:
            return []
        payload = resp.json() or {}
        pairs = payload.get("pairs") or []
        out: List[Dict[str, Any]] = []
        for p in pairs:
            try:
                bt = (p.get("baseToken") or {}).get("symbol", "").upper()
                qt = (p.get("quoteToken") or {}).get("symbol", "").upper()
                if bt != base or qt != quote:
                    continue
                mid = float(p.get("priceUsd") or 0.0)
                if mid <= 0:
                    continue
                liq_usd = float((p.get("liquidity") or {}).get("usd") or 0.0)
                vol_usd = float((p.get("volume") or {}).get("h24") or 0.0)
                out.append({
                    "dex": str(p.get("dexId") or "unknown"),
                    "chain": str(p.get("chainId") or "unknown"),
                    "mid": mid,
                    "h24_volume_usd": vol_usd,
                    "pool_address": p.get("pairAddress"),
                    "liquidity_usd": liq_usd,
                })
            except (TypeError, ValueError, KeyError):
                continue
        return out
