"""LaunchOpportunityVerifier — sole canonical construction point for
``OpportunityType.LAUNCH_ARBITRAGE``.

Verifier-first discipline (INV-2):
  - Implements ``OpportunityVerifier`` ABC; the registry routes every
    DiscoveryCandidate of type LAUNCH_ARBITRAGE here.
  - This module does NOT call EmissionBus. It returns
    (CanonicalOpportunity | None, outcome_tag) to the future D-4.5 scanner
    which is the single emit caller.
  - All five D-4.3 evidence engines (PhaseClassifier, LaunchTimelineEngine,
    ROIProbabilityEngine, SmartMoneyDetector, HolderAnalytics) are folded
    into ``CanonicalOpportunity.category_metadata``.

Provenance (INV-3):
  - Both legs are tagged with ``source_id = "helius_token_rpc"`` (or the
    on-chain RPC source actually used). The universal
    ``derive_provenance`` over those legs yields ``source_data_quality``
    — never the aggregator HINT classification.

This verifier does NOT execute live RPC calls itself. The D-4.5 scanner
constructs a ``LaunchVenueProvider`` (Helius-backed) and injects the per-
candidate verification facts as the ``venue_provider`` callable below.
That keeps the verifier pure, deterministically testable, and provider-
agnostic.
"""
from __future__ import annotations

import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Tuple

from ...intel.launch.holder_analytics import HolderAnalytics, HolderSnapshot
from ...intel.launch.phase_classifier import PhaseClassifier
from ...intel.launch.smart_money import (
    SmartMoneyDetector,
    SmartMoneyPanel,
)
from ...intel.launch.timeline import LaunchTimelineEngine
from ...models.canonical import CanonicalOpportunity
from ...models.discovery import DiscoveryCandidate, VerifiedOutcome
from ...models.enums import (
    DataProvenance,
    MevRiskLevel,
    OpportunityType,
)
from ..opportunity_verifier import OpportunityVerifier
from ..verification_evidence import (
    EvidenceLegRole,
    LegEvidence,
    VerificationEvidence,
    build_canonical_from_evidence,
    derive_provenance,
)
from .economics import LaunchEconomicsAssessor, LaunchEconomicsResult


# ============================================================================
# Venue-provider protocol — D-4.5 wires the live Helius reader
# ============================================================================

class LaunchVenueProvider(Protocol):
    """Read-only authoritative provider. Returns a dict shaped as::

        {
            "primary_venue_id": str,       # e.g. "pumpfun:solana:<mint>"
            "secondary_venue_id": str,     # e.g. "raydium:solana:<pool>"
            "chain": str,                  # 'solana'
            "source_id": str,              # SOURCE_REGISTRY key for both legs
                                            # — typically 'helius_token_rpc'
            "listing_price_usd": float | None,
            "liquidity_usd": float,
            "primary_fee_bps": int,
            "secondary_fee_bps": int,
            "slippage_primary_pct": float,
            "slippage_secondary_pct": float,
            "mint_authority_revoked": bool,
            "freeze_authority_revoked": bool,
            "lp_burned_or_locked_pct": float,
            "total_supply": float,
            "holders": list[dict],         # {address, balance, last_seen_ts}
            "launchpad": str,              # 'pumpfun' | 'raydium' | ...
            "age_hours": float,
            "buyer_wallets": list[str],
            "wallet_profiles": dict[str, dict],   # address -> WalletProfile.dict()
            "signal_categories": list[str],
            "real_outcomes": list[dict],
            "synthetic_outcomes": list[dict],
            "token_intel": dict,           # passes to PhaseClassifier/TimelineEngine
                                            # carries token-shaped fields:
                                            # score, score_delta_24h, liquidity_usd,
                                            # volume_h24, holders, age_hours,
                                            # price_change_24h, launchpad_id, ...
            "signals": list[dict],         # signals consumed by PhaseClassifier
        }
    """

    async def __call__(self,
                       candidate: DiscoveryCandidate,
                       ) -> Optional[Dict[str, Any]]:
        ...


# ============================================================================
# LaunchOpportunityVerifier
# ============================================================================

class LaunchOpportunityVerifier(OpportunityVerifier):
    """The single canonical construction point for LAUNCH_ARBITRAGE.

    Returned ``CanonicalOpportunity`` is INV-1-compliant (built fresh from
    LegEvidence — never from the candidate directly) and INV-3-compliant
    (source_data_quality derived from per-leg SOURCE_REGISTRY classifications,
    NOT from aggregator HINTs).
    """

    opportunity_type = OpportunityType.LAUNCH_ARBITRAGE
    verifier_id = "launch_opportunity_verifier"

    def __init__(self,
                 *,
                 venue_provider: LaunchVenueProvider,
                 phase_classifier: PhaseClassifier,
                 timeline_engine: LaunchTimelineEngine,
                 smart_money_detector: SmartMoneyDetector,
                 holder_analytics: HolderAnalytics,
                 economics_assessor: LaunchEconomicsAssessor,
                 gate_1: Optional[Any] = None,
                 gate_6: Optional[Any] = None,
                 default_notional_usd: float = 250.0,
                 ) -> None:
        self.venue_provider = venue_provider
        self.phase = phase_classifier
        self.timeline = timeline_engine
        self.smart_money = smart_money_detector
        self.holders = holder_analytics
        self.economics = economics_assessor
        self.gate_1 = gate_1                # LaunchGate1Filter (operator-tunable)
        self.gate_6 = gate_6                # LaunchGate6RugRiskFilter
        self.default_notional_usd = default_notional_usd

    async def verify(self, candidate: DiscoveryCandidate,
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        """Returns (canonical, outcome_tag).

        Outcome tags come from ``VerifiedOutcome`` vocabulary. On any
        canonical construction the scanner orchestrator is responsible for
        the single emit (INV-2). This method only constructs the value
        object — it does not persist, mutate state, or emit.
        """
        try:
            facts = await self.venue_provider(candidate)
        except Exception as exc:  # noqa: BLE001
            return None, f"{VerifiedOutcome.DENIED_VENUE_UNREADABLE}:{type(exc).__name__}"
        if not facts:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE
        chain = (facts.get("chain") or "solana").lower()
        source_id = facts.get("source_id") or "helius_token_rpc"

        # ---- D-4.3 evidence engines fold-in ----------------------------------
        # Phase + timeline are pure-sync; smart-money + holders may be async.
        phase_result = self.phase.classify(
            token=facts.get("token_intel") or {},
            signals=facts.get("signals") or [],
        )

        holder_snap = self.holders.analyse(
            token_id=candidate.subject_id,
            holders=facts.get("holders") or [],
            total_supply=float(facts.get("total_supply") or 0.0),
            now_ts=facts.get("verified_at_ts"),
        )

        smart_panel = await self.smart_money.panel(
            token_id=candidate.subject_id,
            buyer_wallets=list(facts.get("buyer_wallets") or []),
            profiles=facts.get("wallet_profiles") or {},
        )

        # economics needs the ROI from outcome history
        econ = self.economics.assess(
            chain=chain,
            primary_venue_id=facts.get("primary_venue_id", "unknown"),
            secondary_venue_id=facts.get("secondary_venue_id", "unknown"),
            listing_price_usd=facts.get("listing_price_usd"),
            primary_fee_bps=int(facts.get("primary_fee_bps") or 0),
            secondary_fee_bps=int(facts.get("secondary_fee_bps") or 0),
            slippage_primary_pct=float(facts.get("slippage_primary_pct") or 0.0),
            slippage_secondary_pct=float(facts.get("slippage_secondary_pct") or 0.0),
            signal_categories=list(facts.get("signal_categories") or []),
            real_outcomes=list(facts.get("real_outcomes") or []),
            synthetic_outcomes=list(facts.get("synthetic_outcomes") or []),
            bonding_curve_progress_pct=facts.get("bonding_curve_progress_pct"),
            holder_count=holder_snap.holder_count,
            notional_usd=facts.get("notional_usd") or self.default_notional_usd,
            mev_risk_level=MevRiskLevel.MEDIUM,
        )

        timeline_result = self.timeline.derive(
            token=facts.get("token_intel") or {},
            intel={
                "phase": phase_result.to_dict(),
                "composite_score": float(facts.get("composite_score") or 0),
                "confidence_score": float(facts.get("confidence_score") or 0),
                "roi": {
                    "base_low": econ.roi.base_low,
                    "base_high": econ.roi.base_high,
                },
            },
        )

        # ---- Composite launch score (Gate 1 input) ---------------------------
        composite_launch_score = _composite_score(
            phase_conf=phase_result.phase_confidence,
            smart_money_quality_or_better=(
                smart_panel.elite_count + smart_panel.quality_count
            ),
            dispersion=holder_snap.dispersion_score,
            roi_breakout_prob=(econ.roi.breakout_probability or 0.0),
        )

        # ---- Gate 1 — composite launch score ---------------------------------
        if self.gate_1 is not None:
            g1 = self.gate_1.evaluate(
                composite_launch_score=composite_launch_score,
                bonding_curve_progress_pct=float(
                    facts.get("bonding_curve_progress_pct") or 0.0),
                holder_count=holder_snap.holder_count,
                smart_money_entry_count=(
                    smart_panel.elite_count + smart_panel.quality_count
                ),
                holder_concentration_top10_pct=holder_snap.top_10_concentration_pct,
                confidence_score=float(facts.get("confidence_score") or 0.0),
                launchpad=facts.get("launchpad"),
            )
            if not g1.passed:
                return None, f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_1:{g1.reason}"

        # ---- Gate 6 — rug risk (Solana hard rejection) -----------------------
        if self.gate_6 is not None:
            g6 = self.gate_6.evaluate(
                mint_authority_revoked=bool(facts.get("mint_authority_revoked")),
                freeze_authority_revoked=bool(facts.get("freeze_authority_revoked")),
                lp_burned_or_locked_pct=float(facts.get("lp_burned_or_locked_pct") or 0.0),
                holder_concentration_top10_pct=holder_snap.top_10_concentration_pct,
            )
            if not g6.passed:
                return None, f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_6:{g6.reason}"

        # ---- Build VerificationEvidence (universal substrate) ---------------
        legs: List[LegEvidence] = [
            LegEvidence(
                leg_role=EvidenceLegRole.LAUNCH_PRIMARY,
                venue_id=facts.get("primary_venue_id", "unknown"),
                source_id=source_id,
                price=facts.get("listing_price_usd"),
                size_usd=econ.notional_usd,
                depth_usd=float(facts.get("liquidity_usd") or 0.0),
                fee_bps=int(facts.get("primary_fee_bps") or 0),
                chain=chain,
                metadata={"launchpad": facts.get("launchpad")},
            ),
            LegEvidence(
                leg_role=EvidenceLegRole.LAUNCH_SECONDARY,
                venue_id=facts.get("secondary_venue_id", "unknown"),
                source_id=source_id,
                price=facts.get("listing_price_usd"),
                size_usd=econ.notional_usd,
                depth_usd=float(facts.get("liquidity_usd") or 0.0),
                fee_bps=int(facts.get("secondary_fee_bps") or 0),
                chain=chain,
            ),
        ]

        # INV-3 — provenance derives strictly from leg source_ids. Catch
        # DEAD/CONTAMINATED so we degrade cleanly to outcome tag.
        try:
            _ = derive_provenance(legs)
        except ValueError:
            return None, VerifiedOutcome.DENIED_VENUE_UNREADABLE

        evidence = VerificationEvidence(
            verifier_id=self.verifier_id,
            candidate_id=candidate.candidate_id,
            discovery_source=candidate.hint_source,
            subject_id=candidate.subject_id,
            asset=candidate.asset,
            chain=chain,
            legs=legs,
            gross_spread_pct=None,
            expected_profit_usd=econ.economics.expected_profit_usd,
            capital_required_usd=econ.economics.capital_required_usd,
            notional_usd=econ.notional_usd,
            extra_metrics={
                "phase": phase_result.to_dict(),
                "timeline": timeline_result.to_dict(),
                "smart_money_panel": smart_panel.to_dict(),
                "holder_snapshot": holder_snap.to_dict(),
                "economics": _econ_to_dict(econ),
                "composite_launch_score": round(composite_launch_score, 1),
            },
        )

        # ---- category_metadata fold-in (D-4.0 vocabulary) ------------------
        category_metadata = _fold_metadata(
            phase_result=phase_result,
            timeline=timeline_result,
            smart_panel=smart_panel,
            holder_snap=holder_snap,
            econ=econ,
            facts=facts,
            composite=composite_launch_score,
        )

        canonical = build_canonical_from_evidence(
            evidence,
            opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
            opportunity_id=_opp_id(candidate, evidence.verified_at_ts),
            expected_profit_usd=econ.economics.expected_profit_usd,
            capital_required_usd=econ.economics.capital_required_usd,
            liquidity_score=min(100.0,
                                  (float(facts.get("liquidity_usd") or 0.0) / 1000.0)),
            mev_risk_level=econ.economics.mev_risk_level,
            category_metadata=category_metadata,
            extra_metadata={
                "composite_launch_score": round(composite_launch_score, 1),
            },
        )
        return canonical, VerifiedOutcome.CONFIRMED_PREFIX + canonical.opportunity_id


# ============================================================================
# Helpers — composite, metadata fold-in, opportunity_id
# ============================================================================

def _composite_score(*,
                     phase_conf: float,
                     smart_money_quality_or_better: int,
                     dispersion: float,
                     roi_breakout_prob: float,
                     ) -> float:
    """0..100 composite. Conservative weights — operator-tunable later."""
    phase_pts = max(0.0, min(40.0, phase_conf * 40.0))          # 0..40
    smart_pts = max(0.0, min(25.0, smart_money_quality_or_better * 12.5))  # 0..25
    disp_pts = max(0.0, min(20.0, dispersion * 0.20))           # 0..20
    roi_pts = max(0.0, min(15.0, roi_breakout_prob * 60.0))     # 0..15
    return phase_pts + smart_pts + disp_pts + roi_pts


def _fold_metadata(*,
                    phase_result,
                    timeline,
                    smart_panel: SmartMoneyPanel,
                    holder_snap: HolderSnapshot,
                    econ: LaunchEconomicsResult,
                    facts: Dict[str, Any],
                    composite: float,
                    ) -> Dict[str, Any]:
    """Project every D-4.3 engine output into the D-4.0 vocabulary keys."""
    out: Dict[str, Any] = {
        # Phase classifier
        "launch_phase": phase_result.phase,
        "phase_confidence": phase_result.phase_confidence,
        "phase_rationale": "; ".join(phase_result.rationale)[:240],
        # Timeline
        "timeline_confidence": timeline.temporal_confidence,
        "timeline_label": timeline.eta_label,
        # Holder analytics
        "holder_count": holder_snap.holder_count,
        "holder_concentration_top10_pct": holder_snap.top_10_concentration_pct,
        # Smart money
        "smart_money_entry_count": (
            smart_panel.elite_count + smart_panel.quality_count
        ),
        "early_quality_wallet_count": (
            smart_panel.elite_count + smart_panel.quality_count
            + smart_panel.emerging_count
        ),
        # On-chain rug-risk facts (Helius-derived)
        "mint_authority_revoked": bool(facts.get("mint_authority_revoked")),
        "freeze_authority_revoked": bool(facts.get("freeze_authority_revoked")),
        "lp_burned_pct": float(facts.get("lp_burned_or_locked_pct") or 0.0),
        # Discovery context
        "chain": (facts.get("chain") or "solana").lower(),
        "launchpad": facts.get("launchpad"),
        "token_address": facts.get("token_address"),
        "age_hours": facts.get("age_hours"),
        # Economics
        "roi_base_low_pct": econ.roi.base_low,
        "roi_base_high_pct": econ.roi.base_high,
        "roi_breakout_probability": econ.roi.breakout_probability,
        "roi_drawdown_probability": econ.roi.drawdown_probability,
        "roi_sample_size": econ.roi.sample_size,
    }
    if econ.bonding_curve_progress_pct is not None:
        out["bonding_curve_progress_pct"] = econ.bonding_curve_progress_pct
    return out


def _econ_to_dict(econ: LaunchEconomicsResult) -> Dict[str, Any]:
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
    return f"launch_arb:{candidate.subject_id}:{int(ts)}"
