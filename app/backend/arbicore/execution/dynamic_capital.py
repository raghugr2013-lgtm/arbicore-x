"""Dynamic capital resolution — the ACTUAL current wallet balance is the source
of truth for plan-time sizing. No fixed initial-capital assumption exists here.

Pure / offline (no I/O). Callers supply a live wallet balance (USD) + a live gas
cost estimate; this module derives the protected-gas-reserve floor, the available
operating capital, and the balance-delta revalidation — all fail-closed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, asdict
from typing import Any, Dict, Optional


def _cfg_f(key: str, default: float) -> float:
    try:
        v = os.environ.get(key)
        return float(v) if v is not None and str(v).strip() != "" else default
    except (TypeError, ValueError):
        return default


# Protected native-gas reserve (USD) kept aside and never treated as spendable
# operating capital. Safety floor — NOT a capital ceiling.
def gas_reserve_usd() -> float:
    return max(0.0, _cfg_f("ARBICORE_GAS_RESERVE_USD", 25.0))


# Max tolerated wallet-balance drift between sizing and broadcast (fraction).
def balance_delta_tolerance() -> float:
    return max(0.0, _cfg_f("ARBICORE_BALANCE_DELTA_TOLERANCE_PCT", 0.005))


@dataclass(frozen=True)
class CapitalContext:
    ok: bool
    reference_capital_usd: Optional[float]   # available operating capital (post-reserve)
    wallet_balance_usd: Optional[float]
    gas_cost_usd: Optional[float]
    gas_reserve_usd: float
    required_floor_usd: Optional[float]      # gas + reserve
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def resolve_operating_capital(
    *,
    wallet_balance_usd: Optional[float],
    gas_cost_usd: Optional[float],
    reserve_usd: Optional[float] = None,
    min_operating_usd: float = 0.0,
) -> CapitalContext:
    """Derive operating capital from the LIVE wallet balance, fail-closed.

    reference_capital_usd = wallet_balance_usd - (gas_cost + protected_reserve).
    Any missing input, or a balance that cannot cover gas+reserve, or a non-
    positive operating balance → ok=False (deny). Never assumes a fixed amount.
    """
    reserve = gas_reserve_usd() if reserve_usd is None else max(0.0, reserve_usd)
    if wallet_balance_usd is None or gas_cost_usd is None:
        return CapitalContext(False, None, wallet_balance_usd, gas_cost_usd,
                              reserve, None,
                              "live wallet balance and/or gas estimate unavailable")
    try:
        bal = float(wallet_balance_usd)
        gas = float(gas_cost_usd)
    except (TypeError, ValueError):
        return CapitalContext(False, None, wallet_balance_usd, gas_cost_usd,
                              reserve, None, "non-numeric balance/gas")
    if bal < 0 or gas < 0:
        return CapitalContext(False, None, bal, gas, reserve, None,
                              "negative balance/gas")
    floor = gas + reserve
    if bal < floor:
        return CapitalContext(False, None, bal, gas, reserve, floor,
                              f"balance ${bal:.2f} < gas+reserve ${floor:.2f} "
                              f"(gas ${gas:.2f} + reserve ${reserve:.2f})")
    operating = bal - floor
    if operating <= float(min_operating_usd):
        return CapitalContext(False, None, bal, gas, reserve, floor,
                              f"operating capital ${operating:.2f} ≤ "
                              f"min ${float(min_operating_usd):.2f}")
    return CapitalContext(True, round(operating, 6), bal, gas, reserve, floor,
                          "ok")


@dataclass(frozen=True)
class BalanceDeltaResult:
    ok: bool
    delta_fraction: Optional[float]
    tolerance: float
    reason: str


def balance_delta_ok(
    *,
    sizing_balance_usd: Optional[float],
    fresh_balance_usd: Optional[float],
    tolerance: Optional[float] = None,
) -> BalanceDeltaResult:
    """Revalidate that the wallet balance has not drifted beyond tolerance
    between sizing/plan creation and broadcast. Fail-closed on any None."""
    tol = balance_delta_tolerance() if tolerance is None else max(0.0, tolerance)
    if sizing_balance_usd is None or fresh_balance_usd is None:
        return BalanceDeltaResult(False, None, tol,
                                  "balance unavailable at revalidation")
    try:
        base = float(sizing_balance_usd)
        fresh = float(fresh_balance_usd)
    except (TypeError, ValueError):
        return BalanceDeltaResult(False, None, tol, "non-numeric balance")
    if base <= 0:
        return BalanceDeltaResult(False, None, tol,
                                  "sizing-time balance non-positive")
    delta = abs(fresh - base) / base
    if delta > tol:
        return BalanceDeltaResult(False, round(delta, 6), tol,
                                  f"balance drift {delta:.4%} > tolerance {tol:.4%} "
                                  f"— recalculate plan from current balance")
    return BalanceDeltaResult(True, round(delta, 6), tol, "ok")
