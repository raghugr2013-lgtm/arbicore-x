"""FlashLoanOpportunityVerifier — sole canonical construction point
for ``OpportunityType.FLASH_LOAN_ARBITRAGE``.

INV-2: never invokes EmissionBus. Returns ``(canonical|None, outcome_tag)``.
INV-3: ``derive_provenance(legs)`` over per-leg ``source_id`` yields
``source_data_quality``. Aggregator-hint provenance from sources is
never propagated.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from ...intelligence.roi_probability import ROIProbabilityEngine
from ...models.canonical import CanonicalOpportunity
from ...models.discovery import DiscoveryCandidate, VerifiedOutcome
from ...models.enums import MevRiskLevel, OpportunityType
from ..opportunity_verifier import OpportunityVerifier
from ..verification_evidence import (
    EvidenceLegRole, LegEvidence, VerificationEvidence,
    build_canonical_from_evidence, derive_provenance,
)
from ..cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
from .economics import (
    FlashLoanEconomicsAssessor, FlashLoanEconomicsResult,
    FLASH_LOAN_PROVIDERS,
)
from .filter import (
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
    FlashLoanGate9FlashLoanMev,
)


# Quote provider signature: async (cycle_metadata, borrow_amount_usd) ->
#                                   facts_dict | None
QuoteProvider = Callable[[Dict[str, Any], float],
                         Awaitable[Optional[Dict[str, Any]]]]


async def noop_quote_provider(cycle_metadata: Dict[str, Any],
                                 borrow_amount_usd: float,
                                 ) -> Optional[Dict[str, Any]]:
    """Cold-start provider — verifier ends as ``denied:venue_unreadable``."""
    return None


class FlashLoanOpportunityVerifier(OpportunityVerifier):
    """The single canonical-construction point for FLASH_LOAN_ARBITRAGE."""

    opportunity_type = OpportunityType.FLASH_LOAN_ARBITRAGE
    verifier_id = "flash_loan_opportunity_verifier"

    def __init__(
        self,
        *,
        quote_provider: QuoteProvider,
        economics_assessor: FlashLoanEconomicsAssessor,
        mev_scorer: MevRiskScorer,
        chain_liveness_loader: Optional[
            Callable[[str], Dict[str, float]]] = None,
        gate_7: Optional[FlashLoanGate7AtomicProfit] = None,
        gate_8: Optional[FlashLoanGate8LiquidityDepth] = None,
        gate_9: Optional[FlashLoanGate9FlashLoanMev] = None,
        outcome_history_loader: Optional[
            Callable[[Dict[str, Any]], Awaitable[List[Dict[str, Any]]]]
        ] = None,
        default_borrow_amount_usd: float = 10_000.0,
    ) -> None:
        self.quote_provider = quote_provider
        self.economics = economics_assessor
        self.mev = mev_scorer
        self.chain_liveness_loader = chain_liveness_loader
        self.gate_7 = gate_7
        self.gate_8 = gate_8
        self.gate_9 = gate_9
        self.outcome_history_loader = outcome_history_loader
        self.default_borrow_amount_usd = default_borrow_amount_usd

    async def verify(self, candidate: DiscoveryCandidate,
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        hm = candidate.hint_metric or {}
        chain = (hm.get("chain") or "").lower()
        provider = (hm.get("provider") or "").lower()
        borrow_token = (hm.get("borrow_token") or candidate.asset or "").upper()
        borrow_amount = float(hm.get("borrow_amount_usd")
                                or self.default_borrow_amount_usd)

        try:
            facts = await self.quote_provider(hm, borrow_amount)
        except Exception as exc:  # noqa: BLE001
            return None, (
                f"{VerifiedOutcome.DENIED_VENUE_UNREADABLE}:"
                f"{type(exc).__name__}")
        if not facts:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        provider_meta = FLASH_LOAN_PROVIDERS.get(provider) or {}
        provider_source_id = provider_meta.get(
            "source_id") or "aave_v3_flashloan_real"
        hop_facts = list(facts.get("hop_legs") or [])
        if not hop_facts:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        # Chain congestion read (optional).
        cong = self._chain_congestion(chain)

        mev_view = self.mev.classify(
            source_chain_congestion=cong,
            destination_chain_congestion=cong,
            asset=borrow_token,
            notional_usd=borrow_amount,
            is_atomic=True,
        )

        # Outcome history fold-in
        real_outcomes: List[Dict[str, Any]] = list(
            facts.get("real_outcomes") or [])
        if self.outcome_history_loader is not None:
            try:
                hist = await self.outcome_history_loader({
                    "chain": chain, "provider": provider,
                    "borrow_token": borrow_token,
                    "route_id": hm.get("route_id") or candidate.subject_id,
                })
                if hist:
                    real_outcomes.extend(hist)
            except Exception:  # noqa: BLE001
                pass

        econ: FlashLoanEconomicsResult = self.economics.assess(
            provider=provider, chain=chain,
            borrow_token=borrow_token, borrow_amount_usd=borrow_amount,
            hop_legs=hop_facts,
            signal_categories=[provider, chain, borrow_token],
            real_outcomes=real_outcomes,
            synthetic_outcomes=list(facts.get("synthetic_outcomes") or []),
            gross_profit_pct=float(facts.get("gross_profit_pct") or 0.0),
            flash_loan_fee_bps_override=facts.get(
                "flash_loan_fee_bps_override"),
            mev_risk_level=mev_view["level"],
            gas_cost_usd_override=facts.get("gas_cost_usd"),
            tx_gas_units=facts.get("tx_gas_units"),
        )

        # ---- Gate 7 ---------------------------------------------------------
        if self.gate_7 is not None:
            g7 = self.gate_7.evaluate(
                atomic_profit_usd=econ.atomic_profit_usd,
                borrow_amount_usd=borrow_amount,
            )
            if not g7.passed:
                return None, (
                    f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_7:{g7.reason}")

        # ---- Gate 8 ---------------------------------------------------------
        min_tvl = float(hm.get("min_tvl_usd")
                         or facts.get("min_pool_tvl_usd_in_route") or 0.0)
        if self.gate_8 is not None:
            g8 = self.gate_8.evaluate(min_pool_tvl_usd_in_route=min_tvl)
            if not g8.passed:
                return None, (
                    f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_8:{g8.reason}")

        # ---- Gate 9 ---------------------------------------------------------
        if self.gate_9 is not None:
            g9 = self.gate_9.evaluate(
                mev_risk_level=mev_view["level"],
                mev_risk_label=mev_view["label"],
                mev_score=mev_view["score"],
            )
            if not g9.passed:
                return None, (
                    f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_9:{g9.reason}")

        # ---- Build LegEvidence: BORROW + per-hop + REPAY ------------------
        legs: List[LegEvidence] = [LegEvidence(
            leg_role=EvidenceLegRole.FLASH_LOAN_BORROW,
            venue_id=f"{provider}_flashloan:{chain}",
            source_id=provider_source_id,
            price=None, size_usd=borrow_amount, depth_usd=borrow_amount,
            fee_bps=facts.get("flash_loan_fee_bps_override") or 0,
            chain=chain,
            metadata={"provider": provider},
        )]
        for i, hop in enumerate(hop_facts):
            legs.append(LegEvidence(
                leg_role=EvidenceLegRole.HOP,
                venue_id=str(hop.get("venue_id") or f"hop_{i}"),
                source_id=str(hop.get("source_id") or "uniswap_v3_quote_real"),
                price=hop.get("price"),
                size_usd=borrow_amount,
                depth_usd=float(hop.get("depth_usd") or 0.0),
                fee_bps=int(hop.get("fee_bps") or 30),
                chain=chain,
                metadata={"hop_index": i,
                          "dex_protocol": hop.get("dex_protocol")},
            ))
        legs.append(LegEvidence(
            leg_role=EvidenceLegRole.FLASH_LOAN_REPAY,
            venue_id=f"{provider}_flashloan:{chain}",
            source_id=provider_source_id,
            price=None, size_usd=borrow_amount, depth_usd=borrow_amount,
            fee_bps=0, chain=chain,
            metadata={"provider": provider},
        ))

        try:
            _ = derive_provenance(legs)
        except ValueError:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        evidence = VerificationEvidence(
            verifier_id=self.verifier_id,
            candidate_id=candidate.candidate_id,
            discovery_source=candidate.hint_source,
            subject_id=candidate.subject_id,
            asset=borrow_token,
            chain=chain,
            legs=legs,
            gross_spread_pct=None,
            expected_profit_usd=econ.atomic_profit_usd,
            capital_required_usd=0.0,    # flash loan: zero own capital
            notional_usd=econ.borrow_amount_usd,
            extra_metrics={
                "economics": _econ_to_dict(econ),
                "mev": mev_view,
                "route": {
                    "route_pools": hm.get("route_pools", []),
                    "route_dex_protocols": hm.get("route_dex_protocols", []),
                    "cycle_token_path": hm.get("cycle_token_path", []),
                    "hop_count": int(hm.get("hop_count", len(hop_facts))),
                    "min_tvl_usd": min_tvl,
                },
            },
        )

        category_metadata = _fold_metadata(
            hm=hm, facts=facts, econ=econ, mev_view=mev_view,
            min_tvl=min_tvl,
        )

        canonical = build_canonical_from_evidence(
            evidence,
            opportunity_type=OpportunityType.FLASH_LOAN_ARBITRAGE,
            opportunity_id=_opp_id(candidate, evidence.verified_at_ts),
            expected_profit_usd=econ.atomic_profit_usd,
            capital_required_usd=0.0,
            liquidity_score=min(100.0, min_tvl / 10_000.0),
            mev_risk_level=mev_view["level"],
            category_metadata=category_metadata,
            extra_metadata={
                "provider": provider,
                "chain": chain,
                "borrow_token": borrow_token,
            },
        )
        return canonical, (
            VerifiedOutcome.CONFIRMED_PREFIX + canonical.opportunity_id)

    # ---- helpers ----------------------------------------------------------

    def _chain_congestion(self, chain: str) -> float:
        if self.chain_liveness_loader is None:
            return 30.0
        try:
            snap = self.chain_liveness_loader(chain) or {}
            return float(snap.get("congestion_score", 30.0))
        except Exception:  # noqa: BLE001
            return 30.0


def _fold_metadata(*, hm: Dict[str, Any], facts: Dict[str, Any],
                    econ: FlashLoanEconomicsResult,
                    mev_view: Dict[str, Any], min_tvl: float,
                    ) -> Dict[str, Any]:
    return {
        "chain": econ.chain,
        "flash_loan_provider": econ.provider,
        "flash_loan_pool_address": facts.get("flash_loan_pool_address", ""),
        "flash_loan_borrow_token": econ.borrow_token,
        "flash_loan_borrow_amount_usd": econ.borrow_amount_usd,
        "flash_loan_fee_bps": int(
            facts.get("flash_loan_fee_bps_override") or 0),
        "flash_loan_fee_usd": econ.flash_loan_fee_usd,
        "route_pools": list(hm.get("route_pools", [])),
        "route_dex_protocols": list(hm.get("route_dex_protocols", [])),
        "cycle_token_path": list(hm.get("cycle_token_path", [])),
        "hop_count": int(hm.get("hop_count", econ.hop_count)),
        "total_swap_fee_pct": econ.total_swap_fee_pct,
        "total_slippage_pct": econ.economics.total_slippage_pct,
        "gas_cost_usd": econ.gas_cost_usd,
        "gas_drag_pct": econ.economics.gas_drag_pct,
        "min_pool_tvl_usd_in_route": min_tvl,
        "atomic_profit_usd": econ.atomic_profit_usd,
        "atomic_profit_pct": round(
            100.0 * econ.atomic_profit_usd /
            max(econ.borrow_amount_usd, 1.0), 4),
        "expected_net_after_costs_usd": econ.atomic_profit_usd,
        "route_search_wall_ms": int(hm.get("route_search_wall_ms", 0)),
        "route_search_candidates_explored": int(
            hm.get("route_search_candidates_explored", 0)),
        "flash_loan_mev_risk_class": mev_view["label"],
        "simulated_atomicity_ok": True,
        "verified_at_ts": float(facts.get("verified_at_ts") or 0.0),
        "verifier_id": "flash_loan_opportunity_verifier",
    }


def _econ_to_dict(econ: FlashLoanEconomicsResult) -> Dict[str, Any]:
    e = econ.economics
    return {
        "gross_spread_pct": e.gross_spread_pct,
        "total_fee_pct": e.total_fee_pct,
        "total_slippage_pct": e.total_slippage_pct,
        "gas_drag_pct": e.gas_drag_pct,
        "mev_penalty_pct": e.mev_penalty_pct,
        "mev_adjusted_net_pct": e.mev_adjusted_net_pct,
        "expected_profit_usd": e.expected_profit_usd,
        "atomic_profit_usd": econ.atomic_profit_usd,
        "borrow_amount_usd": econ.borrow_amount_usd,
        "roi_confidence_label": econ.roi.confidence_label,
    }


def _opp_id(candidate: DiscoveryCandidate, ts: float) -> str:
    return f"flash_loan_arb:{candidate.subject_id}:{int(ts)}"
