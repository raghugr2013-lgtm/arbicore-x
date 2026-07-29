"""ArbiCore X — Phase C Wave 1 + 2 concrete learners.

All implementations here are:
  - Category-agnostic (operate exclusively through CanonicalOpportunity)
  - Execution-free (no signing, no fund movement, no trade writes)
  - Provenance-gated (only VERIFIED_REAL / REAL feed learning state)
"""
from .adaptive_weights import MongoBackedAdaptiveWeights, adaptive_weight
from .audit_log import MongoAuditLog
from .confidence_engine import (
    AdaptiveConfidenceEngine,
    ConfidenceBreakdown,
    SIGNAL_DIRECTION_HINTS,
)
from .metrics_aggregator import MetricsAggregator
from .models import OpportunityOutcome, RoutePerformance
from .outcome_tracker import OutcomeTracker
from .route_success_tracker import MongoRouteSuccessTracker
from .state_observers import (
    CategoryMetadataStateObserver,
    DEFAULT_OBSERVER_CONFIGS,
    make_default_observer,
)

__all__ = [
    "OutcomeTracker",
    "MongoRouteSuccessTracker",
    "MetricsAggregator",
    "MongoAuditLog",
    "OpportunityOutcome",
    "RoutePerformance",
    # Wave 2
    "MongoBackedAdaptiveWeights",
    "AdaptiveConfidenceEngine",
    "ConfidenceBreakdown",
    "CategoryMetadataStateObserver",
    "DEFAULT_OBSERVER_CONFIGS",
    "SIGNAL_DIRECTION_HINTS",
    "adaptive_weight",
    "make_default_observer",
]
