"""ArbiCore X — Phase D D-4.2 Launch-Intel Wallet Intelligence Substrate.

Wave D-4.2 ships the wallet-side intelligence layer for Launch Intelligence:

  - WalletProfile             (REUSE WITH REFINEMENT, Pydantic v2)
  - WalletScorer (4-factor)   (REUSE WITH REFINEMENT)
  - load_labels / curated     (REUSE WITH REFINEMENT, lift labels.json verbatim)
  - TimeWindowClusterDetector (PARTIAL HARVEST — time-window strategy only)
  - signal_predicates (7)     (PARTIAL HARVEST — emitted as DiscoveryCandidate)
  - WalletEnrichmentOrchestrator (REBUILD FRESH — asyncio only)

INV-1 / INV-2 / INV-3 are preserved:
  - signal_predicates emit DiscoveryCandidate ONLY (never CanonicalOpportunity)
  - No EmissionBus calls anywhere in this package
  - All hints are telemetry; the verifier (D-4.4) re-derives canonical
    ``source_data_quality`` from per-leg on-chain RPC reads.

At D-4.2 there is NO orchestrator/scanner activation. The
``WalletEnrichmentOrchestrator`` is constructible but spawns no task. The
LaunchArbitrageScanner at D-4.5 is what ticks it.
"""
from __future__ import annotations

from .cluster_detector import TimeWindowClusterDetector
from .enrichment import WalletEnrichmentOrchestrator
from .holder_analytics import HolderAnalytics, HolderSnapshot
from .labels import CURATED_LABELS_PATH, LABEL_VOCABULARY, curated_index, load_curated
from .phase_classifier import PHASE_TAGS, PhaseClassifier, PhaseResult
from .signal_predicates import (
    SignalPredicateInput,
    WalletActivityEvent,
    evaluate_all_predicates,
)
from .smart_money import (
    TIER_ELITE,
    TIER_EMERGING,
    TIER_NONE,
    TIER_ORDER,
    TIER_QUALITY,
    SmartMoneyDetector,
    SmartMoneyPanel,
    SmartMoneyVerdict,
)
from .timeline import (
    LIVE_LAUNCHPADS,
    PHASE_TO_TEMPORAL,
    PRESALE_LAUNCHPADS,
    TEMPORAL_STATES,
    LaunchTimelineEngine,
    TimelineResult,
)
from .wallet_profile import WalletProfile, is_smart_money, merge_stats
from .wallet_scorer import WalletScorer

__all__ = [
    "WalletProfile",
    "WalletScorer",
    "TimeWindowClusterDetector",
    "WalletEnrichmentOrchestrator",
    "WalletActivityEvent",
    "SignalPredicateInput",
    "evaluate_all_predicates",
    "load_curated",
    "curated_index",
    "is_smart_money",
    "merge_stats",
    "LABEL_VOCABULARY",
    "CURATED_LABELS_PATH",
    # D-4.3 additions
    "PhaseClassifier", "PhaseResult", "PHASE_TAGS",
    "LaunchTimelineEngine", "TimelineResult",
    "TEMPORAL_STATES", "PHASE_TO_TEMPORAL",
    "PRESALE_LAUNCHPADS", "LIVE_LAUNCHPADS",
    "SmartMoneyDetector", "SmartMoneyPanel", "SmartMoneyVerdict",
    "TIER_ELITE", "TIER_QUALITY", "TIER_EMERGING",
    "TIER_NONE", "TIER_ORDER",
    "HolderAnalytics", "HolderSnapshot",
]
