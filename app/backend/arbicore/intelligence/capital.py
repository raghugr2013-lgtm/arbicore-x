"""ArbiCore X — Capital Sizing service.

Migrated from ArbitrageX position-sizing math (server.py L2107-2117).
Pure computation. NO wallet interaction, NO execution.

Dependency map: stdlib only (dataclasses).

Example:
    >>> sizer = CapitalSizer()
    >>> s = sizer.size(available_liquidity=1_000_000, reference_capital_usd=40_000)
    >>> s.suggested_trade_size_usd
    8000.0
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CapitalLimits:
    max_pool_percent: float = 0.008     # 0.8% of pool liquidity
    max_wallet_percent: float = 0.25    # 25% of reference capital
    max_per_trade_usd: float = 10_000.0


@dataclass(frozen=True)
class CapitalSizing:
    suggested_trade_size_usd: float
    max_safe_trade_percent: float       # suggested as % of pool liquidity
    pool_limit_usd: float
    wallet_limit_usd: float
    binding_constraint: str             # which limit was the smallest


class CapitalSizer:
    def __init__(self, limits: CapitalLimits | None = None) -> None:
        self.limits = limits or CapitalLimits()

    def size(self, *, available_liquidity: float, reference_capital_usd: float) -> CapitalSizing:
        pool_limit = available_liquidity * self.limits.max_pool_percent
        wallet_limit = reference_capital_usd * self.limits.max_wallet_percent
        cap = self.limits.max_per_trade_usd

        candidates = {"pool": pool_limit, "wallet": wallet_limit, "per_trade_cap": cap}
        binding = min(candidates, key=candidates.get)
        suggested = candidates[binding]

        max_safe_pct = (suggested / available_liquidity * 100) if available_liquidity > 0 else 0.0

        return CapitalSizing(
            suggested_trade_size_usd=round(suggested, 2),
            max_safe_trade_percent=round(max_safe_pct, 4),
            pool_limit_usd=round(pool_limit, 2),
            wallet_limit_usd=round(wallet_limit, 2),
            binding_constraint=binding,
        )
