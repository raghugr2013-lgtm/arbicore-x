"""Flash-Loan Gates 7, 8, 9.

(Gates 2-5 are the universal substrate gates inherited automatically.)

  - Gate 7  Atomic Profit       atomic_profit_usd ≥ floor (default $25)
  - Gate 8  Liquidity Depth     min pool TVL on the route ≥ floor
  - Gate 9  Flash-Loan MEV      MevRiskScorer (with is_atomic=True) cap

Pure-function evaluators. INV-1/2/3 preserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...models.enums import MevRiskLevel


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    reason: str
    metric_snapshot: Dict[str, Any] = field(default_factory=dict)
    rationale: List[str] = field(default_factory=list)


# ============================================================================
# Gate 7 — Atomic Profit
# ============================================================================

class FlashLoanGate7AtomicProfit:
    """Hard veto when atomic profit is below the operator floor."""

    def __init__(self, thresholds: Dict[str, Any]) -> None:
        self.cfg = thresholds or {}

    def evaluate(self,
                  *,
                  atomic_profit_usd: float,
                  borrow_amount_usd: float,
                  ) -> GateResult:
        floor = float(self.cfg.get("min_atomic_profit_usd", 25.0))
        snap = {
            "atomic_profit_usd": atomic_profit_usd,
            "borrow_amount_usd": borrow_amount_usd,
            "floor_usd": floor,
        }
        passed = atomic_profit_usd >= floor
        reason = ("atomic-profit gate passed" if passed
                   else f"atomic_profit ${atomic_profit_usd:.2f} "
                         f"< floor ${floor:.2f}")
        return GateResult(
            gate_id="gate_7_atomic_profit",
            passed=passed, reason=reason,
            metric_snapshot=snap, rationale=[reason],
        )


# ============================================================================
# Gate 8 — Liquidity Depth (min pool TVL along route)
# ============================================================================

class FlashLoanGate8LiquidityDepth:
    """Veto when the thinnest pool in the route is too shallow."""

    def __init__(self, thresholds: Dict[str, Any]) -> None:
        self.cfg = thresholds or {}

    def evaluate(self,
                  *,
                  min_pool_tvl_usd_in_route: float,
                  ) -> GateResult:
        floor = float(self.cfg.get("min_pool_tvl_usd_in_route", 100_000.0))
        snap = {"min_pool_tvl_usd_in_route": min_pool_tvl_usd_in_route,
                 "floor_usd": floor}
        # T0-6: FAIL CLOSED when liquidity cannot be verified. A non-positive
        # route TVL means no real depth was resolved (the old $5M sentinel is
        # gone) — never pass the liquidity gate on fabricated depth.
        if min_pool_tvl_usd_in_route <= 0.0:
            reason = ("liquidity-depth gate FAILED CLOSED — route TVL "
                      "unverifiable (no fabricated liquidity pass)")
            return GateResult(
                gate_id="gate_8_liquidity_depth",
                passed=False, reason=reason,
                metric_snapshot={**snap, "liquidity_unverifiable": True},
                rationale=[reason],
            )
        passed = min_pool_tvl_usd_in_route >= floor
        reason = ("liquidity-depth gate passed" if passed
                   else f"min route TVL ${min_pool_tvl_usd_in_route:.0f} "
                         f"< floor ${floor:.0f}")
        return GateResult(
            gate_id="gate_8_liquidity_depth",
            passed=passed, reason=reason,
            metric_snapshot=snap, rationale=[reason],
        )


# ============================================================================
# Gate 9 — Flash-Loan MEV (reuses lightweight MevRiskScorer)
# ============================================================================

_MEV_ORDER = {MevRiskLevel.LOW: 0,
              MevRiskLevel.MEDIUM: 1,
              MevRiskLevel.HIGH: 2}


class FlashLoanGate9FlashLoanMev:
    """Veto when MEV classification exceeds the operator cap.

    The cap default is MEDIUM (HIGH rejects). The MevRiskScorer is
    invoked elsewhere (in the verifier) with ``is_atomic=True``; this
    gate only enforces the cap.
    """

    def __init__(self, thresholds: Dict[str, Any]) -> None:
        self.cfg = thresholds or {}

    def evaluate(self,
                  *,
                  mev_risk_level: MevRiskLevel,
                  mev_risk_label: str,
                  mev_score: float,
                  ) -> GateResult:
        cap_label = str(self.cfg.get(
            "max_flash_loan_mev_risk_class", "MEDIUM")).upper()
        try:
            cap_level = MevRiskLevel(cap_label)
        except ValueError:
            cap_level = MevRiskLevel.MEDIUM
        snap = {"mev_risk_level": mev_risk_level.value,
                 "mev_risk_label": mev_risk_label,
                 "mev_score": mev_score,
                 "cap": cap_level.value}
        passed = _MEV_ORDER[mev_risk_level] <= _MEV_ORDER[cap_level]
        reason = ("flash-loan MEV gate passed" if passed
                   else f"MEV level {mev_risk_level.value} "
                         f"exceeds cap {cap_level.value}")
        return GateResult(
            gate_id="gate_9_flash_loan_mev",
            passed=passed, reason=reason,
            metric_snapshot=snap, rationale=[reason],
        )
