"""ArbiCore X — Phase D D-1: CEXOrderBookVerifier.

INV-2: This is the ONLY code path that constructs a CanonicalOpportunity
       from a DiscoveryCandidate. Reads authoritative order-book depth from
       each viable venue, picks the best buy/sell pair, runs the 5-gate
       filter, returns the resulting opp (or None).
INV-3: source_data_quality is sourced from the VENUE's SOURCE_REGISTRY
       classification — never from candidate.hint_source.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ...data.provenance import get_classification
from ...data.venue_capability_repo import VenueCapabilityRepository
from ...models.canonical import CanonicalOpportunity
from ...models.discovery import DiscoveryCandidate, VerifiedOutcome
from ...models.enums import (
    DataProvenance, MarketRegime, MevRiskLevel,
    OpportunityStatus, OpportunityType, RouteHealth,
)
from ..opportunity_verifier import OpportunityVerifier
from .filter import GateContext, run_five_gates
from .sources import VENUE_SOURCE_CLASSES

logger = logging.getLogger("arbicore.scanners.cex_arb.verifier")

# Public order-book endpoints (top-of-book + N levels of depth)
_ORDER_BOOK_ENDPOINTS = {
    "bybit":   ("https://api.bybit.com",     "/v5/market/orderbook?category=spot&symbol={sym}&limit=25"),
    "okx":     ("https://www.okx.com",        "/api/v5/market/books?instId={sym}&sz=25"),
    "kucoin":  ("https://api.kucoin.com",     "/api/v1/market/orderbook/level2_20?symbol={sym}"),
    "mexc":    ("https://api.mexc.com",       "/api/v3/depth?symbol={sym}&limit=25"),
    "gate":    ("https://api.gateio.ws",      "/api/v4/spot/order_book?currency_pair={sym}&limit=25"),
    "bitget":  ("https://api.bitget.com",     "/api/v2/spot/market/orderbook?symbol={sym}&limit=25"),
}

_VENUE_PROVENANCE = {
    "bybit": "bybit_public", "okx": "okx_public", "kucoin": "kucoin_public",
    "mexc": "mexc_public", "gate": "gate_public", "bitget": "bitget_public",
}

# All execution-eligible venues (excludes Binance reference)
_EXECUTION_VENUES = ["bybit", "okx", "kucoin", "mexc", "gate", "bitget"]


def _venue_pair(venue_id: str, pair_canonical: str) -> str:
    cls = VENUE_SOURCE_CLASSES.get(venue_id)
    if cls is None:
        return pair_canonical
    # Borrow normalise_pair from the source class
    return cls.normalise_pair(cls, pair_canonical)  # type: ignore[arg-type]


def _parse_book(venue_id: str, body: Any) -> Tuple[Optional[float], Optional[float],
                                                    Optional[float], Optional[float]]:
    """Return (best_bid, bid_depth_usd, best_ask, ask_depth_usd) or Nones."""
    try:
        if venue_id == "bybit":
            r = body.get("result", {})
            bids = r.get("b") or []; asks = r.get("a") or []
        elif venue_id == "okx":
            d = (body.get("data") or [{}])[0]
            bids = d.get("bids") or []; asks = d.get("asks") or []
        elif venue_id == "kucoin":
            d = body.get("data", {})
            bids = d.get("bids") or []; asks = d.get("asks") or []
        elif venue_id == "mexc":
            bids = body.get("bids") or []; asks = body.get("asks") or []
        elif venue_id == "gate":
            bids = body.get("bids") or []; asks = body.get("asks") or []
        elif venue_id == "bitget":
            d = body.get("data", {})
            bids = d.get("bids") or []; asks = d.get("asks") or []
        else:
            return None, None, None, None
        if not bids or not asks:
            return None, None, None, None
        best_bid = float(bids[0][0]); best_ask = float(asks[0][0])
        bid_depth = sum(float(b[0]) * float(b[1]) for b in bids[:10])
        ask_depth = sum(float(a[0]) * float(a[1]) for a in asks[:10])
        return best_bid, bid_depth, best_ask, ask_depth
    except Exception:  # noqa: BLE001
        return None, None, None, None


class CEXOrderBookVerifier(OpportunityVerifier):
    opportunity_type = OpportunityType.CEX_ARBITRAGE

    def __init__(self, *,
                 venue_capability_repo: VenueCapabilityRepository,
                 config_loader,
                 confidence_engine=None,
                 ) -> None:
        self._caps = venue_capability_repo
        self._cfg = config_loader
        self._confidence = confidence_engine
        self._client = httpx.AsyncClient(timeout=10.0)

    async def close(self) -> None:
        await self._client.aclose()

    async def verify(self, candidate: DiscoveryCandidate
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        if not candidate.asset or not candidate.asset.endswith("USDT"):
            return None, VerifiedOutcome.DENIED_VENUE_DISAGREES
        cfg = self._cfg() or {}

        # Read ALL execution-eligible venues' order books concurrently.
        # We don't trust the candidate.candidate_venues to be exhaustive — the
        # hint points to ONE venue with divergence; we find the best counterparty.
        venue_books: Dict[str, Tuple[float, float, float, float]] = {}
        for venue_id in _EXECUTION_VENUES:
            base, path_tpl = _ORDER_BOOK_ENDPOINTS[venue_id]
            sym = _venue_pair(venue_id, candidate.asset)
            url = base + path_tpl.format(sym=sym)
            try:
                r = await self._client.get(url)
                if r.status_code != 200:
                    continue
                bid, bid_d, ask, ask_d = _parse_book(venue_id, r.json())
                if bid and ask and bid_d and ask_d:
                    venue_books[venue_id] = (bid, bid_d, ask, ask_d)
            except Exception as exc:  # noqa: BLE001
                logger.debug("verifier book read failed %s/%s: %s",
                             venue_id, sym, exc)

        if len(venue_books) < 2:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        # Best buy = lowest ask; best sell = highest bid
        buy_venue = min(venue_books, key=lambda v: venue_books[v][2])
        sell_venue = max(venue_books, key=lambda v: venue_books[v][0])
        if buy_venue == sell_venue:
            return None, VerifiedOutcome.DENIED_VENUE_DISAGREES
        buy_bid, buy_bid_d, buy_ask, buy_ask_d = venue_books[buy_venue]
        sell_bid, sell_bid_d, sell_ask, sell_ask_d = venue_books[sell_venue]
        spread_pct = (sell_bid - buy_ask) / buy_ask * 100.0
        if spread_pct <= 0:
            return None, VerifiedOutcome.DENIED_VENUE_DISAGREES

        # Provenance: venue read (INV-3). Both venues are REAL.
        provenance = DataProvenance.REAL  # both sides classified REAL
        for vid in (buy_venue, sell_venue):
            cls = get_classification(_VENUE_PROVENANCE[vid])
            if cls is DataProvenance.DEAD:
                return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE
            if cls is DataProvenance.SIMULATED:
                provenance = DataProvenance.SIMULATED

        buy_side_depth_usd = buy_ask_d
        sell_side_depth_usd = sell_bid_d
        min_depth = min(buy_side_depth_usd, sell_side_depth_usd)

        # Build canonical opportunity (status will be set by 5-gate filter)
        epoch_min = int(time.time() / 60)
        opp_id = f"cexarb:{candidate.asset}:{buy_venue}->{sell_venue}:{epoch_min}"
        # Estimate expected profit for a $1000 trade
        notional = 1000.0
        expected_profit = notional * (spread_pct / 100.0)
        opp = CanonicalOpportunity(
            opportunity_id=opp_id,
            opportunity_type=OpportunityType.CEX_ARBITRAGE,
            subject_id=candidate.subject_id,
            asset=candidate.asset,
            chain=None,
            buy_venue=buy_venue,
            sell_venue=sell_venue,
            buy_price=buy_ask,
            sell_price=sell_bid,
            spread_pct=round(spread_pct, 4),
            expected_profit_usd=round(expected_profit, 4),
            capital_required_usd=notional,
            confidence_score=0.0,  # gate 4 sets this
            risk_score=0.0,
            liquidity_score=80.0 if min_depth >= 5000 else 30.0,
            execution_feasibility=0.7,
            mev_risk_level=MevRiskLevel.LOW,
            market_regime=MarketRegime.UNKNOWN,
            route_health=RouteHealth.NEW,
            source_data_quality=provenance,
            status=OpportunityStatus.CANDIDATE,
            category_metadata={
                "best_bid_price": sell_bid,
                "best_ask_price": buy_ask,
                "profitable_buyer_depth_usd": sell_side_depth_usd,
                "fee_drag_pct": 0.2,
            },
            metadata={
                "scanner": "cex_arb",
                "tier": "primary",
                "discovery_candidate_id": candidate.candidate_id,
                "discovery_source": candidate.hint_source,
                "discovery_reason": candidate.reason,
                "buy_side_depth_usd": buy_side_depth_usd,
                "sell_side_depth_usd": sell_side_depth_usd,
            },
        )

        # Run 5-gate filter
        gate_ctx = GateContext(
            cfg=cfg,
            venue_caps=self._caps,
            buy_venue=buy_venue,
            sell_venue=sell_venue,
            buy_side_depth_usd=buy_side_depth_usd,
            sell_side_depth_usd=sell_side_depth_usd,
            confidence_engine=self._confidence,
        )
        passed, gate, reason = await run_five_gates(opp, gate_ctx)
        if passed:
            opp.status = OpportunityStatus.VALIDATED
            return opp, VerifiedOutcome.CONFIRMED_PREFIX + opp_id
        # Still emit a CANDIDATE row with rejection metadata for gate analysis
        if opp.metadata is None:
            opp.metadata = {}
        opp.metadata["rejected_at_gate"] = gate
        opp.metadata["rejected_gate_name"] = reason.split(":")[0] if reason else ""
        opp.metadata["rejected_reason"] = reason
        return opp, VerifiedOutcome.DENIED_GATE_PREFIX + (reason or "unknown")
