"""ArbiCore X — Phase D D-3.2 Verification Evidence (universal substrate).

This module defines the **normalized verification evidence vocabulary** every
opportunity family produces and the **universal CanonicalOpportunity
factory** that consumes it. Verifiers across families (D-3 DEX, D-4 Launch,
D-5 Cross-Chain, D-6 FlashLoan) build LegEvidence + VerificationEvidence
objects and call ``build_canonical_from_evidence`` — producing a
protocol-agnostic CanonicalOpportunity skeleton with INV-3-correct
``source_data_quality`` derived from each leg's SOURCE_REGISTRY
classification.

INV-1: This module never imports DiscoveryCandidate as a CanonicalOpportunity
       supplier. ``build_canonical_from_evidence`` takes evidence (which
       carries a discovery_candidate_id) and produces a fresh canonical row.
INV-2: This module never calls EmissionBus. It returns CanonicalOpportunity
       value objects; only scanner orchestrators emit them.
INV-3: ``source_data_quality`` is computed from the minimum-trust
       SOURCE_REGISTRY classification across all evidence legs — never from
       a candidate.hint_source nor from any aggregator HINT.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ..data.provenance import get_classification, is_learning_eligible
from ..models.canonical import CanonicalOpportunity
from ..models.enums import (
    DataProvenance, MarketRegime, MevRiskLevel,
    OpportunityStatus, OpportunityType, RouteHealth,
)


# ============================================================================
# Leg role vocabulary
# ============================================================================

class EvidenceLegRole:
    """Universal leg-role vocabulary spanning all opportunity families.

    Conventions:
      - DEX/CEX arb: ``BUY`` + ``SELL``
      - Funding arb: ``LONG`` + ``SHORT`` (one perp + one spot/perp counter-leg)
      - Cross-chain: ``BRIDGE_OUT`` + ``BRIDGE_IN`` (source and destination)
      - Launch:      ``LAUNCH_PRIMARY`` (presale/listing) + ``LAUNCH_SECONDARY`` (DEX listing)
      - Flash-loan:  ``BORROW`` + ordered ``HOP`` legs + ``REPAY``
    """
    BUY = "buy"
    SELL = "sell"
    LONG = "long"
    SHORT = "short"
    BRIDGE_IN = "bridge_in"
    BRIDGE_OUT = "bridge_out"
    LAUNCH_PRIMARY = "launch_primary"
    LAUNCH_SECONDARY = "launch_secondary"
    BORROW = "borrow"
    REPAY = "repay"
    HOP = "hop"
    # D-6.0 — explicit aliases for flash-loan family clarity. Same string
    # values as BORROW / REPAY (back-compat preserved).
    FLASH_LOAN_BORROW = "borrow"
    FLASH_LOAN_REPAY = "repay"

    KNOWN = frozenset({
        BUY, SELL, LONG, SHORT, BRIDGE_IN, BRIDGE_OUT,
        LAUNCH_PRIMARY, LAUNCH_SECONDARY, BORROW, REPAY, HOP,
    })


# ============================================================================
# LegEvidence — one normalized leg, protocol-agnostic
# ============================================================================

@dataclass
class LegEvidence:
    """One leg of verified evidence. Pure value object — never persisted."""

    leg_role: str                    # one of EvidenceLegRole.KNOWN (advisory)
    venue_id: str                    # opaque "<dex>:<chain>:<pool>" / "<cex>:<pair>" / etc.
    source_id: str                   # SOURCE_REGISTRY key — drives provenance (INV-3)
    price: Optional[float] = None    # effective price (output/input) at the requested size
    size_usd: Optional[float] = None
    depth_usd: Optional[float] = None
    fee_bps: Optional[int] = None
    age_ms: Optional[int] = None
    chain: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# VerificationEvidence — full evidence bundle for a candidate
# ============================================================================

@dataclass
class VerificationEvidence:
    """Normalized evidence; protocol-agnostic. Any verifier produces this."""

    verifier_id: str                            # e.g. "dex_quote_verifier"
    candidate_id: str                           # the DiscoveryCandidate that prompted us
    discovery_source: str                       # candidate.hint_source (provenance trail)
    subject_id: str                             # canonical pair / route subject
    asset: Optional[str] = None
    chain: Optional[str] = None
    legs: List[LegEvidence] = field(default_factory=list)
    gross_spread_pct: Optional[float] = None    # cross-leg gross spread when applicable
    expected_profit_usd: Optional[float] = None
    capital_required_usd: Optional[float] = None
    notional_usd: Optional[float] = None
    extra_metrics: Dict[str, Any] = field(default_factory=dict)
    verified_at_ts: float = field(default_factory=lambda: time.time())

    def leg_by_role(self, role: str) -> Optional[LegEvidence]:
        for lg in self.legs:
            if lg.leg_role == role:
                return lg
        return None


# ============================================================================
# Universal canonical builder
# ============================================================================

# Trust ordering: a CanonicalOpportunity's source_data_quality is set to the
# MINIMUM-trust classification across all legs. SIMULATED < VERIFIED_REAL <
# REAL by convention here — VERIFIED_REAL means "REAL + we've cross-checked"
# so we treat it equivalent-or-better than REAL for trust purposes. DEAD /
# CONTAMINATED block emission entirely (verifier callers must abort earlier).
_PROVENANCE_TRUST_ORDER = {
    DataProvenance.SIMULATED: 0,
    DataProvenance.REAL: 1,
    DataProvenance.VERIFIED_REAL: 2,
}


def derive_provenance(legs: List[LegEvidence]) -> DataProvenance:
    """Compute source_data_quality from the MINIMUM-trust leg classification.

    Raises ValueError if any leg carries CONTAMINATED or DEAD provenance —
    callers must catch and translate to DENIED_VENUE_UNREADABLE.
    """
    if not legs:
        raise ValueError("derive_provenance: no legs provided")
    worst: Optional[DataProvenance] = None
    for lg in legs:
        cls = get_classification(lg.source_id)
        if cls in (DataProvenance.DEAD, DataProvenance.CONTAMINATED):
            raise ValueError(
                f"derive_provenance: leg {lg.venue_id} carries {cls.value} "
                f"provenance ({lg.source_id}); inadmissible to canonical"
            )
        if worst is None:
            worst = cls
        elif _PROVENANCE_TRUST_ORDER.get(cls, 1) < _PROVENANCE_TRUST_ORDER.get(worst, 1):
            worst = cls
    return worst or DataProvenance.REAL


def build_canonical_from_evidence(
    evidence: VerificationEvidence,
    *,
    opportunity_type: OpportunityType,
    opportunity_id: str,
    buy_venue_override: Optional[str] = None,
    sell_venue_override: Optional[str] = None,
    expected_profit_usd: Optional[float] = None,
    capital_required_usd: Optional[float] = None,
    liquidity_score: Optional[float] = None,
    mev_risk_level: MevRiskLevel = MevRiskLevel.LOW,
    market_regime: MarketRegime = MarketRegime.UNKNOWN,
    route_health: RouteHealth = RouteHealth.NEW,
    category_metadata: Optional[Dict[str, Any]] = None,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> CanonicalOpportunity:
    """Build a CanonicalOpportunity skeleton from normalized evidence.

    Pure function — no I/O, no persistence, no EmissionBus. The caller
    (verifier or scanner) is responsible for setting status to VALIDATED
    after Gates 1-5 pass, and for the eventual single emit-call from the
    scanner orchestrator (INV-2).

    ``source_data_quality`` is derived strictly from the legs' SOURCE_REGISTRY
    classifications (INV-3). DEAD or CONTAMINATED leg → ValueError.

    For 2-leg families (DEX/CEX/funding/cross-chain) we conventionally use
    the first BUY/LONG/BRIDGE_OUT leg as the "buy" side and the SELL/SHORT/
    BRIDGE_IN as the "sell" side; ``buy_venue_override`` / ``sell_venue_override``
    accept explicit values for families that don't fit the convention
    (e.g. flash-loan, launch).
    """
    provenance = derive_provenance(evidence.legs)

    # Resolve buy/sell venue identifiers
    buy_venue = buy_venue_override
    sell_venue = sell_venue_override
    if buy_venue is None:
        for role in (EvidenceLegRole.BUY, EvidenceLegRole.LONG,
                     EvidenceLegRole.BRIDGE_OUT, EvidenceLegRole.LAUNCH_PRIMARY,
                     EvidenceLegRole.BORROW):
            lg = evidence.leg_by_role(role)
            if lg is not None:
                buy_venue = lg.venue_id
                break
    if sell_venue is None:
        for role in (EvidenceLegRole.SELL, EvidenceLegRole.SHORT,
                     EvidenceLegRole.BRIDGE_IN, EvidenceLegRole.LAUNCH_SECONDARY,
                     EvidenceLegRole.REPAY):
            lg = evidence.leg_by_role(role)
            if lg is not None:
                sell_venue = lg.venue_id
                break
    # Fallback: first two legs in order
    if buy_venue is None and evidence.legs:
        buy_venue = evidence.legs[0].venue_id
    if sell_venue is None and len(evidence.legs) >= 2:
        sell_venue = evidence.legs[1].venue_id

    # Pricing
    buy_leg = (evidence.leg_by_role(EvidenceLegRole.BUY)
               or evidence.leg_by_role(EvidenceLegRole.LONG))
    sell_leg = (evidence.leg_by_role(EvidenceLegRole.SELL)
                or evidence.leg_by_role(EvidenceLegRole.SHORT))
    buy_price = buy_leg.price if buy_leg else None
    sell_price = sell_leg.price if sell_leg else None

    # Liquidity score (heuristic — verifier may override)
    if liquidity_score is None:
        depths = [lg.depth_usd for lg in evidence.legs if lg.depth_usd is not None]
        min_depth = min(depths) if depths else 0.0
        liquidity_score = 80.0 if min_depth >= 5000 else 30.0

    # Resolved economics
    notional = evidence.notional_usd or capital_required_usd or 1000.0
    if expected_profit_usd is None:
        expected_profit_usd = (
            notional * (evidence.gross_spread_pct / 100.0)
            if evidence.gross_spread_pct is not None else 0.0
        )
    if capital_required_usd is None:
        capital_required_usd = notional

    # Metadata assembly — preserve discovery trail (provenance audit)
    meta: Dict[str, Any] = {
        "scanner": evidence.verifier_id,
        "discovery_candidate_id": evidence.candidate_id,
        "discovery_source": evidence.discovery_source,
        "verifier_id": evidence.verifier_id,
        "verified_at_ts": evidence.verified_at_ts,
        "leg_count": len(evidence.legs),
        "leg_venues": [lg.venue_id for lg in evidence.legs],
        "leg_source_ids": [lg.source_id for lg in evidence.legs],
        "leg_roles": [lg.leg_role for lg in evidence.legs],
    }
    if evidence.extra_metrics:
        meta["extra_metrics"] = dict(evidence.extra_metrics)
    if extra_metadata:
        meta.update(extra_metadata)

    return CanonicalOpportunity(
        opportunity_id=opportunity_id,
        opportunity_type=opportunity_type,
        subject_id=evidence.subject_id,
        asset=evidence.asset,
        chain=evidence.chain,
        buy_venue=buy_venue or "",
        sell_venue=sell_venue or "",
        buy_price=buy_price,
        sell_price=sell_price,
        spread_pct=(round(evidence.gross_spread_pct, 4)
                    if evidence.gross_spread_pct is not None else None),
        expected_profit_usd=round(expected_profit_usd, 4),
        capital_required_usd=round(capital_required_usd, 4),
        confidence_score=0.0,                       # Gate 4 sets this
        risk_score=0.0,
        liquidity_score=liquidity_score,
        execution_feasibility=0.7,
        mev_risk_level=mev_risk_level,
        market_regime=market_regime,
        route_health=route_health,
        source_data_quality=provenance,
        status=OpportunityStatus.CANDIDATE,
        category_metadata=dict(category_metadata or {}),
        metadata=meta,
    )


__all__ = [
    "EvidenceLegRole", "LegEvidence", "VerificationEvidence",
    "derive_provenance", "build_canonical_from_evidence",
]
