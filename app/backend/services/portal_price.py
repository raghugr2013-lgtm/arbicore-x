"""Phase E1 — BlockDAG Portal Price Connector (READ-ONLY).

Polls the official purchase portal swap API (`sw-api.blockdag.network/getInfo`)
for the live BDAG swap price + pay-coin USD prices. Pure data capture: no
purchase, no fund movement, no execution. Provides the live price that replaces
manual BDAG buy-price entry (with an optional manual override upstream).
"""
import asyncio
import logging
import time

import httpx

from core.models import new_id, now_iso
from services import db

logger = logging.getLogger("portal_price")

GETINFO_URL = "https://sw-api.blockdag.network/getInfo"
POLL_EVERY_S = 60
STALE_AFTER_S = 300          # mark price stale if no successful refresh in this window
REQUEST_TIMEOUT_S = 12


class PortalPriceService:
    def __init__(self):
        self._running = False
        self._task = None
        self._client = None
        self.bdag_price = None
        self.coin_prices = {}
        self.wallet_address = None
        self.fetched_at = None        # iso of last successful fetch
        self._fetched_mono = None
        self.last_error = None
        self.consecutive_failures = 0
        self.poll_count = 0
        self.snapshot_count = 0

    # ---------- lifecycle ----------
    async def start(self):
        if self._running:
            return
        self._running = True
        self._client = httpx.AsyncClient(timeout=REQUEST_TIMEOUT_S,
                                         headers={"User-Agent": "ArbiCore/E1 (read-only price discovery)"})
        self._task = asyncio.create_task(self._loop())
        logger.info("Portal price connector started (poll %ss)", POLL_EVERY_S)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        if self._client:
            await self._client.aclose()

    async def _loop(self):
        while self._running:
            try:
                await self.refresh()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.warning("portal price loop error: %s", e)
            await asyncio.sleep(POLL_EVERY_S)

    # ---------- fetch ----------
    async def refresh(self) -> bool:
        """Fetch getInfo once; persist a snapshot. Never raises."""
        self.poll_count += 1
        try:
            r = await self._client.get(GETINFO_URL)
            r.raise_for_status()
            payload = r.json()
            data = payload.get("data") or {}
            price = data.get("bdagPrice")
            if not isinstance(price, (int, float)) or price <= 0:
                raise ValueError(f"invalid bdagPrice: {price!r}")
            self.bdag_price = float(price)
            self.coin_prices = data.get("coinPrices") or {}
            self.wallet_address = data.get("walletAddress")
            self.fetched_at = now_iso()
            self._fetched_mono = time.monotonic()
            self.last_error = None
            self.consecutive_failures = 0
            await db.portal_price_snapshots.insert_one({
                "id": new_id(), "ts": self.fetched_at, "created_at": self.fetched_at,
                "source": "sw-api/getInfo", "bdag_price": self.bdag_price,
                "coin_prices": self.coin_prices, "wallet_address": self.wallet_address})
            self.snapshot_count += 1
            return True
        except Exception as e:
            self.consecutive_failures += 1
            self.last_error = str(e)[:200]
            logger.warning("portal price fetch failed (#%d): %s", self.consecutive_failures, self.last_error)
            return False

    # ---------- accessors ----------
    def _is_stale(self) -> bool:
        if self._fetched_mono is None:
            return True
        return (time.monotonic() - self._fetched_mono) > STALE_AFTER_S

    def current_bdag_price(self):
        """Live BDAG swap price, or None if never fetched or stale."""
        if self.bdag_price is None or self._is_stale():
            return None
        return self.bdag_price

    def status_brief(self) -> dict:
        """Compact block for route snapshot."""
        return {
            "bdag_price": self.bdag_price,
            "stale": self._is_stale(),
            "fetched_at": self.fetched_at,
            "source": "sw-api/getInfo",
            "wallet_address": self.wallet_address,
        }

    async def status(self) -> dict:
        total = await db.portal_price_snapshots.count_documents({})
        return {
            "running": self._running,
            "source": GETINFO_URL,
            "poll_interval_s": POLL_EVERY_S,
            "bdag_price": self.bdag_price,
            "coin_prices": self.coin_prices,
            "wallet_address": self.wallet_address,
            "fetched_at": self.fetched_at,
            "stale": self._is_stale(),
            "last_error": self.last_error,
            "consecutive_failures": self.consecutive_failures,
            "poll_count": self.poll_count,
            "snapshots_total": total,
            "note": "Read-only price discovery — no purchase, no execution, no transfers.",
        }


portal_price = PortalPriceService()
