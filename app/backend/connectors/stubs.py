"""Registered stubs — prove the connector recipe; promoted to live in later phases."""
from connectors.base import ExchangeConnector
from core.errors import SymbolNotListed
from core.models import Candle, OrderBook, Ticker


class _Stub(ExchangeConnector):
    async def get_ticker(self, base, quote) -> Ticker:
        raise SymbolNotListed(f"{self.key}: connector stub — promoted in {self.capabilities.get('phase')}")

    async def get_orderbook(self, base, quote, limit=50) -> OrderBook:
        raise SymbolNotListed(f"{self.key}: connector stub")

    async def get_candles(self, base, quote, interval_min=5, limit=100):
        raise SymbolNotListed(f"{self.key}: connector stub")


def _mk(key, name, phase, **extra):
    cls = type(f"{name}Stub", (_Stub,), {
        "key": key, "name": name,
        "capabilities": {"public_market_data": False, "stub": True, "phase": phase, **extra},
    })
    return cls()


def make_stubs():
    return [
        _mk("ascendex", "AscendEX", "future (BDAG deposit/withdraw enabled; 300 confirmations)",
            trading_api=True, withdrawal_api=False, deposit_monitoring=False),
        _mk("pionex", "Pionex", "future (no withdrawal API)", trading_api=True, withdrawal_api=False),
        _mk("lbank", "LBank", "watchlist (BDAG withdraw infra ready, no pair)",
            trading_api=True, withdrawal_api=True, deposit_monitoring=True),
        _mk("binance", "Binance", "future", trading_api=True, withdrawal_api=True, deposit_monitoring=True),
        _mk("bybit", "Bybit", "future", trading_api=True, withdrawal_api=True, deposit_monitoring=True),
        _mk("bitget", "Bitget", "future", trading_api=True, withdrawal_api=True, deposit_monitoring=True),
        _mk("kucoin", "KuCoin", "future", trading_api=True, withdrawal_api=True, deposit_monitoring=True),
        _mk("biconomy", "Biconomy", "monitor-only (data quality concerns)", trading_api=False, withdrawal_api=False),
    ]
