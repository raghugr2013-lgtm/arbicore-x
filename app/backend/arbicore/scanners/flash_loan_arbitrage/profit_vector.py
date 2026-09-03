"""T1 · Canonical full profit vector (§19).

Projects the single canonical ``EconomicAssessment`` (T0-4 source of truth)
into the complete profitability vector every opportunity must carry:

    gross_profit_usd, total_cost_usd, expected_net_profit_usd,
    worst_case_net_profit_usd, profit_margin_bps, confidence,
    execution_probability

expected_net_profit_usd == EconomicAssessment.expected_profit_usd (no second
calculation). worst_case applies a slippage stress multiplier to the modelled
slippage. Pure / deterministic. Does NOT change any gate (Gate 7 still reads
atomic_profit_usd = expected_profit_usd).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict

from ..economics import EconomicAssessment


@dataclass
class ProfitVector:
    gross_profit_usd: float
    total_cost_usd: float
    expected_net_profit_usd: float
    worst_case_net_profit_usd: float
    profit_margin_bps: float
    confidence: float
    execution_probability: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def build_profit_vector(
    *,
    assessment: EconomicAssessment,
    execution_probability: float,
    confidence: float,
    slippage_stress_mult: float = 2.0,
) -> ProfitVector:
    notional = float(assessment.notional_usd)
    gross = notional * float(assessment.gross_spread_pct) / 100.0
    expected_net = float(assessment.expected_profit_usd)
    total_cost = gross - expected_net
    # Worst-case: stress the slippage component beyond the modelled figure.
    extra_slip_pct = float(assessment.total_slippage_pct) * max(slippage_stress_mult - 1.0, 0.0)
    worst_case = expected_net - notional * extra_slip_pct / 100.0
    margin_bps = (expected_net / notional * 10_000.0) if notional > 0 else 0.0
    return ProfitVector(
        gross_profit_usd=round(gross, 6),
        total_cost_usd=round(total_cost, 6),
        expected_net_profit_usd=round(expected_net, 6),
        worst_case_net_profit_usd=round(worst_case, 6),
        profit_margin_bps=round(margin_bps, 3),
        confidence=round(max(0.0, min(1.0, float(confidence))), 4),
        execution_probability=round(max(0.0, min(1.0, float(execution_probability))), 4),
    )


__all__ = ["ProfitVector", "build_profit_vector"]
