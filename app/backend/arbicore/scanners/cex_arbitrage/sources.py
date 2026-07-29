"""ArbiCore X — Phase D D-1: per-venue REST ticker discovery sources.

Each venue ships a single class derived from ``BaseVenueTickerSource``.
The base class does:
  - Periodic ticker poll
  - Filter to active pairs (Tier A + Tier B from scanner_config)
  - Compute mid divergence vs Binance reference (when available)
  - Emit one DiscoveryCandidate per pair that exceeds ticker_divergence_threshold_bps

INV-1 enforced: emits DiscoveryCandidate ONLY. Never CanonicalOpportunity.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import httpx

from ...models.discovery import DiscoveryCandidate, SourceHealth, make_candidate_id
from ...models.enums import DataProvenance, OpportunityType
from ..discovery_source import DiscoverySource

logger = logging.getLogger("arbicore.scanners.cex_arb.sources")

_TICKER_CACHE_TTL_S = 30.0  # other venues' tickers reused as references


class TickerCache:
    """Shared cache of latest ticker mids by (venue, pair). Sources push
    their tickers in after every poll; verifier + other sources read."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, str], Tuple[float, float]] = {}  # (vid,pair)->(ts,mid)

    def put(self, venue_id: str, pair: str, mid: float) -> None:
        self._cache[(venue_id, pair)] = (time.time(), mid)

    def get(self, venue_id: str, pair: str) -> Optional[float]:
        ent = self._cache.get((venue_id, pair))
        if ent is None:
            return None
        ts, mid = ent
        if (time.time() - ts) > _TICKER_CACHE_TTL_S:
            return None
        return mid

    def reference_mid(self, pair: str,
                      exclude_venue: Optional[str] = None) -> Optional[float]:
        """Average mid across all venues with fresh data for `pair`."""
        mids = []
        now = time.time()
        for (vid, p), (ts, mid) in self._cache.items():
            if p != pair or vid == exclude_venue:
                continue
            if (now - ts) > _TICKER_CACHE_TTL_S:
                continue
            mids.append(mid)
        if not mids:
            return None
        return sum(mids) / len(mids)


class BaseVenueTickerSource(DiscoverySource):
    """Common REST ticker poller shared by all 7 D-1 venues."""

    venue_id: str = ""
    api_base: str = ""
    ticker_path: str = ""
    provenance_of_hint = DataProvenance.REAL
    opportunity_types = {OpportunityType.CEX_ARBITRAGE}
    cadence_s = 30
    tier = 1

    def __init__(self, *, ticker_cache: TickerCache,
                 config_loader: Callable[[], Dict[str, Any]],
                 reference_only: bool = False,
                 ) -> None:
        self.source_id = f"venue_ticker:{self.venue_id}"
        self._cache = ticker_cache
        self._config_loader = config_loader
        self._reference_only = reference_only
        self._client = httpx.AsyncClient(timeout=10.0)
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms: int = 0

    async def close(self) -> None:
        await self._client.aclose()

    # ---- Subclass extension points -----------------------------------------

    def normalise_pair(self, pair_universe_symbol: str) -> str:
        """Convert canonical 'BTCUSDT' to the venue's symbol convention."""
        return pair_universe_symbol

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        """Parse venue ticker response into {venue_symbol: mid_price}. Override."""
        raise NotImplementedError

    # ---- DiscoverySource implementation ------------------------------------

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._config_loader() or {}
        active_pairs: List[str] = list(cfg.get("tier_a_pairs", [])) + \
                                  list(cfg.get("tier_b_pairs", []))
        source_cfg = cfg.get("discovery_sources", {}).get(self.source_id, {})
        if source_cfg.get("enabled") is False:
            return []
        threshold_bps = float(source_cfg.get(
            "ticker_divergence_threshold_bps", 20))

        t0 = time.monotonic()
        try:
            r = await self._client.get(f"{self.api_base}{self.ticker_path}")
            r.raise_for_status()
            tickers = self.parse_tickers(r.json())
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("[%s] discover failed: %s", self.source_id, exc)
            return []
        self._last_latency_ms = int((time.monotonic() - t0) * 1000)
        self._last_error = None

        # Update cache: store every pair we see (canonical key form)
        for pair in active_pairs:
            venue_sym = self.normalise_pair(pair)
            mid = tickers.get(venue_sym)
            if mid is not None and mid > 0:
                self._cache.put(self.venue_id, pair, mid)

        if self._reference_only:
            return []  # Binance reference: never emits candidates

        # Emit hints
        now = time.time()
        out: List[DiscoveryCandidate] = []
        for pair in active_pairs:
            venue_sym = self.normalise_pair(pair)
            mid = tickers.get(venue_sym)
            if mid is None or mid <= 0:
                continue
            ref = self._cache.reference_mid(pair, exclude_venue=self.venue_id)
            if ref is None or ref <= 0:
                continue
            divergence_bps = abs(mid - ref) / ref * 10_000.0
            if divergence_bps < threshold_bps:
                continue
            # We DON'T pick the other venue here — the verifier reads all
            # active venues' order books and finds the best counterparty.
            candidate_venues = [self.venue_id]
            subject_id = pair[:-4] if pair.endswith("USDT") else pair
            cid = make_candidate_id(
                hint_source=self.source_id,
                opportunity_type=OpportunityType.CEX_ARBITRAGE,
                subject_id=subject_id,
                asset=pair,
                candidate_venues=candidate_venues,
                hint_observed_at=now,
            )
            out.append(DiscoveryCandidate(
                candidate_id=cid,
                opportunity_type=OpportunityType.CEX_ARBITRAGE,
                hint_source=self.source_id,
                hint_observed_at=now,
                subject_id=subject_id,
                asset=pair,
                candidate_venues=candidate_venues,
                hint_metric={
                    "venue_mid": mid,
                    "reference_mid": ref,
                    "divergence_bps": round(divergence_bps, 2),
                    "threshold_bps": threshold_bps,
                },
                reason="ticker_divergence",
            ))
        if out:
            self._last_emission_at = now
        return out

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=(self._last_error is None),
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )


# =============================================================================
# Concrete venue ticker sources — public REST tickers
# =============================================================================

class BybitTickerSource(BaseVenueTickerSource):
    venue_id = "bybit"
    api_base = "https://api.bybit.com"
    ticker_path = "/v5/market/tickers?category=spot"

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t in (resp_json.get("result", {}).get("list") or []):
            try:
                bid = float(t.get("bid1Price") or 0)
                ask = float(t.get("ask1Price") or 0)
                if bid > 0 and ask > 0:
                    out[t["symbol"]] = (bid + ask) / 2
            except (TypeError, ValueError):
                continue
        return out


class OKXTickerSource(BaseVenueTickerSource):
    venue_id = "okx"
    api_base = "https://www.okx.com"
    ticker_path = "/api/v5/market/tickers?instType=SPOT"

    def normalise_pair(self, pair_universe_symbol: str) -> str:
        # 'BTCUSDT' -> 'BTC-USDT'
        if pair_universe_symbol.endswith("USDT"):
            return pair_universe_symbol[:-4] + "-USDT"
        return pair_universe_symbol

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t in resp_json.get("data", []):
            try:
                bid = float(t.get("bidPx") or 0)
                ask = float(t.get("askPx") or 0)
                if bid > 0 and ask > 0:
                    out[t["instId"]] = (bid + ask) / 2
            except (TypeError, ValueError):
                continue
        return out


class KucoinTickerSource(BaseVenueTickerSource):
    venue_id = "kucoin"
    api_base = "https://api.kucoin.com"
    ticker_path = "/api/v1/market/allTickers"

    def normalise_pair(self, pair_universe_symbol: str) -> str:
        if pair_universe_symbol.endswith("USDT"):
            return pair_universe_symbol[:-4] + "-USDT"
        return pair_universe_symbol

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t in resp_json.get("data", {}).get("ticker", []):
            try:
                buy = float(t.get("buy") or 0)
                sell = float(t.get("sell") or 0)
                if buy > 0 and sell > 0:
                    out[t["symbol"]] = (buy + sell) / 2
            except (TypeError, ValueError):
                continue
        return out


class MexcTickerSource(BaseVenueTickerSource):
    venue_id = "mexc"
    api_base = "https://api.mexc.com"
    ticker_path = "/api/v3/ticker/bookTicker"

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t in resp_json or []:
            try:
                bid = float(t.get("bidPrice") or 0)
                ask = float(t.get("askPrice") or 0)
                if bid > 0 and ask > 0:
                    out[t["symbol"]] = (bid + ask) / 2
            except (TypeError, ValueError):
                continue
        return out


class GateTickerSource(BaseVenueTickerSource):
    venue_id = "gate"
    api_base = "https://api.gateio.ws"
    ticker_path = "/api/v4/spot/tickers"

    def normalise_pair(self, pair_universe_symbol: str) -> str:
        if pair_universe_symbol.endswith("USDT"):
            return pair_universe_symbol[:-4] + "_USDT"
        return pair_universe_symbol

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t in resp_json or []:
            try:
                last = float(t.get("last") or 0)
                if last > 0:
                    out[t["currency_pair"]] = last
            except (TypeError, ValueError):
                continue
        return out


class BitgetTickerSource(BaseVenueTickerSource):
    venue_id = "bitget"
    api_base = "https://api.bitget.com"
    ticker_path = "/api/v2/spot/market/tickers"

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t in (resp_json.get("data") or []):
            try:
                bid = float(t.get("bidPr") or 0)
                ask = float(t.get("askPr") or 0)
                if bid > 0 and ask > 0:
                    out[t["symbol"]] = (bid + ask) / 2
            except (TypeError, ValueError):
                continue
        return out


class BinanceReferenceTickerSource(BaseVenueTickerSource):
    venue_id = "binance_reference"
    api_base = "https://api.binance.com"
    ticker_path = "/api/v3/ticker/bookTicker"

    def __init__(self, *, ticker_cache, config_loader):
        super().__init__(ticker_cache=ticker_cache,
                         config_loader=config_loader,
                         reference_only=True)

    def parse_tickers(self, resp_json: Any) -> Dict[str, float]:
        out: Dict[str, float] = {}
        for t in resp_json or []:
            try:
                bid = float(t.get("bidPrice") or 0)
                ask = float(t.get("askPrice") or 0)
                if bid > 0 and ask > 0:
                    out[t["symbol"]] = (bid + ask) / 2
            except (TypeError, ValueError):
                continue
        return out


# All seven sources, indexed by venue_id for composition wiring
VENUE_SOURCE_CLASSES = {
    "bybit":             BybitTickerSource,
    "okx":               OKXTickerSource,
    "kucoin":            KucoinTickerSource,
    "mexc":              MexcTickerSource,
    "gate":              GateTickerSource,
    "bitget":            BitgetTickerSource,
    "binance_reference": BinanceReferenceTickerSource,
}


def build_all_sources(*, ticker_cache: TickerCache,
                      config_loader: Callable[[], Dict[str, Any]],
                      ) -> List[BaseVenueTickerSource]:
    sources: List[BaseVenueTickerSource] = []
    for vid, cls in VENUE_SOURCE_CLASSES.items():
        if vid == "binance_reference":
            sources.append(cls(ticker_cache=ticker_cache,
                               config_loader=config_loader))
        else:
            sources.append(cls(ticker_cache=ticker_cache,
                               config_loader=config_loader,
                               reference_only=False))
    return sources
