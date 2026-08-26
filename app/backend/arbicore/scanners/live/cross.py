"""Cex↔Dex and Dex↔Dex scanner (Stage 3 · v2.6.0).

Both scanners reuse the existing ``ScannerEvidenceBridge`` to write into
MID and the existing ``ProviderRegistry`` to fetch quotes. Every emitted
opportunity is normalised through ``arbicore.economics.compute_net_profit``
so the Paper Engine only ever consumes net-profit-aware payloads.

Kept intentionally small: one class per family, one 15-30s tick loop,
one representative pair (WETH/USDC on Ethereum). This mirrors the shape
the operator-journey and validation frameworks depend on.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ...data.mid.readers import MidReader
from ...data.mid.writers import MidWriter
from .ids import stable_live_id
from ...economics import (
    compute_net_profit,
    VENUE_FEE_BPS,
    WITHDRAWAL_FEE_USD,
    NATIVE_PRICE_USD_FALLBACK,
)
from ...providers.base import ProviderKind
from ...providers.registry import ProviderRegistry
from ...scanners.wave1b.bridge import ScannerEvidenceBridge

logger = logging.getLogger(__name__)


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# WETH/USDC references — mainnet
_WETH = "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2"
_USDC = "0xa0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"


def _reg_provider_by_venue(registry: ProviderRegistry,
                            kind: ProviderKind, venue: str
                            ) -> Optional[Any]:
    for h in registry.list(kind=kind):
        p = registry.get(h.provider_id)
        if p is None:
            continue
        v = getattr(p, "venue", None) or getattr(p, "dex_family", None)
        if v == venue:
            return p
    return None


class _BaseLiveXScanner:
    tick_interval_s: float = 20.0
    min_net_bps: float = 5.0
    notional_usd: float = 10_000.0
    opportunity_type: str = "unknown"
    chain: str = "ethereum"
    scanner_id: str = "base_x"

    def __init__(self, *, registry: ProviderRegistry,
                 bridge: ScannerEvidenceBridge,
                 mid_reader: MidReader,
                 paper_engine: Any = None,
                 tick_interval_s: Optional[float] = None,
                 min_net_bps: Optional[float] = None,
                 notional_usd: Optional[float] = None) -> None:
        self._registry = registry
        self._bridge = bridge
        self._mid = mid_reader
        self._paper = paper_engine
        if tick_interval_s is not None:
            self.tick_interval_s = float(tick_interval_s)
        if min_net_bps is not None:
            self.min_net_bps = float(min_net_bps)
        if notional_usd is not None:
            self.notional_usd = float(notional_usd)
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._stats: Dict[str, Any] = {
            "iterations": 0, "quotes_collected": 0,
            "opportunities_emitted": 0,
            "last_run_at": None, "last_error": None,
            "started_at": None, "stopped_at": None,
        }

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    async def start(self) -> Dict[str, Any]:
        if self.is_running():
            return {"already_running": True}
        self._stop.clear()
        self._stats["started_at"] = _iso()
        self._stats["stopped_at"] = None
        self._task = asyncio.create_task(self._loop(),
                                            name=f"arbicore_{self.scanner_id}_scanner")
        logger.info("%s: scanner started", self.scanner_id)
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
        return {"stopped": True, "stopped_at": self._stats["stopped_at"]}

    async def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.time()
            try:
                await self._tick()
            except Exception as exc:                                 # noqa
                self._stats["last_error"] = f"tick: {exc!r}"
                logger.exception("%s tick failed: %s",
                                 self.scanner_id, exc)
            self._stats["iterations"] += 1
            self._stats["last_run_at"] = _iso()
            elapsed = time.time() - t0
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=max(0.0, self.tick_interval_s - elapsed))
            except asyncio.TimeoutError:
                pass

    async def _tick(self) -> None:                                   # noqa
        raise NotImplementedError

    async def _emit(self, *, symbol: str, buy_side: Dict[str, Any],
                     sell_side: Dict[str, Any], net: Any,
                     provenance: Dict[str, Any]) -> None:
        opp_id = stable_live_id(
            opportunity_type=self.opportunity_type, chain=self.chain,
            symbol=symbol, venue_buy=buy_side.get("venue"),
            venue_sell=sell_side.get("venue"))
        payload = {
            "opportunity_type": self.opportunity_type,
            "chain": self.chain,
            "symbol": symbol,
            "venue_buy": buy_side.get("venue"),
            "venue_sell": sell_side.get("venue"),
            "buy_price": buy_side.get("price"),
            "sell_price": sell_side.get("price"),
            "spread_bps": net.inputs["gross_spread_bps"],
            "notional_usd": net.inputs["notional_usd"],
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
            "capital_required_usd": net.inputs["notional_usd"],
            "confidence": 0.55, "risk_score": 0.45,
            "market_regime": "UNKNOWN",
            "observed_at": _iso(),
            "shadow": False, "live": True,
            "net_profit_breakdown": net.to_dict(),
            "provenance": provenance,
        }
        route = {
            "route_id": f"{self.opportunity_type}:{buy_side.get('venue')}"
                        f"->{sell_side.get('venue')}:{symbol}",
            "fingerprint_parts": {
                "kind": self.opportunity_type,
                "buy_venue": buy_side.get("venue"),
                "sell_venue": sell_side.get("venue"),
                "symbol": symbol,
            },
        }
        await self._bridge.publish_emission(
            scanner_id=self.scanner_id, opp_id=opp_id,
            payload=payload, route=route,
        )
        self._stats["opportunities_emitted"] += 1
        if self._paper is not None:
            try:
                await self._paper.analyse({**payload, "opp_id": opp_id})
            except Exception as exc:                                 # noqa
                logger.exception("paper analyse %s: %s", opp_id, exc)


class CexDexScanner(_BaseLiveXScanner):
    """WETH/USDC on-chain quote vs. ETH/USDT on a live CEX."""

    scanner_id = "live_cex_dex"
    opportunity_type = "cex_dex_arbitrage"

    async def _tick(self) -> None:
        # 1 WETH → USDC on Uniswap V3 (1e18 wei)
        v3 = _reg_provider_by_venue(self._registry, ProviderKind.DEX,
                                       "uniswap_v3")
        if v3 is None:
            return
        try:
            q = await v3.get_quote(_WETH, _USDC, 10**18, 3000)
        except Exception as exc:                                     # noqa
            self._stats["last_error"] = f"dex_quote: {exc!r}"
            return
        dex_price = float(q["amount_out"]) / 1e6   # USDC has 6 decimals
        self._stats["quotes_collected"] += 1

        # collect first live CEX ticker for ETH/USDT
        cex_price = None
        cex_venue = None
        for venue in ("okx", "coinbase", "kraken", "kucoin",
                      "binance", "bybit"):
            p = _reg_provider_by_venue(self._registry,
                                          ProviderKind.QUOTE_AGGREGATOR,
                                          venue)
            if p is None:
                continue
            try:
                t = await p.get_ticker("ETH/USDT")
            except Exception:                                        # noqa
                continue
            cex_price = float(t["last"] or ((t["bid"] + t["ask"]) / 2))
            cex_venue = venue
            self._stats["quotes_collected"] += 1
            break

        if not cex_price or not cex_venue:
            return
        # symmetric compute — try both directions
        for buy_side_kind, buy_price, buy_venue, sell_price, sell_venue in (
            ("dex_to_cex", dex_price, "uniswap_v3", cex_price, cex_venue),
            ("cex_to_dex", cex_price, cex_venue, dex_price, "uniswap_v3"),
        ):
            if sell_price <= buy_price:
                continue
            gross_bps = (sell_price - buy_price) / buy_price * 10_000.0
            net = compute_net_profit(
                gross_spread_bps=gross_bps,
                notional_usd=self.notional_usd,
                buy_venue_fee_bps=VENUE_FEE_BPS.get(buy_venue, 30.0),
                sell_venue_fee_bps=VENUE_FEE_BPS.get(sell_venue, 30.0),
                withdrawal_fee_usd=WITHDRAWAL_FEE_USD.get(buy_side_kind, 6.0),
                gas_native_wei=int(15e9),          # 15 gwei fallback
                native_price_usd=NATIVE_PRICE_USD_FALLBACK["ethereum"],
                estimated_gas_units=q.get("gas_estimate") or 150_000,
                slippage_bps=8.0,
                liquidity_impact_bps=4.0,
            )
            if net.net_profit_bps < self.min_net_bps:
                continue
            await self._emit(
                symbol="ETH/USDC",
                buy_side={"venue": buy_venue, "price": buy_price},
                sell_side={"venue": sell_venue, "price": sell_price},
                net=net,
                provenance={"dex": "uniswap_v3", "cex": cex_venue,
                             "gas_estimate_units": q.get("gas_estimate")})
            break  # emit at most one per tick


class DexDexScanner(_BaseLiveXScanner):
    """WETH/USDC Uniswap V3 vs. SushiSwap V2 on Ethereum."""

    scanner_id = "live_dex_dex"
    opportunity_type = "dex_arbitrage"

    async def _tick(self) -> None:
        v3 = _reg_provider_by_venue(self._registry, ProviderKind.DEX,
                                       "uniswap_v3")
        sushi = _reg_provider_by_venue(self._registry, ProviderKind.DEX,
                                          "sushiswap")
        uni2 = _reg_provider_by_venue(self._registry, ProviderKind.DEX,
                                         "uniswap_v2")
        if v3 is None:
            return
        alt = sushi or uni2
        if alt is None:
            return
        try:
            q1 = await v3.get_quote(_WETH, _USDC, 10**18, 3000)
            q2 = await alt.get_quote(_WETH, _USDC, 10**18)
        except Exception as exc:                                     # noqa
            self._stats["last_error"] = f"dex_quote: {exc!r}"
            return
        p1 = float(q1["amount_out"]) / 1e6
        p2 = float(q2["amount_out"]) / 1e6
        self._stats["quotes_collected"] += 2

        if p1 == p2:
            return
        if p1 > p2:
            buy_venue, buy_price = alt.dex_family, p2
            sell_venue, sell_price = "uniswap_v3", p1
        else:
            buy_venue, buy_price = "uniswap_v3", p1
            sell_venue, sell_price = alt.dex_family, p2
        gross_bps = (sell_price - buy_price) / buy_price * 10_000.0
        net = compute_net_profit(
            gross_spread_bps=gross_bps,
            notional_usd=self.notional_usd,
            buy_venue_fee_bps=VENUE_FEE_BPS.get(buy_venue, 30.0),
            sell_venue_fee_bps=VENUE_FEE_BPS.get(sell_venue, 30.0),
            withdrawal_fee_usd=0.0,   # in-chain
            gas_native_wei=int(15e9),
            native_price_usd=NATIVE_PRICE_USD_FALLBACK["ethereum"],
            estimated_gas_units=(q1.get("gas_estimate") or 200_000) * 2,
            slippage_bps=10.0,
            liquidity_impact_bps=6.0,
        )
        if net.net_profit_bps < self.min_net_bps:
            return
        await self._emit(
            symbol="ETH/USDC",
            buy_side={"venue": buy_venue, "price": buy_price},
            sell_side={"venue": sell_venue, "price": sell_price},
            net=net,
            provenance={"buy_dex": buy_venue, "sell_dex": sell_venue,
                         "buy_amount_out": q2["amount_out"] if p1 > p2 else q1["amount_out"],
                         "sell_amount_out": q1["amount_out"] if p1 > p2 else q2["amount_out"]})


__all__ = ["CexDexScanner", "DexDexScanner"]
