"""ArbiCore X — Canonical Opportunity Model.

THE universal contract for the entire platform. Every scanner, validator,
scoring service, confidence engine, approval workflow and (future) execution
workflow emits / consumes this single object. No module may introduce a
separate opportunity schema.

Lifecycle:
    candidate -> validated -> approved -> executed -> completed
    candidate -> rejected   (also validated/approved -> rejected)

NOTE: ``executed`` and ``completed`` are reserved for a future, separately
gated execution layer. Phase 1/B intelligence services must never set them.

Phase B schema changes (locked):
  - 7 trade-exec fields are ``Optional[T] = None`` (no zero defaults)
  - ``subject_id`` (Optional[str]) — disambiguates ``asset`` per category
  - ``category_metadata`` (Optional[dict]) — soft-typed extension per type
  - ``market_regime_tags`` (Optional[list[str]]) — multi-label regime context
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .category_metadata import validate_category_metadata
from .enums import (
    LEARNING_ELIGIBLE_PROVENANCE,
    DataProvenance,
    MarketRegime,
    MevRiskLevel,
    OpportunityStatus,
    OpportunityType,
    RouteHealth,
    StrategyType,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Allowed lifecycle transitions. Execution transitions are intentionally NOT
# permitted from within Phase 1/B services (see can_transition guard usage).
_ALLOWED_TRANSITIONS: Dict[OpportunityStatus, set] = {
    OpportunityStatus.CANDIDATE: {OpportunityStatus.VALIDATED, OpportunityStatus.REJECTED},
    OpportunityStatus.VALIDATED: {OpportunityStatus.APPROVED, OpportunityStatus.REJECTED},
    OpportunityStatus.APPROVED: {OpportunityStatus.EXECUTED, OpportunityStatus.REJECTED},
    OpportunityStatus.EXECUTED: {OpportunityStatus.COMPLETED},
    OpportunityStatus.COMPLETED: set(),
    OpportunityStatus.REJECTED: set(),
}


class InvalidTransitionError(Exception):
    """Raised when an illegal lifecycle transition is attempted."""


class CanonicalOpportunity(BaseModel):
    """Universal opportunity object for ArbiCore X."""

    model_config = ConfigDict(use_enum_values=False, extra="forbid")

    # Identity
    opportunity_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    opportunity_type: OpportunityType
    strategy: Optional[StrategyType] = None   # Phase 2: flash-loan sub-strategy
    subject_id: Optional[str] = None     # Phase B: per-category disambiguator

    # Market / venue (Phase B: Optional, default None)
    asset: str                                   # e.g. "WETH/USDC"
    chain: Optional[str] = None                  # optional for CEX-only routes
    chain_id: Optional[int] = None               # Phase 2: numeric EVM chain id
    buy_venue: Optional[str] = None
    sell_venue: Optional[str] = None
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    spread_pct: Optional[float] = None

    # Economics (detection-only estimates — never an instruction to trade)
    expected_profit_usd: Optional[float] = None
    capital_required_usd: Optional[float] = None

    # Intelligence scores (0–100 unless noted)
    confidence_score: float = 0.0
    risk_score: float = 0.0
    liquidity_score: float = 0.0
    execution_feasibility: float = 0.0           # 0–1 feasibility estimate
    mev_risk_level: MevRiskLevel = MevRiskLevel.MEDIUM

    # Context
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    market_regime_tags: Optional[List[str]] = None   # Phase B (Adj. B1b): multi-label
    route_health: RouteHealth = RouteHealth.UNKNOWN
    source_data_quality: DataProvenance = DataProvenance.SIMULATED

    # Lifecycle
    status: OpportunityStatus = OpportunityStatus.CANDIDATE
    rejection_reason: Optional[str] = None

    # Free-form, type-specific extras (legacy free-form bag kept for back-compat).
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # Phase B: soft-typed, per-OpportunityType extension dict.
    category_metadata: Optional[Dict[str, Any]] = None

    # Timestamps
    created_at: str = Field(default_factory=_utc_now)
    updated_at: str = Field(default_factory=_utc_now)

    # ---- Validators ------------------------------------------------------
    @model_validator(mode="after")
    def _validate_category_metadata(self) -> "CanonicalOpportunity":
        # Soft-typed validator — never raises; warns once per unknown key.
        validate_category_metadata(self.opportunity_type, self.category_metadata)
        return self

    # ---- Derived helpers -------------------------------------------------
    @property
    def route(self) -> str:
        """Canonical route key used by confidence / learning subsystems.

        Returns an empty-ish key when one or both venues are absent (Phase B
        allows Optional venues for non-trade-exec opportunity types).
        """
        buy = self.buy_venue or ""
        sell = self.sell_venue or ""
        return f"{buy}->{sell}"

    @property
    def is_learning_eligible(self) -> bool:
        """True only when backed by REAL or VERIFIED_REAL data."""
        return self.source_data_quality in LEARNING_ELIGIBLE_PROVENANCE

    # ---- Lifecycle management -------------------------------------------
    def can_transition(self, target: OpportunityStatus) -> bool:
        return target in _ALLOWED_TRANSITIONS.get(self.status, set())

    def _transition(self, target: OpportunityStatus, reason: Optional[str] = None) -> "CanonicalOpportunity":
        if not self.can_transition(target):
            raise InvalidTransitionError(
                f"Cannot transition {self.status.value} -> {target.value}"
            )
        self.status = target
        if reason is not None:
            self.rejection_reason = reason
        self.updated_at = _utc_now()
        return self

    def mark_validated(self) -> "CanonicalOpportunity":
        return self._transition(OpportunityStatus.VALIDATED)

    def mark_approved(self) -> "CanonicalOpportunity":
        return self._transition(OpportunityStatus.APPROVED)

    def mark_rejected(self, reason: str) -> "CanonicalOpportunity":
        return self._transition(OpportunityStatus.REJECTED, reason=reason)
