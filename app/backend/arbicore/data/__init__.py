from .horizons import DEFAULT_HORIZONS_S, HorizonSpec, default_horizon_specs, due_at_for
from .metrics_repo import MetricsRepository, SignalMetric, WalletMetric
from .opportunity_repo import OpportunityRepository, validate_for_upsert
from .outcome_repo import (
    OutcomeRepository,
    OutcomeRow,
    StateRow,
    make_outcome_rows_for,
)
from .provenance import (
    ContaminatedDataError,
    PHASE_B_NATIVE_SOURCES,
    SOURCE_REGISTRY,
    SourceClassification,
    assert_learning_eligible,
    classify,
    coverage_pct,
    get_classification,
    is_learning_eligible,
    list_sources_by_provenance,
    native_coverage_pct,
    registry_counts_by_provenance,
)
from .regime_snapshot_repo import RegimeSnapshot, RegimeSnapshotRepository
from .state_observer import (
    NullStateObserver,
    OpportunityState,
    StateObserver,
    StateObserverRegistry,
)

__all__ = [
    # provenance
    "ContaminatedDataError",
    "PHASE_B_NATIVE_SOURCES",
    "SOURCE_REGISTRY",
    "SourceClassification",
    "assert_learning_eligible",
    "classify",
    "coverage_pct",
    "get_classification",
    "is_learning_eligible",
    "list_sources_by_provenance",
    "native_coverage_pct",
    "registry_counts_by_provenance",
    # horizons
    "DEFAULT_HORIZONS_S",
    "HorizonSpec",
    "default_horizon_specs",
    "due_at_for",
    # ABCs
    "OpportunityRepository",
    "OutcomeRepository",
    "MetricsRepository",
    "RegimeSnapshotRepository",
    "StateObserver",
    "StateObserverRegistry",
    "NullStateObserver",
    # data classes
    "OutcomeRow",
    "StateRow",
    "OpportunityState",
    "SignalMetric",
    "WalletMetric",
    "RegimeSnapshot",
    # helpers
    "make_outcome_rows_for",
    "validate_for_upsert",
]
