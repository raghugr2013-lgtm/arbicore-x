"""Phase-2 · Reusable multi-chain EVM all-in gas-cost layer (fail-closed).

Generalises the proven Base estimator (``searcher/base_all_in_cost.py``) to the
other Phase-2 chains WITHOUT touching Base (Base keeps its own dedicated,
regression-frozen estimator via ``BaseGasModel``). The economics engine can ask
one question per chain:

    "What is the realistic ALL-IN transaction cost for this exact
     chain + route + provider + gas usage?"

and get either a full USD breakdown or ``None`` (⇒ DENY). It NEVER fabricates a
cost, and it NEVER falls back to Base math for a non-Base chain.

All-in cost model (per chain):
    L2/execution fee = gas_units × gas_price_ceiling × NATIVE_USD
    L1 data/security fee:
        * OP-stack (Optimism): GasPriceOracle.getL1Fee(tx_bytes) × NATIVE_USD
        * Arbitrum:            ArbGasInfo.getL1BaseFeeEstimate() priced over the
                               tx calldata (16 gas / non-zero byte) × NATIVE_USD
        * L1 chains (Ethereum) / side-chains (Polygon, BNB): NO separate L1 fee
    flash-loan fee   = borrow_usd × flash_fee_bps            (env, provider fee
                       is separately accounted by the economics assessor)
    slippage/risk    = notional_usd × slippage_bps

Returns ``None`` (⇒ DENY, fail-closed) when ANY essential input is unavailable:
no RPC, gas units unknown / over the safety ceiling, gas price unreadable / over
the safety ceiling, an L1 fee that cannot be read, or NATIVE_USD unavailable.

``NATIVE_USD`` is the chain's NATIVE token price in USD (ETH for
Base/OP/Arb/Eth, POL for Polygon, BNB for BNB). The caller passes it via the
``eth_usd`` protocol parameter — it is treated as "native USD", never assumed.

Pure helpers (``l2_fee_usd`` / ``op_stack_l1_fee_usd`` / ``arbitrum_l1_fee_usd``)
are unit-testable offline; the estimator wires them to real RPC reads.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional

from eth_utils import function_signature_to_4byte_selector


# OP-stack L1 GasPriceOracle predeploy (same address on Base & Optimism).
OP_GAS_PRICE_ORACLE = "0x420000000000000000000000000000000000000F"
# Arbitrum ArbGasInfo precompile.
ARB_GAS_INFO = "0x000000000000000000000000000000000000006C"

# Protocol block-gas maxima are ceilings only, NEVER a normal per-tx limit.
PROTOCOL_GAS_MAX = 30_000_000


def _sel(sig: str) -> str:
    return "0x" + function_signature_to_4byte_selector(sig).hex()


SEL_GET_L1_FEE = _sel("getL1Fee(bytes)")
SEL_ARB_L1_BASE_FEE = _sel("getL1BaseFeeEstimate()")


def _cfg_f(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "") or default)
    except (TypeError, ValueError):
        return default


def _cfg_i(key: str, default: int) -> int:
    try:
        return int(float(os.environ.get(key, "") or default))
    except (TypeError, ValueError):
        return default


@dataclass
class EvmGasConfig:
    chain: str
    chain_id: int
    l1_mechanism: str            # "none" | "op_stack" | "arbitrum"
    native_token: str            # ETH / POL / BNB — the token gas is paid in
    gas_price_buffer_pct: float
    max_gas_price_wei: int
    gas_limit_ceiling: int       # sane per-tx bound — NEVER the protocol max
    flash_loan_fee_bps: float
    slippage_bps: float
    l1_tx_bytes: int

    @property
    def supports_l1_data_fee(self) -> bool:
        return self.l1_mechanism in ("op_stack", "arbitrum")

    @classmethod
    def from_env(cls, chain: str, chain_id: int, l1_mechanism: str,
                 native_token: str) -> "EvmGasConfig":
        c = chain.upper()
        ceiling = _cfg_i(f"ARBICORE_GAS_LIMIT_CEILING_{c}",
                         _cfg_i("ARBICORE_GAS_LIMIT_CEILING", 3_000_000))
        ceiling = max(1, min(ceiling, PROTOCOL_GAS_MAX - 1))
        return cls(
            chain=chain, chain_id=chain_id, l1_mechanism=l1_mechanism,
            native_token=native_token,
            gas_price_buffer_pct=max(0.0, _cfg_f("ARBICORE_GAS_PRICE_BUFFER_PCT", 0.25)),
            max_gas_price_wei=max(1, _cfg_i(f"ARBICORE_MAX_GAS_PRICE_WEI_{c}",
                                            _cfg_i("ARBICORE_MAX_GAS_PRICE_WEI",
                                                   50_000_000_000))),
            gas_limit_ceiling=ceiling,
            flash_loan_fee_bps=max(0.0, _cfg_f("ARBICORE_FLASH_LOAN_FEE_BPS", 0.0)),
            slippage_bps=max(0.0, _cfg_f("ARBICORE_SLIPPAGE_BPS", 30.0)),
            l1_tx_bytes=max(1, _cfg_i("ARBICORE_L1_TX_BYTES", 1200)),
        )


# --------------------------------------------------------------------------
# Pure math helpers (offline-testable). Never return negative fees.
# --------------------------------------------------------------------------
def l2_fee_usd(gas_units: int, gas_price_wei: int, native_usd: float) -> float:
    return (float(gas_units) * float(gas_price_wei) / 1e18) * float(native_usd)


def op_stack_l1_fee_usd(l1_fee_wei: int, native_usd: float) -> float:
    return (float(l1_fee_wei) / 1e18) * float(native_usd)


def arbitrum_l1_fee_usd(l1_base_fee_wei: int, calldata_bytes: int,
                        native_usd: float) -> float:
    """Conservative Arbitrum L1 posting cost.

    Arbitrum charges the L1 calldata-posting component via the sequencer. A
    conservative estimate prices every calldata byte at 16 L1 gas (non-zero
    byte cost) against the current L1 base fee. This never understates the
    security fee (over-pessimistic → fail-safe for the profit gate).
    """
    l1_gas = int(calldata_bytes) * 16
    return (float(l1_base_fee_wei) * l1_gas / 1e18) * float(native_usd)


def _encode_get_l1_fee(n_bytes: int) -> str:
    offset_hex = f"{32:064x}"
    length_hex = f"{n_bytes:064x}"
    body = "ff" * n_bytes  # 0xff maximises L1 gas → conservative
    pad = (64 - (len(body) % 64)) % 64
    return SEL_GET_L1_FEE + offset_hex + length_hex + body + ("0" * pad)


CostEstimator = Callable[..., Awaitable[Optional[Dict[str, float]]]]


def make_evm_all_in_cost_estimator(chain: str, url: str,
                                   cfg: EvmGasConfig) -> CostEstimator:
    """Build an async all-in-cost estimator bound to ``chain`` + RPC ``url``."""
    from ..providers.rpc import EthJsonRpcProvider
    provider = EthJsonRpcProvider(chain=chain, url=url)

    async def estimate(*, gross_profit_usd: float, borrow_amount_usd: float,
                       notional_usd: float, gas_units: Optional[int],
                       eth_usd: Optional[float], tx_bytes: Optional[str] = None,
                       estimate_gas_fn: Optional[Callable[[], Awaitable[int]]] = None
                       ) -> Optional[Dict[str, float]]:
        native_usd = eth_usd  # native token USD price for this chain
        if native_usd is None or native_usd <= 0:
            return None
        # (1) exact gas units.
        if estimate_gas_fn is not None:
            try:
                gas_units = await estimate_gas_fn()
            except Exception:  # noqa: BLE001 — cannot estimate ⇒ DENY
                return None
        if (gas_units is None or gas_units <= 0
                or gas_units > cfg.gas_limit_ceiling):
            return None
        # (2) gas price ceiling.
        try:
            gp = await provider.eth_get_gas_price()
        except Exception:  # noqa: BLE001
            return None
        if not gp or gp <= 0:
            return None
        gp_ceiling = int(gp * (1.0 + cfg.gas_price_buffer_pct))
        if gp_ceiling > cfg.max_gas_price_wei:
            return None
        l2 = l2_fee_usd(gas_units, gp_ceiling, native_usd)
        # (3) L1 data/security fee (chain-specific, fail-closed).
        n_bytes = (len(tx_bytes.replace("0x", "")) // 2
                   if tx_bytes else cfg.l1_tx_bytes)
        l1 = 0.0
        if cfg.l1_mechanism == "op_stack":
            try:
                raw = await provider.eth_call(
                    {"to": OP_GAS_PRICE_ORACLE, "data": _encode_get_l1_fee(n_bytes)})
            except Exception:  # noqa: BLE001
                return None
            if not raw or raw in ("0x", "0x0"):
                return None
            try:
                l1 = op_stack_l1_fee_usd(int(raw, 16), native_usd)
            except (TypeError, ValueError):
                return None
        elif cfg.l1_mechanism == "arbitrum":
            try:
                raw = await provider.eth_call(
                    {"to": ARB_GAS_INFO, "data": SEL_ARB_L1_BASE_FEE})
            except Exception:  # noqa: BLE001
                return None
            if not raw or raw in ("0x", "0x0"):
                return None
            try:
                l1 = arbitrum_l1_fee_usd(int(raw, 16), n_bytes, native_usd)
            except (TypeError, ValueError):
                return None
        # (4) flash-loan fee + (5) slippage/risk allowance.
        flash_fee = float(borrow_amount_usd) * cfg.flash_loan_fee_bps / 1e4
        slippage = float(notional_usd) * cfg.slippage_bps / 1e4
        all_in = l2 + l1 + flash_fee + slippage
        return {
            "all_in_cost_usd": all_in,
            "net_profit_all_in_usd": float(gross_profit_usd) - all_in,
            "l2_fee_usd": l2, "l1_fee_usd": l1,
            "flash_loan_fee_usd": flash_fee, "slippage_usd": slippage,
            "gas_units": float(gas_units),
            "gas_price_wei_ceiling": float(gp_ceiling),
            "chain": chain, "native_token": cfg.native_token,
        }

    return estimate


class EvmGasModel:
    """ChainGasModel implementation for a single EVM chain.

    When no RPC is configured the estimator is ``None`` and ``all_in_cost``
    returns ``None`` (⇒ DENY) — never a fabricated or Base-derived cost.
    """

    def __init__(self, chain: str, supports_l1_data_fee: bool,
                 estimator: Optional[CostEstimator]) -> None:
        self.chain = chain
        self.supports_l1_data_fee = supports_l1_data_fee
        self._estimator = estimator

    async def all_in_cost(self, **kwargs) -> Optional[Dict[str, float]]:
        if self._estimator is None:
            return None
        return await self._estimator(**kwargs)


# Per-chain specification (chain_id, L1 mechanism, native token).
CHAIN_SPECS: Dict[str, Dict[str, object]] = {
    "arbitrum": {"chain_id": 42161, "l1": "arbitrum", "native": "ETH"},
    "optimism": {"chain_id": 10, "l1": "op_stack", "native": "ETH"},
    "ethereum": {"chain_id": 1, "l1": "none", "native": "ETH"},
    "polygon": {"chain_id": 137, "l1": "none", "native": "POL"},
    "bnb": {"chain_id": 56, "l1": "none", "native": "BNB"},
}


def make_evm_gas_model(chain: str) -> Optional[EvmGasModel]:
    """Build the gas model for a supported EVM chain, or ``None`` if unknown."""
    spec = CHAIN_SPECS.get((chain or "").lower())
    if spec is None:
        return None
    from ..config.persistent import resolve_rpc_url_from_env
    cfg = EvmGasConfig.from_env(chain, int(spec["chain_id"]),
                                str(spec["l1"]), str(spec["native"]))
    url = resolve_rpc_url_from_env(chain)
    estimator = (make_evm_all_in_cost_estimator(chain, url, cfg)
                 if url else None)
    return EvmGasModel(chain, cfg.supports_l1_data_fee, estimator)


__all__ = [
    "EvmGasConfig", "EvmGasModel", "CHAIN_SPECS",
    "make_evm_all_in_cost_estimator", "make_evm_gas_model",
    "l2_fee_usd", "op_stack_l1_fee_usd", "arbitrum_l1_fee_usd",
    "OP_GAS_PRICE_ORACLE", "ARB_GAS_INFO",
    "SEL_GET_L1_FEE", "SEL_ARB_L1_BASE_FEE",
]
