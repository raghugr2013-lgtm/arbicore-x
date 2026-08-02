"""ArbiCore X — Phase D D-4.1 Launch Intelligence DiscoverySources.

Five sources land at this wave, all built atop the universal DiscoverySource
ABC. Sources never call EmissionBus.emit (INV-2); they only emit
DiscoveryCandidate rows (INV-1). Per INV-3 the three aggregator HINTs
(DexScreener fresh-launch, Pump.fun, Jupiter trending) are tagged with
provenance_of_hint=REAL but the downstream verifier (D-4.4) MUST re-derive
``CanonicalOpportunity.source_data_quality`` from the per-leg on-chain
``helius_token_rpc`` source classification — the aggregator classification
is telemetry only.

Each source ships fully functional parsers (the legacy adapter knowledge
from `archive/backend/ingestion/adapters/{dexscreener,pumpfun,jupiter}.py`
and `archive/backend/intel/providers/helius.py` is harvested per the
LEGACY_ARCHIVE_IMPORT_ASSESSMENT.md decisions), but every source is
DISABLED at boot (operator-controlled, per the D-4.0 substrate seed).
The orchestrator at D-4.5 is what activates them.

Graceful-disable contract:
  - aggregators (no credentials)  : poll always allowed when the per-source
                                    config block has `enabled=True`
  - credentialed sources          : when `credentials_env_var` is absent
                                    from os.environ, discover() returns []
                                    and health() reports ok=False with
                                    last_error=credentials_missing:<ENV>
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional, Set

import httpx

from ...models.discovery import DiscoveryCandidate, SourceHealth, make_candidate_id
from ...models.enums import DataProvenance, OpportunityType
from ..discovery_source import DiscoverySource

logger = logging.getLogger("arbicore.scanners.launch_arbitrage.sources")


# ============================================================================
# Helpers
# ============================================================================

def _per_source_config(cfg: Dict[str, Any], source_id: str) -> Dict[str, Any]:
    return (cfg.get("discovery_sources") or {}).get(source_id, {}) or {}


def _now_ts() -> float:
    return time.time()


# ============================================================================
# DexScreenerFreshLaunchSource (PARTIAL HARVEST — endpoints + httpx pattern)
# ============================================================================

class DexScreenerFreshLaunchSource(DiscoverySource):
    """Fresh-launch discovery via DexScreener public REST aggregator.

    Polls (round-robin per cycle, to respect rate limits):
      - /token-profiles/latest/v1   newly profiled tokens
      - /token-boosts/latest/v1     boosted tokens (community-trust signal)
      - /token-boosts/top/v1        top-boosted tokens

    INV-3: aggregator HINT — the verifier re-derives source_data_quality
    from the per-leg on-chain RPC source (`helius_token_rpc`).
    """

    source_id = "dexscreener_fresh_launch"
    cadence_s = 60
    opportunity_types: Set[OpportunityType] = {OpportunityType.LAUNCH_ARBITRAGE}
    tier = 2
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None
    base_url = "https://api.dexscreener.com"

    ENDPOINT_ROTATION = (
        "/token-profiles/latest/v1",
        "/token-boosts/latest/v1",
        "/token-boosts/top/v1",
    )

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                 http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._config_loader = config_loader
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None
        self._cursor = 0
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return True

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ----- public DiscoverySource API --------------------------------------

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        per_source = _per_source_config(cfg, self.source_id)
        if not per_source.get("enabled", False):
            return []
        max_age_hours = float(per_source.get("max_age_hours", 72))
        endpoint = self._next_endpoint()
        t0 = _now_ts()
        try:
            rows = await self._fetch(endpoint)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_latency_ms = int((_now_ts() - t0) * 1000)
            return []
        self._last_latency_ms = int((_now_ts() - t0) * 1000)
        self._last_error = None
        now = _now_ts()
        candidates: List[DiscoveryCandidate] = []
        for row in rows:
            try:
                token_addr = (row.get("tokenAddress") or "").strip()
                chain = (row.get("chainId") or "").strip().lower()
                if not token_addr or not chain:
                    continue
                # /token-profiles entries occasionally include a `links`
                # list with a website / twitter / telegram presence — used
                # as a `socials_present` flag downstream (D-4.3 narrative).
                links = row.get("links") or []
                socials_present = bool(links)
                # Some endpoints embed an `amount` (boost score) for ranking
                boost_amount = float(row.get("amount") or row.get("totalAmount") or 0.0)
                subject_id = f"{chain}:{token_addr}"
                asset = (row.get("description") or "")[:32] or token_addr[:10]
                hint_obs = now
                candidate_id = make_candidate_id(
                    hint_source=self.source_id,
                    opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
                    subject_id=subject_id, asset=asset,
                    candidate_venues=[chain],
                    hint_observed_at=hint_obs,
                )
                candidates.append(DiscoveryCandidate(
                    candidate_id=candidate_id,
                    opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
                    hint_source=self.source_id,
                    hint_observed_at=hint_obs,
                    subject_id=subject_id,
                    asset=asset,
                    candidate_venues=[chain],
                    hint_metric={
                        "endpoint": endpoint,
                        "boost_amount": boost_amount,
                        "socials_present": socials_present,
                        "max_age_hours_cap": max_age_hours,
                    },
                    reason=f"dexscreener_fresh_launch:{endpoint}",
                ))
            except (TypeError, ValueError, KeyError):
                continue
        if candidates:
            self._last_emission_at = now
        return candidates

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=self._last_error is None,
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )

    # ----- helpers ----------------------------------------------------------

    def _next_endpoint(self) -> str:
        ep = self.ENDPOINT_ROTATION[self._cursor % len(self.ENDPOINT_ROTATION)]
        self._cursor += 1
        return ep

    async def _fetch(self, endpoint: str) -> List[Dict[str, Any]]:
        resp = await self._client.get(f"{self.base_url}{endpoint}")
        if resp.status_code != 200:
            return []
        payload = resp.json()
        # DexScreener returns either a top-level list or {pairs:[]} shape;
        # the boosts endpoints are flat lists.
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            return payload.get("pairs") or payload.get("tokens") or []
        return []


# ============================================================================
# PumpfunLaunchesSource (REUSE WITH REFINEMENT)
# ============================================================================

class PumpfunLaunchesSource(DiscoverySource):
    """Solana bonding-curve launch discovery via Pump.fun frontend-api.

    Endpoint is unofficial — multi-base fallback respected per the legacy
    adapter knowledge. Best-effort: a failed fetch MUST never crash the
    discovery loop (graceful failure → empty list).

    Per-source config window: `min_market_cap_usd` and `max_market_cap_usd`
    select tokens still on the bonding curve (default 5k - 100k USD).
    """

    source_id = "pumpfun_launches"
    cadence_s = 30
    opportunity_types: Set[OpportunityType] = {OpportunityType.LAUNCH_ARBITRAGE}
    tier = 2
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None

    # Pump.fun v1/v2 fronts were retired by upstream (HTTP 530 / 503);
    # v3 is the live frontend. Path also rotated from
    # ``/coins/king-of-the-hill`` (empty body) to ``/coins`` (full payload).
    BASE_CANDIDATES = (
        "https://frontend-api-v3.pump.fun",
    )

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                 http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._config_loader = config_loader
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return True

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        per_source = _per_source_config(cfg, self.source_id)
        if not per_source.get("enabled", False):
            return []
        mc_min = float(per_source.get("min_market_cap_usd", 5_000))
        mc_max = float(per_source.get("max_market_cap_usd", 100_000))
        max_age_hours = float(per_source.get("max_age_hours", 24))
        t0 = _now_ts()
        rows: List[Dict[str, Any]] = []
        last_exc: Optional[Exception] = None
        for base in self.BASE_CANDIDATES:
            try:
                resp = await self._client.get(f"{base}/coins",
                                              params={"limit": 50})
                if resp.status_code == 200:
                    payload = resp.json()
                    if isinstance(payload, list):
                        rows = payload
                    elif isinstance(payload, dict):
                        rows = payload.get("coins") or []
                    last_exc = None
                    break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        self._last_latency_ms = int((_now_ts() - t0) * 1000)
        if last_exc is not None:
            self._last_error = f"{type(last_exc).__name__}: {last_exc}"
        else:
            self._last_error = None
        now = _now_ts()
        candidates: List[DiscoveryCandidate] = []
        for row in rows:
            try:
                mint = (row.get("mint") or row.get("mintAddress") or "").strip()
                if not mint:
                    continue
                market_cap = float(row.get("usd_market_cap")
                                    or row.get("marketCap") or 0.0)
                if market_cap < mc_min or market_cap > mc_max:
                    continue
                created_at = float(row.get("created_timestamp")
                                    or row.get("createdAt") or 0.0)
                age_hours = (now - created_at) / 3600.0 if created_at > 0 else None
                if age_hours is not None and age_hours > max_age_hours:
                    continue
                # Bonding-curve progress signal — Pump.fun migrates at ~$69k
                progress_pct = min(100.0, market_cap / 690.0)  # 0..100
                subject_id = f"solana:{mint}"
                symbol = (row.get("symbol") or "")[:16] or mint[:10]
                candidate_id = make_candidate_id(
                    hint_source=self.source_id,
                    opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
                    subject_id=subject_id, asset=symbol,
                    candidate_venues=["pumpfun:solana"],
                    hint_observed_at=now,
                )
                candidates.append(DiscoveryCandidate(
                    candidate_id=candidate_id,
                    opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
                    hint_source=self.source_id,
                    hint_observed_at=now,
                    subject_id=subject_id, asset=symbol,
                    candidate_venues=["pumpfun:solana"],
                    hint_metric={
                        "market_cap_usd": market_cap,
                        "bonding_curve_progress_pct": progress_pct,
                        "age_hours": age_hours,
                        "launchpad": "pumpfun",
                        "name": (row.get("name") or "")[:64],
                    },
                    reason=f"pumpfun_launch:mc={market_cap:.0f}",
                ))
            except (TypeError, ValueError, KeyError):
                continue
        if candidates:
            self._last_emission_at = now
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
# JupiterTrendingSource (REUSE WITH REFINEMENT)
# ============================================================================

class JupiterTrendingSource(DiscoverySource):
    """Solana DEX aggregator trending pools via Jupiter."""

    source_id = "jupiter_trending"
    cadence_s = 90
    opportunity_types: Set[OpportunityType] = {OpportunityType.LAUNCH_ARBITRAGE}
    tier = 2
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var: Optional[str] = None

    # Jupiter rotated its trending feed away from /v6/tokens/trending in 2025.
    # Live replacement: https://datapi.jup.ag/v1/pools/toptraded/24h
    # Schema is richer: returns pool objects with nested baseAsset.{id,symbol,
    # holderCount,audit.topHoldersPercentage} and pool-level volume24h.
    BASE_CANDIDATES = (
        "https://datapi.jup.ag",
    )

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                 http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._config_loader = config_loader
        self._client = http_client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = http_client is None
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return True

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        per_source = _per_source_config(cfg, self.source_id)
        if not per_source.get("enabled", False):
            return []
        limit = int(per_source.get("trending_limit", 50))
        min_vol = float(per_source.get("min_volume_usd_24h", 50_000))
        t0 = _now_ts()
        rows: List[Dict[str, Any]] = []
        last_exc: Optional[Exception] = None
        for base in self.BASE_CANDIDATES:
            try:
                resp = await self._client.get(
                    f"{base}/v1/pools/toptraded/24h",
                    params={"limit": limit},
                )
                if resp.status_code == 200:
                    payload = resp.json()
                    # New schema (post-2025): {"pools": [{...,"baseAsset":{...}}]}
                    # Legacy schema (pre-2025): {"tokens": [...]} or top-level list
                    if isinstance(payload, dict) and "pools" in payload:
                        rows = payload.get("pools") or []
                    elif isinstance(payload, list):
                        rows = payload
                    else:
                        rows = (payload.get("tokens")
                                or payload.get("data") or [])
                    last_exc = None
                    break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                continue
        self._last_latency_ms = int((_now_ts() - t0) * 1000)
        self._last_error = (f"{type(last_exc).__name__}: {last_exc}"
                             if last_exc else None)
        now = _now_ts()
        candidates: List[DiscoveryCandidate] = []
        for row in rows:
            try:
                # Post-2025 schema: row is a pool object with nested baseAsset.
                # Legacy schema: row is a flat token object with address/mint.
                base_asset = row.get("baseAsset")
                if isinstance(base_asset, dict):
                    # Skip pools whose base asset is a quote/stable (would
                    # produce noisy candidates on the cross-pair side).
                    base_mint = (base_asset.get("id") or "").strip()
                    base_symbol = (base_asset.get("symbol") or "")[:16]
                    holder_count = int(base_asset.get("holderCount") or 0)
                    audit = base_asset.get("audit") or {}
                    top10_pct = float(audit.get("topHoldersPercentage") or 0.0)
                    chain = (row.get("chain") or "solana").lower()
                    if chain != "solana":
                        continue
                    mint = base_mint
                    symbol = base_symbol or mint[:10]
                else:
                    mint = (row.get("address") or row.get("mint") or "").strip()
                    symbol = (row.get("symbol") or "")[:16] or mint[:10]
                    holder_count = 0
                    top10_pct = 0.0
                if not mint:
                    continue
                vol_24h = float(row.get("volume24h") or row.get("v24hUSD")
                                or 0.0)
                if vol_24h < min_vol:
                    continue
                subject_id = f"solana:{mint}"
                candidate_id = make_candidate_id(
                    hint_source=self.source_id,
                    opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
                    subject_id=subject_id, asset=symbol,
                    candidate_venues=["jupiter:solana"],
                    hint_observed_at=now,
                )
                hint_metric: Dict[str, Any] = {
                    "volume_24h_usd": vol_24h,
                    "price_usd": float(row.get("priceUsd")
                                        or row.get("price") or 0.0),
                    "launchpad": "jupiter_trending",
                }
                # Propagate enrichment surfaced by the new endpoint.
                # Verifier downstream may use these instead of placeholders.
                if holder_count:
                    hint_metric["holder_count"] = holder_count
                if top10_pct:
                    hint_metric["top10_concentration_pct"] = top10_pct
                candidates.append(DiscoveryCandidate(
                    candidate_id=candidate_id,
                    opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
                    hint_source=self.source_id,
                    hint_observed_at=now,
                    subject_id=subject_id, asset=symbol,
                    candidate_venues=["jupiter:solana"],
                    hint_metric=hint_metric,
                    reason=f"jupiter_trending:vol={vol_24h:.0f}",
                ))
            except (TypeError, ValueError, KeyError):
                continue
        if candidates:
            self._last_emission_at = now
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
# HeliusWalletSource (PARTIAL HARVEST — URLs + response shape only)
# ============================================================================

class HeliusWalletSource(DiscoverySource):
    """Solana wallet intelligence — recent buyers of tracked tokens.

    Requires HELIUS_API_KEY. Graceful-disable when absent.

    At D-4.1 this source emits ONE DiscoveryCandidate per (token, time-window)
    summarising buyer activity. The full wallet enrichment pipeline (scoring,
    labelling, clustering) lands at D-4.2 and consumes these candidates.

    The set of "tracked tokens" is supplied by ``token_universe_loader``.
    At D-4.1 there is no orchestrator wiring this loader, so the source
    returns ``[]`` when the loader returns an empty universe — which is the
    expected D-4.1 dormant state.
    """

    source_id = "helius_wallet_source"
    cadence_s = 60
    opportunity_types: Set[OpportunityType] = {OpportunityType.LAUNCH_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var = "HELIUS_API_KEY"

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]],
                 token_universe_loader: Callable[[], List[str]],
                 http_client: Optional[httpx.AsyncClient] = None) -> None:
        self._config_loader = config_loader
        self._token_universe_loader = token_universe_loader
        self._client = http_client or httpx.AsyncClient(timeout=15.0)
        self._owns_client = http_client is None
        self._cursor = 0
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return bool(os.environ.get(self.credentials_env_var, "").strip())

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def discover(self) -> List[DiscoveryCandidate]:
        if not self.credentials_available:
            self._last_error = f"credentials_missing:{self.credentials_env_var}"
            return []
        cfg = self._config_loader() or {}
        per_source = _per_source_config(cfg, self.source_id)
        if not per_source.get("enabled", False):
            return []
        recent_buyers_limit = int(per_source.get("recent_buyers_limit", 50))
        universe = self._token_universe_loader() or []
        if not universe:
            self._last_error = None
            return []
        # Round-robin one token per cycle (rate-limit-safe)
        token_mint = universe[self._cursor % len(universe)]
        self._cursor += 1
        t0 = _now_ts()
        try:
            buyers = await self._fetch_recent_buyers(token_mint, recent_buyers_limit)
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._last_latency_ms = int((_now_ts() - t0) * 1000)
            return []
        self._last_latency_ms = int((_now_ts() - t0) * 1000)
        self._last_error = None
        if not buyers:
            return []
        now = _now_ts()
        subject_id = f"solana:{token_mint}"
        candidate_id = make_candidate_id(
            hint_source=self.source_id,
            opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
            subject_id=subject_id, asset=token_mint[:10],
            candidate_venues=["helius:solana"],
            hint_observed_at=now,
        )
        self._last_emission_at = now
        return [DiscoveryCandidate(
            candidate_id=candidate_id,
            opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
            hint_source=self.source_id,
            hint_observed_at=now,
            subject_id=subject_id, asset=token_mint[:10],
            candidate_venues=["helius:solana"],
            hint_metric={
                "recent_buyer_count": len(buyers),
                "buyer_wallets_sample": [b.get("wallet") for b in buyers[:5]
                                          if b.get("wallet")],
                "earliest_buy_ts": min((b.get("ts") for b in buyers
                                         if b.get("ts")), default=None),
                "token_mint": token_mint,
            },
            reason=f"helius_recent_buyers:{len(buyers)}",
        )]

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

    async def _fetch_recent_buyers(self, token_mint: str, limit: int
                                    ) -> List[Dict[str, Any]]:
        """Helius parsed-transactions API.

        Endpoint shape (per legacy `intel/providers/helius.py`):
          GET https://api.helius.xyz/v0/addresses/{mint}/transactions
              ?api-key=<KEY>&type=SWAP&limit=<N>
        Returns a list of parsed swap transactions. We project each into:
          {wallet, ts, amount_sol, amount_token}
        """
        api_key = os.environ.get(self.credentials_env_var, "")
        url = f"https://api.helius.xyz/v0/addresses/{token_mint}/transactions"
        resp = await self._client.get(url, params={
            "api-key": api_key,
            "type": "SWAP",
            "limit": limit,
        })
        if resp.status_code != 200:
            return []
        payload = resp.json() or []
        out: List[Dict[str, Any]] = []
        for tx in payload:
            try:
                wallet = (tx.get("feePayer") or tx.get("signature") or "").strip()
                if not wallet:
                    continue
                ts = float(tx.get("timestamp") or 0.0)
                out.append({"wallet": wallet, "ts": ts, "tx_signature": tx.get("signature")})
            except (TypeError, ValueError):
                continue
        return out


# ============================================================================
# BitqueryWalletSource (REBUILD FRESH — stubbed, awaiting BITQUERY_API_KEY)
# ============================================================================

class BitqueryWalletSource(DiscoverySource):
    """Bitquery GraphQL cross-chain wallet enrichment.

    Per Operator Decision 3 (D4_AUTHORIZATION_PACKAGE.md §4.3) this source
    is SCAFFOLDED BUT STUBBED at D-4.1. The graceful-disable contract is
    fully wired and the surface is registered, but `discover()` returns []
    until `BITQUERY_API_KEY` is provisioned AND the operator flips
    ``scaffolded_only`` to False in scanner_config.launch_arb.

    Health probe explicitly reports ``scaffolded_only:true`` so the
    diagnostic preview endpoint surfaces the deferred state.
    """

    source_id = "bitquery_wallet_source"
    cadence_s = 120
    opportunity_types: Set[OpportunityType] = {OpportunityType.LAUNCH_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL
    credentials_env_var = "BITQUERY_API_KEY"

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]]) -> None:
        self._config_loader = config_loader
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = "scaffolded_only:true"
        self._last_latency_ms = 0

    @property
    def credentials_available(self) -> bool:
        return bool(os.environ.get(self.credentials_env_var, "").strip())

    async def close(self) -> None:
        pass

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        per_source = _per_source_config(cfg, self.source_id)
        # Two gates: scaffolded flag, then enabled flag, then credentials.
        if per_source.get("scaffolded_only", True):
            self._last_error = "scaffolded_only:true"
            return []
        if not per_source.get("enabled", False):
            return []
        if not self.credentials_available:
            self._last_error = f"credentials_missing:{self.credentials_env_var}"
            return []
        # Live wiring deferred — this branch never fires until D-4 operator
        # action provisions the key AND lifts scaffolded_only.
        self._last_error = "live_wiring_deferred"
        return []

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=False,    # always False at D-4.1 — scaffolded state
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )



# ============================================================================
# D-4.5 — factory used by the LaunchArbitrageScanner orchestrator
# ============================================================================

def build_all_launch_sources(
    *,
    config_loader: Callable[[], Dict[str, Any]],
    token_universe_loader: Callable[[], List[str]],
    http_client: Optional[httpx.AsyncClient] = None,
) -> List[DiscoverySource]:
    """Construct one instance of every D-4 launch DiscoverySource.

    The orchestrator (D-4.5) calls this once at boot and registers each
    instance with its source_registry. The HeliusWalletSource gets the
    token-universe loader so the orchestrator can pass in tracked tokens
    from upstream (DexScreener + Pumpfun + Jupiter) candidate streams.
    """
    return [
        DexScreenerFreshLaunchSource(
            config_loader=config_loader, http_client=http_client),
        PumpfunLaunchesSource(
            config_loader=config_loader, http_client=http_client),
        JupiterTrendingSource(
            config_loader=config_loader, http_client=http_client),
        HeliusWalletSource(
            config_loader=config_loader,
            token_universe_loader=token_universe_loader,
            http_client=http_client),
        BitqueryWalletSource(config_loader=config_loader),
    ]
