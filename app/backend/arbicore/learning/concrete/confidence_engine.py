"""ArbiCore X — Adaptive Confidence Engine concrete (Phase C Wave 2).

Computes a confidence score in [0, 100] for any CanonicalOpportunity using:
  - base confidence (neutral 50.0)
  - signal contributions (extracted from category_metadata, weighted by
    AdaptiveWeightProvider)
  - route performance bonus (from RouteSuccessTracker)
  - observer-state bonus (placeholder — Wave 2 only confirms availability;
    the algorithm leaves headroom for Wave 3 regime adjustments)

Reversibility invariant (P4): with zero signals, no route history, and no
observer state, the engine returns 50.0 exactly.

Category-agnostic: signals are extracted by looking up known numeric keys in
``KNOWN_CATEGORY_METADATA_KEYS`` per type. No exchange/asset assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ...data.regime_snapshot_repo import RegimeSnapshotRepository
from ...data.state_observer import StateObserverRegistry
from ...models.canonical import CanonicalOpportunity
from ...models.category_metadata import KNOWN_CATEGORY_METADATA_KEYS
from .adaptive_weights import MongoBackedAdaptiveWeights, NEUTRAL_WEIGHT
from .route_success_tracker import MongoRouteSuccessTracker, route_key_for


BASE_CONFIDENCE = 50.0
ROUTE_INFLUENCE_RANGE = 10.0   # max ±10 confidence from route win-rate
SIGNAL_SCALE = 100.0           # category_metadata numeric → signal score_impact normalisation
REGIME_INFLUENCE_RANGE = 5.0   # ±5 confidence from current regime (Wave 3)
MIN_CONFIDENCE = 0.0
MAX_CONFIDENCE = 100.0


# Wave 3: dominant-regime → confidence multiplier (additive points before clamp).
# Reversible — all entries default to 0 unless explicitly tuned.
REGIME_DELTA: Dict[str, float] = {
    "CALM":      +REGIME_INFLUENCE_RANGE * 0.5,
    "TRENDING":  +REGIME_INFLUENCE_RANGE * 0.3,
    "VOLATILE":  -REGIME_INFLUENCE_RANGE * 0.5,
    "ILLIQUID":  -REGIME_INFLUENCE_RANGE,
    "UNKNOWN":    0.0,
}
# Tag-level adjustments — additive on top of dominant.
REGIME_TAG_DELTA: Dict[str, float] = {
    "thin_liquidity":   -2.0,
    "deep_liquidity":   +1.0,
    "high_volatility":  -1.0,
    "low_volatility":   +1.0,
}


# Per-OpportunityType: which category_metadata keys are positive vs negative
# signal contributors. Conservative defaults — easy to extend in Wave 3.
# Sign convention:
#   +1 → higher value increases confidence
#   -1 → higher value decreases confidence (cost / risk indicators)
SIGNAL_DIRECTION_HINTS: Dict[str, Dict[str, int]] = {
    "CEX_ARBITRAGE": {
        "venue_health_score": +1,
        "profitable_buyer_depth_usd": +1,
        "combined_survival_prob": +1,
        "fee_drag_pct": -1,
        "verified_quote_age_s": -1,
    },
    "DEX_ARBITRAGE": {
        "tvl_usd": +1,
        "estimated_slippage_pct": -1,
        "mev_competition_count": -1,
        "snipers_in_pool": -1,
    },
    "FUNDING_ARBITRAGE": {
        "funding_rate_pct": +1,
        "open_interest_usd": +1,
        "perp_index_basis_pct": +1,
    },
    "LAUNCH_ARBITRAGE": {
        "expected_roi_probability": +1,
        "vesting_tge_pct": +1,
    },
    "CROSS_CHAIN_ARBITRAGE": {
        "bridge_latency_s": -1,
        "bridge_fee_usd": -1,
    },
    "FLASH_LOAN_ARBITRAGE": {},  # reserved
}


@dataclass
class ConfidenceBreakdown:
    """Explainable confidence — every contribution recorded."""
    base: float = BASE_CONFIDENCE
    signal_contributions: List[Tuple[str, float, float]] = field(default_factory=list)
    # (signal_id, weight, contribution_delta)
    route_contribution: float = 0.0
    state_observation_available: bool = False
    regime_contribution: float = 0.0
    regime_dominant: Optional[str] = None
    regime_tags: List[str] = field(default_factory=list)
    final: float = BASE_CONFIDENCE

    def to_dict(self) -> Dict[str, Any]:
        return {
            "base": self.base,
            "signal_contributions": [
                {"signal_id": s, "weight": w, "delta": d}
                for s, w, d in self.signal_contributions
            ],
            "route_contribution": self.route_contribution,
            "state_observation_available": self.state_observation_available,
            "regime_contribution": self.regime_contribution,
            "regime_dominant": self.regime_dominant,
            "regime_tags": self.regime_tags,
            "final": self.final,
        }


def _extract_signal_values(opp: CanonicalOpportunity) -> Dict[str, float]:
    """Pull numeric signal candidates from category_metadata. Filters to keys
    known for the opportunity_type (no drift surprises into confidence)."""
    md = opp.category_metadata or {}
    if not md:
        return {}
    known = KNOWN_CATEGORY_METADATA_KEYS.get(opp.opportunity_type, frozenset())
    out: Dict[str, float] = {}
    for k, v in md.items():
        if k not in known:
            continue
        try:
            out[k] = float(v)
        except (TypeError, ValueError):
            continue
    return out


def _normalize(raw_value: float, direction: int) -> float:
    """Map a raw numeric category_metadata value into [-1, 1] using
    direction-aware tanh-scaling. The chosen scale (SIGNAL_SCALE) is
    intentionally conservative — no single signal can swing confidence by
    more than its weighted contribution allows."""
    import math
    bounded = math.tanh(raw_value / SIGNAL_SCALE)
    return bounded * (1 if direction >= 0 else -1)


class AdaptiveConfidenceEngine:
    """Concrete signal-confidence engine — Wave 2.

    Construction:
        engine = AdaptiveConfidenceEngine(weights, route_tracker, observers)

    Inference:
        confidence = await engine.score(opp)
        breakdown  = await engine.score_with_breakdown(opp)
    """

    def __init__(self,
                 weights: MongoBackedAdaptiveWeights,
                 route_tracker: MongoRouteSuccessTracker,
                 observer_registry: StateObserverRegistry,
                 regime_repo: Optional[RegimeSnapshotRepository] = None,
                 signal_unit_strength: float = 5.0):
        self._weights = weights
        self._routes = route_tracker
        self._observers = observer_registry
        self._regimes = regime_repo
        self._signal_unit_strength = float(signal_unit_strength)

    async def score(self, opp: CanonicalOpportunity) -> float:
        bd = await self.score_with_breakdown(opp)
        return bd.final

    async def score_with_breakdown(self,
                                   opp: CanonicalOpportunity,
                                   ) -> ConfidenceBreakdown:
        bd = ConfidenceBreakdown()
        confidence = BASE_CONFIDENCE

        # Make sure the weight cache is fresh enough.
        await self._weights.refresh()

        # ---- Signals
        signals = _extract_signal_values(opp)
        directions = SIGNAL_DIRECTION_HINTS.get(opp.opportunity_type.value, {})
        for sig_id, raw in signals.items():
            direction = directions.get(sig_id, 0)
            if direction == 0:
                continue  # unknown polarity → reversibility invariant; no contribution
            normalised = _normalize(raw, direction)
            weight = self._weights.get_weight(sig_id)
            delta = normalised * self._signal_unit_strength * weight
            confidence += delta
            bd.signal_contributions.append((sig_id, weight, delta))

        # ---- Route
        rk = route_key_for(opp.buy_venue, opp.sell_venue)
        if rk:
            stats = await self._routes.get(rk)
            if stats and stats.trials > 0:
                wr = stats.win_rate
                # tanh-bound shrinkage by trials → small-sample safety.
                import math
                shrinkage = stats.trials / (stats.trials + 20)
                route_delta = (math.tanh((wr - 0.5) * 4 * shrinkage)
                               * ROUTE_INFLUENCE_RANGE)
                confidence += route_delta
                bd.route_contribution = route_delta

        # ---- Observer availability (Wave 2 keeps this a binary flag)
        observer = self._observers.get(opp.opportunity_type)
        from ...data.state_observer import NullStateObserver
        bd.state_observation_available = not isinstance(observer, NullStateObserver)

        # ---- Wave 3: regime contribution (latest snapshot)
        if self._regimes is not None:
            try:
                latest = await self._regimes.latest()
            except Exception:
                latest = None
            if latest is not None:
                regime_delta = REGIME_DELTA.get(latest.dominant_regime, 0.0)
                for tag in (latest.tags or []):
                    regime_delta += REGIME_TAG_DELTA.get(tag, 0.0)
                # Clamp regime contribution to ±REGIME_INFLUENCE_RANGE to keep
                # any single regime from dominating the score.
                regime_delta = max(-REGIME_INFLUENCE_RANGE,
                                   min(REGIME_INFLUENCE_RANGE, regime_delta))
                confidence += regime_delta
                bd.regime_contribution = regime_delta
                bd.regime_dominant = latest.dominant_regime
                bd.regime_tags = list(latest.tags or [])

        # Clamp
        confidence = max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, confidence))
        bd.final = confidence
        return bd
