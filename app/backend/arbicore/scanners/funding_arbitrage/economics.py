"""ArbiCore X — Phase D D-2.0 Funding Economics Assessor.

Sits between ``FundingDifferentialVerifier`` and the (next-checkpoint)
opportunity-emitting verifier. Takes a confirmed ``FundingDifferential``
and produces an ``EconomicAssessment`` that proves (or disproves) the
differential is economically meaningful before any opportunity layer
consumes it.

EXPLICITLY NOT in scope:
  - CanonicalOpportunity construction (INV-2 enforced by AST tests).
  - EmissionBus interaction.
  - source_data_quality manipulation (INV-3).
  - Confidence engine integration / opportunity scoring / ranking.

The assessor returns *evidence*, not a decision. The next opportunity
layer interprets the evidence and gates accordingly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .verifier import FundingDifferential


# ============================================================================
# Per-venue execution profile — operator-tunable.
# ============================================================================

@dataclass
class VenueExecutionProfile:
    venue: str
    taker_fee_pct: float            # round-trip cost is 2 × taker by default
    maker_fee_pct: float            # may be negative (rebate)
    min_notional_usd: float = 10.0  # most venues' perp minimums are low


# Realistic public spot-funding-rate-taker fees for D-2 venues as of 2026-02.
# Operator can override any entry via cfg["venue_fees"][venue].
DEFAULT_VENUE_FEES_PCT: Dict[str, Dict[str, float]] = {
    "bybit":       {"taker": 0.055, "maker": 0.020},
    "okx":         {"taker": 0.050, "maker": 0.020},
    "gate":        {"taker": 0.050, "maker": 0.020},
    "bitget":      {"taker": 0.060, "maker": 0.020},
    "mexc":        {"taker": 0.050, "maker": 0.020},
    "kucoin":      {"taker": 0.060, "maker": 0.020},
    "hyperliquid": {"taker": 0.025, "maker": 0.010},
}


# ============================================================================
# Result.
# ============================================================================

@dataclass
class EconomicAssessment:
    """Evidence-only economic assessment of one funding differential."""
    asset_base: str
    canonical_asset: str
    long_venue: str
    short_venue: str
    differential_apr_pct: float        # from the math verifier

    # Execution costs (round-trip on each leg → open + close at taker)
    long_round_trip_cost_pct: float
    short_round_trip_cost_pct: float
    total_round_trip_cost_pct: float

    # Funding revenue projections
    funding_revenue_apr_pct: float
    funding_revenue_pct_per_hour: float

    # Break-even on holding time required to recoup execution costs
    break_even_hours: float            # math.inf if differential_apr_pct ≤ 0
    break_even_funding_periods_long: float
    break_even_funding_periods_short: float

    # Position sizing (capital-required is operator-supplied)
    capital_required_usd: float
    long_depth_usd: Optional[float] = None
    short_depth_usd: Optional[float] = None
    max_position_usd_by_liquidity: Optional[float] = None
    depth_safety_factor: float = 5.0

    # Verdict booleans (per-criterion — combined into a single
    # ``is_economically_actionable`` flag for downstream convenience).
    meets_min_diff_threshold: Optional[bool] = None
    meets_break_even_horizon: Optional[bool] = None
    meets_liquidity_threshold: Optional[bool] = None
    is_economically_actionable: Optional[bool] = None

    # Configuration snapshot (so the next layer can audit which thresholds
    # produced this verdict).
    min_diff_apr_pct: float = 0.0
    max_break_even_hours: float = 0.0
    min_position_usd: float = 0.0

    economics_notes: List[str] = field(default_factory=list)


# ============================================================================
# Assessor.
# ============================================================================

class FundingEconomicsAssessor:
    """Pure-economics layer. No I/O, no state."""

    DEFAULT_NOTIONAL_USD       = 1_000.0
    DEFAULT_MIN_DIFF_APR_PCT   = 5.0
    DEFAULT_MAX_BREAK_EVEN_H   = 24.0
    DEFAULT_MIN_POSITION_USD   = 100.0
    DEFAULT_DEPTH_SAFETY_X     = 5.0

    def __init__(self, *, config_loader: Callable[[], Dict[str, Any]]) -> None:
        self._cfg = config_loader

    def _profile(self, venue: str) -> VenueExecutionProfile:
        cfg = self._cfg() or {}
        fees = cfg.get("venue_fees") or {}
        per_venue = fees.get(venue) or DEFAULT_VENUE_FEES_PCT.get(venue) or {}
        return VenueExecutionProfile(
            venue=venue,
            taker_fee_pct=float(per_venue.get("taker", 0.06)),
            maker_fee_pct=float(per_venue.get("maker", 0.02)),
        )

    def assess(self,
               diff: FundingDifferential,
               *,
               capital_required_usd: Optional[float] = None,
               long_leg_depth_usd: Optional[float] = None,
               short_leg_depth_usd: Optional[float] = None,
               ) -> EconomicAssessment:
        cfg = self._cfg() or {}
        notional = float(capital_required_usd
                          if capital_required_usd is not None
                          else cfg.get("default_notional_usd",
                                        self.DEFAULT_NOTIONAL_USD))
        min_diff   = float(cfg.get("min_diff_apr_pct",
                                    self.DEFAULT_MIN_DIFF_APR_PCT))
        max_be_h   = float(cfg.get("max_break_even_hours",
                                    self.DEFAULT_MAX_BREAK_EVEN_H))
        min_pos    = float(cfg.get("min_position_usd",
                                    self.DEFAULT_MIN_POSITION_USD))
        safety_x   = float(cfg.get("depth_safety_factor",
                                    self.DEFAULT_DEPTH_SAFETY_X))
        notes: List[str] = []

        lp = self._profile(diff.long_venue)
        sp = self._profile(diff.short_venue)

        # Round-trip costs (open + close at taker). Maker-rebates are an
        # OPTIMISTIC assumption we deliberately don't take here — the
        # operator can adjust by overriding venue_fees in config.
        long_rt  = 2.0 * lp.taker_fee_pct
        short_rt = 2.0 * sp.taker_fee_pct
        total_rt = long_rt + short_rt   # both legs round-tripped

        # Revenue projections (APR → per-hour).
        apr = diff.differential_apr_pct
        per_hour = apr / 8760.0   # 24 × 365 hours
        break_even_h = (total_rt / per_hour) if per_hour > 0 else float("inf")

        # Per-funding-period break-even, separate for each leg's interval.
        be_long_periods  = (break_even_h / max(1, diff.long_read.funding_interval_h))
        be_short_periods = (break_even_h / max(1, diff.short_read.funding_interval_h))

        # Liquidity-driven max position.
        max_pos_by_liq: Optional[float] = None
        if long_leg_depth_usd is not None and short_leg_depth_usd is not None:
            min_leg_depth = min(long_leg_depth_usd, short_leg_depth_usd)
            max_pos_by_liq = min_leg_depth / max(1.0, safety_x)
        elif long_leg_depth_usd is not None or short_leg_depth_usd is not None:
            notes.append("partial_depth_provided:liquidity_verdict_inconclusive")

        # Per-criterion verdicts (None ⇒ inconclusive / data-missing).
        meets_diff = apr >= min_diff
        if not meets_diff:
            notes.append(
                f"min_diff_threshold:{apr:.2f}pct_apr_lt_{min_diff:.2f}pct")

        meets_be = break_even_h <= max_be_h
        if not meets_be:
            notes.append(
                f"break_even_too_long:{break_even_h:.1f}h_gt_{max_be_h:.1f}h")

        if max_pos_by_liq is None:
            meets_liq: Optional[bool] = None
            notes.append("liquidity_unknown:no_depth_inputs_provided")
        elif max_pos_by_liq < min_pos:
            meets_liq = False
            notes.append(
                f"insufficient_liquidity:max_pos_{max_pos_by_liq:.0f}usd_"
                f"lt_min_{min_pos:.0f}usd")
        elif max_pos_by_liq < notional:
            meets_liq = False
            notes.append(
                f"depth_below_requested_notional:max_pos_{max_pos_by_liq:.0f}"
                f"usd_lt_notional_{notional:.0f}usd")
        else:
            meets_liq = True

        # Combined actionability (None if any leg is inconclusive).
        if meets_diff and meets_be and meets_liq is True:
            is_actionable: Optional[bool] = True
        elif meets_liq is None:
            is_actionable = None
        else:
            is_actionable = False

        return EconomicAssessment(
            asset_base=diff.asset_base,
            canonical_asset=diff.canonical_asset,
            long_venue=diff.long_venue,
            short_venue=diff.short_venue,
            differential_apr_pct=round(apr, 6),
            long_round_trip_cost_pct=round(long_rt, 6),
            short_round_trip_cost_pct=round(short_rt, 6),
            total_round_trip_cost_pct=round(total_rt, 6),
            funding_revenue_apr_pct=round(apr, 6),
            funding_revenue_pct_per_hour=round(per_hour, 8),
            break_even_hours=round(break_even_h, 4)
                              if break_even_h != float("inf") else float("inf"),
            break_even_funding_periods_long=round(be_long_periods, 4)
                                              if break_even_h != float("inf")
                                              else float("inf"),
            break_even_funding_periods_short=round(be_short_periods, 4)
                                               if break_even_h != float("inf")
                                               else float("inf"),
            capital_required_usd=notional,
            long_depth_usd=long_leg_depth_usd,
            short_depth_usd=short_leg_depth_usd,
            max_position_usd_by_liquidity=max_pos_by_liq,
            depth_safety_factor=safety_x,
            meets_min_diff_threshold=meets_diff,
            meets_break_even_horizon=meets_be,
            meets_liquidity_threshold=meets_liq,
            is_economically_actionable=is_actionable,
            min_diff_apr_pct=min_diff,
            max_break_even_hours=max_be_h,
            min_position_usd=min_pos,
            economics_notes=notes,
        )
