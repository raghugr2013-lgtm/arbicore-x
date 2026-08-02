"""CrossChainOpportunityVerifier — sole canonical construction point for
``OpportunityType.CROSS_CHAIN_ARBITRAGE``.

Verifier-first discipline (INV-2):
  - Implements ``OpportunityVerifier`` ABC; the registry routes every
    DiscoveryCandidate of type CROSS_CHAIN_ARBITRAGE here.
  - This module does NOT call EmissionBus. Returns
    ``(CanonicalOpportunity | None, outcome_tag)``; only the scanner
    orchestrator (``CrossChainArbitrageScanner._tick``) emits.

Provenance (INV-3):
  - Both legs (BRIDGE_OUT + BRIDGE_IN) carry a ``source_id`` returned by
    the transfer provider — one of ``lifi_quote_real`` or
    ``stargate_quote_real``. The universal ``derive_provenance``
    substrate yields ``source_data_quality=REAL``. Aggregator hint
    sources are never propagated to the canonical.
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
from .bridge_intelligence import BridgeRouteCatalog, MevRiskScorer
from .chain_liveness import ChainLivenessRegistry
from .economics import BridgeEconomicsAssessor, BridgeEconomicsResult
from .filter import (
    CrossChainGate7BridgeLiveness, CrossChainGate8ChainLiveness,
    CrossChainGate9CrossChainMev,
)
from .transfer_provider import TransferModelProvider


class CrossChainOpportunityVerifier(OpportunityVerifier):
    """The single canonical construction point for CROSS_CHAIN_ARBITRAGE."""

    opportunity_type = OpportunityType.CROSS_CHAIN_ARBITRAGE
    verifier_id = "cross_chain_opportunity_verifier"

    def __init__(self,
                 *,
                 transfer_provider: TransferModelProvider,
                 economics_assessor: BridgeEconomicsAssessor,
                 chain_liveness: ChainLivenessRegistry,
                 route_catalog: BridgeRouteCatalog,
                 mev_scorer: MevRiskScorer,
                 gate_7: Optional[CrossChainGate7BridgeLiveness] = None,
                 gate_8: Optional[CrossChainGate8ChainLiveness] = None,
                 gate_9: Optional[CrossChainGate9CrossChainMev] = None,
                 outcome_history_loader: Optional[
                     Callable[[Dict[str, Any]], Awaitable[List[Dict[str, Any]]]]
                 ] = None,
                 default_notional_usd: float = 1000.0,
                 ) -> None:
        self.transfer_provider = transfer_provider
        self.economics = economics_assessor
        self.chain_liveness = chain_liveness
        self.routes = route_catalog
        self.mev = mev_scorer
        self.gate_7 = gate_7
        self.gate_8 = gate_8
        self.gate_9 = gate_9
        # D-5.2 — optional operator-injected loader. Signature:
        #   async ({bridge, source_chain, destination_chain, asset}) -> [outcomes]
        # When wired, the verifier passes the returned list to the
        # economics assessor as ``real_outcomes`` (ROI engine consumer).
        # Default: None → economics assessor falls back to synthetic
        # outcomes (mirrors D-4 first-ship posture).
        self.outcome_history_loader = outcome_history_loader
        self.default_notional_usd = default_notional_usd

    async def verify(self, candidate: DiscoveryCandidate,
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        try:
            facts = await self.transfer_provider(candidate)
        except Exception as exc:  # noqa: BLE001
            return None, (
                f"{VerifiedOutcome.DENIED_VENUE_UNREADABLE}:"
                f"{type(exc).__name__}")
        if not facts:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE
        bridge = (facts.get("bridge") or "").lower()
        src_chain = (facts.get("source_chain") or "").lower()
        dst_chain = (facts.get("destination_chain") or "").lower()
        asset = (facts.get("asset") or candidate.asset or "").upper()
        source_id = facts.get("source_id") or "lifi_quote_real"
        notional = float(facts.get("notional_usd") or self.default_notional_usd)

        # ---- Bridge intelligence / chain liveness fold-in -----------------
        route = self.routes.get(
            bridge=bridge, source_chain=src_chain,
            destination_chain=dst_chain, asset=asset,
        )
        src_snap = self.chain_liveness.get(src_chain)
        dst_snap = self.chain_liveness.get(dst_chain)
        mev_view = self.mev.classify(
            bridge=bridge,
            source_chain_congestion=src_snap.congestion_score,
            destination_chain_congestion=dst_snap.congestion_score,
            asset=asset, notional_usd=notional,
        )

        # ---- Outcome history fold-in (D-5.2 hook) ------------------------
        real_outcomes: List[Dict[str, Any]] = list(
            facts.get("real_outcomes") or [])
        if self.outcome_history_loader is not None:
            try:
                history = await self.outcome_history_loader({
                    "bridge": bridge,
                    "source_chain": src_chain,
                    "destination_chain": dst_chain,
                    "asset": asset,
                })
                if history:
                    real_outcomes.extend(history)
            except Exception:  # noqa: BLE001
                # Loader failures must never break verification.
                pass

        # ---- Economics -----------------------------------------------------
        econ: BridgeEconomicsResult = self.economics.assess(
            bridge=bridge,
            source_chain=src_chain,
            destination_chain=dst_chain,
            primary_venue_id=facts.get("primary_venue_id", "unknown"),
            secondary_venue_id=facts.get("secondary_venue_id", "unknown"),
            primary_fee_bps=int(facts.get("primary_fee_bps") or 0),
            secondary_fee_bps=int(facts.get("secondary_fee_bps") or 0),
            slippage_bridge_pct=float(facts.get("slippage_bridge_pct") or 0.0),
            total_bridge_fee_usd=float(facts.get("total_bridge_fee_usd") or 0.0),
            signal_categories=[bridge, src_chain, dst_chain],
            real_outcomes=real_outcomes,
            synthetic_outcomes=list(facts.get("synthetic_outcomes") or []),
            notional_usd=notional,
            mev_risk_level=mev_view["level"],
            gas_source_chain_usd=facts.get("gas_source_chain_usd"),
            gas_destination_chain_usd=facts.get("gas_destination_chain_usd"),
        )

        # ---- Gate 7 ---------------------------------------------------------
        if self.gate_7 is not None:
            g7 = self.gate_7.evaluate(
                bridge=bridge,
                bridge_health_score=route.bridge_health_score,
                bridge_liveness_score=route.bridge_liveness_score,
                bridge_inventory_pct=route.bridge_inventory_pct,
                inbound_latency_p95_s=float(facts.get(
                    "inbound_latency_p95_s") or route.inbound_latency_p95_s),
            )
            if not g7.passed:
                return None, (
                    f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_7:{g7.reason}")
        # ---- Gate 8 ---------------------------------------------------------
        if self.gate_8 is not None:
            g8 = self.gate_8.evaluate(
                source_chain=src_chain, destination_chain=dst_chain,
                source_finality_s=src_snap.finality_s,
                destination_finality_s=dst_snap.finality_s,
                source_congestion_score=src_snap.congestion_score,
                destination_congestion_score=dst_snap.congestion_score,
            )
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

        # ---- Build VerificationEvidence ------------------------------------
        legs: List[LegEvidence] = [
            LegEvidence(
                leg_role=EvidenceLegRole.BRIDGE_OUT,
                venue_id=facts.get("primary_venue_id", "unknown"),
                source_id=source_id,
                price=facts.get("expected_out_amount_usd"),
                size_usd=notional,
                depth_usd=float(facts.get("expected_out_amount_usd") or 0.0),
                fee_bps=int(facts.get("primary_fee_bps") or 0),
                chain=src_chain,
                metadata={"bridge": bridge},
            ),
            LegEvidence(
                leg_role=EvidenceLegRole.BRIDGE_IN,
                venue_id=facts.get("secondary_venue_id", "unknown"),
                source_id=source_id,
                price=facts.get("expected_out_amount_usd"),
                size_usd=notional,
                depth_usd=float(facts.get("expected_out_amount_usd") or 0.0),
                fee_bps=int(facts.get("secondary_fee_bps") or 0),
                chain=dst_chain,
                metadata={"bridge": bridge},
            ),
        ]
        try:
            _ = derive_provenance(legs)
        except ValueError:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        evidence = VerificationEvidence(
            verifier_id=self.verifier_id,
            candidate_id=candidate.candidate_id,
            discovery_source=candidate.hint_source,
            subject_id=candidate.subject_id,
            asset=asset,
            chain=dst_chain,
            legs=legs,
            gross_spread_pct=None,
            expected_profit_usd=econ.economics.expected_profit_usd,
            capital_required_usd=econ.economics.capital_required_usd,
            notional_usd=econ.notional_usd,
            extra_metrics={
                "economics": _econ_to_dict(econ),
                "route": route.to_dict(),
                "mev": mev_view,
                "source_chain_snapshot": src_snap.to_dict(),
                "destination_chain_snapshot": dst_snap.to_dict(),
            },
        )

        category_metadata = _fold_metadata(
            facts=facts, econ=econ, route=route,
            src_snap=src_snap, dst_snap=dst_snap, mev_view=mev_view,
        )

        canonical = build_canonical_from_evidence(
            evidence,
            opportunity_type=OpportunityType.CROSS_CHAIN_ARBITRAGE,
            opportunity_id=_opp_id(candidate, evidence.verified_at_ts),
            expected_profit_usd=econ.economics.expected_profit_usd,
            capital_required_usd=econ.economics.capital_required_usd,
            liquidity_score=min(100.0, route.bridge_inventory_pct),
            mev_risk_level=mev_view["level"],
            category_metadata=category_metadata,
            extra_metadata={
                "bridge": bridge,
                "corridor_id": route.corridor_id,
            },
        )
        return canonical, VerifiedOutcome.CONFIRMED_PREFIX + canonical.opportunity_id


# ============================================================================
# Helpers
# ============================================================================

def _fold_metadata(*,
                    facts: Dict[str, Any],
                    econ: BridgeEconomicsResult,
                    route,
                    src_snap, dst_snap, mev_view,
                    ) -> Dict[str, Any]:
    """Project everything into the D-5.0 CROSS_CHAIN vocabulary."""
    out: Dict[str, Any] = {
        # Phase B baseline
        "source_chain": route.source_chain,
        "destination_chain": route.destination_chain,
        "bridge_provider": route.bridge,
        "bridge_latency_s": float(facts.get("inbound_latency_p50_s")
                                   or route.inbound_latency_p50_s),
        "bridge_fee_usd": econ.total_bridge_fee_usd,
        # Corridor identity
        "bridge_route_id": route.route_id,
        "bridge_corridor_id": route.corridor_id,
        # Gate 7 inputs
        "bridge_health_score": route.bridge_health_score,
        "bridge_liveness_score": route.bridge_liveness_score,
        "inbound_latency_p50_s": route.inbound_latency_p50_s,
        "inbound_latency_p95_s": route.inbound_latency_p95_s,
        "bridge_inventory_pct": route.bridge_inventory_pct,
        # Gate 8 inputs
        "source_chain_finality_s": src_snap.finality_s,
        "destination_chain_finality_s": dst_snap.finality_s,
        "source_chain_congestion_score": src_snap.congestion_score,
        "destination_chain_congestion_score": dst_snap.congestion_score,
        # Transfer modelling outputs
        "expected_out_amount": float(facts.get("expected_out_amount") or 0.0),
        "expected_out_amount_usd": float(
            facts.get("expected_out_amount_usd") or 0.0),
        "slippage_bridge_pct": float(facts.get("slippage_bridge_pct") or 0.0),
        "transfer_modelling_confidence": float(
            facts.get("transfer_modelling_confidence") or 0.0),
        # Cost surface
        "gas_source_chain_usd": econ.gas_source_chain_usd,
        "gas_destination_chain_usd": econ.gas_destination_chain_usd,
        "total_bridge_fee_usd": econ.total_bridge_fee_usd,
        "total_round_trip_cost_pct": round(
            econ.economics.total_fee_pct +
            econ.economics.total_slippage_pct +
            econ.economics.gas_drag_pct, 4),
        # MEV
        "cross_chain_mev_risk_class": mev_view["label"],
        # Audit
        "verified_at_ts": float(facts.get("verified_at_ts") or 0.0),
        "transfer_quote_source": str(facts.get("quote_source") or ""),
    }
    return out


def _econ_to_dict(econ: BridgeEconomicsResult) -> Dict[str, Any]:
    e = econ.economics
    return {
        "gross_spread_pct": e.gross_spread_pct,
        "total_fee_pct": e.total_fee_pct,
        "total_slippage_pct": e.total_slippage_pct,
        "gas_drag_pct": e.gas_drag_pct,
        "mev_penalty_pct": e.mev_penalty_pct,
        "mev_adjusted_net_pct": e.mev_adjusted_net_pct,
        "expected_profit_usd": e.expected_profit_usd,
        "notional_usd": econ.notional_usd,
        "roi_confidence_label": econ.roi.confidence_label,
    }


def _opp_id(candidate: DiscoveryCandidate, ts: float) -> str:
    return f"cross_chain_arb:{candidate.subject_id}:{int(ts)}"
