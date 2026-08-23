"""T0-8 · BaseChainAdapter — isolates Base-specific assumptions.

Delegates to existing Base wiring (``discovery.base_venues``,
``config.persistent`` RPC resolution, flash-loan provider catalog). Pure
refactor of accessors — no behavior change to the running pipeline. Adding
Arbitrum later (T4) means writing a sibling adapter, not editing the
pipeline.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .adapter import ChainCapability

CHAIN = "base"
CHAIN_ID = 8453
NATIVE_TOKEN = "ETH"


class BaseChainAdapter:
    chain = CHAIN

    def chain_id(self) -> Optional[int]:
        return CHAIN_ID

    def native_token(self) -> str:
        return NATIVE_TOKEN

    def resolve_rpc_url(self) -> Optional[str]:
        # Single canonical (T0-5) synchronous precedence resolver.
        from ..config.persistent import resolve_rpc_url_from_env
        return resolve_rpc_url_from_env(CHAIN)

    def token_registry(self) -> Dict[str, Any]:
        from ..discovery.base_venues import TOKENS
        return dict(TOKENS)

    def dex_registry(self) -> List[str]:
        from ..discovery.base_venues import VENUES
        return sorted({dex for (dex, _a, _b, _p) in VENUES})

    def flashloan_provider_registry(self) -> List[str]:
        from ..scanners.flash_loan_arbitrage.economics import FLASH_LOAN_PROVIDERS
        return sorted(FLASH_LOAN_PROVIDERS.keys())

    def executor_address(self) -> Optional[str]:
        import os
        return os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") or None

    async def capability(self) -> ChainCapability:
        cap = ChainCapability(chain=CHAIN, chain_id=CHAIN_ID)
        cap.rpc_ok = bool(self.resolve_rpc_url())
        cap.identity_ok = cap.rpc_ok  # real eth_chainId check wired in T1/T4
        cap.tokens_ok = len(self.token_registry()) > 0
        cap.dex_ok = len(self.dex_registry()) > 0
        cap.flashloan_ok = len(self.flashloan_provider_registry()) > 0
        cap.execution_ok = bool(self.executor_address())
        # quote/gas/simulation health are probed live (T1); default False
        # so a chain is never "active_ready" on assumptions alone.
        cap.notes.append("T0: quote/gas/simulation health not probed yet")
        return cap


__all__ = ["BaseChainAdapter", "CHAIN", "CHAIN_ID", "NATIVE_TOKEN"]
