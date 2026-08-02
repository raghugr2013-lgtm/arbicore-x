"""ArbiCore X — Liquidity Validation.

Migrated from ArbitrageX liquidity floors (server.py L2080, SIGNAL_QUALITY_CONFIG).
Pure, config-driven. Execution-free.

Example:
    >>> v = LiquidityValidator()
    >>> v.validate(liquidity_usd=150_000, trade_amount=10_000).passed
    True
    >>> v.validate(liquidity_usd=50_000, trade_amount=10_000).passed
    False
"""
from __future__ import annotations

from .base import ValidationResult


class LiquidityValidator:
    def __init__(self, min_liquidity_usd: float = 100_000.0, depth_multiplier: float = 2.0) -> None:
        self.min_liquidity_usd = min_liquidity_usd
        self.depth_multiplier = depth_multiplier

    def validate(self, *, liquidity_usd: float, trade_amount: float = 0.0) -> ValidationResult:
        if liquidity_usd < self.min_liquidity_usd:
            return ValidationResult(
                passed=False,
                reason=f"Liquidity ${liquidity_usd:,.0f} < floor ${self.min_liquidity_usd:,.0f}",
                details={"liquidity_usd": liquidity_usd, "floor": self.min_liquidity_usd},
            )

        required_depth = trade_amount * self.depth_multiplier
        if trade_amount > 0 and liquidity_usd < required_depth:
            return ValidationResult(
                passed=False,
                reason=f"Insufficient depth: ${liquidity_usd:,.0f} < {self.depth_multiplier}x trade ${required_depth:,.0f}",
                details={"liquidity_usd": liquidity_usd, "required_depth": required_depth},
            )

        return ValidationResult(
            passed=True,
            reason="Liquidity OK",
            details={"liquidity_usd": liquidity_usd, "required_depth": required_depth},
        )
