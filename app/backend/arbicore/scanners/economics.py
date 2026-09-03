"""ArbiCore X — Phase D D-3.3 Economics substrate (protocol-agnostic).

This module defines the **normalized economics vocabulary** every opportunity
family produces and the **universal cost aggregator** that consumes it.
D-3 DEX-arb is the first consumer; D-5 Cross-Chain (bridge fees / transfer
cost) and D-6 FlashLoan (multi-hop slippage + flash-loan fee + N-leg gas)
plug in by emitting the same LegCost shape — no new aggregator needed.

INV-1: This module never imports DiscoveryCandidate or CanonicalOpportunity.
       It operates on numbers and per-leg cost objects only.
INV-2: This module never calls EmissionBus. It returns pure value objects.
INV-3: This module never overrides source_data_quality. Provenance derivation
       lives in verification_evidence.py.

Design contract for D-5 / D-6 reuse:
  - Any N-leg opportunity (2 for DEX arb, 4+ for flash-loan cycles, etc.)
    can be assessed by passing a list of LegCost objects.
  - Per-chain (or per-leg) gas estimates are summed; bridge fees / flash-loan
    fees are just additional LegCost entries with appropriate ``fee_kind``.
  - MEV risk is a single dimensionless penalty multiplier, independent of
    family. D-5/D-6 may produce different MEV-risk levels but the math is
    identical.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..models.enums import MevRiskLevel


# ============================================================================
# Per-leg cost (protocol-agnostic)
# ============================================================================

@dataclass(frozen=True)
class LegCost:
    """Generic per-leg cost. One per execution step in the opportunity.

    For a 2-leg DEX arb: 2 LegCost objects (buy leg, sell leg).
    For an N-leg flash-loan cycle: N LegCost objects, optionally plus one
        more with ``fee_kind='flash_loan_fee'`` for the loan-provider fee.
    For a cross-chain swap: 2 LegCost objects (source leg, destination leg)
        plus one with ``fee_kind='bridge_fee'``.

    ``fee_kind`` is advisory — the aggregator only sums; it doesn't branch
    on this string.
    """
    leg_role: str                            # advisory: matches EvidenceLegRole vocab
    venue_id: str                            # advisory; not used by aggregator
    fee_bps: Optional[int] = None            # protocol fee (taker bps); summed → total_fee_pct
    slippage_pct: Optional[float] = None     # size-induced slippage; summed → total_slippage_pct
    gas_estimate_usd: Optional[float] = None # leg-specific gas estimate
    extra_cost_usd: Optional[float] = None   # any fixed cost (bridge fee, flash-loan fee, etc.)
    fee_kind: str = "swap_fee"               # advisory tag for downstream telemetry


# ============================================================================
# Per-chain gas defaults (D-3.6 will replace with live fee feeds)
# ============================================================================

# Conservative static per-chain gas estimates (USD per swap leg). These are
# operator-overridable via scanner_config (`per_chain_gas_estimate_usd` patch).
# Values reflect typical 2026 mainnet conditions; intentionally pessimistic
# to keep Gate 1 conservative until live feeds land in D-3.6.
DEFAULT_PER_CHAIN_GAS_USD: Dict[str, float] = {
    "ethereum": 8.00,   # heaviest L1
    "bnb":       0.40,
    "arbitrum":  0.30,
    "base":      0.15,
    "optimism":  0.15,
    "polygon":   0.05,
    "avalanche": 0.10,
    "solana":    0.005,
}


def per_chain_gas_estimate_usd(chain: str,
                               overrides: Optional[Dict[str, float]] = None,
                               ) -> float:
    """Return USD gas cost for one leg on `chain`.

    Operator override path: ``scanner_config["per_chain_gas_estimate_usd"]``
    dict. Returns 0.5 USD for unknown chains (conservative default).
    """
    if overrides and chain in overrides:
        return float(overrides[chain])
    return DEFAULT_PER_CHAIN_GAS_USD.get(chain, 0.5)


# ============================================================================
# MEV risk penalty (protocol-agnostic)
# ============================================================================

# Default penalty factor per MEV risk level (additive pct off net spread).
# Operator override via ``scanner_config["mev_risk_factor"]`` dict
# {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.5} (already seeded in D-3.0).
DEFAULT_MEV_RISK_FACTORS: Dict[str, float] = {
    MevRiskLevel.LOW.value: 0.0,
    MevRiskLevel.MEDIUM.value: 0.5,
    MevRiskLevel.HIGH.value: 1.5,
}


def mev_penalty_pct(mev_risk_level: MevRiskLevel,
                    factors: Optional[Dict[str, float]] = None) -> float:
    """Convert (MEV level, scaling factors) → additive penalty pct."""
    factors = factors or {}
    key = mev_risk_level.value if hasattr(mev_risk_level, "value") else str(mev_risk_level)
    return float(factors.get(key, DEFAULT_MEV_RISK_FACTORS.get(key, 0.0)))


# ============================================================================
# EconomicAssessment — protocol-agnostic result
# ============================================================================

@dataclass
class EconomicAssessment:
    """Universal output of the economics aggregator.

    All percentages are in PERCENTAGE POINTS (0.30 == 0.30%, not 30%).
    """
    gross_spread_pct: float
    total_slippage_pct: float
    total_fee_pct: float
    total_extra_cost_usd: float
    total_gas_usd: float
    gas_drag_pct: float
    mev_risk_level: MevRiskLevel
    mev_penalty_pct: float
    net_spread_after_slip_after_fees_pct: float    # gross − slip − fees
    net_after_costs_pct: float                      # − gas_drag
    mev_adjusted_net_pct: float                     # − mev_penalty
    notional_usd: float
    expected_profit_usd: float
    capital_required_usd: float
    profitable: bool                                # mev_adjusted_net_pct > 0
    breakdown: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# Universal aggregator
# ============================================================================

def aggregate_economics(*,
                        legs: List[LegCost],
                        gross_spread_pct: float,
                        notional_usd: float,
                        mev_risk_level: MevRiskLevel = MevRiskLevel.LOW,
                        mev_risk_factors: Optional[Dict[str, float]] = None,
                        ) -> EconomicAssessment:
    """Compute a normalized EconomicAssessment from a list of LegCost objects.

    Works for any leg count ≥ 1:
      * 2-leg DEX arb (buy + sell)
      * 2-leg CEX arb (buy + sell)
      * 2-leg funding arb (long + short)
      * 2-leg cross-chain (bridge_out + bridge_in) + 1 fee leg (bridge_fee)
      * N-leg flash-loan cycle (borrow + hop×N + repay) + 1 fee leg

    INV-2 safe: pure function, no I/O, no EmissionBus, no canonical mutation.
    """
    total_slippage_pct = sum((lg.slippage_pct or 0.0) for lg in legs)
    total_fee_pct = sum(((lg.fee_bps or 0) / 100.0) for lg in legs)
    total_extra_cost_usd = sum((lg.extra_cost_usd or 0.0) for lg in legs)
    total_gas_usd = sum((lg.gas_estimate_usd or 0.0) for lg in legs)
    safe_notional = float(notional_usd) if notional_usd and notional_usd > 0 else 1.0
    gas_drag_pct = ((total_gas_usd + total_extra_cost_usd) / safe_notional) * 100.0

    net_after_slip_fees = gross_spread_pct - total_slippage_pct - total_fee_pct
    net_after_costs = net_after_slip_fees - gas_drag_pct
    mev_pen = mev_penalty_pct(mev_risk_level, mev_risk_factors)
    mev_adj = net_after_costs - mev_pen

    expected_profit = safe_notional * (mev_adj / 100.0)
    profitable = mev_adj > 0

    return EconomicAssessment(
        gross_spread_pct=round(gross_spread_pct, 6),
        total_slippage_pct=round(total_slippage_pct, 6),
        total_fee_pct=round(total_fee_pct, 6),
        total_extra_cost_usd=round(total_extra_cost_usd, 6),
        total_gas_usd=round(total_gas_usd, 6),
        gas_drag_pct=round(gas_drag_pct, 6),
        mev_risk_level=mev_risk_level,
        mev_penalty_pct=round(mev_pen, 6),
        net_spread_after_slip_after_fees_pct=round(net_after_slip_fees, 6),
        net_after_costs_pct=round(net_after_costs, 6),
        mev_adjusted_net_pct=round(mev_adj, 6),
        notional_usd=safe_notional,
        expected_profit_usd=round(expected_profit, 6),
        capital_required_usd=safe_notional,
        profitable=profitable,
        breakdown={
            "leg_count": len(legs),
            "leg_roles": [lg.leg_role for lg in legs],
            "leg_venue_ids": [lg.venue_id for lg in legs],
            "leg_fee_kinds": [lg.fee_kind for lg in legs],
        },
    )


def canonical_net_profit_usd(assessment: "EconomicAssessment") -> float:
    """T0-4 · single canonical USD profit view.

    ``aggregate_economics``/``EconomicAssessment`` is THE canonical economic
    kernel (it drives the flash-loan verifier + Gate 7). This helper is the
    one authoritative USD projection of that assessment so every caller uses
    the same number — no divergent second calculation. Gate semantics and the
    $25 floor are unchanged (they read ``atomic_profit_usd`` =
    ``EconomicAssessment.expected_profit_usd``).
    """
    return float(getattr(assessment, "expected_profit_usd", 0.0))


__all__ = [
    "LegCost", "EconomicAssessment",
    "DEFAULT_PER_CHAIN_GAS_USD", "DEFAULT_MEV_RISK_FACTORS",
    "per_chain_gas_estimate_usd", "mev_penalty_pct",
    "aggregate_economics", "canonical_net_profit_usd",
]
