"""SmartMoneyDetector — Phase C Wave 4 EntityScorer + D-4.2 WalletScorer.

REBUILD FRESH (no legacy equivalent). Per the D-4 Authorization Package
§2.2 Wave D-4.3 (Phase + Timeline + ROI + Smart Money + Holder Analytics),
this detector is the bridge between:

  - **Phase C Wave 4** ``EntityScorer`` — historical success_rate and
    avg_outcome_score per wallet entity (provenance-gated learning data).
  - **D-4.2** ``WalletProfile.scores["wallet_quality"]`` — algorithmic
    4-factor wallet quality from real activity.

It produces a deterministic *smart-money tier* (`elite`, `quality`,
`emerging`, `none`) and a smart-money panel summarising how many
wallets in each tier touched a token in the observation window.

Discipline:
  - INV-1 — output is intelligence ONLY (never DiscoveryCandidate /
    Canonical).
  - INV-2 — no EmissionBus references.
  - Pure compute layered on top of read-only `EntityScorer.get(...)`.
  - Reuses the existing universal substrate; introduces ZERO new
    collections or new emit paths.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol


# ============================================================================
# Tier definitions
# ============================================================================

TIER_ELITE = "elite"
TIER_QUALITY = "quality"
TIER_EMERGING = "emerging"
TIER_NONE = "none"

TIER_ORDER = (TIER_ELITE, TIER_QUALITY, TIER_EMERGING, TIER_NONE)


# ============================================================================
# EntityScorer protocol (Phase C Wave 4 surface — minimal)
# ============================================================================

class EntityScorerLike(Protocol):
    """Minimal async surface the detector needs from Phase C Wave 4."""

    async def get(self, entity_id: str) -> Optional[Any]:
        ...


# ============================================================================
# Output types
# ============================================================================

@dataclass
class SmartMoneyVerdict:
    """Per-wallet verdict — evidence-only."""

    wallet: str
    tier: str                              # elite | quality | emerging | none
    historical_success_rate: Optional[float]   # 0..1 (None if no Phase C data)
    historical_sample_size: int
    algo_quality: Optional[float]          # 0..100 (from D-4.2 WalletScorer)
    curated_label: Optional[str]
    confidence: float                      # 0..1
    rationale: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "wallet": self.wallet,
            "tier": self.tier,
            "historical_success_rate": self.historical_success_rate,
            "historical_sample_size": self.historical_sample_size,
            "algo_quality": self.algo_quality,
            "curated_label": self.curated_label,
            "confidence": round(self.confidence, 3),
            "rationale": list(self.rationale),
        }


@dataclass
class SmartMoneyPanel:
    """Per-token roll-up of smart-money verdicts. Evidence-only."""

    token_id: str
    verdicts: List[SmartMoneyVerdict] = field(default_factory=list)
    elite_count: int = 0
    quality_count: int = 0
    emerging_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_id": self.token_id,
            "elite_count": self.elite_count,
            "quality_count": self.quality_count,
            "emerging_count": self.emerging_count,
            "total_quality_or_better": self.elite_count + self.quality_count,
            "verdicts": [v.to_dict() for v in self.verdicts],
        }


# ============================================================================
# Detector
# ============================================================================

class SmartMoneyDetector:
    """Combines Phase C Wave 4 entity outcomes with D-4.2 algorithmic quality.

    The tiering is deliberately conservative — `elite` requires BOTH a
    strong historical track record AND a strong algorithmic quality score.
    `none` is the default for under-evidenced wallets.

    Thresholds are constructor-injected so operators can re-tune from
    `scanner_config.launch_arb.smart_money_tiering` once shadow rollout
    data accumulates.
    """

    def __init__(self,
                 *,
                 entity_scorer: EntityScorerLike,
                 elite_min_success_rate: float = 0.70,
                 elite_min_sample_size: int = 8,
                 elite_min_algo_quality: float = 75.0,
                 quality_min_success_rate: float = 0.55,
                 quality_min_sample_size: int = 4,
                 quality_min_algo_quality: float = 60.0,
                 emerging_min_algo_quality: float = 55.0,
                 emerging_min_sample_size: int = 0,
                 ) -> None:
        self._scorer = entity_scorer
        self.t_elite_sr = elite_min_success_rate
        self.t_elite_n = elite_min_sample_size
        self.t_elite_q = elite_min_algo_quality
        self.t_quality_sr = quality_min_success_rate
        self.t_quality_n = quality_min_sample_size
        self.t_quality_q = quality_min_algo_quality
        self.t_emerging_q = emerging_min_algo_quality
        self.t_emerging_n = emerging_min_sample_size

    # ------------------------------------------------------------ public

    async def verdict_for(self, *,
                           wallet: str,
                           profile: Optional[Dict[str, Any]] = None,
                           ) -> SmartMoneyVerdict:
        """Compute the tier for a single wallet.

        ``profile`` is the D-4.2 WalletProfile dict (carrying
        ``scores["wallet_quality"]`` and ``label``). When omitted the
        detector falls back to Phase C Wave 4 entity history only.
        """
        algo_q = None
        curated_label = None
        if profile:
            algo_q = (profile.get("scores") or {}).get("wallet_quality")
            curated_label = profile.get("label")

        es = await self._scorer.get(wallet)
        sr = float(es.success_rate) if es is not None else None
        sample = int(es.sample_count) if es is not None else 0

        tier, rationale, conf = self._tier(
            sr=sr, sample=sample, algo_q=algo_q, curated_label=curated_label,
        )
        return SmartMoneyVerdict(
            wallet=wallet,
            tier=tier,
            historical_success_rate=sr,
            historical_sample_size=sample,
            algo_quality=algo_q,
            curated_label=curated_label,
            confidence=conf,
            rationale=rationale,
        )

    async def panel(self,
                     token_id: str,
                     buyer_wallets: List[str],
                     profiles: Optional[Dict[str, Dict[str, Any]]] = None,
                     ) -> SmartMoneyPanel:
        """Per-token roll-up. ``profiles`` is `{wallet -> profile_dict}`."""
        profiles = profiles or {}
        verdicts: List[SmartMoneyVerdict] = []
        for w in buyer_wallets:
            v = await self.verdict_for(wallet=w, profile=profiles.get(w))
            verdicts.append(v)
        panel = SmartMoneyPanel(token_id=token_id, verdicts=verdicts)
        for v in verdicts:
            if v.tier == TIER_ELITE:
                panel.elite_count += 1
            elif v.tier == TIER_QUALITY:
                panel.quality_count += 1
            elif v.tier == TIER_EMERGING:
                panel.emerging_count += 1
        return panel

    # ------------------------------------------------------------ internal

    def _tier(self, *,
               sr: Optional[float],
               sample: int,
               algo_q: Optional[float],
               curated_label: Optional[str],
               ) -> tuple:
        rationale: List[str] = []
        # Hard veto — curated rug_wallet → never smart money
        if curated_label == "rug_wallet":
            rationale.append("curated_label=rug_wallet — advisory veto")
            return TIER_NONE, rationale, 0.95
        # Elite — strong on both axes
        if (sr is not None and sample >= self.t_elite_n
                and sr >= self.t_elite_sr
                and algo_q is not None and algo_q >= self.t_elite_q):
            rationale.append(
                f"historical {sr:.0%} on n={sample} ≥ thresholds"
            )
            rationale.append(f"algo quality {algo_q:.0f} ≥ {self.t_elite_q:.0f}")
            return TIER_ELITE, rationale, 0.92
        # Quality — solid on both
        if (sr is not None and sample >= self.t_quality_n
                and sr >= self.t_quality_sr
                and algo_q is not None and algo_q >= self.t_quality_q):
            rationale.append(
                f"historical {sr:.0%} on n={sample}"
            )
            rationale.append(f"algo quality {algo_q:.0f}")
            return TIER_QUALITY, rationale, 0.78
        # Emerging — only algorithmic evidence (no/limited Phase C history)
        if (algo_q is not None and algo_q >= self.t_emerging_q
                and sample >= self.t_emerging_n):
            rationale.append(
                f"algo quality {algo_q:.0f} ≥ {self.t_emerging_q:.0f}"
            )
            if sample > 0:
                rationale.append(f"sparse history (n={sample})")
            else:
                rationale.append("no Phase C history yet")
            return TIER_EMERGING, rationale, 0.55
        # Quality boost via curated label even without algo score
        if curated_label in ("smart_money", "whale", "influencer"):
            rationale.append(f"curated_label={curated_label}")
            return TIER_QUALITY, rationale, 0.62
        # Default
        if algo_q is None and sample == 0:
            rationale.append("no evidence")
        elif algo_q is not None:
            rationale.append(f"algo quality {algo_q:.0f} below thresholds")
        else:
            rationale.append(f"history n={sample}, no algo quality")
        return TIER_NONE, rationale, 0.50
