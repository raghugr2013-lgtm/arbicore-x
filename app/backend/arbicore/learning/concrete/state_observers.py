"""ArbiCore X — Concrete StateObservers (Phase C Wave 2).

Passive, category-agnostic observers — one configurable class, one default
instance per OpportunityType. Each observer derives ``primary_metric`` from
data that already lives on the CanonicalOpportunity (``buy_price`` /
``sell_price`` mid, or a configured ``category_metadata`` numeric key).

These observers **do not call exchange APIs**, **do not query the network**,
and **do not assume any specific asset, venue, or chain**. They simply
project the CanonicalOpportunity into the StateObserver contract so the
OutcomeTracker can compute deltas once snapshots accumulate.
"""
from __future__ import annotations

import time
from typing import Dict, Optional

from ...data.state_observer import OpportunityState, StateObserver
from ...models.canonical import CanonicalOpportunity
from ...models.enums import DataProvenance, OpportunityType


def _mid_price(opp: CanonicalOpportunity) -> Optional[float]:
    if opp.buy_price is not None and opp.sell_price is not None:
        return (opp.buy_price + opp.sell_price) / 2.0
    if opp.buy_price is not None:
        return opp.buy_price
    if opp.sell_price is not None:
        return opp.sell_price
    return None


def _from_category_metadata(opp: CanonicalOpportunity,
                            key: str) -> Optional[float]:
    md = opp.category_metadata or {}
    val = md.get(key)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


class CategoryMetadataStateObserver(StateObserver):
    """Generic observer — one instance per ``OpportunityType``.

    Args:
        opportunity_type: which type this observer serves
        primary_metric_key: optional category_metadata key whose value
            becomes ``primary_metric``. If None, falls back to mid-price.
        secondary_metric_keys: additional category_metadata keys to copy
            into ``secondary_metrics``.

    Source provenance is inherited from the CanonicalOpportunity itself —
    observers do not synthesise data, they only project it.
    """

    def __init__(self,
                 opportunity_type: OpportunityType,
                 primary_metric_key: Optional[str] = None,
                 secondary_metric_keys: Optional[Dict[str, str]] = None,
                 ) -> None:
        self.opportunity_type = opportunity_type
        self.primary_metric_key = primary_metric_key
        self.secondary_metric_keys = secondary_metric_keys or {}

    async def fetch_state(self, opp: CanonicalOpportunity) -> Optional[OpportunityState]:
        if opp.opportunity_type is not self.opportunity_type:
            return None

        # Resolve primary metric
        primary: Optional[float] = None
        if self.primary_metric_key:
            primary = _from_category_metadata(opp, self.primary_metric_key)
        if primary is None:
            primary = _mid_price(opp)
        if primary is None:
            return None  # Nothing to observe — caller treats this as null-observer

        # Resolve secondary metrics
        secondary: Dict[str, float] = {}
        for out_key, md_key in self.secondary_metric_keys.items():
            v = _from_category_metadata(opp, md_key)
            if v is not None:
                secondary[out_key] = v

        return OpportunityState(
            subject_id=opp.subject_id or opp.opportunity_id,
            opportunity_type=self.opportunity_type,
            captured_at_ts=time.time(),
            primary_metric=primary,
            secondary_metrics=secondary,
            source="category_metadata_observer",
            provenance=opp.source_data_quality
            if isinstance(opp.source_data_quality, DataProvenance)
            else DataProvenance.SIMULATED,
        )


# Default per-type observer configurations. Keys chosen from
# ``KNOWN_CATEGORY_METADATA_KEYS`` — every key is opportunity-type-scoped.
DEFAULT_OBSERVER_CONFIGS = {
    OpportunityType.CEX_ARBITRAGE: {
        "primary_metric_key": "best_bid_price",
        "secondary_metric_keys": {
            "best_ask": "best_ask_price",
            "depth_usd": "profitable_buyer_depth_usd",
            "venue_health": "venue_health_score",
            "survival_prob": "combined_survival_prob",
        },
    },
    OpportunityType.DEX_ARBITRAGE: {
        "primary_metric_key": "tvl_usd",
        "secondary_metric_keys": {
            "slippage_pct": "estimated_slippage_pct",
            "mev_competitors": "mev_competition_count",
        },
    },
    OpportunityType.FUNDING_ARBITRAGE: {
        "primary_metric_key": "funding_rate_pct",
        "secondary_metric_keys": {
            "open_interest": "open_interest_usd",
            "perp_basis": "perp_index_basis_pct",
        },
    },
    OpportunityType.LAUNCH_ARBITRAGE: {
        "primary_metric_key": "public_price",
        "secondary_metric_keys": {
            "presale_price": "presale_price",
            "expected_roi": "expected_roi_probability",
        },
    },
    OpportunityType.CROSS_CHAIN_ARBITRAGE: {
        "primary_metric_key": "bridge_fee_usd",
        "secondary_metric_keys": {
            "latency_s": "bridge_latency_s",
        },
    },
    OpportunityType.FLASH_LOAN_ARBITRAGE: {
        "primary_metric_key": None,
        "secondary_metric_keys": {},
    },
}


def make_default_observer(opportunity_type: OpportunityType
                          ) -> CategoryMetadataStateObserver:
    cfg = DEFAULT_OBSERVER_CONFIGS.get(opportunity_type, {})
    return CategoryMetadataStateObserver(
        opportunity_type=opportunity_type,
        primary_metric_key=cfg.get("primary_metric_key"),
        secondary_metric_keys=cfg.get("secondary_metric_keys") or {},
    )
