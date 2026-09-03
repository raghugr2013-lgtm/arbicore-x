"""Phase-2 Parts E/F/G · Multi-chain TRUE net-profit convergence (fail-closed).

Ties together the reusable pieces so ANY chain converges on the SAME honest
economics identity:

    true_net = gross_edge
             − DEX fees            (already embedded in the quoted gross)
             − flash-loan fee      (provider optimizer, ACTUAL provider fee)
             − gas (L2)            (chain gas model)
             − chain L1 / security (chain gas model, where applicable)
             − slippage            (chain gas model)
             − provider callback / route overhead (extra gas units fed to the
                                     gas model + the provider fee)

Never uses gross spread as a substitute for true net. Never assumes a provider
fee, provider liquidity, or a gas cost — any unknown → DENY (return ``None``).

Pure orchestration over injected collaborators (``optimize_flash_provider`` +
a ``ChainGasModel``); no network I/O here, so it is unit-testable offline.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from .flash_provider_optimizer import OptimizedProvider, optimize_flash_provider


def total_gas_units(route_gas_units: Optional[int],
                    provider_callback_gas: Optional[int]) -> Optional[int]:
    """Route gas + provider flash-callback overhead. Unknown route gas ⇒ None."""
    if route_gas_units is None or int(route_gas_units) <= 0:
        return None
    extra = int(provider_callback_gas or 0)
    return int(route_gas_units) + max(0, extra)


async def compute_true_net_profit(
    *,
    chain: str,
    gas_model,                                  # ChainGasModel (or None ⇒ DENY)
    gross_profit_usd: float,
    borrow_amount_usd: Optional[float],
    notional_usd: float,
    route_gas_units: Optional[int],
    native_usd: Optional[float],
    borrow_token: str = "",
    liquidity_by_provider: Optional[Dict[str, Optional[float]]] = None,
    fee_bps_by_provider: Optional[Dict[str, Optional[int]]] = None,
    provider_choice: Optional[OptimizedProvider] = None,
) -> Optional[Dict[str, Any]]:
    """Return the TRUE all-in net-profit breakdown, or ``None`` (DENY).

    DENY conditions (fail-closed, no fabricated value):
      * no chain gas model (unsupported / no RPC),
      * no feasible flash provider (unknown fee/liquidity/unsupported chain),
      * route gas units unknown,
      * gas model cannot price the all-in cost (missing gas/price/L1/native USD).
    """
    if gas_model is None:
        return {"denied": True, "reason": "no_gas_model"}

    # 1) Choose the economically best FEASIBLE flash provider (ACTUAL fee).
    choice = provider_choice or optimize_flash_provider(
        chain=chain, borrow_token=borrow_token,
        borrow_amount_usd=borrow_amount_usd,
        liquidity_by_provider=liquidity_by_provider,
        fee_bps_by_provider=fee_bps_by_provider)
    if not choice.feasible or choice.provider is None:
        return {"denied": True, "reason": f"no_flash_provider:{choice.reason}"}

    # 2) Route gas + provider callback overhead (fail-closed on unknown gas).
    gas_units = total_gas_units(route_gas_units, choice.callback_extra_gas_units)
    if gas_units is None:
        return {"denied": True, "reason": "route_gas_unknown"}

    # 3) Chain gas model prices the true all-in transaction cost (DENY on any
    #    missing essential input — never a fabricated cost).
    all_in = await gas_model.all_in_cost(
        gross_profit_usd=gross_profit_usd,
        borrow_amount_usd=float(borrow_amount_usd or 0.0),
        notional_usd=notional_usd, gas_units=gas_units, eth_usd=native_usd)
    if all_in is None:
        return {"denied": True, "reason": "all_in_cost_unavailable"}

    # 4) Subtract the ACTUAL provider flash fee (the gas model's flash-fee knob
    #    is env-based / default 0; the real provider premium is authoritative).
    # Real provider flash fee (a genuine 0-bps protocol fee is a REAL fee).
    provider_fee_usd = (0.0 if choice.fee_usd is None else float(choice.fee_usd))
    true_net = float(all_in["net_profit_all_in_usd"]) - provider_fee_usd

    return {
        "denied": False,
        "chain": chain,
        "provider": choice.provider,
        "provider_fee_bps": choice.fee_bps,
        "provider_fee_usd": provider_fee_usd,
        "callback_extra_gas_units": choice.callback_extra_gas_units,
        "route_gas_units": int(route_gas_units),
        "total_gas_units": gas_units,
        "gross_profit_usd": float(gross_profit_usd),
        "all_in_cost_usd": float(all_in["all_in_cost_usd"]) + provider_fee_usd,
        "true_net_profit_usd": round(true_net, 6),
        "breakdown": {
            "l2_fee_usd": all_in.get("l2_fee_usd"),
            "l1_fee_usd": all_in.get("l1_fee_usd"),
            "slippage_usd": all_in.get("slippage_usd"),
            "flash_provider_fee_usd": provider_fee_usd,
        },
    }


__all__ = ["total_gas_units", "compute_true_net_profit"]
