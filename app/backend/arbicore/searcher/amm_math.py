"""Universal local AMM / CL / StableSwap math (RPC-free, exact-within-model).

Used by the searcher hot path to quote routes locally from cached pool state
instead of an on-chain call per hop. Never fabricates output: invalid/empty
state returns 0.0 (caller treats as unpriceable → honest refusal).

Models:
  * v2  — Uniswap-V2 constant product with fee (exact).
  * v3  — Uniswap-V3 concentrated liquidity, single active tick (exact within
          the tick; large swaps that would cross ticks are conservatively
          under-quoted, never over-quoted).
  * stable — Curve StableSwap invariant (Newton), 2-coin.
"""
from __future__ import annotations

from typing import List


def v2_amount_out(amount_in: float, reserve_in: float, reserve_out: float,
                  fee_bps: int = 30) -> float:
    if amount_in <= 0 or reserve_in <= 0 or reserve_out <= 0:
        return 0.0
    fee = max(0, min(10_000, int(fee_bps)))
    ain = amount_in * (10_000 - fee) / 10_000.0
    return (ain * reserve_out) / (reserve_in + ain)


def v3_amount_out(amount_in: float, liquidity: float, sqrt_p: float,
                  zero_for_one: bool, fee_bps: int = 5) -> float:
    """Single-tick V3 swap. ``sqrt_p`` = sqrt(price token1/token0) as float.

    zero_for_one=True: token0 in → token1 out (price falls).
    """
    if amount_in <= 0 or liquidity <= 0 or sqrt_p <= 0:
        return 0.0
    fee = max(0, min(10_000, int(fee_bps)))
    ain = amount_in * (10_000 - fee) / 10_000.0
    L = float(liquidity)
    if zero_for_one:
        # sqrtP_next = L*sqrtP / (L + ain*sqrtP)
        sqrt_next = (L * sqrt_p) / (L + ain * sqrt_p)
        out = L * (sqrt_p - sqrt_next)                    # token1 out
    else:
        sqrt_next = sqrt_p + ain / L
        out = L * (sqrt_next - sqrt_p) / (sqrt_p * sqrt_next)  # token0 out
    return max(0.0, out)


def _stable_D(balances: List[float], amp: float, iters: int = 64) -> float:
    n = len(balances)
    S = sum(balances)
    if S == 0:
        return 0.0
    Ann = amp * n
    D = S
    for _ in range(iters):
        D_P = D
        for b in balances:
            D_P = D_P * D / (n * b) if b > 0 else 0.0
        Dprev = D
        D = (Ann * S + D_P * n) * D / ((Ann - 1) * D + (n + 1) * D_P)
        if abs(D - Dprev) <= 1e-9:
            break
    return D


def stable_amount_out(amount_in: float, i: int, j: int,
                      balances: List[float], amp: float = 100.0,
                      fee_bps: int = 4, iters: int = 64) -> float:
    """Curve-style StableSwap exact-in for coin i → coin j (n coins)."""
    if amount_in <= 0 or i == j or i >= len(balances) or j >= len(balances):
        return 0.0
    if any(b <= 0 for b in balances):
        return 0.0
    n = len(balances)
    D = _stable_D(balances, amp, iters)
    Ann = amp * n
    x = balances[i] + amount_in
    # solve for y = balances[j] given D and new x (standard Curve get_y)
    c = D
    S_ = 0.0
    for k in range(n):
        _x = x if k == i else (balances[k] if k != j else None)
        if _x is None:
            continue
        S_ += _x
        c = c * D / (_x * n)
    c = c * D / (Ann * n)
    b = S_ + D / Ann
    y = D
    for _ in range(iters):
        yprev = y
        y = (y * y + c) / (2 * y + b - D)
        if abs(y - yprev) <= 1e-9:
            break
    dy = balances[j] - y
    fee = max(0, min(10_000, int(fee_bps)))
    return max(0.0, dy * (10_000 - fee) / 10_000.0)


__all__ = ["v2_amount_out", "v3_amount_out", "stable_amount_out"]
