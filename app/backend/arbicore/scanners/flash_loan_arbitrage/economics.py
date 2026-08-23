"""FlashLoanEconomicsAssessor + inline provider catalog.

Consumes the universal ``aggregate_economics`` substrate. Models the
flash-loan premium as an extra ``LegCost(fee_kind='flash_loan_premium')``
leg appended to the multi-hop swap legs.

INV-1/2/3 preserved.
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


# ============================================================================
# Provider catalog (inline — no separate file per operator absorption review)
# ============================================================================

# Operator-locked at D-6.0. fee_bps applies to flash-borrow amount.
# Note: Uniswap V3 fee depends on the pool's fee tier; the verifier
# resolves the actual tier from the borrow-pool address.
FLASH_LOAN_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "aave_v3": {
        "fee_bps_default": 5,
        "source_id": "aave_v3_flashloan_real",
        "supports_chains": (
            "ethereum", "arbitrum", "base", "optimism", "polygon"),
    },
    "balancer_v2": {
        "fee_bps_default": 0,
        "source_id": "balancer_v2_flashloan_real",
        "supports_chains": (
            "ethereum", "arbitrum", "base", "optimism", "polygon"),
    },
    "uniswap_v3": {
        # Uniswap V3 flash fee = pool swap-fee tier (caller-resolved).
        # 5 / 30 / 100 bps. We expose only a conservative default; the
        # verifier reads the actual tier and overrides per call.
        "fee_bps_default": 30,
        "source_id": "uniswap_v3_flashloan_real",
        "supports_chains": (
            "ethereum", "arbitrum", "base", "optimism", "polygon"),
    },
    "morpho_blue": {
        # T1: 0-fee, gas-efficient singleton flash loans. Ethereum + Base.
        "fee_bps_default": 0,
        "source_id": "morpho_blue_flashloan_real",
        "supports_chains": ("ethereum", "base"),
    },
}


def provider_fee_bps(provider: str,
                      override_tier_bps: Optional[int] = None,
                      ) -> int:
    """Return the fee in basis points for the given provider.

    Override (Uniswap V3 caller) takes precedence over the catalog
    default. Unknown provider returns a conservative 30 bps.
    """
    if override_tier_bps is not None:
        return int(override_tier_bps)
    meta = FLASH_LOAN_PROVIDERS.get((provider or "").lower())
    if meta is None:
        return 30
    return int(meta["fee_bps_default"])


# ============================================================================
# FlashLoanEconomicsResult + Assessor
# ============================================================================

@dataclass
class FlashLoanEconomicsResult:
    """Atomic flash-loan economics summary."""
    economics: EconomicAssessment
    roi: ROIProbability
    chain: str
    provider: str
    borrow_token: str
    borrow_amount_usd: float
    flash_loan_fee_usd: float
    gas_cost_usd: float
    atomic_profit_usd: float
    hop_count: int
    total_swap_fee_pct: float
    rationale: List[str] = field(default_factory=list)

    def to_metadata(self) -> Dict[str, Any]:
        return {
            "chain": self.chain,
            "flash_loan_provider": self.provider,
            "flash_loan_borrow_token": self.borrow_token,
            "flash_loan_borrow_amount_usd": self.borrow_amount_usd,
            "flash_loan_fee_usd": self.flash_loan_fee_usd,
            "gas_cost_usd": self.gas_cost_usd,
            "atomic_profit_usd": self.atomic_profit_usd,
            "atomic_profit_pct": round(
                100.0 * self.atomic_profit_usd /
                max(self.borrow_amount_usd, 1.0), 4),
            "hop_count": self.hop_count,
            "total_swap_fee_pct": self.total_swap_fee_pct,
        }


class FlashLoanEconomicsAssessor:
    """Stateless. Wraps ``aggregate_economics`` for the multi-hop
    atomic flash-loan family.
    """

    def __init__(
        self,
        *,
        roi_engine,
        per_chain_gas_overrides: Optional[Dict[str, float]] = None,
        default_borrow_amount_usd: float = 10_000.0,
    ) -> None:
        self.roi_engine = roi_engine
        self.gas_overrides = per_chain_gas_overrides or {}
        self.default_borrow_amount_usd = default_borrow_amount_usd

    def assess(
        self,
        *,
        provider: str,
        chain: str,
        borrow_token: str,
        borrow_amount_usd: Optional[float] = None,
        hop_legs: List[Dict[str, Any]],
        signal_categories: List[str],
        real_outcomes: List[Dict[str, Any]],
        synthetic_outcomes: Optional[List[Dict[str, Any]]] = None,
        gross_profit_pct: float = 0.0,
        flash_loan_fee_bps_override: Optional[int] = None,
        mev_risk_level: MevRiskLevel = MevRiskLevel.MEDIUM,
        gas_cost_usd_override: Optional[float] = None,
        tx_gas_units: Optional[int] = None,
    ) -> FlashLoanEconomicsResult:
        """Build the multi-hop economics surface.

        ``hop_legs`` schema: list of dicts with keys ``venue_id``,
        ``fee_bps``, ``slippage_pct``. Each becomes a ``LegCost``.
        """
        borrow = float(borrow_amount_usd or self.default_borrow_amount_usd)
        provider_n = (provider or "").lower()
        chain_n = (chain or "").lower()

        # Flash-loan premium (added once as a separate cost leg).
        fee_bps = provider_fee_bps(provider_n,
                                     override_tier_bps=flash_loan_fee_bps_override)
        flash_fee_usd = borrow * (fee_bps / 10_000.0)

        # Per-chain gas — operator override OR per_chain_gas_estimate_usd.
        gas_cost = (float(gas_cost_usd_override)
                    if gas_cost_usd_override is not None
                    else per_chain_gas_estimate_usd(chain_n,
                                                       self.gas_overrides))
        # Tx-gas-units scaling — flash-loan txs are multi-hop and burn
        # more gas than a single-leg swap. If config provides a scaling
        # hint, apply it as a multiplier vs the base single-swap gas.
        if tx_gas_units is not None and tx_gas_units > 0:
            gas_cost = gas_cost * (float(tx_gas_units) / 250_000.0)

        # Build per-hop LegCost objects + flash-loan premium leg.
        legs: List[LegCost] = []
        for i, hop in enumerate(hop_legs):
            legs.append(LegCost(
                leg_role=f"hop_{i}",
                venue_id=str(hop.get("venue_id", f"hop_{i}")),
                fee_bps=int(hop.get("fee_bps", 30)),
                slippage_pct=float(hop.get("slippage_pct", 0.0)),
                gas_estimate_usd=0.0,  # gas applied once on the loan leg
                fee_kind="swap_fee",
            ))
        # Flash-loan premium leg
        legs.append(LegCost(
            leg_role="flash_loan_premium",
            venue_id=f"{provider_n}_flashloan",
            fee_bps=fee_bps,
            slippage_pct=0.0,
            gas_estimate_usd=gas_cost,   # all gas accounted here
            extra_cost_usd=0.0,
            fee_kind="flash_loan_premium",
        ))

        econ = aggregate_economics(
            legs=legs, gross_spread_pct=float(gross_profit_pct),
            notional_usd=borrow, mev_risk_level=mev_risk_level,
        )
        roi = self.roi_engine.estimate(
            categories=signal_categories,
            real_outcomes=real_outcomes,
            synthetic_outcomes=synthetic_outcomes,
        )
        atomic = econ.expected_profit_usd
        total_swap_fee_pct = sum((leg.fee_bps for leg in legs[:-1]),
                                  0) / 100.0
        rationale: List[str] = [
            f"borrow ${borrow:.0f} on {provider_n} @ {fee_bps} bps "
            f"(${flash_fee_usd:.2f})",
            f"{len(hop_legs)} hops on {chain_n}, gas ${gas_cost:.2f}",
        ]
        if roi.confidence_label != "insufficient":
            rationale.append(
                f"ROI band {roi.base_low}% – {roi.base_high}% "
                f"(n={roi.sample_size}, {roi.confidence_label})"
            )
        else:
            rationale.append("ROI history insufficient — neutral framing")
        return FlashLoanEconomicsResult(
            economics=econ, roi=roi, chain=chain_n, provider=provider_n,
            borrow_token=borrow_token, borrow_amount_usd=borrow,
            flash_loan_fee_usd=flash_fee_usd, gas_cost_usd=gas_cost,
            atomic_profit_usd=atomic, hop_count=len(hop_legs),
            total_swap_fee_pct=total_swap_fee_pct,
            rationale=rationale,
        )
