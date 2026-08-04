"""Provider protocols + shared value types.

Every provider category is a :class:`Protocol`. Concrete implementations
must be async-native and non-blocking. No provider is allowed to raise
outside of documented error types — everything else counts as a health
event and lowers the provider's score.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import (
    Any, Dict, List, Optional, Protocol, runtime_checkable,
)


class ProviderKind(str, Enum):
    RPC              = "rpc"
    DEX              = "dex"
    QUOTE_AGGREGATOR = "quote_aggregator"
    TOKEN_METADATA   = "token_metadata"
    LIQUIDITY        = "liquidity"
    GAS              = "gas"
    FLASH_LOAN       = "flash_loan"
    WALLET_CUSTODY   = "wallet_custody"
    SECRET           = "secret"


class ProviderStatus(str, Enum):
    HEALTHY    = "HEALTHY"
    DEGRADED   = "DEGRADED"
    UNHEALTHY  = "UNHEALTHY"
    TRIPPED    = "TRIPPED"        # circuit breaker open


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class HealthEvent:
    ts: str
    ok: bool
    latency_ms: float
    error: Optional[str] = None
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderHealth:
    """One row per provider instance. All numbers are JSON-friendly."""

    provider_id: str
    kind: ProviderKind
    chain: Optional[str] = None
    priority: int = 100
    status: ProviderStatus = ProviderStatus.HEALTHY

    successes: int = 0
    failures: int = 0
    consecutive_failures: int = 0

    ewma_latency_ms: float = 0.0
    last_latency_ms: Optional[float] = None
    last_ok_at: Optional[str] = None
    last_error_at: Optional[str] = None
    last_error: Optional[str] = None

    circuit_open_until: Optional[str] = None
    last_events: List[HealthEvent] = field(default_factory=list)

    def score(self) -> float:
        """Higher = healthier. Used by the registry to pick a provider."""
        if self.status == ProviderStatus.TRIPPED:
            return -1.0
        total = self.successes + self.failures
        success_rate = (self.successes / total) if total > 0 else 1.0
        latency_penalty = min(self.ewma_latency_ms / 1000.0, 5.0)
        priority_boost = max(0.0, 1.0 - self.priority / 1000.0)
        return (success_rate * 100.0) + priority_boost * 5.0 - latency_penalty

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "kind": self.kind.value,
            "chain": self.chain,
            "priority": self.priority,
            "status": self.status.value,
            "successes": self.successes,
            "failures": self.failures,
            "consecutive_failures": self.consecutive_failures,
            "ewma_latency_ms": round(self.ewma_latency_ms, 3),
            "last_latency_ms": self.last_latency_ms,
            "last_ok_at": self.last_ok_at,
            "last_error_at": self.last_error_at,
            "last_error": self.last_error,
            "circuit_open_until": self.circuit_open_until,
            "score": round(self.score(), 3),
        }


# ---------------------------------------------------------------------------
# Provider Protocols — one per external category.
#
# Every method is async. Every method that could contact the network
# must have a bounded timeout and return a value or raise
# ``ProviderError``. The registry translates any exception into a health
# event and fails over.
# ---------------------------------------------------------------------------


class ProviderError(Exception):
    """Uniform provider failure — carries retryability hint."""

    def __init__(self, message: str, *, retryable: bool = True,
                  provider_id: Optional[str] = None) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.provider_id = provider_id


@runtime_checkable
class BaseProvider(Protocol):
    provider_id: str
    kind: ProviderKind
    chain: Optional[str]


@runtime_checkable
class RPCProvider(Protocol):
    """Ethereum-style JSON-RPC provider."""
    provider_id: str
    kind: ProviderKind
    chain: str

    async def eth_call(self, tx: Dict[str, Any],
                       block: str = "latest") -> str: ...
    async def eth_get_block_number(self) -> int: ...
    async def eth_get_gas_price(self) -> int: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class DEXProvider(Protocol):
    """DEX-family read interface (quotes, pools). Never executes."""
    provider_id: str
    kind: ProviderKind
    chain: str
    dex_family: str      # 'uniswap_v3', 'sushiswap_v2', ...

    async def get_pool(self, token_in: str, token_out: str,
                        fee_tier: Optional[int] = None
                        ) -> Optional[Dict[str, Any]]: ...
    async def get_quote(self, token_in: str, token_out: str,
                         amount_in: int) -> Dict[str, Any]: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class QuoteAggregator(Protocol):
    """1inch/0x/Paraswap-style multi-source quote aggregation."""
    provider_id: str
    kind: ProviderKind
    chain: str

    async def aggregate_quote(self, token_in: str, token_out: str,
                               amount_in: int) -> Dict[str, Any]: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class TokenMetadataProvider(Protocol):
    provider_id: str
    kind: ProviderKind

    async def get_token(self, chain: str,
                         address: str) -> Optional[Dict[str, Any]]: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class LiquidityProvider(Protocol):
    provider_id: str
    kind: ProviderKind
    chain: str

    async def get_liquidity(self, pool_address: str) -> Dict[str, Any]: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class GasProvider(Protocol):
    provider_id: str
    kind: ProviderKind
    chain: str

    async def suggest_gas(self) -> Dict[str, Any]: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class FlashLoanProvider(Protocol):
    """Read-only shape for Phase 7. Actual borrow calls are gated by
    Phase 8 approval infrastructure and remain disabled by default."""
    provider_id: str
    kind: ProviderKind
    chain: str
    family: str          # 'aave_v3', 'balancer', 'maker', 'morpho'

    async def get_available_liquidity(self,
                                       asset: str) -> Dict[str, Any]: ...
    async def get_fee_bps(self, asset: str) -> int: ...
    async def simulate_flashloan(self, payload: Dict[str, Any]
                                  ) -> Dict[str, Any]: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class WalletCustodyProvider(Protocol):
    """Hardware / MPC / HSM / KMS — signs, never reveals keys."""
    provider_id: str
    kind: ProviderKind
    custody_kind: str    # 'local_kms', 'hardware_ledger', 'mpc_fireblocks', 'aws_kms'

    async def list_addresses(self, chain: str) -> List[str]: ...
    async def sign_transaction(self, chain: str, address: str,
                                unsigned_tx: Dict[str, Any]
                                ) -> Dict[str, Any]: ...
    async def health_probe(self) -> Dict[str, Any]: ...


@runtime_checkable
class SecretProvider(Protocol):
    """Env / Vault / AWS-SM / sops. Reads only — never persists secrets
    from the app back to the store."""
    provider_id: str
    kind: ProviderKind
    backend: str

    async def get(self, key: str) -> Optional[str]: ...
    async def list_keys(self, prefix: str = "") -> List[str]: ...
    async def health_probe(self) -> Dict[str, Any]: ...
