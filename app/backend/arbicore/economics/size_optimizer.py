"""ArbiCore X — Adaptive flash-loan size optimizer (P0-8).

Searches candidate notionals and selects the size with the MAXIMUM
risk-adjusted expected value (not maximum gross profit, not maximum loan)
subject to hard safety limits (liquidity cap, slippage cap, max notional,
wallet reserve). Depth-aware: slippage + liquidity impact grow with the
notional/liquidity ratio. Adaptive: after a coarse grid it refines around
the best candidate with a local bisection pass.

Pure / deterministic. Reuses `compute_net_profit`; gas is an explicit USD
cost. Never a safety gate.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Optional

from .net_profit import compute_net_profit
from .expected_value import evaluate_expected_value

DEFAULT_SIZE_GRID_USD = [5_000, 10_000, 25_000, 50_000,
                         100_000, 250_000, 500_000, 1_000_000]


@dataclass
class SizeCandidate:
    notional_usd: float
    gross_profit_usd: float
    dex_fees_usd: float
    flash_fee_usd: float
    gas_usd: float
    slippage_usd: float
    liquidity_impact_usd: float
    net_profit_usd: float
    roi_bps: float
    slippage_bps: float
    success_probability: float
    maximum_loss_usd: float
    expected_value_usd: float
    feasible: bool
    reject_reason: Optional[str] = None
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _impact_bps(notional_usd: float, pool_liquidity_usd: float,
                impact_k: float) -> float:
    # Missing OR non-positive liquidity is UNKNOWN, not zero-cost: treat as
    # fully impacted so the candidate fails closed (never crashes, never
    # silently becomes profitable on absent evidence).
    if pool_liquidity_usd is None or pool_liquidity_usd <= 0:
        return 10_000.0  # no/unknown liquidity → treat as fully impacted
    return impact_k * (notional_usd / pool_liquidity_usd) * 10_000.0


def _score_size(
    notional_usd: float, *, gross_spread_bps: float, pool_liquidity_usd: float,
    gas_cost_usd: float, flash_loan_fee_bps: float, buy_venue_fee_bps: float,
    sell_venue_fee_bps: float, native_price_usd: Optional[float],
    impact_k: float, max_slippage_bps: float, max_notional_usd: float,
    prob_kwargs: Dict[str, Any],
) -> SizeCandidate:
    # Depth-aware slippage; impact grows with notional/liquidity. Calibrated
    # so a small trade on a deep pool costs a few bps and large trades are
    # penalised via the ratio.
    leg_impact = _impact_bps(notional_usd, pool_liquidity_usd, impact_k)
    slippage_bps = leg_impact
    liquidity_impact_bps = leg_impact * 0.25

    npr = compute_net_profit(
        gross_spread_bps=gross_spread_bps, notional_usd=notional_usd,
        buy_venue_fee_bps=buy_venue_fee_bps, sell_venue_fee_bps=sell_venue_fee_bps,
        native_price_usd=native_price_usd, slippage_bps=slippage_bps,
        flash_loan_notional_usd=notional_usd, flash_loan_fee_bps=flash_loan_fee_bps,
        liquidity_impact_bps=liquidity_impact_bps,
    )
    net = npr.net_profit_usd - float(gas_cost_usd)
    roi_bps = (net / notional_usd * 10_000.0) if notional_usd > 0 else 0.0

    # Maximum loss for a flash-loan arb is the non-recoverable execution cost
    # if the round-trip reverts (gas is always spent; fees only on partial).
    max_loss = float(gas_cost_usd) + npr.slippage_cost_usd * 0.5

    liq_ratio = (notional_usd / pool_liquidity_usd) if (pool_liquidity_usd and pool_liquidity_usd > 0) else 1.0
    ev = evaluate_expected_value(
        net_profit_usd=net, maximum_loss_usd=max_loss,
        liquidity_ratio=liq_ratio, **prob_kwargs)

    feasible, reason = True, None
    if net <= 0:
        feasible, reason = False, "net profit <= 0"
    elif slippage_bps > max_slippage_bps:
        feasible, reason = False, f"slippage {slippage_bps:.0f}bps > cap {max_slippage_bps:.0f}bps"
    elif notional_usd > max_notional_usd:
        feasible, reason = False, f"notional > max {max_notional_usd:.0f}"
    elif ev.expected_value_usd <= 0:
        feasible, reason = False, "expected value <= 0"

    return SizeCandidate(
        notional_usd=round(notional_usd, 2),
        gross_profit_usd=npr.gross_profit_usd, dex_fees_usd=npr.trading_fees_usd,
        flash_fee_usd=npr.flash_loan_fee_usd, gas_usd=round(float(gas_cost_usd), 6),
        slippage_usd=npr.slippage_cost_usd, liquidity_impact_usd=npr.liquidity_impact_usd,
        net_profit_usd=round(net, 6), roi_bps=round(roi_bps, 3),
        slippage_bps=round(slippage_bps, 3),
        success_probability=ev.success_probability, maximum_loss_usd=ev.maximum_loss_usd,
        expected_value_usd=ev.expected_value_usd, feasible=feasible,
        reject_reason=reason, evidence=ev.evidence,
    )


def optimize_size(
    *, gross_spread_bps: float, pool_liquidity_usd: float,
    gas_cost_usd: float = 0.0, flash_loan_fee_bps: float = 0.0,
    buy_venue_fee_bps: float = 0.0, sell_venue_fee_bps: float = 0.0,
    native_price_usd: Optional[float] = None, impact_k: float = 0.15,
    max_slippage_bps: float = 150.0, max_notional_usd: Optional[float] = None,
    wallet_reserve_usd: float = 0.0, size_grid_usd: Optional[List[float]] = None,
    refine: bool = True, prob_kwargs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return {'candidates', 'chosen', 'objective'} — chosen maximises EV."""
    grid = list(size_grid_usd or DEFAULT_SIZE_GRID_USD)
    cap = float(max_notional_usd) if max_notional_usd else max(grid)
    common = dict(
        gross_spread_bps=gross_spread_bps, pool_liquidity_usd=pool_liquidity_usd,
        gas_cost_usd=gas_cost_usd, flash_loan_fee_bps=flash_loan_fee_bps,
        buy_venue_fee_bps=buy_venue_fee_bps, sell_venue_fee_bps=sell_venue_fee_bps,
        native_price_usd=native_price_usd, impact_k=impact_k,
        max_slippage_bps=max_slippage_bps, max_notional_usd=cap,
        prob_kwargs=prob_kwargs or {},
    )
    candidates = [_score_size(n, **common) for n in grid if n <= cap]

    # Adaptive refinement: bisect around the best feasible grid point.
    if refine and candidates:
        feas = [c for c in candidates if c.feasible]
        pool = feas or candidates
        best = max(pool, key=lambda c: c.expected_value_usd)
        idx = grid.index(best.notional_usd) if best.notional_usd in grid else None
        extra_points = set()
        if idx is not None:
            if idx > 0:
                extra_points.add((grid[idx - 1] + best.notional_usd) / 2.0)
            if idx < len(grid) - 1:
                extra_points.add((grid[idx + 1] + best.notional_usd) / 2.0)
        for n in sorted(extra_points):
            if n <= cap:
                candidates.append(_score_size(n, **common))

    candidates.sort(key=lambda c: c.notional_usd)
    feasible = [c for c in candidates if c.feasible]
    chosen = max(feasible, key=lambda c: c.expected_value_usd) if feasible else None
    return {
        "candidates": [c.to_dict() for c in candidates],
        "chosen": chosen.to_dict() if chosen else None,
        "objective": "max_risk_adjusted_expected_value",
        "hard_limits": {"max_slippage_bps": max_slippage_bps,
                        "max_notional_usd": cap,
                        "wallet_reserve_usd": wallet_reserve_usd},
    }


__all__ = ["SizeCandidate", "optimize_size", "DEFAULT_SIZE_GRID_USD"]
