"""IntelligenceActivation — Wave 1B-α factory.

Constructs the six previously-dormant engines and registers them with the
:class:`IntelligenceRegistry`. Each engine is built defensively: any
individual failure is caught, recorded in the registry, and does not
prevent other engines from activating.

Engines activated in this wave:
  * ``confidence``       — SignalConfidenceEngine
  * ``roi``              — ROIProbabilityEngine
  * ``route_ranking``    — ScoringEngine
  * ``economics``        — CapitalSizer
  * ``entity_scoring``   — EntityScorer  (uses in-memory MetricsRepository)
  * ``regime``           — HeuristicRegimeClassifier  (uses in-memory Outcome
                           + RegimeSnapshot repos)

None of these engines start a background worker. They are pure adapters
that a caller (Wave 1B-β scanners or an operator via the API) invokes on
demand. Their evidence flows into MID via :class:`MidEvidenceBridge`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ...data.mid.writers import MidWriter
from ..capital import CapitalSizer
from ..confidence import SignalConfidenceEngine
from ..roi_probability import ROIProbabilityEngine
from ..scoring import ScoringEngine
from ...intel.scorer import EntityScorer
from ...learning.concrete.regime_classifier import HeuristicRegimeClassifier
from .bridge import MidEvidenceBridge
from .inmemory_repos import (
    InMemoryMetricsRepository,
    InMemoryOutcomeRepository,
    InMemoryRegimeSnapshotRepository,
)
from .registry import IntelligenceRegistry

logger = logging.getLogger(__name__)


@dataclass
class IntelligenceActivation:
    """Return value of :func:`activate_all`.

    Holds live references to every engine + supporting repository + the
    single :class:`MidEvidenceBridge`. Also exposes the
    :class:`IntelligenceRegistry` that the API endpoints render.
    """

    registry: IntelligenceRegistry
    bridge: MidEvidenceBridge
    confidence: Optional[SignalConfidenceEngine] = None
    roi: Optional[ROIProbabilityEngine] = None
    route_ranking: Optional[ScoringEngine] = None
    economics: Optional[CapitalSizer] = None
    entity_scoring: Optional[EntityScorer] = None
    regime: Optional[HeuristicRegimeClassifier] = None
    # supporting in-memory repos, exposed for tests
    _metrics_repo: Optional[InMemoryMetricsRepository] = None
    _outcome_repo: Optional[InMemoryOutcomeRepository] = None
    _regime_repo: Optional[InMemoryRegimeSnapshotRepository] = None

    def get(self, engine_id: str) -> Any:
        return getattr(self, engine_id, None)

    def summary(self) -> Dict[str, Any]:
        s = self.registry.summary()
        s["bridge_stats"] = self.bridge.stats.to_dict()
        return s


def activate_all(writer: MidWriter) -> IntelligenceActivation:
    """Instantiate every engine + the bridge and register them.

    Never raises: any per-engine failure is captured in the registry.
    """
    registry = IntelligenceRegistry()
    bridge = MidEvidenceBridge(writer)
    result = IntelligenceActivation(registry=registry, bridge=bridge)

    # ------------------------------------------------------------------
    # 1. Confidence — SignalConfidenceEngine
    # ------------------------------------------------------------------
    try:
        eng = SignalConfidenceEngine()
        result.confidence = eng
        registry.register(
            engine_id="confidence",
            description=(
                "Persistence-based per-route confidence score in [0, 100]"
            ),
            instance=eng,
            dependencies=["intelligence.confidence.SignalConfidenceEngine"],
            snapshot_fn=lambda e=eng: {
                "routes_tracked": len(e.store.all()),
                "sample": [s.as_dict() for s in list(e.store.all())[:5]],
            },
        )
        logger.info("intelligence: activated engine=confidence")
    except Exception as exc:  # noqa: BLE001
        logger.exception("intelligence: failed to activate confidence: %s", exc)
        registry.register(
            engine_id="confidence",
            description="Persistence-based per-route confidence score",
            instance=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    # ------------------------------------------------------------------
    # 2. ROI probability — ROIProbabilityEngine
    # ------------------------------------------------------------------
    try:
        eng = ROIProbabilityEngine()
        result.roi = eng
        registry.register(
            engine_id="roi",
            description="Winsorised ROI distribution + breakout probability",
            instance=eng,
            dependencies=["intelligence.roi_probability.ROIProbabilityEngine"],
            snapshot_fn=lambda e=eng: {
                "min_sample": e.min_sample,
                "winsorize_pct": e.winsorize_pct,
                "horizon_hours": e.horizon_hours,
            },
        )
        logger.info("intelligence: activated engine=roi")
    except Exception as exc:  # noqa: BLE001
        logger.exception("intelligence: failed to activate roi: %s", exc)
        registry.register(
            engine_id="roi",
            description="Winsorised ROI distribution + breakout probability",
            instance=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    # ------------------------------------------------------------------
    # 3. Route ranking — ScoringEngine
    # ------------------------------------------------------------------
    try:
        eng = ScoringEngine()
        result.route_ranking = eng
        registry.register(
            engine_id="route_ranking",
            description=(
                "Chain-agnostic route scoring (spread × persistence × "
                "liquidity ÷ gas·mev)"
            ),
            instance=eng,
            dependencies=["intelligence.scoring.ScoringEngine"],
            snapshot_fn=lambda e=eng: {
                "weights": {
                    "spread_multiplier": e.weights.spread_multiplier,
                    "spread_score_cap": e.weights.spread_score_cap,
                    "liquidity_score_cap": e.weights.liquidity_score_cap,
                    "persistence_max": e.weights.persistence_max,
                },
            },
        )
        logger.info("intelligence: activated engine=route_ranking")
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "intelligence: failed to activate route_ranking: %s", exc)
        registry.register(
            engine_id="route_ranking",
            description="Chain-agnostic route scoring",
            instance=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    # ------------------------------------------------------------------
    # 4. Economics / capital sizing — CapitalSizer
    # ------------------------------------------------------------------
    try:
        eng = CapitalSizer()
        result.economics = eng
        registry.register(
            engine_id="economics",
            description=(
                "Capital sizing under pool / wallet / per-trade constraints"
            ),
            instance=eng,
            dependencies=["intelligence.capital.CapitalSizer"],
            snapshot_fn=lambda e=eng: {
                "limits": {
                    "max_pool_percent": e.limits.max_pool_percent,
                    "max_wallet_percent": e.limits.max_wallet_percent,
                    "max_per_trade_usd": e.limits.max_per_trade_usd,
                },
            },
        )
        logger.info("intelligence: activated engine=economics")
    except Exception as exc:  # noqa: BLE001
        logger.exception("intelligence: failed to activate economics: %s", exc)
        registry.register(
            engine_id="economics",
            description="Capital sizing under pool/wallet/per-trade limits",
            instance=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    # ------------------------------------------------------------------
    # 5. Entity scoring — EntityScorer
    # ------------------------------------------------------------------
    try:
        result._metrics_repo = InMemoryMetricsRepository()
        eng = EntityScorer(metrics_repo=result._metrics_repo)
        result.entity_scoring = eng
        registry.register(
            engine_id="entity_scoring",
            description=(
                "Universal per-entity outcome tracker (win-rate + mean "
                "outcome across wallet / smart-money / venue rows)"
            ),
            instance=eng,
            dependencies=[
                "intel.scorer.EntityScorer",
                "wave1b.inmemory_repos.InMemoryMetricsRepository",
            ],
            snapshot_fn=lambda repo=result._metrics_repo: {
                "wallet_metrics_tracked": len(repo._wallets),
                "signal_metrics_tracked": len(repo._signals),
            },
        )
        logger.info("intelligence: activated engine=entity_scoring")
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            "intelligence: failed to activate entity_scoring: %s", exc)
        registry.register(
            engine_id="entity_scoring",
            description="Universal per-entity outcome tracker",
            instance=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    # ------------------------------------------------------------------
    # 6. Regime detection — HeuristicRegimeClassifier
    # ------------------------------------------------------------------
    try:
        result._outcome_repo = InMemoryOutcomeRepository()
        result._regime_repo = InMemoryRegimeSnapshotRepository()
        eng = HeuristicRegimeClassifier(
            outcome_repo=result._outcome_repo,
            regime_repo=result._regime_repo,
        )
        result.regime = eng
        registry.register(
            engine_id="regime",
            description=(
                "Heuristic market regime classifier (dominant + multi-tag "
                "context)"
            ),
            instance=eng,
            dependencies=[
                "learning.concrete.regime_classifier.HeuristicRegimeClassifier",
                "wave1b.inmemory_repos.InMemoryOutcomeRepository",
                "wave1b.inmemory_repos.InMemoryRegimeSnapshotRepository",
            ],
            snapshot_fn=lambda repo=result._regime_repo, eng=eng: {
                "window_seconds": eng._window_s,
                "min_samples": eng._min_samples,
                "snapshots_persisted": len(repo._rows),
                "latest": (repo._rows[-1].__dict__ if repo._rows else None),
            },
        )
        logger.info("intelligence: activated engine=regime")
    except Exception as exc:  # noqa: BLE001
        logger.exception("intelligence: failed to activate regime: %s", exc)
        registry.register(
            engine_id="regime",
            description="Heuristic market regime classifier",
            instance=None,
            error=f"{type(exc).__name__}: {exc}",
        )

    logger.info(
        "intelligence: activation complete — %d/%d engines active",
        len([e for e in registry.all() if e.active]),
        len(registry.all()),
    )
    return result
