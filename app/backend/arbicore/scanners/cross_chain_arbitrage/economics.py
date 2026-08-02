"""BridgeEconomicsAssessor — D-3 economics substrate consumer.

Mirrors ``LaunchEconomicsAssessor`` shape exactly. Reuses:
  - ``arbicore/scanners/economics.py`` (LegCost + aggregate_economics +
    per_chain_gas_estimate_usd)
  - ``arbicore/intelligence/roi_probability.py`` (ROIProbabilityEngine)

INV-2: pure function. No EmissionBus. No persistence. No I/O.
INV-3: never overrides source_data_quality.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ...intelligence.roi_probability import ROIProbability
from ...models.enums import MevRiskLevel
from ..economics import (
    EconomicAssessment, LegCost, aggregate_economics,
    per_chain_gas_estimate_usd,
)


@dataclass
class BridgeEconomicsResult:
    """Cross-chain economics summary. Evidence-only."""

    economics: EconomicAssessment
    roi: ROIProbability
    notional_usd: float
    source_chain: str
    destination_chain: str
    bridge: str
    total_bridge_fee_usd: float
    gas_source_chain_usd: float
    gas_destination_chain_usd: float
    rationale: List[str] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "source_chain": self.source_chain,
            "destination_chain": self.destination_chain,
            "bridge_provider": self.bridge,
            "total_bridge_fee_usd": self.total_bridge_fee_usd,
            "gas_source_chain_usd": self.gas_source_chain_usd,
            "gas_destination_chain_usd": self.gas_destination_chain_usd,
            "total_round_trip_cost_pct": round(
                self.economics.total_fee_pct +
                self.economics.total_slippage_pct +
                self.economics.gas_drag_pct, 4),
        }
        return out


class BridgeEconomicsAssessor:
    """Stateless. Builds 2-leg + bridge-fee + per-chain-gas cost model."""

    def __init__(self,
                 *,
                 roi_engine,
                 per_chain_gas_overrides: Optional[Dict[str, float]] = None,
                 default_notional_usd: float = 1000.0,
                 ) -> None:
        self.roi_engine = roi_engine
        self.gas_overrides = per_chain_gas_overrides or {}
        self.default_notional_usd = default_notional_usd

    def assess(self,
                *,
                bridge: str,
                source_chain: str,
                destination_chain: str,
                primary_venue_id: str,
                secondary_venue_id: str,
                primary_fee_bps: int,
                secondary_fee_bps: int,
                slippage_bridge_pct: float,
                total_bridge_fee_usd: float,
                signal_categories: List[str],
                real_outcomes: List[Dict[str, Any]],
                synthetic_outcomes: Optional[List[Dict[str, Any]]] = None,
                notional_usd: Optional[float] = None,
                mev_risk_level: MevRiskLevel = MevRiskLevel.MEDIUM,
                gross_spread_pct: Optional[float] = None,
                gas_source_chain_usd: Optional[float] = None,
                gas_destination_chain_usd: Optional[float] = None,
                ) -> BridgeEconomicsResult:
        notional = float(notional_usd or self.default_notional_usd)
        src_n = (source_chain or "").lower()
        dst_n = (destination_chain or "").lower()
        bridge_n = (bridge or "").lower()
        gas_src = (float(gas_source_chain_usd) if gas_source_chain_usd is not None
                   else per_chain_gas_estimate_usd(src_n, self.gas_overrides))
        gas_dst = (float(gas_destination_chain_usd)
                   if gas_destination_chain_usd is not None
                   else per_chain_gas_estimate_usd(dst_n, self.gas_overrides))

        bridge_fee_usd = max(0.0, float(total_bridge_fee_usd or 0.0))
        legs: List[LegCost] = [
            LegCost(
                leg_role="bridge_out",
                venue_id=primary_venue_id,
                fee_bps=primary_fee_bps,
                slippage_pct=float(slippage_bridge_pct) / 2.0,
                gas_estimate_usd=gas_src,
                fee_kind="bridge_fee_src",
            ),
            LegCost(
                leg_role="bridge_in",
                venue_id=secondary_venue_id,
                fee_bps=secondary_fee_bps,
                slippage_pct=float(slippage_bridge_pct) / 2.0,
                gas_estimate_usd=gas_dst,
                # Bridge fee modelled as extra_cost on the inbound leg.
                extra_cost_usd=bridge_fee_usd,
                fee_kind="bridge_fee_dst",
            ),
        ]
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
        rationale: List[str] = [
            f"gas {gas_src:.2f}+{gas_dst:.2f} USD over ${notional:.0f}",
            f"bridge_fee ${bridge_fee_usd:.2f} · "
            f"slippage {slippage_bridge_pct:.2f}%",
        ]
        if roi.confidence_label != "insufficient":
            rationale.append(
                f"ROI band {roi.base_low}% – {roi.base_high}% "
                f"(n={roi.sample_size}, {roi.confidence_label})"
            )
        else:
            rationale.append("ROI history insufficient — neutral framing")
        return BridgeEconomicsResult(
            economics=econ, roi=roi, notional_usd=notional,
            source_chain=src_n, destination_chain=dst_n, bridge=bridge_n,
            total_bridge_fee_usd=bridge_fee_usd,
            gas_source_chain_usd=gas_src,
            gas_destination_chain_usd=gas_dst,
            rationale=rationale,
        )
