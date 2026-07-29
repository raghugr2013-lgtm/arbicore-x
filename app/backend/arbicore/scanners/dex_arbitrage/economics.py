"""ArbiCore X — Phase D D-3.3 DEXEconomicsAssessor.

Thin DEX-specific facade over the universal economics substrate.
Maps two ``DEXQuoteResult`` instances (buy + sell) into universal
``LegCost`` objects and dispatches to ``aggregate_economics``.

INV-2 safe: pure-compute; no EmissionBus; no canonical mutation.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..economics import (
    EconomicAssessment, LegCost, aggregate_economics,
    per_chain_gas_estimate_usd,
)
from ...models.enums import MevRiskLevel
from .quoter import DEXQuoteResult


class DEXEconomicsAssessor:
    """DEX-specific assessment. Stateless; safe to share across verifiers."""

    def __init__(self, *, config_loader=lambda: {}) -> None:
        self._config_loader = config_loader

    def assess(self, *,
               buy_quote: DEXQuoteResult,
               sell_quote: DEXQuoteResult,
               chain: str,
               gross_spread_pct: float,
               notional_usd: float,
               mev_risk_level: MevRiskLevel = MevRiskLevel.LOW,
               ) -> EconomicAssessment:
        cfg = self._config_loader() or {}
        venue_fees: Dict[str, Dict[str, Any]] = cfg.get("venue_fees", {}) or {}
        mev_factors = cfg.get("mev_risk_factor") or None
        gas_overrides = cfg.get("per_chain_gas_estimate_usd") or None

        per_chain_gas = per_chain_gas_estimate_usd(chain, overrides=gas_overrides)

        def _leg(role: str, q: DEXQuoteResult) -> LegCost:
            fee_bps = q.fee_tier_bps
            if fee_bps is None:
                fee_bps = int(((venue_fees.get(q.dex) or {}).get("taker_bps", 5)))
            gas_est = q.gas_estimate_usd
            if gas_est is None:
                gas_est = per_chain_gas
            return LegCost(
                leg_role=role,
                venue_id=f"{q.dex}:{q.chain}:{q.pool_address or ''}",
                fee_bps=int(fee_bps) if fee_bps is not None else 0,
                slippage_pct=float(q.slippage_pct or 0.0),
                gas_estimate_usd=float(gas_est or 0.0),
                fee_kind="swap_fee",
            )

        legs = [_leg("buy", buy_quote), _leg("sell", sell_quote)]
        return aggregate_economics(
            legs=legs,
            gross_spread_pct=gross_spread_pct,
            notional_usd=notional_usd,
            mev_risk_level=mev_risk_level,
            mev_risk_factors=mev_factors,
        )


__all__ = ["DEXEconomicsAssessor"]
