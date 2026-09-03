"""T0-8 · Minimal ChainAdapter protocol.

Aggregates exactly what the flash-loan pipeline needs per chain so that
Base-specific assumptions stop being scattered constants. Concrete
adapters (only ``BaseChainAdapter`` in T0) delegate to existing wiring —
this is a seam, not a behavior change.

A chain must NOT be considered active until ``capability()`` reports the
required health flags green (RPC + identity + tokens + DEX + quote + gas +
simulation + flash-loan provider + execution). T0 ships the interface and
the Base adapter; multi-chain activation gating lands in T4.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ChainCapability:
    chain: str
    chain_id: Optional[int] = None
    rpc_ok: bool = False
    identity_ok: bool = False
    tokens_ok: bool = False
    dex_ok: bool = False
    quote_ok: bool = False
    gas_ok: bool = False
    simulation_ok: bool = False
    flashloan_ok: bool = False
    execution_ok: bool = False
    notes: List[str] = field(default_factory=list)

    @property
    def active_ready(self) -> bool:
        return all([
            self.rpc_ok, self.identity_ok, self.tokens_ok, self.dex_ok,
            self.quote_ok, self.gas_ok, self.simulation_ok,
            self.flashloan_ok, self.execution_ok,
        ])

    def to_dict(self) -> Dict[str, Any]:
        d = self.__dict__.copy()
        d["active_ready"] = self.active_ready
        return d


@runtime_checkable
class ChainAdapter(Protocol):
    chain: str

    def chain_id(self) -> Optional[int]: ...
    def native_token(self) -> str: ...
    def resolve_rpc_url(self) -> Optional[str]: ...
    def token_registry(self) -> Dict[str, Any]: ...
    def dex_registry(self) -> List[str]: ...
    def flashloan_provider_registry(self) -> List[str]: ...
    def executor_address(self) -> Optional[str]: ...
    async def capability(self) -> ChainCapability: ...


__all__ = ["ChainAdapter", "ChainCapability"]
