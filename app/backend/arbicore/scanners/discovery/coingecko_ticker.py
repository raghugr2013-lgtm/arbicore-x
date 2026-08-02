"""ArbiCore X — Phase D D-1.5: CoinGeckoTickerSource.

First aggregator DiscoverySource. Cross-CEX ticker divergence vs CoinGecko's
median USDT mid for each target coin. Public free-tier endpoint; no API key.

Hard contract:
  - INV-1: emits DiscoveryCandidate ONLY; never CanonicalOpportunity.
  - INV-2: verifier (CEXOrderBookVerifier) is the only path to canonical.
  - INV-3: ``coingecko_public`` provenance is telemetry only — when a CG-sourced
           candidate is later confirmed, the emitted CanonicalOpportunity's
           ``source_data_quality`` is set by the verifier from the venue read's
           SOURCE_REGISTRY classification, never from this source.
"""
from __future__ import annotations

import asyncio
import logging
import statistics
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

from ...models.discovery import DiscoveryCandidate, SourceHealth, make_candidate_id
from ...models.enums import DataProvenance, OpportunityType
from ..discovery_source import DiscoverySource

logger = logging.getLogger("arbicore.scanners.discovery.coingecko")

DEFAULT_COIN_IDS: List[str] = [
    "bitcoin", "ethereum", "solana",
]

# Map CG coin_id → canonical base symbol (uppercase) for asset string.
_COIN_TO_SYMBOL: Dict[str, str] = {
    "bitcoin": "BTC", "ethereum": "ETH", "solana": "SOL", "binancecoin": "BNB",
    "ripple": "XRP", "dogecoin": "DOGE", "cardano": "ADA", "chainlink": "LINK",
    "avalanche-2": "AVAX", "tron": "TRX",
}


class CoinGeckoTickerSource(DiscoverySource):
    """Cross-CEX ticker divergence hint source via CoinGecko."""

    source_id = "coingecko_ticker"
    cadence_s = 60   # one coin per cycle (round-robin); ~1 req/min, well within CG free-tier
    opportunity_types = {OpportunityType.CEX_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL   # telemetry only (INV-3)

    def __init__(self, *,
                 config_loader: Callable[[], Dict[str, Any]],
                 target_coins: Optional[List[str]] = None) -> None:
        self._cfg = config_loader
        self._target_coins = target_coins or DEFAULT_COIN_IDS
        self._client = httpx.AsyncClient(
            timeout=10.0,
            headers={"User-Agent": "ArbiCoreX/D-1.5"},
        )
        self._sem = asyncio.Semaphore(1)   # serialize CG calls (free-tier strict)
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0
        self._consecutive_429 = 0
        self._last_discover_at: float = 0.0   # cadence-respecting throttle
        self._round_robin_idx: int = 0        # rotate one coin per cycle

    async def close(self) -> None:
        await self._client.aclose()

    # ---- DiscoverySource implementation ------------------------------------

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._cfg() or {}
        src_cfg = (cfg.get("discovery_sources", {})
                      .get(self.source_id, {}))
        if src_cfg.get("enabled") is False:
            return []
        # Auto-recover from rate-limit lockout after a 10-minute cool-down,
        # but only if we have a prior discovery timestamp — a fresh source
        # that was started with consecutive_429 already ≥ 3 (e.g. via test
        # injection or persistence in a future release) stays locked until
        # an actual probe attempt has been recorded.
        if self._consecutive_429 >= 3:
            now_mono = time.monotonic()
            if self._last_discover_at > 0 and (now_mono - self._last_discover_at) >= 600.0:
                # Cool-down elapsed; allow one probe attempt.
                self._consecutive_429 = 0
                self._last_error = None
            else:
                return []
        # Honour our declared cadence_s even if the scanner ticks faster:
        # the CG free-tier rate-limit demands we self-throttle. The scanner
        # invokes every source every tick (30 s); we only do work every cadence.
        now_mono = time.monotonic()
        if (now_mono - self._last_discover_at) < self.cadence_s:
            return []
        self._last_discover_at = now_mono
        threshold_bps = float(src_cfg.get("cg_divergence_threshold_bps", 30))
        volume_floor = float(src_cfg.get("volume_floor_usd", 50_000))
        coins_all = src_cfg.get("target_coins") or self._target_coins
        # Round-robin: fetch ONE coin per cycle to stay well within CG
        # free-tier rate limits. Over N cycles all coins are covered.
        if not coins_all:
            return []
        coin = coins_all[self._round_robin_idx % len(coins_all)]
        self._round_robin_idx = (self._round_robin_idx + 1) % len(coins_all)
        coins = [coin]

        out: List[DiscoveryCandidate] = []
        t0 = time.monotonic()
        try:
            tickers_by_coin = await asyncio.gather(
                *[self._fetch_coin_tickers(coin_id) for coin_id in coins],
                return_exceptions=True,
            )
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"gather: {exc!r}"
            return []
        self._last_latency_ms = int((time.monotonic() - t0) * 1000)

        had_any_success = False
        for coin_id, result in zip(coins, tickers_by_coin):
            if isinstance(result, Exception) or result is None:
                continue
            had_any_success = True
            cands = self._build_candidates_for_coin(
                coin_id, result, threshold_bps, volume_floor,
            )
            out.extend(cands)
        if had_any_success:
            self._last_error = None
            self._consecutive_429 = 0
        if out:
            self._last_emission_at = time.time()
        return out

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=(self._last_error is None and self._consecutive_429 < 3),
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )

    # ---- HTTP -------------------------------------------------------------

    async def _fetch_coin_tickers(self, coin_id: str) -> Optional[List[Dict[str, Any]]]:
        url = (f"https://api.coingecko.com/api/v3/coins/{coin_id}/tickers"
               f"?include_exchange_logo=false")
        async with self._sem:
            # Single CG /tickers call per cycle (round-robin); modest jitter.
            await asyncio.sleep(0.25)
            try:
                r = await self._client.get(url)
            except Exception as exc:  # noqa: BLE001
                self._last_error = f"http: {exc!r}"
                return None
        if r.status_code == 429:
            self._consecutive_429 += 1
            self._last_error = "rate_limited:429"
            logger.warning("coingecko 429 (%s consecutive)", self._consecutive_429)
            return None
        if r.status_code != 200:
            self._last_error = f"http_{r.status_code}"
            return None
        try:
            body = r.json()
            return body.get("tickers") or []
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"parse: {exc!r}"
            return None

    # ---- Candidate construction -------------------------------------------

    def _build_candidates_for_coin(self, coin_id: str,
                                   tickers: List[Dict[str, Any]],
                                   threshold_bps: float,
                                   volume_floor_usd: float,
                                   ) -> List[DiscoveryCandidate]:
        symbol = _COIN_TO_SYMBOL.get(coin_id)
        if not symbol:
            return []
        # Filter to USDT pairs with meaningful volume
        usdt = []
        for t in tickers:
            try:
                if (t.get("target") or "").upper() != "USDT":
                    continue
                last = float(t.get("last") or 0)
                vol_usd = float((t.get("converted_volume") or {}).get("usd") or 0)
                if last > 0 and vol_usd >= volume_floor_usd:
                    usdt.append({
                        "market": (t.get("market") or {}).get("identifier") or "?",
                        "last": last, "vol_usd": vol_usd,
                    })
            except (TypeError, ValueError):
                continue
        if len(usdt) < 3:
            return []  # too thin to compute a meaningful median
        median_mid = statistics.median([t["last"] for t in usdt])
        # Emit ONE candidate per coin per minute window (idempotent).
        # The verifier reads all 6 D-1 venues independently — CG just nominates
        # "this coin shows cross-CEX divergence right now".
        outlier = max(usdt, key=lambda t: abs(t["last"] - median_mid))
        divergence_bps = abs(outlier["last"] - median_mid) / median_mid * 10_000.0
        if divergence_bps < threshold_bps:
            return []
        now = time.time()
        asset = f"{symbol}USDT"
        cid = make_candidate_id(
            hint_source=self.source_id,
            opportunity_type=OpportunityType.CEX_ARBITRAGE,
            subject_id=symbol,
            asset=asset,
            candidate_venues=[],   # verifier reads all D-1 venues
            hint_observed_at=now,
        )
        return [DiscoveryCandidate(
            candidate_id=cid,
            opportunity_type=OpportunityType.CEX_ARBITRAGE,
            hint_source=self.source_id,
            hint_observed_at=now,
            subject_id=symbol,
            asset=asset,
            candidate_venues=[],
            hint_metric={
                "cg_outlier_market": outlier["market"],
                "cg_outlier_last": outlier["last"],
                "cg_median_usdt": round(median_mid, 8),
                "divergence_bps": round(divergence_bps, 2),
                "threshold_bps": threshold_bps,
                "cg_observed_markets": len(usdt),
                "cg_outlier_volume_usd": outlier["vol_usd"],
            },
            reason="coingecko_cross_cex_divergence",
        )]
