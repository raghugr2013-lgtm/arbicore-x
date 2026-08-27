"""Step 3 · ChainGasModel seam (chain-neutral all-in cost).

Introduces a chain-neutral interface for the true all-in transaction cost so the
final profit gate is priced per chain instead of assuming Base. The existing
Base estimator (``searcher/base_all_in_cost.py``: L2 execution fee + Base
GasPriceOracle L1 data/security fee + flash-loan fee + slippage allowance) is
preserved EXACTLY — ``BaseGasModel`` is a thin pass-through around it, so Base
behaviour is unchanged and regression-compatible.

Future chains (Arbitrum first) implement the same ``ChainGasModel`` protocol with
their own L1/security-fee math (Arbitrum ``NodeInterface``/``ArbGasInfo`` vs the
OP-stack ``GasPriceOracle``). Until a concrete model exists for a chain,
``get_chain_gas_model`` returns ``None`` so the caller DENIES (fail-closed) —
never a Base fallback for a non-Base chain, and never a fabricated cost.

Fail-closed contract (unchanged from the Base estimator):
  ``all_in_cost(...)`` returns a dict with ``all_in_cost_usd`` /
  ``net_profit_all_in_usd`` (plus L1/L2/flash/slippage breakdown) ONLY when every
  essential input is available; otherwise it returns ``None`` (⇒ DENY).
"""
from __future__ import annotations

from typing import Awaitable, Callable, Dict, Optional, Protocol, runtime_checkable


@runtime_checkable
class ChainGasModel(Protocol):
    """Chain-neutral all-in transaction-cost model."""

    chain: str
    supports_l1_data_fee: bool

    async def all_in_cost(
        self,
        *,
        gross_profit_usd: float,
        borrow_amount_usd: float,
        notional_usd: float,
        gas_units: Optional[int],
        eth_usd: Optional[float],
        tx_bytes: Optional[str] = None,
        estimate_gas_fn: Optional[Callable[[], Awaitable[int]]] = None,
    ) -> Optional[Dict[str, float]]: ...


class BaseGasModel:
    """Base (OP-stack) all-in cost — pass-through over the existing estimator.

    Behaviour is IDENTICAL to calling ``make_base_all_in_cost_estimator_from_env``
    directly. When no Base RPC is configured the wrapped estimator is ``None`` and
    ``all_in_cost`` returns ``None`` (⇒ DENY), matching the prior composition path.
    """

    chain = "base"
    supports_l1_data_fee = True

    def __init__(self, estimator: Optional[Callable[..., Awaitable[Optional[Dict[str, float]]]]]) -> None:
        self._estimator = estimator

    @classmethod
    def from_env(cls) -> "BaseGasModel":
        from ..searcher.base_all_in_cost import (
            make_base_all_in_cost_estimator_from_env)
        return cls(make_base_all_in_cost_estimator_from_env())

    async def all_in_cost(
        self,
        *,
        gross_profit_usd: float,
        borrow_amount_usd: float,
        notional_usd: float,
        gas_units: Optional[int],
        eth_usd: Optional[float],
        tx_bytes: Optional[str] = None,
        estimate_gas_fn: Optional[Callable[[], Awaitable[int]]] = None,
    ) -> Optional[Dict[str, float]]:
        if self._estimator is None:
            return None
        return await self._estimator(
            gross_profit_usd=gross_profit_usd,
            borrow_amount_usd=borrow_amount_usd,
            notional_usd=notional_usd,
            gas_units=gas_units,
            eth_usd=eth_usd,
            tx_bytes=tx_bytes,
            estimate_gas_fn=estimate_gas_fn,
        )


# Registry of concrete per-chain gas models. Base ships as a dedicated
# pass-through (BaseGasModel); the other canonical Phase-2 chains
# (Arbitrum/Optimism/Ethereum/Polygon/BNB) are registered below via the reusable
# evm_gas layer, each with its own L1/security-fee math. Missing chain ⇒
# get_chain_gas_model returns None (fail-closed DENY, never a Base fallback).
_GAS_MODEL_FACTORIES: Dict[str, Callable[[], ChainGasModel]] = {
    "base": BaseGasModel.from_env,
}

# Phase-2 chains (Arbitrum, Optimism, Ethereum, Polygon, BNB) are served by the
# reusable EVM gas layer (``evm_gas``). Each is chain-specific (own L1/security
# math + native token) and fail-closed: no RPC ⇒ all_in_cost returns None (DENY).
def _register_evm_chains() -> None:
    from .evm_gas import CHAIN_SPECS, make_evm_gas_model
    for _chain in CHAIN_SPECS:
        _GAS_MODEL_FACTORIES.setdefault(
            _chain, (lambda c=_chain: make_evm_gas_model(c)))


_register_evm_chains()


def get_chain_gas_model(chain: str) -> Optional[ChainGasModel]:
    """Return the gas model for ``chain`` or ``None`` when unimplemented.

    ``None`` means the caller MUST fail-closed (DENY) — there is no Base fallback
    for a non-Base chain.
    """
    factory = _GAS_MODEL_FACTORIES.get((chain or "").lower())
    if factory is None:
        return None
    return factory()


def supported_gas_model_chains() -> list[str]:
    return sorted(_GAS_MODEL_FACTORIES.keys())


__all__ = [
    "ChainGasModel", "BaseGasModel",
    "get_chain_gas_model", "supported_gas_model_chains",
]
