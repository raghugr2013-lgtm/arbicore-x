"""Phase-2 · EvmChainAdapter — one data-driven adapter for all Phase-2 chains.

Implements the existing ``ChainAdapter`` protocol (``chains/adapter.py``) for
Arbitrum, Optimism, Ethereum, Polygon and BNB by reading the verified public
registries (``chains/registries.py``) + the shared flash-loan provider catalog
+ the reusable EVM gas layer. It does NOT fork the flash-loan pipeline — adding
a chain is one registry entry, not a code branch.

Fail-closed identity: a chain is NEVER reported ``active_ready`` on assumptions.
``capability()`` marks rpc/tokens/dex/flashloan/gas from what is CONFIGURED, but
keeps ``identity_ok`` (real ``eth_chainId``), ``quote_ok`` and ``simulation_ok``
False until they are probed live on the VPS. Concrete pools are resolved +
validated on-chain at runtime, never fabricated here.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from .adapter import ChainCapability
from . import registries


class EvmChainAdapter:
    def __init__(self, chain: str) -> None:
        chain = (chain or "").lower()
        reg = registries.registry_for(chain)
        if not reg:
            raise ValueError(f"unsupported_chain:{chain}")
        self.chain = chain
        self._reg = reg

    def chain_id(self) -> Optional[int]:
        return int(self._reg.get("chain_id")) if self._reg.get("chain_id") else None

    def native_token(self) -> str:
        return str(self._reg.get("native_token", ""))

    def resolve_rpc_url(self) -> Optional[str]:
        from ..config.persistent import resolve_rpc_url_from_env
        return resolve_rpc_url_from_env(self.chain)

    def token_registry(self) -> Dict[str, Any]:
        return registries.tokens_for(self.chain)

    def dex_registry(self) -> List[str]:
        return sorted({d["dex"] for d in registries.dexes_for(self.chain)})

    def route_metadata(self) -> Dict[str, Any]:
        """Chain-specific route metadata for the flash-loan route builders."""
        return {
            "chain": self.chain,
            "chain_id": self.chain_id(),
            "native_token": self.native_token(),
            "dexes": registries.dexes_for(self.chain),
            "l1_mechanism": self._gas_mechanism(),
        }

    def _gas_mechanism(self) -> str:
        from .evm_gas import CHAIN_SPECS
        return str(CHAIN_SPECS.get(self.chain, {}).get("l1", "none"))

    def flashloan_provider_registry(self) -> List[str]:
        from ..scanners.flash_loan_arbitrage.economics import FLASH_LOAN_PROVIDERS
        return sorted(name for name, meta in FLASH_LOAN_PROVIDERS.items()
                      if self.chain in meta.get("supports_chains", ()))

    def executor_address(self) -> Optional[str]:
        return os.environ.get(
            f"ARBICORE_EXECUTOR_ADDRESS_{self.chain.upper()}") or None

    def gas_model(self):
        from .gas_model import get_chain_gas_model
        return get_chain_gas_model(self.chain)

    async def capability(self) -> ChainCapability:
        cap = ChainCapability(chain=self.chain, chain_id=self.chain_id())
        cap.rpc_ok = bool(self.resolve_rpc_url())
        cap.tokens_ok = len(self.token_registry()) > 0
        cap.dex_ok = len(self.dex_registry()) > 0
        cap.flashloan_ok = len(self.flashloan_provider_registry()) > 0
        cap.execution_ok = bool(self.executor_address())
        # A gas model factory exists AND an RPC is configured ⇒ gas can be
        # priced live; still fail-closed until the live probe on the VPS.
        gm = self.gas_model()
        cap.gas_ok = bool(gm is not None and cap.rpc_ok)
        # identity/quote/simulation health are probed live on the VPS — never
        # assumed here, so the chain is not active_ready on config alone.
        cap.notes.append(
            "Phase-2: identity(eth_chainId)/quote/simulation not probed offline; "
            "pools resolved+validated on-chain at runtime (fail-closed).")
        return cap


def make_chain_adapter(chain: str):
    """Return the adapter for ``chain`` (Base uses its dedicated adapter)."""
    c = (chain or "").lower()
    if c == "base":
        from .base_adapter import BaseChainAdapter
        return BaseChainAdapter()
    if c in registries.CHAIN_REGISTRIES:
        return EvmChainAdapter(c)
    return None


def supported_adapter_chains() -> List[str]:
    return ["base"] + sorted(registries.CHAIN_REGISTRIES.keys())


__all__ = ["EvmChainAdapter", "make_chain_adapter", "supported_adapter_chains"]
