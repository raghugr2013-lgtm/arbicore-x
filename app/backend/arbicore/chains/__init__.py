"""T0-8 · Chain abstraction package (Base-only in T0).

Provides the minimal ``ChainAdapter`` protocol + ``BaseChainAdapter`` so a
future chain (Arbitrum, T4) is added as one adapter + config rather than
edits scattered across the flash-loan pipeline. No new chains are enabled
in T0.
"""
from .adapter import ChainAdapter, ChainCapability
from .base_adapter import BaseChainAdapter
from .evm_adapter import (
    EvmChainAdapter,
    make_chain_adapter,
    supported_adapter_chains,
)
from .gas_model import (
    BaseGasModel,
    ChainGasModel,
    get_chain_gas_model,
    supported_gas_model_chains,
)
from .evm_gas import EvmGasModel, make_evm_gas_model

__all__ = [
    "ChainAdapter", "ChainCapability", "BaseChainAdapter",
    "EvmChainAdapter", "make_chain_adapter", "supported_adapter_chains",
    "ChainGasModel", "BaseGasModel", "EvmGasModel",
    "get_chain_gas_model", "supported_gas_model_chains", "make_evm_gas_model",
]
