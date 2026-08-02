"""ArbiCore X — Phase D D-2.0 per-venue funding-rate discovery sources.

Each ``_BaseFundingSource`` subclass polls ONE venue's perp/futures funding
API and emits ``DiscoveryCandidate`` rows when the absolute annualised
funding rate exceeds the configured threshold. Sources are HINT providers
only (INV-1) and never construct ``CanonicalOpportunity`` (INV-2, INV-3).
A future ``FundingDifferentialVerifier`` will read funding directly from
both candidate venues and emit canonical rows from there.

Design notes (per operator directive on this checkpoint):

- Each subclass is INDEPENDENT and venue-specific. No symbol-mapping or
  parsing logic is shared across venues — each venue's raw API quirks
  stay in its own subclass.
- Each subclass captures RAW funding metadata in
  ``hint_metric.raw`` so future learning layers can extract venue-
  specific signals without revisiting the source integration.
- Hyperliquid is the only venue with an hourly funding interval; the
  rest are 8h. The interval is reported in every observation so
  downstream code never has to assume.
- Threshold filtering happens at the source layer (emission contract) —
  the source emits ONLY when the venue's funding signal is interesting.
  No opportunity scoring, ranking, or differential computation is done
  here — that is the verifier's job.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx

from ...models.discovery import DiscoveryCandidate, SourceHealth, make_candidate_id
from ...models.enums import DataProvenance, OpportunityType
from ..discovery_source import DiscoverySource

logger = logging.getLogger("arbicore.scanners.funding_arb.sources")


# ============================================================================
# Funding observation — venue-agnostic shape with raw venue data preserved.
# ============================================================================

@dataclass
class FundingObservation:
    """One venue's read of one perp contract's funding state.

    Each venue subclass returns a list of these. Raw venue-specific fields
    are retained in ``raw`` so future learning code can dig into per-venue
    quirks without modifying source integrations.
    """
    venue: str                          # canonical venue id (e.g. "bybit")
    venue_symbol: str                   # native symbol (e.g. "BTCUSDT", "BTC-USDT-SWAP", "BTC_USDT")
    subject_id: str                     # canonical base symbol (e.g. "BTC")
    canonical_asset: str                # canonical perp identifier (e.g. "BTC-PERP")
    funding_rate_pct: float             # per-interval rate, signed, in %
    funding_interval_h: int             # venue-reported funding interval
    next_funding_ts: Optional[float]    # unix ts of next settlement (None if unknown)
    mark_price: Optional[float] = None
    index_price: Optional[float] = None
    open_interest_usd: Optional[float] = None
    source_observed_at_ts: float = field(default_factory=lambda: time.time())
    raw: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Base class — shared infrastructure only (cadence, 429, candidate build).
# Subclasses override _fetch_observations() and _symbol_to_base() only.
# ============================================================================

class _BaseFundingSource(DiscoverySource):
    """Shared D-2 funding source plumbing.

    Subclass contract:
      - Set ``source_id``, ``venue_id``, ``venue_provenance_id``,
        ``default_funding_interval_h``.
      - Override ``_fetch_observations(self) -> list[FundingObservation]``.
        Should return an empty list on transient failure (after setting
        ``self._last_error``).
      - May override ``_symbol_to_base(sym)`` if symbol mapping requires it.
      - May override ``cadence_s`` and ``_request_timeout_s``.
    """

    # Subclasses override these:
    source_id: str = ""
    venue_id: str = ""
    venue_provenance_id: str = ""
    default_funding_interval_h: int = 8

    # Common DiscoverySource fields
    opportunity_types = {OpportunityType.FUNDING_ARBITRAGE}
    tier = 1
    provenance_of_hint = DataProvenance.REAL  # telemetry only — INV-3
    cadence_s: int = 60                       # default; some venues override

    _request_timeout_s: float = 10.0
    _consecutive_429_lockout: int = 3
    _cooldown_after_lockout_s: float = 600.0

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]]) -> None:
        self._cfg = config_loader
        self._client = httpx.AsyncClient(
            timeout=self._request_timeout_s,
            headers={"User-Agent": "ArbiCoreX/D-2.0"},
        )
        self._last_emission_at: Optional[float] = None
        self._last_error: Optional[str] = None
        self._last_latency_ms = 0
        self._consecutive_429 = 0
        self._last_discover_at: float = 0.0
        self._last_observations_count: int = 0   # diagnostics: raw observations last cycle

    async def close(self) -> None:
        await self._client.aclose()

    # ---- DiscoverySource implementation -----------------------------------

    async def discover(self) -> List[DiscoveryCandidate]:
        cfg = self._cfg() or {}
        src_cfg = (cfg.get("discovery_sources", {})
                      .get(self.source_id, {}))
        if src_cfg.get("enabled") is False:
            return []
        if self._consecutive_429 >= self._consecutive_429_lockout:
            now_mono = time.monotonic()
            if (self._last_discover_at > 0
                    and (now_mono - self._last_discover_at)
                    >= self._cooldown_after_lockout_s):
                self._consecutive_429 = 0
                self._last_error = None
            else:
                return []
        # Honour declared cadence even if the scanner ticks faster.
        now_mono = time.monotonic()
        if (now_mono - self._last_discover_at) < self.cadence_s:
            return []
        self._last_discover_at = now_mono

        threshold_apr_pct = float(src_cfg.get(
            "venue_funding_threshold_apr_pct", 5.0))
        target_assets = src_cfg.get("target_assets") or None   # None ⇒ all

        t0 = time.monotonic()
        try:
            observations = await self._fetch_observations()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"fetch: {exc!r}"
            return []
        self._last_latency_ms = int((time.monotonic() - t0) * 1000)
        self._last_observations_count = len(observations)

        if observations:
            # We touched the venue successfully even if no observation was
            # interesting enough to emit a hint — clear transient errors.
            self._last_error = None
            self._consecutive_429 = 0

        out: List[DiscoveryCandidate] = []
        for obs in observations:
            if target_assets is not None and obs.subject_id not in target_assets:
                continue
            funding_apr_pct = self._annualise(
                obs.funding_rate_pct, obs.funding_interval_h)
            if abs(funding_apr_pct) < threshold_apr_pct:
                continue
            cid = make_candidate_id(
                hint_source=self.source_id,
                opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
                subject_id=obs.subject_id,
                asset=obs.canonical_asset,
                candidate_venues=[obs.venue],
                hint_observed_at=obs.source_observed_at_ts,
            )
            next_iso = (datetime.fromtimestamp(obs.next_funding_ts,
                                                tz=timezone.utc).isoformat()
                        if obs.next_funding_ts else None)
            out.append(DiscoveryCandidate(
                candidate_id=cid,
                opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
                hint_source=self.source_id,
                hint_observed_at=obs.source_observed_at_ts,
                subject_id=obs.subject_id,
                asset=obs.canonical_asset,
                candidate_venues=[obs.venue],
                hint_metric={
                    # ── Canonical funding fields (cross-venue comparable) ──
                    "venue": obs.venue,
                    "venue_symbol": obs.venue_symbol,
                    "funding_rate_pct":      obs.funding_rate_pct,
                    "funding_interval_h":    obs.funding_interval_h,
                    "funding_apr_pct":       round(funding_apr_pct, 4),
                    "next_funding_ts":       obs.next_funding_ts,
                    "next_funding_iso":      next_iso,
                    "mark_price":            obs.mark_price,
                    "index_price":           obs.index_price,
                    "open_interest_usd":     obs.open_interest_usd,
                    "source_observed_at_ts": obs.source_observed_at_ts,
                    "threshold_apr_pct":     threshold_apr_pct,
                    # ── INV-3 provenance documentation ──
                    "venue_funding_provenance_id": self.venue_provenance_id,
                    # ── Raw venue-specific payload (for future learning) ──
                    "raw": obs.raw,
                },
                reason="venue_funding_above_threshold",
            ))
        if out:
            self._last_emission_at = time.time()
        return out

    async def health(self) -> SourceHealth:
        return SourceHealth(
            source_id=self.source_id,
            ok=(self._last_error is None
                and self._consecutive_429 < self._consecutive_429_lockout),
            latency_ms=self._last_latency_ms,
            last_emission_at=self._last_emission_at,
            last_error=self._last_error,
        )

    # ---- Helpers (shared, but venue-agnostic) -----------------------------

    @staticmethod
    def _annualise(rate_pct: float, interval_h: int) -> float:
        if interval_h <= 0:
            return 0.0
        return rate_pct * (24.0 / float(interval_h)) * 365.0

    def _handle_http_status(self, status_code: int) -> None:
        """Common 429 self-protection. Subclasses call this on each HTTP
        response before parsing."""
        if status_code == 429:
            self._consecutive_429 += 1
            self._last_error = "rate_limited:429"
            logger.warning("%s: 429 (%d consecutive)",
                           self.source_id, self._consecutive_429)

    # ---- Subclass contract ------------------------------------------------

    async def _fetch_observations(self) -> List[FundingObservation]:
        raise NotImplementedError


# ============================================================================
# 1. Bybit — single-call batch via /v5/market/tickers?category=linear
# ============================================================================

class BybitFundingSource(_BaseFundingSource):
    source_id = "venue_funding:bybit"
    venue_id = "bybit"
    venue_provenance_id = "bybit_futures_public"
    default_funding_interval_h = 8

    async def _fetch_observations(self) -> List[FundingObservation]:
        url = "https://api.bybit.com/v5/market/tickers?category=linear"
        r = await self._client.get(url)
        self._handle_http_status(r.status_code)
        if r.status_code != 200:
            self._last_error = self._last_error or f"http_{r.status_code}"
            return []
        try:
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"parse: {exc!r}"
            return []
        result = (body.get("result") or {}).get("list") or []
        observations: List[FundingObservation] = []
        now = time.time()
        for row in result:
            try:
                sym = row.get("symbol") or ""
                base = self._symbol_to_base(sym)
                if base is None:
                    continue
                # Bybit reports funding as decimal fraction (e.g. 0.0001 = 0.01%)
                fr = float(row.get("fundingRate") or 0.0) * 100.0
                next_ts_ms = row.get("nextFundingTime")
                next_ts = float(next_ts_ms) / 1000.0 if next_ts_ms else None
                mark = float(row.get("markPrice") or 0.0) or None
                idx = float(row.get("indexPrice") or 0.0) or None
                oi_usd = (float(row.get("openInterestValue") or 0.0) or None)
                observations.append(FundingObservation(
                    venue=self.venue_id,
                    venue_symbol=sym,
                    subject_id=base,
                    canonical_asset=f"{base}-PERP",
                    funding_rate_pct=fr,
                    funding_interval_h=self.default_funding_interval_h,
                    next_funding_ts=next_ts,
                    mark_price=mark,
                    index_price=idx,
                    open_interest_usd=oi_usd,
                    source_observed_at_ts=now,
                    raw=row,
                ))
            except (TypeError, ValueError):
                continue
        return observations

    @staticmethod
    def _symbol_to_base(sym: str) -> Optional[str]:
        """Bybit linear perps are e.g. ``BTCUSDT``. We accept ONLY pure
        ``<BASE>USDT`` (no dated futures, no quanto contracts)."""
        s = sym.upper()
        if not s.endswith("USDT"):
            return None
        base = s[:-4]
        # Reject quanto / inverse-style suffixes (e.g. BTCUSDT_25SEP25 has '_')
        if not base or "_" in base or "-" in base or base.isdigit():
            return None
        return base


# ============================================================================
# 2. OKX — funding per instrument; /api/v5/public/funding-rate?instId=...
#    We use the SWAPS list endpoint to discover instIds, then per-symbol
#    funding. For batch efficiency we limit to a configured asset list.
# ============================================================================

class OKXFundingSource(_BaseFundingSource):
    source_id = "venue_funding:okx"
    venue_id = "okx"
    venue_provenance_id = "okx_futures_public"
    default_funding_interval_h = 8

    # OKX free tier is generous — we still cap concurrency.
    _SEM_LIMIT = 4

    def __init__(self, *, config_loader):
        super().__init__(config_loader=config_loader)
        self._sem = asyncio.Semaphore(self._SEM_LIMIT)

    async def _fetch_observations(self) -> List[FundingObservation]:
        cfg = self._cfg() or {}
        src_cfg = (cfg.get("discovery_sources", {})
                      .get(self.source_id, {}))
        # OKX requires per-instrument calls; we cap to a configured list.
        bases = src_cfg.get("okx_target_bases") or [
            "BTC", "ETH", "SOL", "BNB", "XRP", "DOGE", "ADA", "LINK", "AVAX", "TRX",
        ]
        inst_ids = [f"{b}-USDT-SWAP" for b in bases]
        results = await asyncio.gather(
            *[self._fetch_one(iid) for iid in inst_ids],
            return_exceptions=True,
        )
        out: List[FundingObservation] = []
        for r in results:
            if isinstance(r, Exception) or r is None:
                continue
            out.append(r)
        return out

    async def _fetch_one(self, inst_id: str) -> Optional[FundingObservation]:
        url = f"https://www.okx.com/api/v5/public/funding-rate?instId={inst_id}"
        async with self._sem:
            r = await self._client.get(url)
        self._handle_http_status(r.status_code)
        if r.status_code != 200:
            return None
        try:
            body = r.json()
            data = (body.get("data") or [])
            if not data:
                return None
            d = data[0]
            base = self._symbol_to_base(inst_id)
            if base is None:
                return None
            fr_raw = d.get("fundingRate")
            if fr_raw in (None, ""):
                return None
            fr = float(fr_raw) * 100.0
            next_ts_ms = d.get("nextFundingTime")
            next_ts = float(next_ts_ms) / 1000.0 if next_ts_ms else None
            # OKX returns funding interval in some endpoints but not this one;
            # default 8h is correct for USDT-margined swaps at time of writing.
            return FundingObservation(
                venue=self.venue_id,
                venue_symbol=inst_id,
                subject_id=base,
                canonical_asset=f"{base}-PERP",
                funding_rate_pct=fr,
                funding_interval_h=self.default_funding_interval_h,
                next_funding_ts=next_ts,
                source_observed_at_ts=time.time(),
                raw=d,
            )
        except (TypeError, ValueError, KeyError):
            return None

    @staticmethod
    def _symbol_to_base(sym: str) -> Optional[str]:
        # Expecting "BTC-USDT-SWAP". Anything else → reject.
        parts = sym.upper().split("-")
        if len(parts) != 3 or parts[1] != "USDT" or parts[2] != "SWAP":
            return None
        return parts[0]


# ============================================================================
# 3. Gate.io — /api/v4/futures/usdt/tickers gives all funding rates in
#    a single batch call. We separately read /contracts to learn
#    funding intervals per contract.
# ============================================================================

class GateFundingSource(_BaseFundingSource):
    source_id = "venue_funding:gate"
    venue_id = "gate"
    venue_provenance_id = "gate_futures_public"
    default_funding_interval_h = 8

    async def _fetch_observations(self) -> List[FundingObservation]:
        tickers_url = "https://api.gateio.ws/api/v4/futures/usdt/tickers"
        contracts_url = "https://api.gateio.ws/api/v4/futures/usdt/contracts"
        r_t, r_c = await asyncio.gather(
            self._client.get(tickers_url),
            self._client.get(contracts_url),
            return_exceptions=True,
        )
        if isinstance(r_t, Exception):
            self._last_error = f"tickers: {r_t!r}"
            return []
        self._handle_http_status(r_t.status_code)
        if r_t.status_code != 200:
            self._last_error = self._last_error or f"tickers_http_{r_t.status_code}"
            return []
        try:
            tickers = r_t.json()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"parse_tickers: {exc!r}"
            return []
        # Per-contract funding intervals (in seconds). Best-effort.
        interval_h_by_sym: Dict[str, int] = {}
        if (not isinstance(r_c, Exception)
                and getattr(r_c, "status_code", 0) == 200):
            try:
                for c in r_c.json():
                    sym = c.get("name")
                    if not sym:
                        continue
                    secs = int(c.get("funding_interval") or 0)
                    if secs > 0:
                        interval_h_by_sym[sym] = max(1, round(secs / 3600))
            except Exception:  # noqa: BLE001
                pass

        observations: List[FundingObservation] = []
        now = time.time()
        for t in tickers:
            try:
                sym = t.get("contract") or ""
                base = self._symbol_to_base(sym)
                if base is None:
                    continue
                fr_raw = t.get("funding_rate")
                if fr_raw in (None, ""):
                    continue
                fr = float(fr_raw) * 100.0
                next_ts = t.get("funding_next_apply")
                next_ts_f = float(next_ts) if next_ts else None
                interval_h = interval_h_by_sym.get(
                    sym, self.default_funding_interval_h)
                mark = float(t.get("mark_price") or 0.0) or None
                idx = float(t.get("index_price") or 0.0) or None
                observations.append(FundingObservation(
                    venue=self.venue_id,
                    venue_symbol=sym,
                    subject_id=base,
                    canonical_asset=f"{base}-PERP",
                    funding_rate_pct=fr,
                    funding_interval_h=interval_h,
                    next_funding_ts=next_ts_f,
                    mark_price=mark,
                    index_price=idx,
                    source_observed_at_ts=now,
                    raw=t,
                ))
            except (TypeError, ValueError):
                continue
        return observations

    @staticmethod
    def _symbol_to_base(sym: str) -> Optional[str]:
        # Gate USDT futures symbols are e.g. "BTC_USDT".
        s = sym.upper()
        if not s.endswith("_USDT"):
            return None
        base = s[:-5]
        if not base or "_" in base:
            return None
        return base


# ============================================================================
# 4. Bitget — /api/v2/mix/market/tickers?productType=USDT-FUTURES
# ============================================================================

class BitgetFundingSource(_BaseFundingSource):
    source_id = "venue_funding:bitget"
    venue_id = "bitget"
    venue_provenance_id = "bitget_futures_public"
    default_funding_interval_h = 8

    async def _fetch_observations(self) -> List[FundingObservation]:
        url = ("https://api.bitget.com/api/v2/mix/market/tickers"
               "?productType=USDT-FUTURES")
        r = await self._client.get(url)
        self._handle_http_status(r.status_code)
        if r.status_code != 200:
            self._last_error = self._last_error or f"http_{r.status_code}"
            return []
        try:
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"parse: {exc!r}"
            return []
        data = body.get("data") or []
        observations: List[FundingObservation] = []
        now = time.time()
        for row in data:
            try:
                sym = row.get("symbol") or ""
                base = self._symbol_to_base(sym)
                if base is None:
                    continue
                # Bitget reports fundingRate as decimal fraction.
                fr_raw = row.get("fundingRate")
                if fr_raw in (None, ""):
                    continue
                fr = float(fr_raw) * 100.0
                # Bitget "nextFundingTime" in ms epoch (when present).
                nft = row.get("nextFundingTime")
                next_ts = float(nft) / 1000.0 if nft else None
                mark = float(row.get("markPrice") or 0.0) or None
                idx = float(row.get("indexPrice") or 0.0) or None
                observations.append(FundingObservation(
                    venue=self.venue_id,
                    venue_symbol=sym,
                    subject_id=base,
                    canonical_asset=f"{base}-PERP",
                    funding_rate_pct=fr,
                    funding_interval_h=self.default_funding_interval_h,
                    next_funding_ts=next_ts,
                    mark_price=mark,
                    index_price=idx,
                    source_observed_at_ts=now,
                    raw=row,
                ))
            except (TypeError, ValueError):
                continue
        return observations

    @staticmethod
    def _symbol_to_base(sym: str) -> Optional[str]:
        s = sym.upper()
        if not s.endswith("USDT"):
            return None
        base = s[:-4]
        if not base or "_" in base or "-" in base or base.isdigit():
            return None
        return base


# ============================================================================
# 5. MEXC — /api/v1/contract/funding_rate (one shot, all contracts)
# ============================================================================

class MEXCFundingSource(_BaseFundingSource):
    source_id = "venue_funding:mexc"
    venue_id = "mexc"
    venue_provenance_id = "mexc_futures_public"
    default_funding_interval_h = 8

    async def _fetch_observations(self) -> List[FundingObservation]:
        url = "https://contract.mexc.com/api/v1/contract/funding_rate"
        r = await self._client.get(url)
        self._handle_http_status(r.status_code)
        if r.status_code != 200:
            self._last_error = self._last_error or f"http_{r.status_code}"
            return []
        try:
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"parse: {exc!r}"
            return []
        data = body.get("data") or []
        observations: List[FundingObservation] = []
        now = time.time()
        for row in data:
            try:
                sym = row.get("symbol") or ""
                base = self._symbol_to_base(sym)
                if base is None:
                    continue
                fr_raw = row.get("fundingRate")
                if fr_raw in (None, ""):
                    continue
                fr = float(fr_raw) * 100.0
                next_ts_ms = row.get("nextSettleTime")
                next_ts = float(next_ts_ms) / 1000.0 if next_ts_ms else None
                # MEXC reports collectCycle in hours sometimes; default 8h.
                cc = row.get("collectCycle")
                interval_h = int(cc) if cc else self.default_funding_interval_h
                observations.append(FundingObservation(
                    venue=self.venue_id,
                    venue_symbol=sym,
                    subject_id=base,
                    canonical_asset=f"{base}-PERP",
                    funding_rate_pct=fr,
                    funding_interval_h=interval_h,
                    next_funding_ts=next_ts,
                    source_observed_at_ts=now,
                    raw=row,
                ))
            except (TypeError, ValueError):
                continue
        return observations

    @staticmethod
    def _symbol_to_base(sym: str) -> Optional[str]:
        # MEXC contracts are e.g. "BTC_USDT".
        s = sym.upper()
        if not s.endswith("_USDT"):
            return None
        base = s[:-5]
        if not base or "_" in base:
            return None
        return base


# ============================================================================
# 6. KuCoin Futures — /api/v1/contracts/active
#    Each active contract document carries fundingFeeRate + nextFundingRateTime.
# ============================================================================

class KuCoinFuturesFundingSource(_BaseFundingSource):
    source_id = "venue_funding:kucoin"
    venue_id = "kucoin"
    venue_provenance_id = "kucoin_futures_public"
    default_funding_interval_h = 8

    async def _fetch_observations(self) -> List[FundingObservation]:
        url = "https://api-futures.kucoin.com/api/v1/contracts/active"
        r = await self._client.get(url)
        self._handle_http_status(r.status_code)
        if r.status_code != 200:
            self._last_error = self._last_error or f"http_{r.status_code}"
            return []
        try:
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"parse: {exc!r}"
            return []
        data = body.get("data") or []
        observations: List[FundingObservation] = []
        now = time.time()
        for c in data:
            try:
                sym = c.get("symbol") or ""
                base = self._symbol_to_base(sym)
                if base is None:
                    continue
                fr_raw = c.get("fundingFeeRate")
                if fr_raw in (None, ""):
                    continue
                fr = float(fr_raw) * 100.0
                nft = c.get("nextFundingRateTime")
                # KuCoin "nextFundingRateTime" is ms-remaining, not absolute.
                next_ts = (now + float(nft) / 1000.0) if nft else None
                interval_ms = c.get("fundingRateGranularity")
                interval_h = (max(1, round(int(interval_ms) / 3_600_000))
                              if interval_ms else self.default_funding_interval_h)
                mark = float(c.get("markPrice") or 0.0) or None
                idx = float(c.get("indexPrice") or 0.0) or None
                observations.append(FundingObservation(
                    venue=self.venue_id,
                    venue_symbol=sym,
                    subject_id=base,
                    canonical_asset=f"{base}-PERP",
                    funding_rate_pct=fr,
                    funding_interval_h=interval_h,
                    next_funding_ts=next_ts,
                    mark_price=mark,
                    index_price=idx,
                    source_observed_at_ts=now,
                    raw=c,
                ))
            except (TypeError, ValueError):
                continue
        return observations

    @staticmethod
    def _symbol_to_base(sym: str) -> Optional[str]:
        """KuCoin Futures USDT-margined perp symbols end in ``USDTM``.

        Special case: KuCoin uses ``XBT`` instead of ``BTC`` on the futures
        side, so ``XBTUSDTM`` → canonical base ``BTC``."""
        s = sym.upper()
        if not s.endswith("USDTM"):
            return None
        base = s[:-5]
        if not base or "_" in base or "-" in base:
            return None
        if base == "XBT":
            return "BTC"
        return base


# ============================================================================
# 7. Hyperliquid — POST /info {type:"metaAndAssetCtxs"}
#    Funding interval is 1h (the only D-2 venue not on 8h).
#    Marked experimental — operator-removable via per-source kill switch.
# ============================================================================

class HyperliquidFundingSource(_BaseFundingSource):
    source_id = "venue_funding:hyperliquid"
    venue_id = "hyperliquid"
    venue_provenance_id = "hyperliquid_public"
    default_funding_interval_h = 1   # hourly funding — venue-specific

    async def _fetch_observations(self) -> List[FundingObservation]:
        url = "https://api.hyperliquid.xyz/info"
        try:
            r = await self._client.post(
                url,
                json={"type": "metaAndAssetCtxs"},
                headers={"Content-Type": "application/json"},
            )
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"http: {exc!r}"
            return []
        self._handle_http_status(r.status_code)
        if r.status_code != 200:
            self._last_error = self._last_error or f"http_{r.status_code}"
            return []
        try:
            body = r.json()
        except Exception as exc:  # noqa: BLE001
            self._last_error = f"parse: {exc!r}"
            return []
        # Hyperliquid returns a 2-tuple: [meta, asset_ctxs]
        if not isinstance(body, list) or len(body) < 2:
            self._last_error = "unexpected_response_shape"
            return []
        meta, ctxs = body[0], body[1]
        universe = (meta or {}).get("universe") or []
        if len(universe) != len(ctxs):
            # Hyperliquid expects 1:1 by index; abort cleanly on mismatch.
            self._last_error = "universe_ctxs_length_mismatch"
            return []
        observations: List[FundingObservation] = []
        now = time.time()
        for asset_meta, ctx in zip(universe, ctxs):
            try:
                name = asset_meta.get("name") or ""
                base = self._symbol_to_base(name)
                if base is None:
                    continue
                # Hyperliquid reports funding rate as decimal per HOUR.
                fr_raw = ctx.get("funding")
                if fr_raw in (None, ""):
                    continue
                fr = float(fr_raw) * 100.0   # → per-hour %
                mark = float(ctx.get("markPx") or 0.0) or None
                oracle = float(ctx.get("oraclePx") or 0.0) or None
                oi_coins = float(ctx.get("openInterest") or 0.0)
                oi_usd = oi_coins * mark if mark else None
                # No nextFundingTime in this endpoint — funding is hourly.
                # Compute next top-of-hour as a best-effort approximation.
                next_ts = (int(now // 3600) + 1) * 3600.0
                observations.append(FundingObservation(
                    venue=self.venue_id,
                    venue_symbol=name,
                    subject_id=base,
                    canonical_asset=f"{base}-PERP",
                    funding_rate_pct=fr,
                    funding_interval_h=self.default_funding_interval_h,
                    next_funding_ts=next_ts,
                    mark_price=mark,
                    index_price=oracle,
                    open_interest_usd=oi_usd,
                    source_observed_at_ts=now,
                    raw={"meta": asset_meta, "ctx": ctx},
                ))
            except (TypeError, ValueError):
                continue
        return observations

    @staticmethod
    def _symbol_to_base(sym: str) -> Optional[str]:
        # Hyperliquid asset names are just the base (e.g. "BTC", "ETH").
        s = sym.upper()
        if not s or any(ch in s for ch in "-_/"):
            return None
        return s


# ============================================================================
# Factory + venue index
# ============================================================================

VENUE_FUNDING_SOURCE_CLASSES: Dict[str, type] = {
    "bybit":       BybitFundingSource,
    "okx":         OKXFundingSource,
    "gate":        GateFundingSource,
    "bitget":      BitgetFundingSource,
    "mexc":        MEXCFundingSource,
    "kucoin":      KuCoinFuturesFundingSource,
    "hyperliquid": HyperliquidFundingSource,
}


def build_all_funding_sources(
    *, config_loader: Callable[[], Dict[str, Any]],
) -> List[_BaseFundingSource]:
    """Construct one instance of every venue funding source."""
    return [cls(config_loader=config_loader)
            for cls in VENUE_FUNDING_SOURCE_CLASSES.values()]
