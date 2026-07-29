"""ArbiCore X — Phase C Wave 5: legacy proposal → CanonicalOpportunity mapper.

Pure functions (no I/O). The mapper is the single point that knows about the
legacy ``build_proposals()`` dict schema. Adding a new legacy field is a
one-line change here; the rest of the platform consumes the canonical model.

Determinism rules:
  - Same ``proposal_id`` ALWAYS yields the same ``opportunity_id``
    (``shadow:{proposal_id}``) — guarantees idempotent re-emission.
  - Same legacy snapshot ALWAYS produces the same canonical fields
    (no clocks, no UUIDs, no randomness).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..models.canonical import CanonicalOpportunity
from ..models.enums import (
    DataProvenance,
    MarketRegime,
    MevRiskLevel,
    OpportunityStatus,
    OpportunityType,
    RouteHealth,
)


# ----------------------------------------------------------------------------
# Constants (legacy BDAG context — locked by historical dataset rules)
# ----------------------------------------------------------------------------

# Legacy reference dataset is BDAG/USDT bought on the BlockDAG live-swap
# portal, sold on Coinstore. These are *labels* on the canonical record —
# they do not introduce any execution-side coupling because the canonical
# pipeline never touches venues directly.
LEGACY_OPPORTUNITY_TYPE = OpportunityType.CEX_ARBITRAGE
LEGACY_ASSET = "BDAG/USDT"
LEGACY_SUBJECT_ID = "BDAG"
LEGACY_BUY_VENUE = "blockdag"        # the live-swap portal
LEGACY_SELL_VENUE = "coinstore"
SHADOW_OPP_ID_PREFIX = "shadow:"
LEGACY_CATEGORY = "legacy_bdag"      # tagged so Wave 5 rows are filterable


# ----------------------------------------------------------------------------
# Mapping helpers
# ----------------------------------------------------------------------------

# Legacy regime label → canonical MarketRegime
_REGIME_MAP: Dict[str, MarketRegime] = {
    "Stable":             MarketRegime.CALM,
    "Volatile":           MarketRegime.VOLATILE,
    "Extremely Volatile": MarketRegime.VOLATILE,
}

# Legacy drift risk label → MEV proxy (legacy proposals don't measure MEV
# directly; we map the closest available coarse risk band).
_RISK_TO_MEV: Dict[str, MevRiskLevel] = {
    "LOW":       MevRiskLevel.LOW,
    "MEDIUM":    MevRiskLevel.MEDIUM,
    "HIGH":      MevRiskLevel.HIGH,
    "VERY_HIGH": MevRiskLevel.HIGH,
}

# Legacy ``buy_price_source`` (recorded by the userscript-v2 batch) →
# canonical DataProvenance. Anything unknown falls back to REAL on the
# assumption that the proposal already passed the legacy quote gate
# (which itself enforces source provenance). The shadow binder is *not*
# the source of truth for provenance — the SOURCE_REGISTRY is — but we
# need a sensible projection here so REAL/SIMULATED maps cleanly.
_SOURCE_TO_PROVENANCE: Dict[str, DataProvenance] = {
    "userscript_v2_batch":          DataProvenance.REAL,
    "blockdag_live_swap_userscript": DataProvenance.REAL,
    "quote_capture_batch":           DataProvenance.REAL,
    "userscript_test_mode_batch":    DataProvenance.SIMULATED,
    "historical_replay":             DataProvenance.SIMULATED,
    "manual_config_balance":         DataProvenance.SIMULATED,
}


def _provenance_for(buy_price_source: Optional[str]) -> DataProvenance:
    if not buy_price_source:
        return DataProvenance.REAL
    return _SOURCE_TO_PROVENANCE.get(buy_price_source, DataProvenance.REAL)


def _regime_label_to_enum(label: Optional[str]) -> MarketRegime:
    if not label:
        return MarketRegime.UNKNOWN
    return _REGIME_MAP.get(label, MarketRegime.UNKNOWN)


def _mev_proxy(risk_label: Optional[str]) -> MevRiskLevel:
    if not risk_label:
        return MevRiskLevel.MEDIUM
    return _RISK_TO_MEV.get(risk_label.upper(), MevRiskLevel.MEDIUM)


def _route_health_for(proposal: Dict[str, Any]) -> RouteHealth:
    """Legacy proposals don't have an explicit route_health concept. Project
    one from `liquidity_feasible` + `quote_age_s`."""
    if not proposal.get("liquidity_feasible"):
        return RouteHealth.SHORT_LIVED
    age = proposal.get("quote_age_s")
    try:
        if age is not None and float(age) <= 10.0:
            return RouteHealth.PERSISTENT
    except (TypeError, ValueError):
        pass
    return RouteHealth.NEW


def _confidence_proxy(proposal: Dict[str, Any]) -> float:
    """Wave 5 does NOT run the confidence engine on the legacy snapshot —
    that's a downstream concern of the AdaptiveConfidenceEngine.
    We project the legacy ``quality_score`` into a coarse 0-100 starting
    estimate so the canonical row has a sensible default. The confidence
    engine will later overwrite this with its calibrated value.
    """
    q = proposal.get("quality_score")
    try:
        if q is None:
            return 0.0
        # quality_score is unbounded but typically lives in [-50, +30] for
        # the legacy dataset. We clip to [0, 100] for the canonical field.
        return float(max(0.0, min(100.0, float(q) + 50.0)))
    except (TypeError, ValueError):
        return 0.0


def _execution_feasibility(proposal: Dict[str, Any]) -> float:
    if proposal.get("liquidity_feasible"):
        return 0.8
    return 0.3


# ----------------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------------

def opportunity_id_for(proposal_id: str) -> str:
    """Deterministic opportunity_id for a legacy proposal_id."""
    return f"{SHADOW_OPP_ID_PREFIX}{proposal_id}"


def map_proposal_to_canonical(proposal: Dict[str, Any],
                              *,
                              tier: str = "candidate",
                              ) -> Optional[CanonicalOpportunity]:
    """Map a single legacy proposal dict to a CanonicalOpportunity.

    Args:
        proposal: the proposal dict produced by build_proposals(). Must
            contain at least ``proposal_id`` and either ``buy_price`` or
            ``sell_price``. Returns None if those required keys are missing.
        tier: ``"primary"`` / ``"secondary"`` / ``"candidate"`` — recorded
            in ``category_metadata`` for downstream analysis. Does not
            change the canonical lifecycle state.

    Returns:
        CanonicalOpportunity with ``status=VALIDATED`` when the legacy
        proposal flagged itself ``actionable``, else ``CANDIDATE``. The
        binder never marks anything ``APPROVED`` — legacy approvals are
        a UI concern and we do not impersonate the operator.
    """
    pid = proposal.get("proposal_id")
    if not pid:
        return None
    if proposal.get("buy_price") is None and proposal.get("sell_price") is None:
        return None

    provenance = _provenance_for(proposal.get("buy_price_source"))
    regime = _regime_label_to_enum(proposal.get("regime"))
    mev_proxy = _mev_proxy(proposal.get("risk_label"))
    route_h = _route_health_for(proposal)

    # Lifecycle: actionable legacy proposals are *validated* — they
    # passed the legacy ROI floor + liquidity gate. Non-actionable
    # rows stay as CANDIDATE (the legacy code already filtered them
    # out before returning, but we keep the path symmetric).
    status = (OpportunityStatus.VALIDATED
              if proposal.get("actionable")
              else OpportunityStatus.CANDIDATE)

    # Soft-typed category_metadata (CEX_ARBITRAGE vocabulary lives in
    # /app/backend/arbicore/models/category_metadata.py).
    cm: Dict[str, Any] = {
        "best_bid_price":             proposal.get("sell_price"),
        "best_ask_price":             proposal.get("buy_price"),
        "profitable_buyer_depth_usd": proposal.get("profitable_buyer_depth_usd"),
        "verified_quote_age_s":       proposal.get("quote_age_s"),
        "fee_drag_pct":               proposal.get("fee_drag_pct"),
        "drift_risk_label":           proposal.get("risk_label"),
        "drift_regime":               proposal.get("regime"),
        "combined_survival_prob":     proposal.get("combined_survival_prob"),
        "expected_cycle_s":           proposal.get("expected_cycle_s"),
    }
    # Drop None values so we don't pollute the metadata vocabulary.
    cm = {k: v for k, v in cm.items() if v is not None}

    metadata: Dict[str, Any] = {
        "legacy_category":     LEGACY_CATEGORY,
        "shadow_binding":      True,
        "tier":                tier,
        "legacy_proposal_id":  pid,
        "legacy_batch_id":     proposal.get("batch_id"),
        "legacy_quality_score": proposal.get("quality_score"),
        "legacy_actionable":   bool(proposal.get("actionable")),
        "legacy_net_roi_pct":  proposal.get("net_roi_pct"),
        "legacy_gross_spread_pct": proposal.get("gross_spread_pct"),
        "legacy_risk_score":   proposal.get("risk_score"),
        "legacy_buy_price_source": proposal.get("buy_price_source"),
        "bdag_expected":       proposal.get("bdag_expected"),
    }

    opp = CanonicalOpportunity(
        opportunity_id=opportunity_id_for(pid),
        opportunity_type=LEGACY_OPPORTUNITY_TYPE,
        subject_id=LEGACY_SUBJECT_ID,
        asset=LEGACY_ASSET,
        chain=None,
        buy_venue=LEGACY_BUY_VENUE,
        sell_venue=LEGACY_SELL_VENUE,
        buy_price=_safe_float(proposal.get("buy_price")),
        sell_price=_safe_float(proposal.get("sell_price")),
        spread_pct=_safe_float(proposal.get("gross_spread_pct")),
        expected_profit_usd=_safe_float(proposal.get("expected_profit_usd")),
        capital_required_usd=_safe_float(proposal.get("size_usd")),
        confidence_score=_confidence_proxy(proposal),
        risk_score=_safe_float(proposal.get("risk_score")) or 0.0,
        liquidity_score=80.0 if proposal.get("liquidity_feasible") else 30.0,
        execution_feasibility=_execution_feasibility(proposal),
        mev_risk_level=mev_proxy,
        market_regime=regime,
        market_regime_tags=[proposal["regime"]] if proposal.get("regime") else None,
        route_health=route_h,
        source_data_quality=provenance,
        status=status,
        category_metadata=cm or None,
        metadata=metadata,
    )
    return opp


def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ----------------------------------------------------------------------------
# Snapshot-level mapper (primary + secondary → list[CanonicalOpportunity])
# ----------------------------------------------------------------------------

class LegacyProposalMapper:
    """Stateless façade exposing snapshot-level mapping. Held as a
    composition-root singleton purely for test injection convenience.
    """

    @staticmethod
    def map_snapshot(snapshot: Dict[str, Any]) -> List[CanonicalOpportunity]:
        """Map a full ``build_proposals()`` snapshot.

        Returns one CanonicalOpportunity per (primary + secondary) item.
        Order is preserved: primary first, then secondary in rank order.
        Items lacking ``proposal_id`` or both prices are silently dropped.
        """
        out: List[CanonicalOpportunity] = []
        primary = snapshot.get("primary")
        if primary:
            opp = map_proposal_to_canonical(primary, tier="primary")
            if opp is not None:
                out.append(opp)
        for sec in (snapshot.get("secondary") or []):
            if not isinstance(sec, dict):
                continue
            opp = map_proposal_to_canonical(sec, tier="secondary")
            if opp is not None:
                out.append(opp)
        return out
