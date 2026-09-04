"""ArbiCore X — Runtime composition root (Phase B + Phase C Wave 1).

Lazy-initialized singletons for the data layer + state observer registry
+ Phase C Wave 1 learners (OutcomeTracker, RouteSuccessTracker,
MetricsAggregator, AuditLog, OutcomeEvaluator worker, EventBus).

Wired from server.py lifespan AFTER existing services start.
"""
from __future__ import annotations

import logging as _logging
import time as _time
from typing import Optional

# M3.0 diagnostics — per-stage fail-closed visibility for the controlled-live
# fresh revalidation (build_controlled_live_safety.fresh_fn). Emits WARNING with
# the EXACT stage + underlying value/exception so the VPS validation harness and
# the live loop show precisely which dependency blocked. Behaviour unchanged:
# every failure still fails closed (returns None ⇒ DENY).
_M3_LOG = _logging.getLogger("arbicore.m3_0.fresh_fn")

from ..data.metrics_repo import MetricsRepository
from ..data.mongo.arbicore_collections import ensure_indexes as _ensure_indexes
from ..data.mongo.metrics_repo_mongo import MongoMetricsRepository
from ..data.mongo.opportunity_repo_mongo import MongoOpportunityRepository
from ..data.mongo.outcome_repo_mongo import MongoOutcomeRepository
from ..data.mongo.regime_snapshot_repo_mongo import MongoRegimeSnapshotRepository
from ..data.mongo.wallet_profile_repo_mongo import MongoWalletProfileRepository
from ..data.opportunity_repo import OpportunityRepository
from ..data.outcome_repo import OutcomeRepository
from ..data.regime_snapshot_repo import RegimeSnapshotRepository
from ..data.state_observer import StateObserverRegistry
from ..data.wallet_profile_repo import (
    WalletProfileRepository, seed_curated_into,
)
from ..intel import (
    EntityClusterDetector,
    EntityResolver,
    EntityScorer,
    MongoEntityRepository,
)
from ..learning.concrete.adaptive_weights import MongoBackedAdaptiveWeights
from ..learning.concrete.audit_log import MongoAuditLog
from ..learning.concrete.confidence_engine import AdaptiveConfidenceEngine
from ..learning.concrete.evaluator_worker import OutcomeEvaluator
from ..learning.concrete.metrics_aggregator import MetricsAggregator
from ..learning.concrete.outcome_tracker import OutcomeTracker
from ..learning.concrete.regime_classifier import HeuristicRegimeClassifier
from ..learning.concrete.regime_worker import RegimeClassifierWorker
from ..learning.concrete.route_success_tracker import MongoRouteSuccessTracker
from ..learning.concrete.sequence_miner import SequenceMiner
from ..learning.concrete.state_observers import make_default_observer
from ..learning.concrete.survival import SurvivalAnalytics
from ..models.enums import OpportunityType
from ..shadow.observer import ShadowBindingObserver
from .event_bus import EventBus

# Phase D D-1 — Discovery Layer + CEX Arb scanner imports
from ..emission_bus import EmissionBus
from ..data.discovery_queue import DiscoveryQueue
from ..data.discovery_source_metrics_repo import DiscoverySourceMetricsRepo
from ..data.scanner_config_repo import (
    ScannerConfigRepository, ScannerStateRepository,
)
from ..data.venue_capability_repo import VenueCapabilityRepository
from ..scanners.cex_arbitrage import CEXArbitrageScanner
from ..scanners.funding_arbitrage.scanner import FundingArbitrageScanner
from ..scanners.dex_arbitrage.scanner import DEXArbitrageScanner
from ..scanners.launch_arbitrage.scanner import LaunchArbitrageScanner
from ..scanners.launch_arbitrage.helius_venue_provider import (
    HeliusLaunchVenueProvider,
)
from ..scanners.cross_chain_arbitrage.scanner import (
    CrossChainArbitrageScanner,
)
from ..scanners.cross_chain_arbitrage.chain_liveness import (
    RpcChainLivenessLoader,
)
from ..scanners.cross_chain_arbitrage.transfer_provider import (
    LiFiTransferProvider, StargateTransferProvider,
)
from ..scanners.flash_loan_arbitrage.scanner import (
    FlashLoanArbitrageScanner,
)


_opportunity_repo: Optional[OpportunityRepository] = None
_outcome_repo: Optional[OutcomeRepository] = None
_metrics_repo: Optional[MetricsRepository] = None
_regime_snapshot_repo: Optional[RegimeSnapshotRepository] = None
_state_observer_registry: Optional[StateObserverRegistry] = None

_event_bus: Optional[EventBus] = None
_audit_log: Optional[MongoAuditLog] = None
_route_tracker: Optional[MongoRouteSuccessTracker] = None
_outcome_tracker: Optional[OutcomeTracker] = None
_metrics_aggregator: Optional[MetricsAggregator] = None
_outcome_evaluator: Optional[OutcomeEvaluator] = None

# Wave 2
_adaptive_weights: Optional[MongoBackedAdaptiveWeights] = None
_confidence_engine: Optional[AdaptiveConfidenceEngine] = None

# Wave 3
_survival_analytics: Optional[SurvivalAnalytics] = None
_regime_classifier: Optional[HeuristicRegimeClassifier] = None
_sequence_miner: Optional[SequenceMiner] = None
_regime_worker: Optional[RegimeClassifierWorker] = None

# Wave 4 — Universal Entity Intelligence
_entity_repo: Optional[MongoEntityRepository] = None
_entity_resolver: Optional[EntityResolver] = None
_entity_cluster_detector: Optional[EntityClusterDetector] = None
_entity_scorer: Optional[EntityScorer] = None

# Wave 5 — Shadow Binding
_shadow_binder: Optional[ShadowBindingObserver] = None

# Phase D D-1 — Discovery Layer + scanner
_emission_bus: Optional[EmissionBus] = None
_discovery_queue: Optional[DiscoveryQueue] = None
_discovery_source_metrics: Optional[DiscoverySourceMetricsRepo] = None
_venue_capability_repo: Optional[VenueCapabilityRepository] = None
_scanner_config_repo: Optional[ScannerConfigRepository] = None
_scanner_state_repo: Optional[ScannerStateRepository] = None
_cex_arb_scanner: Optional[CEXArbitrageScanner] = None
_funding_arb_scanner: Optional[FundingArbitrageScanner] = None
_dex_arb_scanner: Optional[DEXArbitrageScanner] = None
_launch_arb_scanner: Optional[LaunchArbitrageScanner] = None
_cross_chain_arb_scanner: Optional[CrossChainArbitrageScanner] = None
_flash_loan_arb_scanner: Optional[FlashLoanArbitrageScanner] = None
_db_handle = None  # raw motor db for route-level aggregations

# D-4 Subset B — WalletProfileRepository (replaces the empty stub
# previously injected as `_wallet_profile_loader`).
_wallet_profile_repo: Optional[WalletProfileRepository] = None

# D-4 Subset D — autonomous token-universe cache for HeliusWalletSource.
# Previously composition.py:542 passed ``token_universe_loader=None``,
# which the scanner wrapped to ``lambda: []`` — leaving the source
# permanently dormant even when the operator toggled ``enabled=True`` in
# scanner_config. Subset D wires a real loader by harvesting recent
# ``LAUNCH_ARBITRAGE`` candidates (any chain prefix; Helius requires the
# bare mint address) from ``arbicore_discovery_candidates``.
#
# INV-1: the cache stores raw mint strings, not DiscoveryCandidate.
# INV-2: this module never emits canonical opportunities.
# INV-3: provenance is unaffected — the universe is intelligence input,
#        not a confirmation source.
_token_universe_cache: list = []
_TOKEN_UNIVERSE_MAX = 100         # rolling window size
_TOKEN_UNIVERSE_LOOKBACK_S = 24 * 3600   # match arbicore_discovery_candidates TTL


def _token_universe_loader_sync() -> list:
    """Synchronous accessor used by HeliusWalletSource.discover().

    Returns a snapshot of the current cache (defensive copy — the source
    iterates and mutates a cursor over this list). Empty list ≡ no
    candidates from upstream sources yet, which is the dormant boot
    state; cache is populated by ``_refresh_token_universe_once`` on the
    existing 15 s launch-arb cache-refresh loop.
    """
    return list(_token_universe_cache)


async def _refresh_token_universe_once() -> None:
    """Read the most-recent LAUNCH_ARBITRAGE candidates from
    ``arbicore_discovery_candidates`` and project ``subject_id`` →
    Solana mint string. Subject IDs are stored as ``{chain}:{addr}`` by
    every D-4.1 source (see ``sources.py:136/293/439/559``). We accept
    only the ``solana:*`` prefix because HeliusWalletSource's
    ``/v0/addresses/{mint}/transactions`` API is Solana-specific.

    Best-effort; any exception is swallowed so a Mongo blip cannot
    crash the cache-refresh loop. The scanner gracefully tolerates an
    empty cache (Gate B fall-through to ``return []``).
    """
    global _token_universe_cache
    try:
        col = _get_db()["arbicore_discovery_candidates"]
        cutoff_ts = _time.time() - _TOKEN_UNIVERSE_LOOKBACK_S
        cursor = col.find(
            {
                "opportunity_type": "LAUNCH_ARBITRAGE",
                "subject_id": {"$regex": "^solana:"},
                "hint_observed_at": {"$gte": cutoff_ts},
            },
            {"subject_id": 1, "_id": 0},
        ).sort("hint_observed_at", -1).limit(_TOKEN_UNIVERSE_MAX * 2)
        seen: set = set()
        out: list = []
        async for doc in cursor:
            sid = (doc.get("subject_id") or "")
            if not sid.startswith("solana:"):
                continue
            mint = sid.split(":", 1)[1].strip()
            if not mint or mint in seen:
                continue
            seen.add(mint)
            out.append(mint)
            if len(out) >= _TOKEN_UNIVERSE_MAX:
                break
        _token_universe_cache = out
    except Exception:  # noqa: BLE001
        # Refresh is best-effort; keep the previous snapshot on failure.
        pass


def get_token_universe_snapshot() -> list:
    """Read-only snapshot for diagnostics / endpoints. Returns a copy."""
    return list(_token_universe_cache)


def get_wallet_profile_repo() -> WalletProfileRepository:
    global _wallet_profile_repo
    if _wallet_profile_repo is None:
        _wallet_profile_repo = MongoWalletProfileRepository()
    return _wallet_profile_repo


def get_opportunity_repo() -> OpportunityRepository:
    global _opportunity_repo
    if _opportunity_repo is None:
        # v2.11.8+ hotfix: MongoOpportunityRepository now requires an
        # explicit db handle.  Use the shared canonical handle exposed
        # by services.db.
        from services import db as _services_db
        _opportunity_repo = MongoOpportunityRepository(_services_db.db)
    return _opportunity_repo


def get_outcome_repo() -> OutcomeRepository:
    global _outcome_repo
    if _outcome_repo is None:
        _outcome_repo = MongoOutcomeRepository()
    return _outcome_repo


def get_metrics_repo() -> MetricsRepository:
    global _metrics_repo
    if _metrics_repo is None:
        _metrics_repo = MongoMetricsRepository()
    return _metrics_repo


def get_regime_snapshot_repo() -> RegimeSnapshotRepository:
    global _regime_snapshot_repo
    if _regime_snapshot_repo is None:
        _regime_snapshot_repo = MongoRegimeSnapshotRepository()
    return _regime_snapshot_repo


def get_state_observer_registry() -> StateObserverRegistry:
    global _state_observer_registry
    if _state_observer_registry is None:
        _state_observer_registry = StateObserverRegistry()
    return _state_observer_registry


def get_event_bus() -> EventBus:
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


def get_audit_log() -> MongoAuditLog:
    global _audit_log
    if _audit_log is None:
        _audit_log = MongoAuditLog()
    return _audit_log


def get_route_tracker() -> MongoRouteSuccessTracker:
    global _route_tracker
    if _route_tracker is None:
        _route_tracker = MongoRouteSuccessTracker()
    return _route_tracker


def get_outcome_tracker() -> OutcomeTracker:
    global _outcome_tracker
    if _outcome_tracker is None:
        _outcome_tracker = OutcomeTracker(
            outcome_repo=get_outcome_repo(),
            observer_registry=get_state_observer_registry(),
            route_tracker=get_route_tracker(),
            audit_log=get_audit_log(),
        )
    return _outcome_tracker


def get_metrics_aggregator() -> MetricsAggregator:
    global _metrics_aggregator
    if _metrics_aggregator is None:
        _metrics_aggregator = MetricsAggregator(metrics_repo=get_metrics_repo())
    return _metrics_aggregator


def get_outcome_evaluator() -> OutcomeEvaluator:
    global _outcome_evaluator
    if _outcome_evaluator is None:
        _outcome_evaluator = OutcomeEvaluator(tracker=get_outcome_tracker())
    return _outcome_evaluator


# ---- Wave 2 -----------------------------------------------------------------

def get_adaptive_weights() -> MongoBackedAdaptiveWeights:
    global _adaptive_weights
    if _adaptive_weights is None:
        _adaptive_weights = MongoBackedAdaptiveWeights(
            metrics_repo=get_metrics_repo(),
        )
    return _adaptive_weights


def get_confidence_engine() -> AdaptiveConfidenceEngine:
    global _confidence_engine
    if _confidence_engine is None:
        _confidence_engine = AdaptiveConfidenceEngine(
            weights=get_adaptive_weights(),
            route_tracker=get_route_tracker(),
            observer_registry=get_state_observer_registry(),
            regime_repo=get_regime_snapshot_repo(),
        )
    return _confidence_engine


# ---- Wave 3 -----------------------------------------------------------------

def get_survival_analytics() -> SurvivalAnalytics:
    global _survival_analytics
    if _survival_analytics is None:
        _survival_analytics = SurvivalAnalytics(outcome_repo=get_outcome_repo())
    return _survival_analytics


def get_regime_classifier() -> HeuristicRegimeClassifier:
    global _regime_classifier
    if _regime_classifier is None:
        _regime_classifier = HeuristicRegimeClassifier(
            outcome_repo=get_outcome_repo(),
            regime_repo=get_regime_snapshot_repo(),
        )
    return _regime_classifier


def get_sequence_miner() -> SequenceMiner:
    global _sequence_miner
    if _sequence_miner is None:
        _sequence_miner = SequenceMiner(regime_repo=get_regime_snapshot_repo())
    return _sequence_miner


def get_regime_worker() -> RegimeClassifierWorker:
    global _regime_worker
    if _regime_worker is None:
        _regime_worker = RegimeClassifierWorker(
            classifier=get_regime_classifier(),
            miner=get_sequence_miner(),
            outcome_repo=get_outcome_repo(),
        )
    return _regime_worker


# ---- Wave 4: Universal Entity Intelligence ---------------------------------

def get_entity_repo() -> MongoEntityRepository:
    global _entity_repo
    if _entity_repo is None:
        _entity_repo = MongoEntityRepository()
    return _entity_repo


def get_entity_resolver() -> EntityResolver:
    global _entity_resolver
    if _entity_resolver is None:
        _entity_resolver = EntityResolver()
    return _entity_resolver


def get_entity_cluster_detector() -> EntityClusterDetector:
    global _entity_cluster_detector
    if _entity_cluster_detector is None:
        _entity_cluster_detector = EntityClusterDetector()
    return _entity_cluster_detector


def get_entity_scorer() -> EntityScorer:
    global _entity_scorer
    if _entity_scorer is None:
        _entity_scorer = EntityScorer(metrics_repo=get_metrics_repo())
    return _entity_scorer


# ---- Wave 5: Shadow Binding -------------------------------------------------

def get_shadow_binder() -> ShadowBindingObserver:
    global _shadow_binder
    if _shadow_binder is None:
        _shadow_binder = ShadowBindingObserver(
            opportunity_repo=get_opportunity_repo(),
            outcome_repo=get_outcome_repo(),
            outcome_tracker=get_outcome_tracker(),
            metrics_aggregator=get_metrics_aggregator(),
            entity_resolver=get_entity_resolver(),
            audit_log=get_audit_log(),
        )
    return _shadow_binder


# ---- Phase D D-1: Discovery Layer + CEX Arb scanner ------------------------

def _get_db():
    """Internal — fetch the Mongo db handle from services.db (initialised
    at server boot)."""
    global _db_handle
    if _db_handle is not None:
        return _db_handle
    from services.db import db
    _db_handle = db
    return _db_handle


def get_db():
    return _get_db()


def get_emission_bus() -> EmissionBus:
    global _emission_bus
    if _emission_bus is None:
        _emission_bus = EmissionBus(
            opportunity_repo=get_opportunity_repo(),
            outcome_repo=get_outcome_repo(),
            outcome_tracker=get_outcome_tracker(),
            entity_resolver=get_entity_resolver(),
            audit_log=get_audit_log(),
        )
    return _emission_bus


def get_discovery_queue() -> DiscoveryQueue:
    global _discovery_queue
    if _discovery_queue is None:
        _discovery_queue = DiscoveryQueue(_get_db())
    return _discovery_queue


def get_discovery_source_metrics() -> DiscoverySourceMetricsRepo:
    global _discovery_source_metrics
    if _discovery_source_metrics is None:
        _discovery_source_metrics = DiscoverySourceMetricsRepo(_get_db())
    return _discovery_source_metrics


def get_venue_capability_repo() -> VenueCapabilityRepository:
    global _venue_capability_repo
    if _venue_capability_repo is None:
        _venue_capability_repo = VenueCapabilityRepository(_get_db())
    return _venue_capability_repo


def get_scanner_config_repo() -> ScannerConfigRepository:
    global _scanner_config_repo
    if _scanner_config_repo is None:
        _scanner_config_repo = ScannerConfigRepository(_get_db())
    return _scanner_config_repo


def get_scanner_state_repo() -> ScannerStateRepository:
    global _scanner_state_repo
    if _scanner_state_repo is None:
        _scanner_state_repo = ScannerStateRepository(_get_db())
    return _scanner_state_repo


# v2.11.8 — Paper Validation Framework repo (canonical evidence store).
def build_controlled_live_safety(quoter_registry, *, kill_switch=None):
    """M3.0 wiring — build (PreBroadcastValidator, CircuitBreaker) for the
    controlled-live broadcaster, reusing the EXISTING M2.1 live quote provider,
    M2.5 price feed, M2.6-resolved TVL, and the flash-loan economics assessor.

    Returns (None, None) when the operator environment lacks a Base RPC — the
    broadcaster is wired with require_revalidation=True, so a None validator
    forces a fail-closed DENY before signing (never a silent broadcast)."""
    from ..execution.pre_broadcast import (
        PreBroadcastValidator, CircuitBreaker, RevalidationInputs)
    from ..searcher.runtime import (
        make_base_eth_call_from_env, build_base_tvl_provider,
        make_base_congestion_source_from_env)
    from ..searcher.price_feed import build_base_price_feed_from_env
    from ..scanners.flash_loan_arbitrage.live_quote_provider import (
        make_live_quote_provider)
    from ..scanners.flash_loan_arbitrage.economics import (
        FlashLoanEconomicsAssessor, FLASH_LOAN_PROVIDERS)
    from ..scanners.cross_chain_arbitrage.bridge_intelligence import MevRiskScorer
    from ..intelligence.roi_probability import ROIProbabilityEngine
    from ..discovery import base_pool_registry as _reg

    eth_call = make_base_eth_call_from_env()
    if eth_call is None:
        return None, None
    price_feed = build_base_price_feed_from_env(quoter_registry)
    if price_feed is None:
        return None, None
    tvl_provider = build_base_tvl_provider(eth_call, price_feed.price_source)
    quote_provider = make_live_quote_provider(quoter_registry,
                                              tvl_provider=tvl_provider)
    econ = FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05))
    mev = MevRiskScorer()
    congestion_source = make_base_congestion_source_from_env()
    from ..chains.gas_model import get_chain_gas_model
    # Base all-in cost is now priced through the chain-neutral gas-model seam.
    # BaseGasModel is a pass-through over make_base_all_in_cost_estimator_from_env
    # → behaviour is identical to the previous direct wiring (fail-closed when no RPC).
    gas_model = get_chain_gas_model("base")
    import os as _os
    vault = (_os.environ.get("BASE_BALANCER_V2_VAULT")
             or "0xBA12222222228d8Ba445958a75a0704d566BF2C8")

    async def _flashloan_available(provider, borrow_token, borrow_amount_usd):
        """Real-time genuine check: Balancer V2 Vault must actually hold at
        least the borrow amount of the borrow token. Any read failure → None.

        Instrumented: every None/False path logs the exact reason so the VPS
        harness shows whether the balanceOf read, price read, or provider/token
        mapping is the blocker. Return semantics are UNCHANGED (fail-closed)."""
        meta = FLASH_LOAN_PROVIDERS.get((provider or "").lower())
        if not meta or "base" not in meta.get("supports_chains", ()):
            _M3_LOG.warning(
                "flashloan_available=False stage=provider_meta provider=%r "
                "(unknown provider or not supported on base)", provider)
            return False
        # The deployed executor head is Balancer V2 + Uniswap V3. Other
        # catalogued providers are not executable by this calldata/contract
        # path, so refuse them instead of checking the wrong vault or allowing
        # a profitable-but-unsupported route through M3.
        if (provider or "").lower() != "balancer_v2":
            _M3_LOG.warning(
                "flashloan_available=False stage=executor_capability provider=%r "
                "(current executor supports balancer_v2 only)", provider)
            return False
        cp = None
        for p in _reg.get_canonical_pools():
            if borrow_token.upper() in (p.token0_symbol.upper(), p.token1_symbol.upper()):
                cp = p
                break
        if cp is None:
            _M3_LOG.warning(
                "flashloan_available=None stage=token_registry borrow_token=%r "
                "(no canonical pool exposes this token)", borrow_token)
            return None
        if cp.token0_symbol.upper() == borrow_token.upper():
            taddr, tdec = cp.token0_address, cp.token0_decimals
        else:
            taddr, tdec = cp.token1_address, cp.token1_decimals
        data = "0x70a08231" + vault.lower().replace("0x", "").rjust(64, "0")
        try:
            raw = await eth_call(taddr, data)
        except Exception as exc:  # noqa: BLE001
            _M3_LOG.warning(
                "flashloan_available=None stage=balanceOf_eth_call vault=%s "
                "token=%s(%s) error=%s: %s", vault, borrow_token, taddr,
                type(exc).__name__, exc)
            return None
        if not raw:
            _M3_LOG.warning(
                "flashloan_available=None stage=balanceOf_empty vault=%s "
                "token=%s(%s) (eth_call returned empty)", vault, borrow_token, taddr)
            return None
        try:
            bal = int(raw, 16) / (10 ** int(tdec))
        except (ValueError, TypeError) as exc:
            _M3_LOG.warning(
                "flashloan_available=None stage=balanceOf_decode raw=%r error=%s: %s",
                raw, type(exc).__name__, exc)
            return None
        px = await price_feed.price_source(borrow_token)
        if px is None or px <= 0:
            _M3_LOG.warning(
                "flashloan_available=None stage=borrow_token_price token=%r price=%r "
                "(price feed could not price the borrow token)", borrow_token, px)
            return None
        ok = bal >= (float(borrow_amount_usd) / px)
        if not ok:
            _M3_LOG.warning(
                "flashloan_available=False stage=insufficient_vault_liquidity "
                "vault_bal=%s needed=%s token=%s px=%s", bal,
                float(borrow_amount_usd) / px, borrow_token, px)
        return ok

    async def fresh_fn(plan):
        """FRESH re-check at broadcast time. Any missing input → None (deny).

        Fully instrumented: every fail-closed path logs the EXACT stage plus the
        underlying value/exception at WARNING (logger ``arbicore.m3_0.fresh_fn``)
        so the VPS validation harness and the live loop reveal precisely which
        dependency blocked. Behaviour is UNCHANGED — any failure still returns
        None (deny) and no gate threshold is altered."""
        stage = "extract_plan"
        try:
            route_pools = list(plan.get("route_pools") or [])
            token_path = list(plan.get("cycle_token_path") or [])
            borrow_token = (plan.get("borrow_token") or "").upper()
            borrow_usd = float(plan.get("borrow_amount_usd") or 0.0)
            provider = (plan.get("flash_loan_provider")
                        or plan.get("provider") or "balancer_v2")
            quoted_block = plan.get("quoted_block")
            if not route_pools or not borrow_token or borrow_usd <= 0:
                _M3_LOG.warning(
                    "DENY stage=extract_plan route_pools=%d borrow_token=%r "
                    "borrow_usd=%s", len(route_pools), borrow_token, borrow_usd)
                return None
            if len(token_path) != len(route_pools) + 1:
                _M3_LOG.warning(
                    "DENY stage=token_path_shape route_pools=%d token_path=%d "
                    "(need %d) — quote provider requires a closed cycle path; "
                    "check evidence-bundle route.cycle_token_path persistence",
                    len(route_pools), len(token_path), len(route_pools) + 1)
                return None
            # The deployed flash-loan executor supports only Balancer V2
            # borrowing plus Uniswap V3 swap hops. Aerodrome/Slipstream quotes
            # are valid intelligence, but cannot produce executable calldata
            # for this head; reject before economics/gas so an unset aggregate
            # gas estimate can never be mistaken for a live candidate.
            from ..discovery.base_pool_registry import canonical_pool_specs
            _pool_specs = canonical_pool_specs()
            unsupported = [pid for pid in route_pools
                           if (_pool_specs.get(pid) or {}).get("dex") not in
                           (None, "uniswap_v3")]
            if unsupported:
                _M3_LOG.warning(
                    "DENY stage=executor_capability unsupported_route_pools=%s "
                    "(current executor supports uniswap_v3 swaps only)", unsupported)
                return None
            stage = "resolve_pools"
            # M2.6 PROPAGATION — resolve+validate the Aerodrome/Slipstream route
            # pools on-chain and write REAL addresses into the ONE canonical
            # registry so the TVL/address path matches the (working) quote path.
            # Best-effort: if it fails, TVL stays unmeasured and Gate 8 keeps
            # failing closed (no address is ever fabricated).
            try:
                from ..searcher.aero_resolver import resolve_and_propagate
                await resolve_and_propagate(
                    eth_call, route_pools, get_block=price_feed._head_block)
            except Exception as exc:  # noqa: BLE001
                _M3_LOG.warning(
                    "aero resolve/propagate soft-fail %s: %s (TVL gate stays "
                    "fail-closed)", type(exc).__name__, exc)
            stage = "live_quote"
            hm = {"chain": "base", "provider": provider,
                  "borrow_token": borrow_token, "route_pools": route_pools,
                  "cycle_token_path": token_path}
            facts = await quote_provider(hm, borrow_usd)      # M2.1 quote + M2.6 TVL
            if not facts:
                _M3_LOG.warning(
                    "DENY stage=live_quote quote_provider returned no facts — "
                    "route unpriceable on-chain (all hops fallback ⇒ "
                    "break_even, malformed route, or unknown token). "
                    "route_pools=%s token_path=%s", route_pools, token_path)
                return None
            stage = "hop_legs"
            hop_legs = list(facts.get("hop_legs") or [])
            if not hop_legs:
                _M3_LOG.warning(
                    "DENY stage=hop_legs facts present but no hop_legs "
                    "route_quote_status=%r", facts.get("route_quote_status"))
                return None
            stage = "mev"
            # Real Base network congestion (eth_feeHistory gasUsedRatio). No
            # source / any read failure ⇒ DENY (fail-closed, never fabricated).
            congestion = (await congestion_source()
                          if congestion_source is not None else None)
            if congestion is None:
                _M3_LOG.warning(
                    "DENY stage=mev real Base congestion unavailable "
                    "(eth_feeHistory gasUsedRatio unreadable / no Base RPC) — "
                    "MEV classification fails closed rather than inventing a "
                    "value")
                return None
            mev_view = mev.classify(source_chain_congestion=congestion,
                                    destination_chain_congestion=congestion,
                                    asset=borrow_token, notional_usd=borrow_usd,
                                    is_atomic=True)
            # Policy (matches flash_loan_arbitrage.filter._MEV_ORDER): LOW/MEDIUM
            # pass, HIGH denies. MevRiskLevel is a str-enum ⇒ compare by label.
            mev_ok = mev_view["label"] != "HIGH"
            stage = "economics"
            e = econ.assess(provider=provider, chain="base",
                            borrow_token=borrow_token, borrow_amount_usd=borrow_usd,
                            hop_legs=hop_legs, signal_categories=[provider, "base"],
                            real_outcomes=[], synthetic_outcomes=[],
                            gross_profit_pct=float(facts.get("gross_profit_pct") or 0.0),
                            mev_risk_level=mev_view["level"],
                            gas_cost_usd_override=facts.get("gas_cost_usd"),
                            tx_gas_units=facts.get("tx_gas_units"),
                            gross_is_quote_inclusive=True)
            stage = "head_block"
            head = None
            try:
                head = await price_feed._head_block()  # reuse cached head reader
            except Exception as exc:  # noqa: BLE001
                _M3_LOG.warning("head_block read failed %s: %s (block_freshness "
                                "will deny) ", type(exc).__name__, exc)
                head = None
            stage = "flashloan_available"
            avail = await _flashloan_available(provider, borrow_token, borrow_usd)
            stage = "all_in_cost"
            # TRUE all-in Base fee: real gas-price ceiling (L2) + Base L1 data
            # fee (GasPriceOracle) + flash-loan fee + slippage/risk allowance.
            # Swap fees are already embedded in the quoted gross round-trip.
            # DENY (fail-closed) if the exact all-in cost cannot be determined.
            gross_profit_usd = (borrow_usd
                                * float(facts.get("gross_profit_pct") or 0.0) / 100.0)
            eth_usd = None
            try:
                eth_usd = await price_feed.price_source("WETH")
            except Exception as exc:  # noqa: BLE001
                _M3_LOG.warning("all_in_cost ETH_USD read failed %s: %s",
                                type(exc).__name__, exc)
            all_in = (await gas_model.all_in_cost(
                gross_profit_usd=gross_profit_usd, borrow_amount_usd=borrow_usd,
                notional_usd=borrow_usd, gas_units=facts.get("tx_gas_units"),
                eth_usd=eth_usd)
                if gas_model is not None else None)
            if all_in is None:
                _M3_LOG.warning(
                    "DENY stage=all_in_cost — true all-in Base fee could not be "
                    "determined safely (exact gas / gas price / L1 GasPriceOracle "
                    "fee / ETH_USD unavailable); fail-closed")
                return None
            net_profit_all_in = all_in["net_profit_all_in_usd"]
            stage = "assemble"
            import time as _t
            # Structured stage summary (INFO) — the harness elevates this logger
            # so a successful fresh read is also visible on the VPS.
            _M3_LOG.info(
                "fresh read OK net_profit_usd=%s (all_in=%s l1=%s l2=%s "
                "pre_l1_atomic=%s) min_tvl_usd=%s quote_ok=%s "
                "price_ok=%s mev_ok=%s flashloan_available=%s head=%s "
                "quoted_block=%s", net_profit_all_in,
                round(all_in["all_in_cost_usd"], 4),
                round(all_in["l1_fee_usd"], 4), round(all_in["l2_fee_usd"], 4),
                round(float(e.atomic_profit_usd), 4),
                facts.get("min_pool_tvl_usd_in_route"),
                facts.get("route_quote_status") == "ok",
                facts.get("tvl_provenance") == "onchain_reserves",
                mev_ok, avail, head, quoted_block)
            return RevalidationInputs(
                block_number=head, quoted_block=quoted_block, now_ts=_t.time(),
                deadline_ts=plan.get("deadline_ts"),
                net_profit_usd=net_profit_all_in,
                min_tvl_usd=float(facts.get("min_pool_tvl_usd_in_route") or 0.0),
                quote_ok=(facts.get("route_quote_status") == "ok"),
                price_ok=(facts.get("tvl_provenance") == "onchain_reserves"),
                mev_ok=mev_ok,
                flashloan_available=avail,
                opp_fingerprint=str(plan.get("opportunity_id")
                                    or plan.get("plan_id") or ""))
        except Exception as exc:  # noqa: BLE001 — any error ⇒ fail closed
            _M3_LOG.exception("EXCEPTION at stage=%s %s: %s",
                              stage, type(exc).__name__, exc)
            return None

    async def _on_trip(reason):
        if kill_switch is not None:
            try:
                await kill_switch.engage(f"circuit_breaker: {reason}",
                                         actor="circuit_breaker")
            except Exception:  # noqa: BLE001
                pass

    validator = PreBroadcastValidator(fresh_fn=fresh_fn)
    breaker = CircuitBreaker(on_trip=_on_trip)
    return validator, breaker


_paper_evidence_repo = None  # type: ignore[assignment]
_evidence_bundles_repo = None  # type: ignore[assignment]


def get_evidence_bundles_repo():
    """M2.3 — singleton :class:`EvidenceBundlesRepo` over ``db.evidence_bundles``
    (append-only audit store). Lazily built against the shared Mongo handle."""
    global _evidence_bundles_repo
    if _evidence_bundles_repo is None:
        from ..data.mongo.evidence_bundles_repo import EvidenceBundlesRepo
        _evidence_bundles_repo = EvidenceBundlesRepo(_get_db())
    return _evidence_bundles_repo


def make_flash_loan_evidence_sink():
    """Return ``async (bundle_dict) -> None`` persisting an audit bundle for
    EVERY verified flash-loan candidate (CONFIRMED and DENIED) into
    ``db.evidence_bundles``. Best-effort by contract (the verifier already
    guards it) — never alters a verdict, never broadcasts."""
    repo = get_evidence_bundles_repo()

    async def _sink(bundle: dict) -> None:
        await repo.insert(bundle)
    return _sink


def _os_env_on(key: str) -> bool:
    import os as _os
    return (_os.environ.get(key) or "").strip().lower() in {
        "1", "true", "yes", "on"}


def make_flash_loan_shadow_sink():
    """M2.4 — return ``async (canonical, evidence) -> None`` that routes a
    CONFIRMED flash-loan candidate through a SHADOW OpportunityPipeline.

    The pipeline is built with NO broadcaster and NO mode_repo, so
    ``_resolve_mode`` returns ``SHADOW`` and broadcast is structurally
    impossible. Evidence lands in the immutable paper-evidence store."""
    from ..execution.pipeline import OpportunityPipeline
    from ..data.journal import OpportunityJournal
    from ..scanners.flash_loan_arbitrage.shadow_route import route_to_shadow
    journal = OpportunityJournal(_get_db())
    pipeline = OpportunityPipeline(
        journal=journal, evidence_repo=get_paper_evidence_repo())

    async def _sink(canonical, evidence: dict) -> None:
        await route_to_shadow(pipeline, canonical, evidence)
    return _sink


def get_paper_evidence_repo():
    """Return the singleton :class:`PaperEvidenceRepository`.

    Lazily constructed against the same Mongo handle as the other
    canonical repos.  Immutable insert-only surface — see the module
    docstring in :mod:`arbicore.paper.repo`.
    """
    global _paper_evidence_repo
    if _paper_evidence_repo is None:
        from ..paper import PaperEvidenceRepository
        _paper_evidence_repo = PaperEvidenceRepository(_get_db())
    return _paper_evidence_repo


def get_cex_arb_scanner() -> CEXArbitrageScanner:
    global _cex_arb_scanner
    if _cex_arb_scanner is None:
        cfg_repo = get_scanner_config_repo()
        state_repo = get_scanner_state_repo()
        cache = {"cfg": dict(), "state": {"enabled": False}}

        def _load_cfg():
            return cache["cfg"] or {}

        def _load_state():
            return cache["state"] or {}

        async def _refresh_caches_once():
            try:
                cache["cfg"] = await cfg_repo.get("cex_arb")
                cache["state"] = await state_repo.get("cex_arb")
            except Exception:
                pass

        _cex_arb_scanner = CEXArbitrageScanner(
            emission_bus=get_emission_bus(),
            discovery_queue=get_discovery_queue(),
            venue_capability_repo=get_venue_capability_repo(),
            config_loader=_load_cfg,
            state_loader=_load_state,
            confidence_engine=get_confidence_engine(),
        )
        # Phase D D-1.5 — register the first aggregator DiscoverySource. The
        # source emits DiscoveryCandidates into the same queue as the venue
        # ticker sources. Verifier dispatch is unchanged (CEXOrderBookVerifier
        # reads venue books and enforces INV-3 by sourcing provenance from
        # the venue's SOURCE_REGISTRY classification, never CG's).
        from ..scanners.discovery.coingecko_ticker import CoinGeckoTickerSource
        _cex_arb_scanner.source_registry.register(
            CoinGeckoTickerSource(config_loader=_load_cfg),
        )
        _cex_arb_scanner._sources.append(  # type: ignore[attr-defined]
            _cex_arb_scanner.source_registry.get("coingecko_ticker"),
        )
        # Expose the refresh hook so initialise_arbicore_runtime can prime caches
        # and start a periodic refresh task.
        _cex_arb_scanner._refresh_caches_once = _refresh_caches_once  # type: ignore[attr-defined]
    return _cex_arb_scanner


def get_funding_arb_scanner() -> FundingArbitrageScanner:
    """Phase D D-2.0 funding-arb scanner factory. Mirrors CEX scanner."""
    global _funding_arb_scanner
    if _funding_arb_scanner is None:
        cfg_repo = get_scanner_config_repo()
        state_repo = get_scanner_state_repo()
        cache = {"cfg": dict(), "state": {"enabled": False}}

        def _load_cfg():
            return cache["cfg"] or {}

        def _load_state():
            return cache["state"] or {}

        async def _refresh_caches_once():
            try:
                cache["cfg"] = await cfg_repo.get("funding_arb")
                cache["state"] = await state_repo.get("funding_arb")
            except Exception:
                pass

        _funding_arb_scanner = FundingArbitrageScanner(
            emission_bus=get_emission_bus(),
            discovery_queue=get_discovery_queue(),
            venue_capability_repo=get_venue_capability_repo(),
            config_loader=_load_cfg,
            state_loader=_load_state,
            confidence_engine=get_confidence_engine(),
            depth_fetcher=None,   # next checkpoint wires order-book depth
        )
        _funding_arb_scanner._refresh_caches_once = _refresh_caches_once  # type: ignore[attr-defined]
    return _funding_arb_scanner


def get_dex_arb_scanner() -> DEXArbitrageScanner:
    """Phase D D-3.4 DEX-arb scanner factory. Mirrors funding-arb scanner."""
    global _dex_arb_scanner
    if _dex_arb_scanner is None:
        cfg_repo = get_scanner_config_repo()
        state_repo = get_scanner_state_repo()
        cache = {"cfg": dict(), "state": {"enabled": False}}

        def _load_cfg():
            return cache["cfg"] or {}

        def _load_state():
            return cache["state"] or {}

        async def _refresh_caches_once():
            try:
                cache["cfg"] = await cfg_repo.get("dex_arb")
                cache["state"] = await state_repo.get("dex_arb")
            except Exception:
                pass

        _dex_arb_scanner = DEXArbitrageScanner(
            emission_bus=get_emission_bus(),
            discovery_queue=get_discovery_queue(),
            venue_capability_repo=get_venue_capability_repo(),
            config_loader=_load_cfg,
            state_loader=_load_state,
            confidence_engine=get_confidence_engine(),
        )
        _dex_arb_scanner._refresh_caches_once = _refresh_caches_once  # type: ignore[attr-defined]
    return _dex_arb_scanner


def get_launch_arb_scanner() -> LaunchArbitrageScanner:
    """Phase D D-4.5 Launch-arb scanner factory. Mirrors funding-arb scanner.

    INV-2: ``LaunchArbitrageScanner._tick()`` is the SINGLE emit call site for
    ``LAUNCH_ARBITRAGE``. The factory wires only the verifier composition and
    the runtime caches; the operator must explicitly enable the scanner state
    AND (for live verification) inject a real ``LaunchVenueProvider`` via
    ``set_venue_provider(...)`` for canonicals to be confirmed. Until then
    the no-op provider returns ``None`` and every candidate ends as
    ``denied:venue_unreadable`` — visibly counted, never emitted.
    """
    global _launch_arb_scanner
    if _launch_arb_scanner is None:
        cfg_repo = get_scanner_config_repo()
        state_repo = get_scanner_state_repo()
        cache = {"cfg": dict(), "state": {"enabled": False}}

        def _load_cfg():
            return cache["cfg"] or {}

        def _load_state():
            return cache["state"] or {}

        async def _refresh_caches_once():
            try:
                cache["cfg"] = await cfg_repo.get("launch_arb")
                cache["state"] = await state_repo.get("launch_arb")
            except Exception:
                pass

        _launch_arb_scanner = LaunchArbitrageScanner(
            emission_bus=get_emission_bus(),
            discovery_queue=get_discovery_queue(),
            venue_capability_repo=get_venue_capability_repo(),
            config_loader=_load_cfg,
            state_loader=_load_state,
            confidence_engine=get_confidence_engine(),
            entity_scorer=get_entity_scorer(),
            venue_provider=None,            # no-op until operator wires Helius
            # D-4 Subset D — autonomous token-universe loader (replaces
            # the previous ``None`` that left HeliusWalletSource gated by
            # an empty universe). Cache is refreshed on the existing
            # 15 s launch-arb cache-refresh loop; see
            # ``_refresh_token_universe_once`` above.
            token_universe_loader=_token_universe_loader_sync,
        )
        _launch_arb_scanner._refresh_caches_once = _refresh_caches_once  # type: ignore[attr-defined]
    return _launch_arb_scanner


def get_cross_chain_arb_scanner() -> CrossChainArbitrageScanner:
    """Phase D D-5.1 Cross-Chain Arbitrage scanner factory.

    INV-2: ``CrossChainArbitrageScanner._tick()`` is the SINGLE emit call
    site for ``CROSS_CHAIN_ARBITRAGE``. The factory wires only the
    verifier composition and runtime caches; the operator must explicitly
    enable scanner state AND (for live verification) inject a real
    ``TransferModelProvider`` via ``set_transfer_provider(...)`` for
    canonicals to be confirmed. Until then the no-op provider returns
    ``None`` and every candidate ends as ``denied:venue_unreadable`` —
    visibly counted, never emitted.
    """
    global _cross_chain_arb_scanner
    if _cross_chain_arb_scanner is None:
        cfg_repo = get_scanner_config_repo()
        state_repo = get_scanner_state_repo()
        cache = {"cfg": dict(), "state": {"enabled": False}}

        def _load_cfg():
            return cache["cfg"] or {}

        def _load_state():
            return cache["state"] or {}

        async def _refresh_caches_once():
            try:
                cache["cfg"] = await cfg_repo.get("cross_chain_arb")
                cache["state"] = await state_repo.get("cross_chain_arb")
            except Exception:
                pass

        _cross_chain_arb_scanner = CrossChainArbitrageScanner(
            emission_bus=get_emission_bus(),
            discovery_queue=get_discovery_queue(),
            venue_capability_repo=get_venue_capability_repo(),
            config_loader=_load_cfg,
            state_loader=_load_state,
            confidence_engine=get_confidence_engine(),
            transfer_provider=None,
            chain_liveness_loader=None,
        )
        _cross_chain_arb_scanner._refresh_caches_once = _refresh_caches_once  # type: ignore[attr-defined]
    return _cross_chain_arb_scanner


# P0-3 runtime UniV3 eligibility snapshot.
#
# The canonical registry remains pure/deterministic. PoolNode identity remains
# the canonical pool id. This mutable set records only pools that must be
# excluded from the live Base route universe because their real on-chain V3
# liquidity is currently unavailable/unreadable.
_BASE_V3_INELIGIBLE = set()

def _failclosed_exclude_all_base_univ3() -> int:
    """Fail-closed baseline: exclude EVERY resolved Base UniV3 pool from the
    runtime universe. Used (a) to pre-seed the deny-list before live reads and
    (b) as the caller's fallback if the refresh raises/cancels — an unverified
    pool must NEVER be admitted merely because a read did not complete. The
    canonical registry itself is never mutated. Best-effort: returns the count
    excluded (0 if the registry is itself unreadable, in which case the
    synchronous route loader independently fails closed by producing no
    resolved universe)."""
    try:
        from ..discovery.base_pool_registry import (
            build_canonical_pool_graph as _g)
        ids = {n.pool_address for n in _g(resolved_only=True)[0]
               if n.dex_protocol == "uniswap_v3"}
    except Exception:  # noqa: BLE001 — registry unreadable ⇒ loader fails closed
        return 0
    _BASE_V3_INELIGIBLE.update(ids)
    return len(ids)


async def _refresh_base_v3_eligibility(eth_call, *, max_concurrency: int = 8,
                                       per_call_timeout_s: Optional[float] = 2.0
                                       ) -> dict:
    """Refresh runtime UniV3 liquidity eligibility from real chain state.

    Fail-closed:
      * missing canonical address → excluded
      * missing/malformed/timed-out/unreadable liquidity() → excluded
      * liquidity == 0 → excluded
      * positive liquidity → eligible

    Aerodrome/Slipstream are deliberately untouched because their
    liquidity state is not represented by UniV3 liquidity().

    P0-3 startup-budget remediation (performance only — classification
    unchanged; nothing is EVER eligible without a positive on-chain read):
      * the per-pool ``liquidity()`` reads run under BOUNDED CONCURRENCY
        (``max_concurrency`` in-flight RPCs) instead of strictly sequentially,
        so ~19 real Base RPC round-trips no longer serialise the canonical
        scanner's startup budget;
      * each read is bounded by ``per_call_timeout_s`` — a stalled RPC is
        classified EXCLUDED (fail-closed), never allowed to hang startup;
      * the deny-list is PRE-SEEDED fail-closed (every resolved UniV3 pool
        excluded) before any await, so a mid-flight exception OR a
        startup-deadline ``CancelledError`` leaves the universe fail-closed —
        a pool is only re-admitted after its genuine ``liquidity()>0`` read
        completes (atomic rebuild at the end).
    """
    import asyncio as _asyncio
    from eth_abi import decode as _abi_decode
    from ..discovery.base_pool_registry import (
        build_canonical_pool_graph as _canonical_base_graph,
        canonical_pool_by_id,
    )

    LIQUIDITY_SELECTOR = "0x1a686502"

    univ3_nodes = [node for node in _canonical_base_graph(resolved_only=True)[0]
                   if node.dex_protocol == "uniswap_v3"]

    # Fail-closed BASELINE established BEFORE any await: exclude every resolved
    # UniV3 pool. A cancellation/exception before the atomic rebuild therefore
    # leaves unverified pools OUT of the runtime universe (never admitted).
    _BASE_V3_INELIGIBLE.clear()
    _BASE_V3_INELIGIBLE.update(node.pool_address for node in univ3_nodes)

    if eth_call is None:
        # No trustworthy runtime state source: fail closed for every
        # deterministic UniV3 pool (baseline already excludes them all).
        return {
            "checked": 0,
            "eligible": 0,
            "excluded": len(univ3_nodes),
            "reason": "base_eth_call_unavailable",
        }

    sem = _asyncio.Semaphore(max(1, int(max_concurrency)))

    async def _read_liquidity(address):
        coro = eth_call(address, LIQUIDITY_SELECTOR)
        if per_call_timeout_s is not None and per_call_timeout_s > 0:
            # TimeoutError is an Exception subclass ⇒ caught below ⇒ excluded.
            return await _asyncio.wait_for(coro, timeout=per_call_timeout_s)
        return await coro

    async def _classify(node):
        """Return ``(pool_id, is_eligible)``. Fail-closed on every abnormal
        path: only a positive on-chain liquidity() read yields eligibility."""
        cp = canonical_pool_by_id(node.pool_address)
        address = getattr(cp, "address", None) if cp is not None else None
        if not address:
            return node.pool_address, False
        async with sem:
            try:
                raw = await _read_liquidity(address)
                if not raw:
                    raise ValueError("empty_liquidity_read")
                decoded = _abi_decode(
                    ["uint128"],
                    bytes.fromhex(
                        raw[2:] if raw.startswith("0x") else raw
                    ),
                )
                liquidity = int(decoded[0])
            except Exception:
                return node.pool_address, False
        return node.pool_address, liquidity > 0

    results = await _asyncio.gather(*(_classify(node) for node in univ3_nodes))

    excluded = {pool_id for pool_id, is_eligible in results if not is_eligible}
    eligible = sum(1 for _, is_eligible in results if is_eligible)

    # Atomic rebuild from the VERIFIED results (supersedes the fail-closed
    # baseline only once every read has completed).
    _BASE_V3_INELIGIBLE.clear()
    _BASE_V3_INELIGIBLE.update(excluded)

    return {
        "checked": len(univ3_nodes),
        "eligible": eligible,
        "excluded": len(excluded),
    }


def get_flash_loan_arb_scanner() -> FlashLoanArbitrageScanner:
    """Phase D D-6.1 Flash-Loan Arbitrage scanner factory.

    SIXTH and FINAL INV-2 emit site (per scanner family). Detection
    only. Boot posture: DORMANT — every per-provider and per-chain
    enable flag in ``scanner_config.flash_loan_arb`` ships ``False``;
    ``scanner_state.flash_loan_arb.enabled`` ships ``False``; the
    default no-op quote provider returns ``None`` so even if the
    operator flips state without wiring a real provider, no canonical
    can confirm.
    """
    global _flash_loan_arb_scanner
    if _flash_loan_arb_scanner is None:
        cfg_repo = get_scanner_config_repo()
        state_repo = get_scanner_state_repo()
        # Canonical activation: detection ENABLED by default (SHADOW/detection
        # only — emission is still fully gated by the economic/atomic/MEV gates
        # in the verifier, and execution by the mode ladder + AutoExecutor).
        cache = {"cfg": {"interval_s": 60.0,
                          "chains": {"base": {"enabled": True}},
                          "providers": {"balancer_v2": {"enabled": True}},
                          "route_search": {"max_hops": 3, "wall_clock_cap_s": 3.0,
                                            "candidate_cap": 48, "min_pool_tvl_usd": 0.0},
                          "gate_thresholds": {"default": {}}},
                 "state": {"enabled": True}}

        def _load_cfg():
            return cache["cfg"] or {}

        def _load_state():
            return cache["state"] or {}

        async def _refresh_caches_once():
            # Merge operator overrides from the repos WITHOUT disabling the
            # canonical detection plane (repo default ships enabled=False; a
            # canonical activation keeps detection on unless an operator has
            # explicitly written enabled=False).
            try:
                rc = await cfg_repo.get("flash_loan_arb")
                if rc:
                    cache["cfg"] = {**cache["cfg"], **rc}
                rs = await state_repo.get("flash_loan_arb")
                if isinstance(rs, dict) and rs.get("enabled") is False and rs.get("_operator_set"):
                    cache["state"] = {"enabled": False}
            except Exception:
                pass

        # Base route universe is sourced from the ONE canonical registry
        # (Z8/Z9 fix): canonical pool identity → resolved real addresses →
        # PoolNode. Built fresh per search so Aerodrome/Slipstream pools that
        # become runtime_resolved on the VPS (M2.6) enter the graph; unresolved
        # (address-less) pools are excluded (fail-closed) so a synthetic-only
        # id can never reach the live quote/execution path. base_venues stays
        # regression-frozen for the separate OpportunityEngine.
        from ..discovery.base_venues import CHAIN as _BASE_CHAIN
        from ..discovery.base_pool_registry import (
            build_canonical_pool_graph as _canonical_base_graph)
        from ..discovery.multichain_venues import (
            build_pool_graph as _mc_pool_graph, supported_discovery_chains)
        from ..config.persistent import resolve_rpc_url_from_env

        def _multichain_pool_loader(chain: str):
            """Generic multi-chain pool universe (SHADOW, fail-closed).

            Base → canonical resolved graph minus the current runtime V3
            eligibility deny-list. The canonical registry itself is never
            mutated by this filter and RouteSearchEngine remains synchronous
            and pure.
            """
            c = (chain or "").lower()
            if c == _BASE_CHAIN:
                pools = _canonical_base_graph(resolved_only=True)[0]
                if _BASE_V3_INELIGIBLE:
                    pools = [
                        n for n in pools
                        if n.pool_address not in _BASE_V3_INELIGIBLE
                    ]
                return pools
            if c in supported_discovery_chains() and resolve_rpc_url_from_env(c):
                return _mc_pool_graph(c)
            return []

        _flash_loan_arb_scanner = FlashLoanArbitrageScanner(
            emission_bus=get_emission_bus(),
            discovery_queue=get_discovery_queue(),
            venue_capability_repo=get_venue_capability_repo(),
            config_loader=_load_cfg,
            state_loader=_load_state,
            pool_loader=_multichain_pool_loader,
            quote_provider=None,   # set to the live provider at activation
            chain_liveness_loader=None,
            confidence_engine=get_confidence_engine(),
        )
        _flash_loan_arb_scanner._refresh_caches_once = _refresh_caches_once  # type: ignore[attr-defined]
    return _flash_loan_arb_scanner


async def _wire_canonical_flash_loan_scanner(quoter_registry):
    """Shared wiring for the canonical FlashLoanArbitrageScanner (live quote
    provider + fail-closed Gate-8 TVL provider + price provenance + auditable
    evidence sink + optional SHADOW route). Returns ``(scanner, meta)`` WITHOUT
    starting the background loop. Never signs / never broadcasts."""
    from ..scanners.flash_loan_arbitrage.live_quote_provider import make_live_quote_provider
    from ..searcher.runtime import (
        make_base_eth_call_from_env, make_base_price_source_from_env,
        build_base_tvl_provider,
    )
    from ..searcher.price_feed import build_base_price_feed_from_env
    scanner = get_flash_loan_arb_scanner()
    # M2.2 — build the REAL, fail-closed Gate-8 TVL provider from the operator
    # environment (Base RPC eth_call + genuine USD price source). Absent either
    # dependency → tvl_provider is None → Gate 8 fails closed (never fabricated).
    # M2.5 — prefer the on-chain multi-token USD price feed (USDC-denominated,
    # peg-guarded, freshness-checked) when ARBICORE_USD_NUMERAIRE is configured;
    # otherwise fall back to the native-only source. Either way: no fabrication.
    tvl_provider = None
    price_feed = None
    price_source_kind = "none"
    aero_resolved = 0
    try:
        eth_call = make_base_eth_call_from_env()

        # P0-3 remediation: refresh the synchronous route-loader's runtime
        # UniV3 eligibility snapshot from real liquidity(). Never alter the
        # canonical registry; unreadable/zero-liquidity pools fail closed.
        try:
            v3_eligibility = await _refresh_base_v3_eligibility(eth_call)
        except Exception:
            # Fail CLOSED: an escaping refresh error must NOT admit unverified
            # UniV3 pools into the runtime universe. Re-assert the fail-closed
            # baseline (the refresh already pre-seeds it before any await, so
            # this also covers a pre-await registry failure).
            _failclosed_exclude_all_base_univ3()
            v3_eligibility = {
                "checked": 0,
                "eligible": 0,
                "excluded": len(_BASE_V3_INELIGIBLE),
                "reason": "eligibility_refresh_error",
            }

        # M2.6 — resolve Aerodrome/Slipstream pools on-chain via factory getPool
        # and record validated addresses into the canonical registry so the
        # EXISTING reserves/TVL path picks them up. Fail-closed per pool.
        if eth_call is not None:
            try:
                from ..searcher.aero_resolver import build_base_aero_resolver_from_env
                from ..discovery import base_pool_registry as _reg
                resolver = build_base_aero_resolver_from_env(eth_call)
                if resolver is not None:
                    results = await resolver.resolve_all(_reg.unresolved_pools())
                    for cid, r in results.items():
                        if _reg.set_runtime_resolved_address(
                                cid, r.address, provenance=r.provenance):
                            aero_resolved += 1
            except Exception:  # noqa: BLE001 — resolution never blocks activation
                aero_resolved = 0
        price_feed = build_base_price_feed_from_env(quoter_registry)
        if price_feed is not None:
            price_source = price_feed.price_source
            price_source_kind = "onchain_usd_feed_m2_5"
        else:
            price_source = make_base_price_source_from_env()
            price_source_kind = ("native_only" if price_source is not None
                                 else "none")
        if eth_call is not None and price_source is not None:
            tvl_provider = build_base_tvl_provider(eth_call, price_source)
    except Exception:  # noqa: BLE001 — fail-closed to None
        tvl_provider = None
    scanner.set_quote_provider(
        make_live_quote_provider(quoter_registry, tvl_provider=tvl_provider))
    # M2.5 — wire per-token USD price provenance into the evidence bundle.
    if price_feed is not None:
        try:
            scanner.set_price_provenance_fn(price_feed.provenance_for)
        except Exception:  # noqa: BLE001
            pass
    # M2.3 — persist an auditable evidence bundle for every verified candidate.
    try:
        scanner.set_evidence_sink(make_flash_loan_evidence_sink())
        evidence_sink_wired = True
    except Exception:  # noqa: BLE001 — audit wiring never blocks activation
        evidence_sink_wired = False
    # M2.4 — route CONFIRMED candidates into the SHADOW/PAPER pipeline. Opt-in
    # (default OFF) to avoid double-processing with the global PaperValidation
    # runner; strictly SHADOW — no broadcaster/mode wired → cannot broadcast.
    shadow_route_wired = False
    if _os_env_on("ARBICORE_FLASH_LOAN_SHADOW_ROUTE"):
        try:
            scanner.set_shadow_sink(make_flash_loan_shadow_sink())
            shadow_route_wired = True
        except Exception:  # noqa: BLE001
            shadow_route_wired = False
    meta = {
        "instantiated": True,
        "class": "FlashLoanArbitrageScanner",
        "scanner_id": scanner.scanner_id,
        "quote_provider": "live" if not scanner.quote_provider_is_default else "noop",
        "tvl_provider": ("onchain_reserves" if tvl_provider is not None
                         else "unverified_fail_closed"),
        "price_source": price_source_kind,
        "aero_pools_resolved": aero_resolved,
        "v3_liquidity_eligibility": v3_eligibility,
        "v3_ineligible_runtime_pools": len(_BASE_V3_INELIGIBLE),
        "evidence_sink": evidence_sink_wired,
        "shadow_route": shadow_route_wired,
        "pool_universe_size": len(_base_pools_size()),
        "detection_only": True,
    }
    return scanner, meta


async def activate_canonical_flash_loan_scanner(quoter_registry) -> dict:
    """STAGE 1 canonical activation of the REAL FlashLoanArbitrageScanner.

    Wires the live Base quote provider (same QuoterRegistry as the
    OpportunityEngine) and starts detection. Detection-only / SHADOW: emission
    remains gated by the economic + atomic-profit + liquidity + MEV gates in the
    verifier, and execution by the mode ladder + AutoExecutor. Never signs or
    broadcasts. Idempotent."""
    scanner, meta = await _wire_canonical_flash_loan_scanner(quoter_registry)
    await scanner.start()
    meta["enabled"] = scanner.is_enabled()
    return meta


async def run_single_canonical_flash_loan_audit_tick(quoter_registry) -> dict:
    """Diagnostic-only: wire the canonical scanner EXACTLY as activation does,
    then execute EXACTLY ONE ``_tick()`` (no background loop) so an auditor can
    capture the ACTUAL ``audit_run_id`` + ``scanner_tick_id`` produced by that
    tick and isolate its evidence. READ-ONLY: detection only, never signs,
    never broadcasts, never enables any live mode.

    Returns the real run/tick identity + wiring meta. The candidate ledger is
    NOT reconstructed here — the caller reads it back from the evidence store
    via ``EvidenceBundlesRepo.find_for_audit(audit_run_id, scanner_tick_id)``,
    which is the authoritative, fail-closed attribution path.
    """
    scanner, meta = await _wire_canonical_flash_loan_scanner(quoter_registry)
    tick_before = getattr(scanner, "_tick_id", 0)
    ran = False
    if scanner.is_enabled():
        await scanner._tick()
        ran = True
    meta.update({
        "mode": "single_audit_tick",
        "enabled": scanner.is_enabled(),
        "tick_executed": ran,
        # ACTUAL identity generated by this exact run/tick (never guessed).
        "audit_run_id": getattr(scanner, "_audit_run_id", None),
        "scanner_tick_id": getattr(scanner, "_tick_id", tick_before),
        "worker_id": getattr(scanner, "_worker_id", None),
    })
    return meta


def flash_loan_quote_readiness(*, quote_provider_is_default: bool,
                               mode: str) -> dict:
    """T0-1 · scanner quote-provider readiness gate.

    The canonical scanner must NEVER run the ``noop_quote_provider`` as a
    silent production quote path. If the flash-loan strategy is in an analysis
    mode (PAPER/SHADOW/LIMITED_LIVE/FULL_LIVE) while still on the default noop
    provider, this returns an explicit ``readiness_error`` and marks the
    scanner NOT active. OBSERVE (and unknown) modes may remain on noop for
    cold-start/tests.
    """
    analysis_modes = {"PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE"}
    m = (mode or "").upper()
    if quote_provider_is_default and m in analysis_modes:
        return {
            "ready": False,
            "active": False,
            "quote_provider": "noop",
            "readiness_error": (
                f"canonical flash-loan scanner is in {m} but still on the "
                "default noop quote provider — refusing to run a synthetic "
                "production quote path (T0-1). Wire the live quote provider "
                "via activate_canonical_flash_loan_scanner()."),
        }
    return {
        "ready": True,
        "active": not quote_provider_is_default,
        "quote_provider": "noop" if quote_provider_is_default else "live",
        "readiness_error": None,
    }


def _base_pools_size():
    # Reflect the ACTUAL Base route universe the scanner loads: the canonical
    # registry graph, resolved addresses only (fail-closed).
    from ..discovery.base_pool_registry import build_canonical_pool_graph
    pools, _ = build_canonical_pool_graph(resolved_only=True)
    return pools


def _register_default_state_observers() -> int:
    """Register one default CategoryMetadataStateObserver per OpportunityType."""
    reg = get_state_observer_registry()
    n = 0
    for t in OpportunityType:
        if reg.is_registered(t):
            continue
        reg.register(make_default_observer(t))
        n += 1
    return n


async def initialise_arbicore_runtime() -> dict:
    """Called once from server.py lifespan AFTER existing services start.

    Phase B: instantiate adapters + indexes.
    Phase C Wave 1: instantiate learners + start the OutcomeEvaluator worker.
    """
    # Phase B foundation
    get_opportunity_repo()
    get_outcome_repo()
    get_metrics_repo()
    get_regime_snapshot_repo()
    get_state_observer_registry()
    index_report = await _ensure_indexes()

    # Phase C Wave 1 learners
    get_event_bus()
    get_audit_log()
    get_route_tracker()
    get_outcome_tracker()
    get_metrics_aggregator()
    evaluator = get_outcome_evaluator()
    await evaluator.start()

    # Phase C Wave 2 — observers + adaptive weights + confidence engine
    observers_registered = _register_default_state_observers()
    weights = get_adaptive_weights()
    await weights.refresh()    # populate cache from existing signal metrics
    get_confidence_engine()

    # Phase C Wave 3 — survival + regime + sequence mining
    get_survival_analytics()
    get_regime_classifier()
    get_sequence_miner()
    regime_worker = get_regime_worker()
    await regime_worker.start()

    # Phase C Wave 4 — Universal Entity Intelligence
    get_entity_repo()
    get_entity_resolver()
    get_entity_cluster_detector()
    get_entity_scorer()

    # Phase C Wave 5 — Shadow Binding: wire the binder and attach it as a
    # post-run hook on the legacy ApprovalProposer. Wrapped in try/except
    # because the legacy module MUST keep running even if the binder fails
    # to attach (e.g. during test isolation).
    binder = get_shadow_binder()
    try:
        from services.execution.approval_proposer import approval_proposer as _proposer
        async def _shadow_hook(snapshot):
            try:
                await binder.observe(snapshot)
            except Exception:  # noqa: BLE001
                # Defence-in-depth: binder.observe is already exception-
                # safe, but we double-guard the legacy loop.
                pass
        _proposer.post_run_hook = _shadow_hook  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass

    await get_audit_log().write(
        actor="composition",
        event="arbicore_runtime_initialised",
        payload={
            "phase": "B+C-wave-1",
            "collections": index_report.get("collections", []),
            "ttl_indexes": index_report.get("ttl_indexes", []),
        },
    )

    # Phase D D-1.0 — Discovery Layer + CEX Arbitrage scanner
    import os as _os
    discovery_q = get_discovery_queue()
    await discovery_q.ensure_indexes()
    venue_caps = get_venue_capability_repo()
    await venue_caps.ensure_indexes()
    source_metrics = get_discovery_source_metrics()
    await source_metrics.ensure_indexes()
    cfg_repo = get_scanner_config_repo()
    await cfg_repo.ensure_indexes()
    await cfg_repo.seed_defaults()
    state_repo = get_scanner_state_repo()
    await state_repo.ensure_indexes()
    await state_repo.seed_defaults()
    # Boot env gate: if ARBICORE_SCANNER_CEX_ARB=on, persist enabled state.
    if _os.environ.get("ARBICORE_SCANNER_CEX_ARB", "off").lower() == "on":
        await state_repo.set_enabled("cex_arb", True, actor="env_boot")
    scanner = get_cex_arb_scanner()
    # Prime caches synchronously now that we're in an async context
    if hasattr(scanner, "_refresh_caches_once"):
        await scanner._refresh_caches_once()  # type: ignore[attr-defined]
    # Start a periodic refresh task (every 15 s)
    async def _scanner_cache_refresh_loop():
        import asyncio as _asyncio
        while True:
            try:
                await scanner._refresh_caches_once()  # type: ignore[attr-defined]
            except Exception:
                pass
            await _asyncio.sleep(15.0)
    import asyncio as _asyncio2
    _asyncio2.create_task(_scanner_cache_refresh_loop())

    # Phase D D-1.0 deferred wire — completed during D-1.5 validation so the
    # source-quality telemetry that D-1.5 introduces aggregator hints into can
    # actually be observed. Invokes existing DiscoverySourceMetricsRepo.
    # aggregate_all() every 60 s; no new behaviour beyond calling that method.
    async def _source_metrics_aggregator_loop():
        import asyncio as _asyncio
        while True:
            await _asyncio.sleep(60.0)
            try:
                await source_metrics.aggregate_all()
            except Exception:
                pass
    _asyncio2.create_task(_source_metrics_aggregator_loop())

    if (await state_repo.get("cex_arb")).get("enabled"):
        try:
            await scanner.start()
        except Exception:
            pass

    # ── Phase D D-2.0 — Funding Arbitrage scanner ──
    if _os.environ.get("ARBICORE_SCANNER_FUNDING_ARB", "off").lower() == "on":
        await state_repo.set_enabled("funding_arb", True, actor="env_boot")
    f_scanner = get_funding_arb_scanner()
    if hasattr(f_scanner, "_refresh_caches_once"):
        await f_scanner._refresh_caches_once()  # type: ignore[attr-defined]
    async def _funding_cache_refresh_loop():
        import asyncio as _asyncio
        while True:
            try:
                await f_scanner._refresh_caches_once()  # type: ignore[attr-defined]
            except Exception:
                pass
            await _asyncio.sleep(15.0)
    _asyncio2.create_task(_funding_cache_refresh_loop())
    if (await state_repo.get("funding_arb")).get("enabled"):
        try:
            await f_scanner.start()
        except Exception:
            pass

    # ── Phase D D-3.4 — DEX Arbitrage scanner ──
    # The scanner + verifier registries are constructed here. INV-2: the
    # DEXArbitrageScanner._tick() is the SINGLE emit call site for DEX_ARBITRAGE.
    # Both scanner state AND every individual discovery source remain
    # DISABLED at boot per operator's D-3.6 shadow-rollout requirement —
    # operator graduates each source via /api/arbicore/discovery/sources/...
    # and the scanner via /api/arbicore/scanners/dex_arb/resume.
    if _os.environ.get("ARBICORE_SCANNER_DEX_ARB", "off").lower() == "on":
        await state_repo.set_enabled("dex_arb", True, actor="env_boot")
    d_scanner = get_dex_arb_scanner()
    if hasattr(d_scanner, "_refresh_caches_once"):
        await d_scanner._refresh_caches_once()  # type: ignore[attr-defined]
    async def _dex_cache_refresh_loop():
        import asyncio as _asyncio
        while True:
            try:
                await d_scanner._refresh_caches_once()  # type: ignore[attr-defined]
            except Exception:
                pass
            await _asyncio.sleep(15.0)
    _asyncio2.create_task(_dex_cache_refresh_loop())
    if (await state_repo.get("dex_arb")).get("enabled"):
        try:
            await d_scanner.start()
        except Exception:
            pass

    # ── Phase D D-4.5 — Launch Arbitrage scanner ──
    # The orchestrator is now wired. INV-2: ``LaunchArbitrageScanner._tick()``
    # is the SINGLE emit call site for ``LAUNCH_ARBITRAGE``. Boot posture is
    # DORMANT: ``scanner_state.launch_arb.enabled`` defaults to ``False``;
    # ``HELIUS_API_KEY`` may be absent (sources self-disable); the default
    # no-op venue_provider returns ``None`` so even if the operator flips
    # state without wiring a real provider, no canonical can confirm.
    # Operator graduates the scanner via /api/arbicore/scanners/launch_arb/
    # resume (D-4.6 endpoint).
    if _os.environ.get("ARBICORE_SCANNER_LAUNCH_ARB", "off").lower() == "on":
        await state_repo.set_enabled("launch_arb", True, actor="env_boot")
    l_scanner = get_launch_arb_scanner()
    if hasattr(l_scanner, "_refresh_caches_once"):
        await l_scanner._refresh_caches_once()  # type: ignore[attr-defined]
    # D-4 Subset D — populate the autonomous token-universe cache once
    # at boot so HeliusWalletSource can emit on its first tick. Failures
    # are swallowed; an empty cache simply means the source gracefully
    # returns ``[]`` until the next refresh cycle harvests new candidates.
    try:
        await _refresh_token_universe_once()
    except Exception:
        pass

    # ── Operational readiness — opt-in reference venue_provider wiring ──
    # When HELIUS_API_KEY is provisioned, auto-wire the reference
    # HeliusLaunchVenueProvider so the scanner can produce verified
    # canonicals once the operator flips scanner_state to enabled. This
    # is a purely additive, operator-controlled step — no automatic
    # enabling, no execution, no INV change. See
    # D4_OPERATIONAL_READINESS_REPORT.md §5 for the full activation path.
    if _os.environ.get("HELIUS_API_KEY", "").strip() \
            and l_scanner.venue_provider_is_default:
        try:
            # D-4 hotfix wave — wire the operator-substrate loaders:
            #   - wallet_profile_loader: reads cached wallet profiles via
            #     the D-4.2 wallet_profile_repo (lazy; returns {} on miss)
            #   - outcome_history_loader: reads realised outcome rows
            #     filtered to LAUNCH_ARBITRAGE provenance via outcome_repo
            outcome_repo_ref = _outcome_repo
            # D-4 Subset B — WalletProfileRepository wiring. Replaces the
            # empty-stub loader that previously returned ``{}``. We seed
            # curated labels from ``intel/launch/labels.json`` on boot so
            # the SmartMoneyDetector's curated-label fallback path
            # (smart_money/whale/influencer → TIER_QUALITY) fires at
            # verification time for any tagged buyer wallet that surfaces
            # in candidate ``hint_metric.buyer_wallets[_sample]``.
            wallet_profile_repo_ref = get_wallet_profile_repo()
            try:
                from ..intel.launch.labels import load_curated as _load_curated
                curated_records = _load_curated()
                if curated_records:
                    seed_profiles = seed_curated_into(
                        wallet_profile_repo_ref, curated_records,
                    )
                    if seed_profiles:
                        await wallet_profile_repo_ref.bulk_upsert(
                            seed_profiles)
            except Exception:  # noqa: BLE001
                # Seeding is best-effort; an empty curated file is normal.
                pass

            async def _wallet_profile_loader(addresses):
                """Read wallet profiles from the persistent repo.

                Returns ``{address: profile_dict}`` for any addresses the
                repo knows about; missing addresses are simply absent. The
                verifier's SmartMoneyDetector handles missing entries by
                falling through to ``TIER_NONE`` (unchanged behaviour).
                """
                if not addresses:
                    return {}
                try:
                    return await wallet_profile_repo_ref.get_many(
                        list(addresses)) or {}
                except Exception:  # noqa: BLE001
                    return {}

            async def _outcome_history_loader(subject_id):
                """Pre-warm real_outcomes from outcome_repo for this
                subject_id. Returns ``[]`` when no history exists (bootstrap
                state). The ROIProbabilityEngine then uses its synthetic
                fallback per min_sample config."""
                if outcome_repo_ref is None:
                    return []
                try:
                    rows = await outcome_repo_ref.list_for_subject(
                        subject_id, evaluated=True)
                    return [r.to_dict() for r in rows]
                except Exception:  # noqa: BLE001
                    return []

            l_scanner.set_venue_provider(HeliusLaunchVenueProvider(
                wallet_profile_loader=_wallet_profile_loader,
                outcome_history_loader=_outcome_history_loader,
            ))
        except Exception:  # noqa: BLE001
            pass

    async def _launch_cache_refresh_loop():
        import asyncio as _asyncio
        while True:
            try:
                await l_scanner._refresh_caches_once()  # type: ignore[attr-defined]
            except Exception:
                pass
            # D-4 Subset D — refresh the autonomous token-universe cache
            # alongside the config/state refresh. Best-effort; failures
            # are swallowed inside the helper so they cannot kill the loop.
            try:
                await _refresh_token_universe_once()
            except Exception:
                pass
            await _asyncio.sleep(15.0)
    _asyncio2.create_task(_launch_cache_refresh_loop())
    if (await state_repo.get("launch_arb")).get("enabled"):
        try:
            await l_scanner.start()
        except Exception:
            pass

    # ── Phase D D-5.1 — Cross-Chain Arbitrage scanner ──
    # The orchestrator is now wired (D-5.0 substrate + D-5.1 sources/
    # verifier/gates/scanner/composition). INV-2:
    # ``CrossChainArbitrageScanner._tick()`` is the SINGLE emit call site
    # for ``CROSS_CHAIN_ARBITRAGE``. Boot posture is DORMANT:
    # ``scanner_state.cross_chain_arb.enabled`` defaults to ``False``;
    # every per-bridge and per-chain enable flag ships ``False``; the
    # default no-op transfer_provider returns ``None`` so even if the
    # operator flips state without wiring a real provider, no canonical
    # can confirm. Operator graduates via /api/arbicore/scanners/
    # cross_chain_arb/resume + per-source enable endpoints.
    if _os.environ.get(
            "ARBICORE_SCANNER_CROSS_CHAIN_ARB", "off").lower() == "on":
        await state_repo.set_enabled(
            "cross_chain_arb", True, actor="env_boot")
    x_scanner = get_cross_chain_arb_scanner()
    if hasattr(x_scanner, "_refresh_caches_once"):
        await x_scanner._refresh_caches_once()  # type: ignore[attr-defined]

    # Opt-in reference providers — auto-attach when corresponding env
    # surface is present. Each provider is REAL on-chain quote source
    # per INV-3. No scanner auto-enables — operator must still flip
    # scanner_state.
    if x_scanner.transfer_provider_is_default:
        try:
            x_scanner.register_transfer_provider(
                "lifi", LiFiTransferProvider())
        except Exception:  # noqa: BLE001
            pass
    # Stargate provider auto-attaches whenever the env surface exists
    # (key present, even empty string is fine — Stargate's public API
    # works without a key but adding it raises rate limits).
    try:
        x_scanner.register_transfer_provider(
            "stargate", StargateTransferProvider())
    except Exception:  # noqa: BLE001
        pass

    # D-5.2 — Live chain-liveness RPC loader auto-attach. Reads per-chain
    # RPC URLs from scanner_config.cross_chain_arb.chains.<id>.rpc_env_var.
    # Loader is a no-op for any chain without a provisioned env URL, so
    # this is safe to attach unconditionally.
    try:
        x_scanner.set_chain_liveness_loader(
            RpcChainLivenessLoader(config_loader=x_scanner.config_loader))
    except Exception:  # noqa: BLE001
        pass

    async def _cross_chain_cache_refresh_loop():
        import asyncio as _asyncio
        while True:
            try:
                await x_scanner._refresh_caches_once()  # type: ignore[attr-defined]
            except Exception:
                pass
            await _asyncio.sleep(15.0)
    _asyncio2.create_task(_cross_chain_cache_refresh_loop())
    if (await state_repo.get("cross_chain_arb")).get("enabled"):
        try:
            await x_scanner.start()
        except Exception:
            pass

    # ── Phase D D-6.1 — Flash-Loan Arbitrage scanner ──
    # Sixth and final INV-2 emit site. Detection only. Boot posture
    # DORMANT — every per-provider and per-chain enable flag ships
    # False; scanner state ships False; default no-op quote provider
    # returns None so even if the operator flips state without wiring
    # a real provider, no canonical can confirm.
    if _os.environ.get(
            "ARBICORE_SCANNER_FLASH_LOAN_ARB", "off").lower() == "on":
        await state_repo.set_enabled(
            "flash_loan_arb", True, actor="env_boot")
    fl_scanner = get_flash_loan_arb_scanner()
    if hasattr(fl_scanner, "_refresh_caches_once"):
        await fl_scanner._refresh_caches_once()  # type: ignore[attr-defined]

    async def _flash_loan_cache_refresh_loop():
        import asyncio as _asyncio
        while True:
            try:
                await fl_scanner._refresh_caches_once()  # type: ignore[attr-defined]
            except Exception:
                pass
            await _asyncio.sleep(15.0)
    _asyncio2.create_task(_flash_loan_cache_refresh_loop())
    if (await state_repo.get("flash_loan_arb")).get("enabled"):
        try:
            await fl_scanner.start()
        except Exception:
            pass

    return {
        "opportunity_repo_alive": _opportunity_repo is not None,
        "outcome_repo_alive": _outcome_repo is not None,
        "metrics_repo_alive": _metrics_repo is not None,
        "regime_snapshot_repo_alive": _regime_snapshot_repo is not None,
        "state_observer_registry_alive": _state_observer_registry is not None,
        # Wave 1
        "event_bus_alive": _event_bus is not None,
        "audit_log_alive": _audit_log is not None,
        "route_tracker_alive": _route_tracker is not None,
        "outcome_tracker_alive": _outcome_tracker is not None,
        "metrics_aggregator_alive": _metrics_aggregator is not None,
        "outcome_evaluator_running": evaluator.running,
        # Wave 2
        "adaptive_weights_alive": _adaptive_weights is not None,
        "confidence_engine_alive": _confidence_engine is not None,
        "default_state_observers_registered": observers_registered,
        # Wave 3
        "survival_analytics_alive": _survival_analytics is not None,
        "regime_classifier_alive": _regime_classifier is not None,
        "sequence_miner_alive": _sequence_miner is not None,
        "regime_worker_running": regime_worker.running,
        # Wave 4
        "entity_repo_alive": _entity_repo is not None,
        "entity_resolver_alive": _entity_resolver is not None,
        "entity_cluster_detector_alive": _entity_cluster_detector is not None,
        "entity_scorer_alive": _entity_scorer is not None,
        # Wave 5
        "shadow_binder_alive": _shadow_binder is not None,
        # D-1.0
        "emission_bus_alive": _emission_bus is not None,
        "discovery_queue_alive": _discovery_queue is not None,
        "venue_capability_repo_alive": _venue_capability_repo is not None,
        "scanner_config_repo_alive": _scanner_config_repo is not None,
        "scanner_state_repo_alive": _scanner_state_repo is not None,
        "cex_arb_scanner_alive": _cex_arb_scanner is not None,
        "funding_arb_scanner_alive": _funding_arb_scanner is not None,
        "dex_arb_scanner_alive": _dex_arb_scanner is not None,
        "launch_arb_scanner_alive": _launch_arb_scanner is not None,
        "cross_chain_arb_scanner_alive": _cross_chain_arb_scanner is not None,
        "flash_loan_arb_scanner_alive": _flash_loan_arb_scanner is not None,
        "indexes": index_report,
    }


async def shutdown_arbicore_runtime() -> None:
    if _outcome_evaluator is not None:
        await _outcome_evaluator.stop()
    if _regime_worker is not None:
        await _regime_worker.stop()


def _reset_for_tests() -> None:
    """Test-only: clear cached singletons so tests can re-init cleanly."""
    global _opportunity_repo, _outcome_repo, _metrics_repo
    global _regime_snapshot_repo, _state_observer_registry
    global _event_bus, _audit_log, _route_tracker
    global _outcome_tracker, _metrics_aggregator, _outcome_evaluator
    global _adaptive_weights, _confidence_engine
    global _survival_analytics, _regime_classifier, _sequence_miner, _regime_worker
    global _entity_repo, _entity_resolver, _entity_cluster_detector, _entity_scorer
    global _shadow_binder
    _opportunity_repo = None
    _outcome_repo = None
    _metrics_repo = None
    _regime_snapshot_repo = None
    _state_observer_registry = None
    _event_bus = None
    _audit_log = None
    _route_tracker = None
    _outcome_tracker = None
    _metrics_aggregator = None
    _outcome_evaluator = None
    _adaptive_weights = None
    _confidence_engine = None
    _survival_analytics = None
    _regime_classifier = None
    _sequence_miner = None
    _regime_worker = None
    _entity_repo = None
    _entity_resolver = None
    _entity_cluster_detector = None
    _entity_scorer = None
    _shadow_binder = None
