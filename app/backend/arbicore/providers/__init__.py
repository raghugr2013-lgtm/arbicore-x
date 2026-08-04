"""Phase 5 — Provider abstraction framework (vendor-independence mandate).

Every external dependency (RPC, DEX, quote aggregator, token metadata,
liquidity, gas, flash-loan, wallet custody, secret storage) is defined
as an abstract Protocol here. Concrete implementations plug into the
:class:`ProviderRegistry` which selects the healthiest available
provider on every call, records health/latency/failure per provider,
and trips a circuit breaker when a provider misbehaves.

Design invariants:
  * NO business-logic module imports a concrete provider directly.
  * Every call goes through :class:`ProviderRegistry.call` (or
    ``ProviderRegistry.get(kind)``).
  * The registry never raises — a provider failure is a health event
    that lowers the provider's score, and control fails over to the
    next healthiest provider automatically.
  * All health data is JSON-serialisable so the Phase-4 dashboard and
    the observability endpoint can render it.
"""
from .base import (
    ProviderKind, ProviderStatus, ProviderHealth, HealthEvent,
    RPCProvider, DEXProvider, QuoteAggregator, TokenMetadataProvider,
    LiquidityProvider, GasProvider, FlashLoanProvider,
    WalletCustodyProvider, SecretProvider,
)
from .registry import ProviderRegistry, CircuitBreaker

__all__ = [
    "ProviderKind", "ProviderStatus", "ProviderHealth", "HealthEvent",
    "RPCProvider", "DEXProvider", "QuoteAggregator",
    "TokenMetadataProvider", "LiquidityProvider", "GasProvider",
    "FlashLoanProvider", "WalletCustodyProvider", "SecretProvider",
    "ProviderRegistry", "CircuitBreaker",
]
