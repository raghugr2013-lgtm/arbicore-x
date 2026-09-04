"""M3 controlled-live · Base ALL-IN transaction-cost estimator (fail-closed).

Computes the TRUE all-in execution cost of a Base flash-loan arbitrage tx so the
final profit gate never approves a trade that only looks profitable before real
fees:

    L2 execution fee = gas_units × gas_price_ceiling × ETH_USD
    L1 data/security fee = Base GasPriceOracle.getL1Fee(tx_bytes) × ETH_USD
    flash-loan fee = borrow_usd × flash_fee_bps
    slippage / risk allowance = notional_usd × slippage_bps

Swap fees are ALREADY embedded in the quoted round-trip ``gross_profit_pct`` (the
quotes reflect pool fees), so they are NOT re-subtracted here — doing so would
double-count. This is documented and intentional.

The gate then requires:
    (gross_profit_usd − all_in_cost_usd) ≥ minimum_profit + safety_buffer

Returns None (⇒ M3 DENY, fail-closed) if:
  * gas units cannot be estimated (or exceed the configured per-tx ceiling),
  * the current gas price is unavailable,
  * the Base L1 fee cannot be read from the GasPriceOracle,
  * or ETH_USD is unavailable.

The per-tx gas ceiling is a controlled sane bound (default 3M), NOT the 25M Base
protocol maximum — that value is only the protocol ceiling and must never be used
as a normal trading gas limit.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Optional


# OP-stack / Base predeploy that prices the L1 data (security) component.
GAS_PRICE_ORACLE = "0x420000000000000000000000000000000000000F"
SEL_GET_L1_FEE = "0x49948e0e"  # getL1Fee(bytes)

# Base protocol block gas maximum — only a protocol ceiling, NEVER a normal
# per-tx trading limit. Our per-tx ceiling is always kept strictly below it.
PROTOCOL_GAS_MAX = 25_000_000


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
class BaseAllInCostConfig:
    gas_price_buffer_pct: float
    max_gas_price_wei: int
    gas_limit_ceiling: int          # sane per-tx bound — NEVER the 25M protocol max
    flash_loan_fee_bps: float
    slippage_bps: float
    l1_tx_bytes: int                # representative flash-loan tx calldata size

    @classmethod
    def from_env(cls) -> "BaseAllInCostConfig":
        # Hard-clamp the per-tx gas ceiling to strictly below the 25M Base
        # protocol max (P0 invariant enforced regardless of operator env), and
        # floor all fee/bps values at 0 (no negative "costs").
        ceiling = _cfg_i("ARBICORE_GAS_LIMIT_CEILING", 3_000_000)
        ceiling = max(1, min(ceiling, PROTOCOL_GAS_MAX - 1))
        return cls(
            gas_price_buffer_pct=max(0.0, _cfg_f("ARBICORE_GAS_PRICE_BUFFER_PCT", 0.25)),
            max_gas_price_wei=max(1, _cfg_i("ARBICORE_MAX_GAS_PRICE_WEI", 5_000_000_000)),
            gas_limit_ceiling=ceiling,
            flash_loan_fee_bps=max(0.0, _cfg_f("ARBICORE_FLASH_LOAN_FEE_BPS", 0.0)),
            slippage_bps=max(0.0, _cfg_f("ARBICORE_SLIPPAGE_BPS", 30.0)),
            l1_tx_bytes=max(1, _cfg_i("ARBICORE_BASE_L1_TX_BYTES", 1200)),
        )


def _encode_get_l1_fee(n_bytes: int) -> str:
    """ABI-encode ``getL1Fee(bytes)`` for an ``n_bytes`` payload of 0xff bytes.
    0xff maximises L1 gas (non-zero bytes cost more) → conservative fee."""
    offset_hex = f"{32:064x}"
    length_hex = f"{n_bytes:064x}"
    body = "ff" * n_bytes
    pad = (64 - (len(body) % 64)) % 64
    return SEL_GET_L1_FEE + offset_hex + length_hex + body + ("0" * pad)


CostEstimator = Callable[..., Awaitable[Optional[Dict[str, float]]]]


def base_rpc_explicitly_configured() -> bool:
    """True iff the operator EXPLICITLY configured a Base RPC endpoint via
    ``PROVIDER_RPC_URLS_BASE`` or ``PROVIDER_RPC_URL_BASE``.

    A hardcoded public default (``DEFAULT_RPC_URLS['base']``) does NOT count:
    the safety-critical all-in-cost gate must fail closed rather than price a
    controlled-live trade against an implicit public endpoint the operator
    never sanctioned. Mirrors exactly the env contract the provider bootstrap
    (`providers/bootstrap.py::_rpc_urls`) treats as an operator override.
    """
    return bool(
        (os.environ.get("PROVIDER_RPC_URLS_BASE") or "").strip()
        or (os.environ.get("PROVIDER_RPC_URL_BASE") or "").strip()
    )


def make_base_all_in_cost_estimator_from_env() -> Optional[CostEstimator]:
    """Return an async all-in-cost estimator, or None when no Base RPC is
    configured (⇒ the M3 all-in gate will DENY, fail-closed).

    "Configured" means an EXPLICIT operator Base RPC endpoint — an
    auto-bootstrapped public default is deliberately NOT sufficient here, so
    the controlled-live profit gate never prices against an implicit endpoint.
    """
    if not base_rpc_explicitly_configured():
        # Fail-closed: no operator-configured Base RPC ⇒ no estimator ⇒ DENY.
        # Checked BEFORE touching the provider registry.
        return None

    from ..providers.rpc_failover import get_registry_rpc_provider

    provider = get_registry_rpc_provider("base")
    if provider is None:
        return None
    cfg = BaseAllInCostConfig.from_env()

    async def estimate(*, gross_profit_usd: float, borrow_amount_usd: float,
                       notional_usd: float, gas_units: Optional[int],
                       eth_usd: Optional[float], tx_bytes: Optional[str] = None,
                       estimate_gas_fn: Optional[Callable[[], Awaitable[int]]] = None
                       ) -> Optional[Dict[str, float]]:
        import logging as _lg
        _LOG = _lg.getLogger("arbicore.m3.all_in_cost")
        if eth_usd is None or eth_usd <= 0:
            _LOG.warning("all_in_cost DENY reason=eth_usd_unavailable value=%r", eth_usd)
            return None
        # (1) exact gas units — prefer eth_estimateGas of the constructed tx.
        if estimate_gas_fn is not None:
            try:
                gas_units = await estimate_gas_fn()
            except Exception:  # noqa: BLE001 — cannot estimate ⇒ DENY
                return None
        if (gas_units is None or gas_units <= 0
                or gas_units > cfg.gas_limit_ceiling):
            _LOG.warning("all_in_cost DENY reason=gas_units_invalid value=%r ceiling=%d",
                         gas_units, cfg.gas_limit_ceiling)
            return None
        # (2) gas price ceiling = real gas price × (1+buffer), capped.
        try:
            gp = await provider.eth_get_gas_price()
        except Exception:  # noqa: BLE001
            _LOG.warning("all_in_cost DENY reason=gas_price_read_failed")
            return None
        if not gp or gp <= 0:
            _LOG.warning("all_in_cost DENY reason=gas_price_unavailable value=%r", gp)
            return None
        gp_buffered = int(gp * (1.0 + cfg.gas_price_buffer_pct))
        # If the real (buffered) gas price is ABOVE our safety ceiling, gas is
        # too expensive to trade safely — DENY (never silently cap, which would
        # understate the L2 fee and could approve a loss-making trade).
        if gp_buffered > cfg.max_gas_price_wei:
            _LOG.warning("all_in_cost DENY reason=gas_price_above_ceiling "
                         "buffered=%d max=%d", gp_buffered, cfg.max_gas_price_wei)
            return None
        gp_ceiling = gp_buffered
        l2_fee_usd = (float(gas_units) * gp_ceiling / 1e18) * eth_usd
        # (3) Base L1 data/security fee via GasPriceOracle — DENY if unreadable.
        n_bytes = (len(tx_bytes.replace("0x", "")) // 2
                   if tx_bytes else cfg.l1_tx_bytes)
        try:
            raw = await provider.eth_call(
                {"to": GAS_PRICE_ORACLE, "data": _encode_get_l1_fee(n_bytes)})
        except Exception:  # noqa: BLE001
            _LOG.warning("all_in_cost DENY reason=l1_gaspriceoracle_read_failed")
            return None
        if not raw or raw in ("0x", "0x0"):
            _LOG.warning("all_in_cost DENY reason=l1_fee_unavailable raw=%r", raw)
            return None
        try:
            l1_wei = int(raw, 16)
        except (TypeError, ValueError):
            _LOG.warning("all_in_cost DENY reason=l1_fee_unparseable raw=%r", raw)
            return None
        l1_fee_usd = (l1_wei / 1e18) * eth_usd
        # (4) flash-loan fee + (5) slippage/risk allowance.
        flash_fee_usd = float(borrow_amount_usd) * cfg.flash_loan_fee_bps / 1e4
        slippage_usd = float(notional_usd) * cfg.slippage_bps / 1e4
        all_in = l2_fee_usd + l1_fee_usd + flash_fee_usd + slippage_usd
        return {
            "all_in_cost_usd": all_in,
            "net_profit_all_in_usd": float(gross_profit_usd) - all_in,
            "l2_fee_usd": l2_fee_usd, "l1_fee_usd": l1_fee_usd,
            "flash_loan_fee_usd": flash_fee_usd, "slippage_usd": slippage_usd,
            "gas_units": float(gas_units), "gas_price_wei_ceiling": float(gp_ceiling),
        }

    return estimate


__all__ = ["BaseAllInCostConfig", "make_base_all_in_cost_estimator_from_env",
           "base_rpc_explicitly_configured",
           "GAS_PRICE_ORACLE", "SEL_GET_L1_FEE"]
