"""ArbiCore X — Market Intelligence Database (MID) — v2.0.1 (Sprint 1A).

Platform-wide persistent intelligence foundation. Single write path. Ten
domains under one façade. Strategy-agnostic — every stored entity carries
``strategy_type``, ``opportunity_type``, ``capital_source``, ``chain``,
``protocol``, ``execution_mode``, ``market_regime``, ``tags`` metadata.

See ``docs/V2_PLATFORM_ROADMAP.md`` §P1-α for the full contract.
"""
from __future__ import annotations

from .schemas import (
    MidMetadata, ReplayContext,
    MarketStateRecord, QuoteRecord, LiquidityRecord, GasRecord,
    ProviderRecord, RouteObservationRecord, OpportunityEventRecord,
    ConfidenceRecord, DecisionRecord, OutcomeRecord, ReplayRecord,
    DOMAINS, MID_COLLECTION_MAP,
)
from .enums import (
    EnumRegistry, get_registry,
    STRATEGY_TYPE, OPPORTUNITY_TYPE, CAPITAL_SOURCE,
    CHAIN, PROTOCOL, EXECUTION_MODE, MARKET_REGIME,
)
from .writers import MidWriter, make_meta, new_mid_id, route_id_for, market_snapshot_id_for
from .readers import MidReader
from .indexes import ensure_indexes, DEFAULT_TTL_SECONDS

__all__ = [
    # schemas
    "MidMetadata", "ReplayContext",
    "MarketStateRecord", "QuoteRecord", "LiquidityRecord", "GasRecord",
    "ProviderRecord", "RouteObservationRecord", "OpportunityEventRecord",
    "ConfidenceRecord", "DecisionRecord", "OutcomeRecord", "ReplayRecord",
    "DOMAINS", "MID_COLLECTION_MAP",
    # enums
    "EnumRegistry", "get_registry",
    "STRATEGY_TYPE", "OPPORTUNITY_TYPE", "CAPITAL_SOURCE",
    "CHAIN", "PROTOCOL", "EXECUTION_MODE", "MARKET_REGIME",
    # writers / readers / indexes
    "MidWriter", "MidReader",
    "make_meta", "new_mid_id", "route_id_for", "market_snapshot_id_for",
    "ensure_indexes", "DEFAULT_TTL_SECONDS",
]
