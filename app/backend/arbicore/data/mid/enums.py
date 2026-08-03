"""MID open-enum registry.

Every MID row carries a metadata block whose values live in these enums.
Enums are OPEN — unknown values do not raise; they emit an audit row in
``mid_enum_warnings`` and continue. This is intentional so a v2.0.1-era
producer never crashes when a v2.5+ strategy family writes a new value.

Only ``execution_mode`` is closed (four mode-ladder values).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set
from threading import Lock

STRATEGY_TYPE = "strategy_type"
OPPORTUNITY_TYPE = "opportunity_type"
CAPITAL_SOURCE = "capital_source"
CHAIN = "chain"
PROTOCOL = "protocol"
EXECUTION_MODE = "execution_mode"
MARKET_REGIME = "market_regime"

# v2.0.1 seeded values (flash-loan family). Future strategy families
# register their values via ``EnumRegistry.register(...)`` at startup.
_SEED_VALUES: Dict[str, Set[str]] = {
    STRATEGY_TYPE: {
        "flash_loan_arbitrage",
        # future: cex_dex_arbitrage, funding_rate, liquidation, treasury_yield,
        # institutional_credit, cross_chain_arbitrage, ...
        "unknown",
    },
    OPPORTUNITY_TYPE: {
        "dex_arbitrage",
        "multi_hop",
        "triangular",
        "stablecoin_depeg",
        # future: cex_dex, funding_delta, liquidation_call, yield_arbitrage, ...
        "unknown",
    },
    CAPITAL_SOURCE: {
        "flash_loan_aave_v3",
        "flash_loan_balancer_v2",
        "flash_loan_uniswap_v3",
        # future: wallet_burner, wallet_treasury, cex_venue_*, margin_*,
        # credit_facility_*, vault_yield, ...
        "unknown",
    },
    CHAIN: {
        "base",
        # future: arbitrum, optimism, polygon, ethereum, solana, sui,
        #         off_chain_cex, ...
        "unknown",
    },
    PROTOCOL: {
        "uniswap_v3",
        "aerodrome_slipstream",
        "aerodrome_classic",
        "aave_v3",
        "balancer_v2",
        # future: binance_spot, okx_spot, bybit_perp, compound_v3, morpho, ...
        "unknown",
    },
    EXECUTION_MODE: {"shadow", "paper", "limited_live", "full_live"},
    MARKET_REGIME: {
        "UNKNOWN",
        # future: CALM, VOLATILE, TRENDING, CHOP, ... (regime engine — dormant
        # until Sprint 1B — back-annotates this field without schema change).
    },
}

_CLOSED_ENUMS: Set[str] = {EXECUTION_MODE}


@dataclass
class EnumRegistry:
    """Thread-safe process-local enum registry.

    Public API:
        register(name, value)        — add a value to an open enum.
        contains(name, value) -> bool
        list(name) -> List[str]
        is_closed(name) -> bool
    """

    _values: Dict[str, Set[str]] = field(default_factory=dict)
    _closed: Set[str] = field(default_factory=set)
    _lock: Lock = field(default_factory=Lock)

    def __post_init__(self) -> None:
        with self._lock:
            for name, vals in _SEED_VALUES.items():
                self._values[name] = set(vals)
            self._closed = set(_CLOSED_ENUMS)

    def register(self, name: str, value: str) -> None:
        with self._lock:
            if name in self._closed:
                # closed enum — silent no-op if value is already valid,
                # audit warning if not.
                if value not in self._values.get(name, set()):
                    return
                return
            self._values.setdefault(name, set()).add(value)

    def contains(self, name: str, value: Optional[str]) -> bool:
        if value is None:
            return True  # None is always allowed for optional metadata fields
        with self._lock:
            return value in self._values.get(name, set())

    def list(self, name: str) -> List[str]:
        with self._lock:
            return sorted(self._values.get(name, set()))

    def is_closed(self, name: str) -> bool:
        with self._lock:
            return name in self._closed

    def snapshot(self) -> Dict[str, List[str]]:
        with self._lock:
            return {n: sorted(v) for n, v in self._values.items()}


_REGISTRY: Optional[EnumRegistry] = None
_REGISTRY_LOCK = Lock()


def get_registry() -> EnumRegistry:
    """Return the process-local enum registry (created on first call)."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        if _REGISTRY is None:
            _REGISTRY = EnumRegistry()
        return _REGISTRY


def reset_registry_for_tests() -> None:
    """Test-only helper — reset the registry to seed state."""
    global _REGISTRY
    with _REGISTRY_LOCK:
        _REGISTRY = None
