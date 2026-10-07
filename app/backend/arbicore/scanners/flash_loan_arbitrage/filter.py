"""Flash-Loan Gates 7, 8, 9.

(Gates 2-5 are the universal substrate gates inherited automatically.)

  - Gate 7  Atomic Profit       risk-adjusted atomic_profit_usd > 0
                                (dynamic floor; historical $25 is reporting-only)
  - Gate 8  Liquidity Depth     min pool TVL on the route ≥ floor
  - Gate 9  Flash-Loan MEV      MevRiskScorer (with is_atomic=True) cap

Pure-function evaluators. INV-1/2/3 preserved.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
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
# Gate 7 — Atomic Profit (dynamic floor)
# ============================================================================

# Historical SHADOW comparison bucket ONLY — never a hard rejection floor.
REPORTING_ATOMIC_PROFIT_FLOOR_USD: float = 25.0

# Default economic floor: dynamic positive risk-adjusted EV.
# ``atomic_profit_usd`` already embeds flash fee + gas + slippage + MEV
# penalty via ``aggregate_economics`` / ``expected_profit_usd``. Requiring
# strictly positive profit is therefore NOT a raw ">= $0 gross" pass.
DEFAULT_MIN_ATOMIC_PROFIT_USD: float = 0.0

# Profit-band edges for SHADOW distribution (USD). Half-open intervals
# [lo, hi) except the last which is [100, +inf).
_PROFIT_BANDS = (
    ("profit_0_to_0_10", 0.0, 0.10),
    ("profit_0_10_to_0_50", 0.10, 0.50),
    ("profit_0_50_to_1", 0.50, 1.0),
    ("profit_1_to_5", 1.0, 5.0),
    ("profit_5_to_10", 5.0, 10.0),
    ("profit_10_to_25", 10.0, 25.0),
    ("profit_25_to_100", 25.0, 100.0),
    ("profit_100_plus", 100.0, None),
)


def profit_band_key(net_profit_usd: float) -> Optional[str]:
    """Return the reporting band key for a positive net profit, else None."""
    if net_profit_usd <= 0.0:
        return None
    for key, lo, hi in _PROFIT_BANDS:
        if hi is None:
            if net_profit_usd >= lo:
                return key
        elif lo <= net_profit_usd < hi:
            return key
    return None


def empty_gate7_profit_metrics() -> Dict[str, Any]:
    """Zeroed Gate-7 distribution metrics for scanner / SHADOW telemetry."""
    bands = {key: 0 for key, _, _ in _PROFIT_BANDS}
    return {
        "total_gate7_evaluations": 0,
        "negative_net_count": 0,
        "positive_net_count": 0,
        "zero_net_count": 0,
        **bands,
        "best_net_profit": None,
        "worst_net_profit": None,
        "mean_net_profit": None,
        "median_net_profit": None,
        "count_ge_25": 0,
        "count_ge_100": 0,
        "count_net_profit_ge_25": 0,
        "count_net_profit_ge_100": 0,
        "reporting_floor_usd": REPORTING_ATOMIC_PROFIT_FLOOR_USD,
        "dynamic_floor_usd": DEFAULT_MIN_ATOMIC_PROFIT_USD,
        "max_net_profit_cap": None,  # unlimited by design
    }


class Gate7ProfitMetrics:
    """Accumulator for Gate-7 profit distribution (reporting / certification)."""

    def __init__(self) -> None:
        self._profits: List[float] = []
        self.reset()

    def reset(self) -> None:
        self._profits = []
        self._snap = empty_gate7_profit_metrics()

    def record(self, atomic_profit_usd: float) -> str:
        """Record one Gate-7 evaluation; return band key or 'negative'/'zero'."""
        p = float(atomic_profit_usd)
        self._profits.append(p)
        self._snap["total_gate7_evaluations"] += 1
        if self._snap["best_net_profit"] is None or p > self._snap["best_net_profit"]:
            self._snap["best_net_profit"] = p
        if self._snap["worst_net_profit"] is None or p < self._snap["worst_net_profit"]:
            self._snap["worst_net_profit"] = p
        if p < 0.0:
            self._snap["negative_net_count"] += 1
            label = "negative"
        elif p == 0.0:
            self._snap["zero_net_count"] += 1
            label = "zero"
        else:
            self._snap["positive_net_count"] += 1
            band = profit_band_key(p)
            if band:
                self._snap[band] += 1
            label = band or "positive"
        if p >= REPORTING_ATOMIC_PROFIT_FLOOR_USD:
            self._snap["count_ge_25"] += 1
            self._snap["count_net_profit_ge_25"] += 1
        if p >= 100.0:
            self._snap["count_ge_100"] += 1
            self._snap["count_net_profit_ge_100"] += 1
        n = len(self._profits)
        self._snap["mean_net_profit"] = sum(self._profits) / n
        self._snap["median_net_profit"] = float(median(self._profits))
        return label

    def snapshot(self) -> Dict[str, Any]:
        return dict(self._snap)


class FlashLoanGate7AtomicProfit:
    """Veto when risk-adjusted atomic profit is non-positive (dynamic floor).

    ``atomic_profit_usd`` is the canonical MEV-adjusted expected profit from
    ``aggregate_economics`` (fees, gas, slippage, MEV penalty already applied).
    Gate 7 therefore rejects ``<= 0`` realistic economics and does **not**
    apply the historical $25 hard floor.

    ``REPORTING_ATOMIC_PROFIT_FLOOR_USD`` ($25) remains available for SHADOW
    distribution / certification comparison only.

    Operators may still *raise* ``min_atomic_profit_usd`` above 0 via config
    for a stricter fixed threshold. There is no maximum profit cap.
    """

    def __init__(self, thresholds: Dict[str, Any]) -> None:
        self.cfg = thresholds or {}
        self.metrics = Gate7ProfitMetrics()

    def evaluate(self,
                  *,
                  atomic_profit_usd: float,
                  borrow_amount_usd: float,
                  ) -> GateResult:
        # Operator may raise; never interpret a negative config as a pass-all.
        floor = max(
            0.0,
            float(self.cfg.get(
                "min_atomic_profit_usd", DEFAULT_MIN_ATOMIC_PROFIT_USD)),
        )
        profit = float(atomic_profit_usd)
        # Dynamic criterion: strictly positive risk-adjusted EV, and
        # (if raised) at/above the operator floor. No MAX_NET_PROFIT.
        passed = profit > 0.0 and profit >= floor
        band_label = self.metrics.record(profit)
        snap = {
            "atomic_profit_usd": profit,
            "borrow_amount_usd": borrow_amount_usd,
            "floor_usd": floor,
            "dynamic_floor": floor <= 0.0,
            "reporting_floor_usd": REPORTING_ATOMIC_PROFIT_FLOOR_USD,
            "reporting_ge_25": profit >= REPORTING_ATOMIC_PROFIT_FLOOR_USD,
            "reporting_ge_100": profit >= 100.0,
            "profit_band": band_label,
            "max_net_profit_cap": None,
        }
        if passed:
            reason = "atomic-profit gate passed"
        elif profit <= 0.0:
            # Keep floor token so existing decision-text parsers still work.
            reason = (f"atomic_profit ${profit:.2f} < floor "
                      f"${floor:.2f}")
        else:
            reason = (f"atomic_profit ${profit:.2f} < floor "
                      f"${floor:.2f}")
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
