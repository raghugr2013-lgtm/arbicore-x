import asyncio
import time
from abc import ABC, abstractmethod
from typing import List, Optional

import httpx

from core import healthstats
from core.errors import (CapabilityNotEnabled, ConnectorUnavailable,
                         MalformedResponse, RateLimited, SymbolNotListed)
from core.models import Candle, FeeInfo, OrderBook, Ticker


class ExchangeConnector(ABC):
    key: str = ""
    name: str = ""
    capabilities: dict = {}

    def __init__(self):
        self._client = httpx.AsyncClient(timeout=10.0)
        self._fee_cache = None
        self._fee_cache_ts = 0.0

    async def close(self):
        await self._client.aclose()

    async def _get(self, url: str, params: dict = None):
        t0 = time.monotonic()
        try:
            resp = await self._client.get(url, params=params)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            healthstats.record(self.key, False, (time.monotonic() - t0) * 1000)
            raise ConnectorUnavailable(f"{self.key}: {e}") from e
        latency = (time.monotonic() - t0) * 1000
        if resp.status_code == 429:
            healthstats.record(self.key, False, latency)
            raise RateLimited(f"{self.key}: rate limited")
        if resp.status_code >= 500:
            healthstats.record(self.key, False, latency)
            raise ConnectorUnavailable(f"{self.key}: HTTP {resp.status_code}")
        healthstats.record(self.key, True, latency)
        try:
            return resp.status_code, resp.json()
        except ValueError as e:
            raise MalformedResponse(f"{self.key}: non-JSON response") from e

    # ---- Phase 1 (public) ----
    @abstractmethod
    async def get_ticker(self, base: str, quote: str) -> Ticker: ...

    @abstractmethod
    async def get_orderbook(self, base: str, quote: str, limit: int = 50) -> OrderBook: ...

    @abstractmethod
    async def get_candles(self, base: str, quote: str, interval_min: int = 5, limit: int = 100) -> List[Candle]: ...

    async def get_fee_info(self, currency: str) -> Optional[FeeInfo]:
        return None  # exchanges without public fee endpoints

    # ---- Phase 2+ (gated) ----
    async def get_balance(self, currency: str):
        raise CapabilityNotEnabled(f"{self.key}: balances ship in Phase 2")

    async def place_order(self, order):
        raise CapabilityNotEnabled(f"{self.key}: trading ships in Phase 3")

    async def withdraw(self, request):
        raise CapabilityNotEnabled(f"{self.key}: withdrawals ship in Phase 4")


class WalletConnector(ABC):
    key: str = ""
    capabilities: dict = {}

    @abstractmethod
    async def check_rpc(self, network: dict) -> dict: ...

    @abstractmethod
    async def get_balance(self, network: dict, address: str) -> Optional[float]: ...

    async def send_token(self, tx):
        raise CapabilityNotEnabled("send_token: client-side signing ships in Phase 3+")
