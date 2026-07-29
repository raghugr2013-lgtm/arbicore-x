"""LaunchEconomicsAssessor — protocol-agnostic launch economics.

Reuses the universal substrates:
  - `arbicore/scanners/economics.py` (LegCost + aggregate_economics)
  - `arbicore/intelligence/roi_probability.py` (ROIProbabilityEngine)

INV-2: pure function. No EmissionBus. No persistence. No I/O.
INV-3: never overrides source_data_quality (that lives in verification_evidence).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...intelligence.roi_probability import ROIProbability
from ...models.enums import MevRiskLevel
from ..economics import (
    EconomicAssessment,
    LegCost,
    aggregate_economics,
    per_chain_gas_estimate_usd,
)


@dataclass
class LaunchEconomicsResult:
    """Launch-specific economics summary. Evidence-only."""

    economics: EconomicAssessment
    roi: ROIProbability
    notional_usd: float
    chain: str
    bonding_curve_progress_pct: Optional[float] = None
    holder_count: Optional[int] = None
    rationale: List[str] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        """Project to CanonicalOpportunity.category_metadata fields.

        Returns ONLY keys present in
        ``KNOWN_CATEGORY_METADATA_KEYS[LAUNCH_ARBITRAGE]`` (seeded at D-4.0).
        """
        out: Dict[str, Any] = {
            "chain": self.chain,
            "roi_base_low_pct": self.roi.base_low,
            "roi_base_high_pct": self.roi.base_high,
            "roi_breakout_probability": self.roi.breakout_probability,
            "roi_drawdown_probability": self.roi.drawdown_probability,
            "roi_sample_size": self.roi.sample_size,
        }
        if self.bonding_curve_progress_pct is not None:
            out["bonding_curve_progress_pct"] = self.bonding_curve_progress_pct
        if self.holder_count is not None:
            out["holder_count"] = self.holder_count
        return out


class LaunchEconomicsAssessor:
    """Universal substrate consumer. Stateless.

    Produces an evidence-only economics summary covering:
      - protocol-agnostic ``EconomicAssessment`` (slippage, gas drag, MEV)
      - winsorized historical ROI distribution (`ROIProbability`)
    """

    def __init__(self,
                 *,
                 roi_engine,                # ROIProbabilityEngine instance
                 per_chain_gas_overrides: Optional[Dict[str, float]] = None,
                 default_notional_usd: float = 250.0,
                 ) -> None:
        self.roi_engine = roi_engine
        self.gas_overrides = per_chain_gas_overrides or {}
        self.default_notional_usd = default_notional_usd

    def assess(self,
                *,
                chain: str,
                primary_venue_id: str,
                secondary_venue_id: str,
                listing_price_usd: Optional[float],
                primary_fee_bps: int,
                secondary_fee_bps: int,
                slippage_primary_pct: float,
                slippage_secondary_pct: float,
                signal_categories: List[str],
                real_outcomes: List[Dict[str, Any]],
                synthetic_outcomes: Optional[List[Dict[str, Any]]] = None,
                bonding_curve_progress_pct: Optional[float] = None,
                holder_count: Optional[int] = None,
                notional_usd: Optional[float] = None,
                mev_risk_level: MevRiskLevel = MevRiskLevel.MEDIUM,
                gross_spread_pct: Optional[float] = None,
                ) -> LaunchEconomicsResult:
        notional = float(notional_usd or self.default_notional_usd)
        chain_norm = (chain or "solana").lower()
        gas_per_leg = per_chain_gas_estimate_usd(chain_norm, self.gas_overrides)

        legs: List[LegCost] = [
            LegCost(
                leg_role="launch_primary",
                venue_id=primary_venue_id,
                fee_bps=primary_fee_bps,
                slippage_pct=slippage_primary_pct,
                gas_estimate_usd=gas_per_leg,
                fee_kind="swap_fee",
            ),
            LegCost(
                leg_role="launch_secondary",
                venue_id=secondary_venue_id,
                fee_bps=secondary_fee_bps,
                slippage_pct=slippage_secondary_pct,
                gas_estimate_usd=gas_per_leg,
                fee_kind="swap_fee",
            ),
        ]

        # Launches don't have a cross-leg "gross_spread" the way DEX arb does.
        # Operator supplies it OR we default to 0 — the ROI engine carries
        # the upside signal; economics only captures *costs*.
        gs = float(gross_spread_pct or 0.0)

        econ = aggregate_economics(
            legs=legs, gross_spread_pct=gs, notional_usd=notional,
            mev_risk_level=mev_risk_level,
        )
        roi = self.roi_engine.estimate(
            categories=signal_categories,
            real_outcomes=real_outcomes,
            synthetic_outcomes=synthetic_outcomes,
        )

        rationale: List[str] = []
        rationale.append(
            f"gas drag {econ.gas_drag_pct:.2f}% on ${notional:.0f} notional"
        )
        rationale.append(
            f"fees {econ.total_fee_pct:.2f}% · slippage {econ.total_slippage_pct:.2f}%"
        )
        if roi.confidence_label != "insufficient":
            rationale.append(
                f"ROI band {roi.base_low}% – {roi.base_high}% "
                f"(n={roi.sample_size}, {roi.confidence_label})"
            )
        else:
            rationale.append("ROI history insufficient — neutral framing")

        return LaunchEconomicsResult(
            economics=econ, roi=roi, notional_usd=notional, chain=chain_norm,
            bonding_curve_progress_pct=bonding_curve_progress_pct,
            holder_count=holder_count, rationale=rationale,
        )
