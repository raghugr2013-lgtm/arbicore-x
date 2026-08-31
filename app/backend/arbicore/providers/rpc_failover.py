"""Registry-backed read-only RPC facade.

Uses the application's ProviderRegistry when one is available.
No transaction broadcast/signing is routed through this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import ProviderError, ProviderKind
from .registry import ProviderRegistry

_default_registry: Optional[ProviderRegistry] = None


def set_default_registry(registry: ProviderRegistry) -> None:
    global _default_registry
    _default_registry = registry


def get_default_registry() -> Optional[ProviderRegistry]:
    return _default_registry


class RegistryRpcProvider:
    """Read-only RPC facade backed by ProviderRegistry."""

    def __init__(
        self,
        *,
        chain: str,
        registry: Optional[ProviderRegistry] = None,
        max_attempts: int = 3,
    ) -> None:
        self.chain = chain
        self.registry = registry or _default_registry
        self.max_attempts = max(1, int(max_attempts))

    async def eth_call(
        self,
        tx: Dict[str, Any],
        block: str = "latest",
    ) -> str:
        registry = self.registry or _default_registry
        if registry is None:
            raise ProviderError(
                f"no ProviderRegistry configured for chain={self.chain}",
                retryable=False,
            )

        return await registry.call(
            ProviderKind.RPC,
            lambda p: p.eth_call(tx, block),
            chain=self.chain,
            max_attempts=self.max_attempts,
        )

    async def eth_get_block_number(self) -> int:
        registry = self.registry or _default_registry
        if registry is None:
            raise ProviderError(
                f"no ProviderRegistry configured for chain={self.chain}",
                retryable=False,
            )

        return await registry.call(
            ProviderKind.RPC,
            lambda p: p.eth_get_block_number(),
            chain=self.chain,
            max_attempts=self.max_attempts,
        )

    async def eth_get_gas_price(self) -> int:
        registry = self.registry or _default_registry
        if registry is None:
            raise ProviderError(
                f"no ProviderRegistry configured for chain={self.chain}",
                retryable=False,
            )

        return await registry.call(
            ProviderKind.RPC,
            lambda p: p.eth_get_gas_price(),
            chain=self.chain,
            max_attempts=self.max_attempts,
        )

    async def eth_get_fee_history(
        self,
        blocks: int = 5,
        newest: str = "latest",
        percentiles: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        registry = self.registry or _default_registry
        if registry is None:
            raise ProviderError(
                f"no ProviderRegistry configured for chain={self.chain}",
                retryable=False,
            )

        return await registry.call(
            ProviderKind.RPC,
            lambda p: p.eth_get_fee_history(
                blocks=blocks,
                newest=newest,
                percentiles=percentiles,
            ),
            chain=self.chain,
            max_attempts=self.max_attempts,
        )


def get_registry_rpc_provider(
    chain: str = "base",
    registry: Optional[ProviderRegistry] = None,
) -> Optional[RegistryRpcProvider]:
    reg = registry or _default_registry
    if reg is None:
        return None
    return RegistryRpcProvider(chain=chain, registry=reg)
