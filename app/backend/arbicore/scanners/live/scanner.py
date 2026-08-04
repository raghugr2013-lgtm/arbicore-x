"""Live Market Scanner (Stage 2 · v2.5.0).

Replaces ``ShadowScannerAdapter`` as the opportunity producer.

Every tick:
  1. Polls the enabled CEX providers via the ProviderRegistry for canonical
     symbols (default: BTC/USDT, ETH/USDT).
  2. Computes the cross-venue best-bid / best-ask spread.
  3. When the spread exceeds ``LIVE_MIN_SPREAD_BPS`` and both venues report
     non-zero depth, produces one real opportunity event:
       - opportunity_type = "cex_spot_arbitrage"
       - chain = "cex"
       - venue_buy / venue_sell / gross bps / est_profit_usd on
         ``LIVE_QUOTE_NOTIONAL_USD``
     and writes it into MID via the existing ``ScannerEvidenceBridge``.
  4. Forwards the same opportunity to the Paper Engine, which will
     compute EV / confidence / execution_probability (Phase 6).

Zero signing. Zero trading. Zero wallet interaction. Kill switch and
capital caps still apply.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...data.mid.readers import MidReader
from ...data.mid.writers import MidWriter
from ...providers.base import ProviderKind
from ...providers.registry import ProviderRegistry
from ...scanners.wave1b.bridge import ScannerEvidenceBridge

logger = logging.getLogger(__name__)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _flt(name: str, default: float) -> float:
    v = os.environ.get(name)
    try:
        return float(v) if v not in (None, "") else default
    except ValueError:
        return default


def _int(name: str, default: int) -> int:
    v = os.environ.get(name)
    try:
        return int(v) if v not in (None, "") else default
    except ValueError:
        return default


def _csv(name: str, default: str) -> List[str]:
    return [s.strip() for s in os.environ.get(name, default).split(",")
             if s.strip()]


class LiveMarketScanner:
    """Cross-venue CEX spread scanner. Read-only. OBSERVE mode."""

    scanner_id = "live_market"
    mode = "observe"

    def __init__(
        self,
        *,
        registry: ProviderRegistry,
        bridge: ScannerEvidenceBridge,
        mid_reader: MidReader,
        paper_engine: Any = None,
        symbols: Optional[List[str]] = None,
        tick_interval_s: float = 15.0,
        min_spread_bps: float = 5.0,
        notional_usd: float = 10_000.0,
    ) -> None:
        self._registry = registry
        self._bridge = bridge
        self._mid = mid_reader
        self._paper = paper_engine
        self._symbols = symbols or _csv("LIVE_SYMBOLS", "BTC/USDT,ETH/USDT")
        self._interval = float(tick_interval_s)
        self._min_spread_bps = float(min_spread_bps)
        self._notional_usd = float(notional_usd)

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._last_ticker_cache: Dict[str, Dict[str, Any]] = {}
        self._stats: Dict[str, Any] = {
            "iterations": 0,
            "quotes_collected": 0,
            "opportunities_emitted": 0,
            "cex_venues_polled": 0,
            "last_run_at": None,
            "last_error": None,
            "started_at": None,
            "stopped_at": None,
            "symbols": list(self._symbols),
        }

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    @property
    def last_prices(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._last_ticker_cache)

    async def start(self) -> Dict[str, Any]:
        if self.is_running():
            return {"already_running": True}
        self._stop.clear()
        self._stats["started_at"] = _iso()
        self._stats["stopped_at"] = None
        self._task = asyncio.create_task(self._loop(),
                                            name="arbicore_live_market_scanner")
        logger.info("live_market: scanner started")
        return {"started": True, "started_at": self._stats["started_at"]}

    async def stop(self) -> Dict[str, Any]:
        if not self.is_running():
            return {"already_stopped": True}
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5.0)
        except asyncio.TimeoutError:
            self._task.cancel()
        self._stats["stopped_at"] = _iso()
        logger.info("live_market: scanner stopped")
        return {"stopped": True, "stopped_at": self._stats["stopped_at"]}

    # ------------------------------------------------------------------
    # loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            try:
                await self._tick()
            except Exception as exc:                                 # noqa
                self._stats["last_error"] = f"tick: {exc!r}"
                logger.exception("live_market tick failed: %s", exc)
            self._stats["iterations"] += 1
            self._stats["last_run_at"] = _iso()
            elapsed = time.time() - t0
            try:
                await asyncio.wait_for(self._stop.wait(),
                                          timeout=max(0.0, self._interval - elapsed))
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:
        # collect CEX tickers for every symbol
        cex_providers = [self._registry.get(h.provider_id)
                          for h in self._registry.list(
                              kind=ProviderKind.QUOTE_AGGREGATOR)
                          if getattr(self._registry.get(h.provider_id),
                                       "chain", None) == "cex"]
        cex_providers = [p for p in cex_providers if p is not None]
        self._stats["cex_venues_polled"] = len(cex_providers)
        if not cex_providers:
            return

        for symbol in self._symbols:
            tickers = await asyncio.gather(
                *(_safe_ticker(p, symbol) for p in cex_providers),
                return_exceptions=False,
            )
            valid = [t for t in tickers
                      if t and t.get("bid") and t.get("ask")]
            if not valid:
                continue
            self._stats["quotes_collected"] += len(valid)
            self._last_ticker_cache[symbol] = {
                "symbol": symbol, "ts": _iso(),
                "venues": [{"venue": t["venue"], "bid": t["bid"],
                             "ask": t["ask"], "last": t["last"],
                             "spread_bps": t["spread_bps"]}
                            for t in valid],
                "best_bid": max(valid, key=lambda t: t["bid"]),
                "best_ask": min(valid, key=lambda t: t["ask"]),
            }
            await self._maybe_emit(symbol, valid)

    async def _maybe_emit(self, symbol: str,
                            tickers: List[Dict[str, Any]]) -> None:
        from ...economics import (compute_net_profit, VENUE_FEE_BPS,
                                     WITHDRAWAL_FEE_USD)
        best_bid = max(tickers, key=lambda t: t["bid"])
        best_ask = min(tickers, key=lambda t: t["ask"])
        if best_bid["venue"] == best_ask["venue"]:
            return
        if not (best_ask["ask"] and best_bid["bid"]):
            return
        spread = (best_bid["bid"] - best_ask["ask"]) / best_ask["ask"]
        spread_bps = spread * 10_000.0
        if spread_bps < self._min_spread_bps:
            return

        buy_venue = best_ask["venue"]
        sell_venue = best_bid["venue"]
        net = compute_net_profit(
            gross_spread_bps=spread_bps,
            notional_usd=self._notional_usd,
            buy_venue_fee_bps=VENUE_FEE_BPS.get(buy_venue, 30.0),
            sell_venue_fee_bps=VENUE_FEE_BPS.get(sell_venue, 30.0),
            withdrawal_fee_usd=WITHDRAWAL_FEE_USD["cex_to_cex"],
            slippage_bps=5.0,
            liquidity_impact_bps=2.0,
        )
        opp_id = f"live:cex_spot_arb:{symbol.replace('/','')}:{uuid.uuid4().hex[:8]}"
        payload = {
            "opportunity_type": "cex_spot_arbitrage",
            "chain": "cex",
            "symbol": symbol,
            "venue_buy": buy_venue,
            "venue_sell": sell_venue,
            "buy_price": best_ask["ask"],
            "sell_price": best_bid["bid"],
            "spread_bps": round(spread_bps, 2),
            "notional_usd": self._notional_usd,
            "gross_profit_usd": net.gross_profit_usd,
            "expected_profit_usd": net.net_profit_usd,
            "net_profit_usd": net.net_profit_usd,
            "net_profit_bps": net.net_profit_bps,
            "expected_gas_usd": net.gas_cost_usd,
            "trading_fees_usd": net.trading_fees_usd,
            "withdrawal_fees_usd": net.withdrawal_fees_usd,
            "slippage_cost_usd": net.slippage_cost_usd,
            "liquidity_impact_usd": net.liquidity_impact_usd,
            "flash_loan_fee_usd": net.flash_loan_fee_usd,
            "capital_required_usd": self._notional_usd,
            "flash_loan_fee_bps": 0.0,
            "confidence": 0.6,
            "risk_score": 0.4,
            "market_regime": "UNKNOWN",
            "observed_at": _iso(),
            "shadow": False,
            "live": True,
            "net_profit_breakdown": net.to_dict(),
        }
        route = {
            "route_id": f"cex:{buy_venue}->{sell_venue}:{symbol}",
            "fingerprint_parts": {
                "kind": "cex_spread",
                "buy_venue": buy_venue,
                "sell_venue": sell_venue,
                "symbol": symbol,
            },
        }
        await self._bridge.publish_emission(
            scanner_id=self.scanner_id, opp_id=opp_id,
            payload=payload, route=route,
        )
        self._stats["opportunities_emitted"] += 1

        # forward to paper engine
        if self._paper is not None:
            try:
                await self._paper.analyse({**payload, "opp_id": opp_id})
            except Exception as exc:                                 # noqa
                logger.exception("paper analyse failed for %s: %s",
                                    opp_id, exc)


async def _safe_ticker(provider: Any, symbol: str
                        ) -> Optional[Dict[str, Any]]:
    try:
        return await provider.get_ticker(symbol)
    except Exception as exc:                                        # noqa
        logger.debug("cex ticker %s %s failed: %s",
                     getattr(provider, "venue", provider.provider_id),
                     symbol, exc)
        return None


__all__ = ["LiveMarketScanner"]
