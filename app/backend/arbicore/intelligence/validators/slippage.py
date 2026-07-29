"""ArbiCore X — Slippage Validation (data-only feasibility estimate).

Migrated from ArbitrageX slippage simulation (server.py L2082-2088).

IMPORTANT: ArbitrageX used ``random.uniform`` to estimate slippage. That is
non-deterministic and must NEVER feed the learning engine. This validator is
fully deterministic: the caller passes an explicit ``slippage_estimate`` (e.g.
derived from real depth / volatility). When omitted, a conservative midpoint of
the configured band is used. Randomness is intentionally absent.

Example:
    >>> v = SlippageValidator()
    >>> r = v.validate(net_profit=100, gas_cost=10, slippage_estimate=0.004)
    >>> r.passed
    True
"""
from __future__ import annotations

from .base import ValidationResult


class SlippageValidator:
    def __init__(
        self,
        min_slippage: float = 0.003,
        max_slippage: float = 0.006,
        profit_gas_multiplier: float = 2.0,
    ) -> None:
        self.min_slippage = min_slippage
        self.max_slippage = max_slippage
        self.profit_gas_multiplier = profit_gas_multiplier

    def default_estimate(self) -> float:
        """Deterministic conservative estimate (band midpoint)."""
        return (self.min_slippage + self.max_slippage) / 2

    def validate(
        self,
        *,
        net_profit: float,
        gas_cost: float,
        slippage_estimate: float | None = None,
    ) -> ValidationResult:
        slippage = self.default_estimate() if slippage_estimate is None else slippage_estimate
        slippage = max(0.0, min(slippage, 1.0))

        adjusted_profit = net_profit * (1 - slippage)
        required_profit = gas_cost * self.profit_gas_multiplier
        passed = adjusted_profit >= required_profit

        return ValidationResult(
            passed=passed,
            reason=(
                "Slippage-adjusted profit OK"
                if passed
                else f"Adjusted profit ${adjusted_profit:.2f} < {self.profit_gas_multiplier}x gas ${required_profit:.2f}"
            ),
            details={
                "slippage_used": round(slippage, 6),
                "adjusted_profit": round(adjusted_profit, 4),
                "required_profit": round(required_profit, 4),
                "deterministic": True,
            },
        )
