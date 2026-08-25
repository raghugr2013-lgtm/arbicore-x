"""T0-8 · Chain abstraction package (Base-only in T0).

Provides the minimal ``ChainAdapter`` protocol + ``BaseChainAdapter`` so a
future chain (Arbitrum, T4) is added as one adapter + config rather than
edits scattered across the flash-loan pipeline. No new chains are enabled
in T0.
"""
from .adapter import ChainAdapter, ChainCapability
from .base_adapter import BaseChainAdapter
from .gas_model import (
    BaseGasModel,
    ChainGasModel,
    get_chain_gas_model,
    supported_gas_model_chains,
)

__all__ = [
    "ChainAdapter", "ChainCapability", "BaseChainAdapter",
    "ChainGasModel", "BaseGasModel",
    "get_chain_gas_model", "supported_gas_model_chains",
]
