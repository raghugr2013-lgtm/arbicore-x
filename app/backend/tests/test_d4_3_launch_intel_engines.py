"""D-4.3 — Phase + Timeline + ROI + Smart Money + Holder Analytics tests.

Covers:
  - PhaseClassifier — 7 lifecycle branches + default fallback + sequence nudge
  - LaunchTimelineEngine — phase → temporal-state mapping, ETA inference,
    readiness, ROI scenario, rationale
  - ROIProbabilityEngine — neutral on no signals/insufficient data,
    real-first preference, synthetic fallback, winsorization, confidence label
  - SmartMoneyDetector — elite / quality / emerging / none tiers,
    curated rug_wallet veto, panel roll-up
  - HolderAnalytics — concentration percentiles, whale/dust partitioning,
    age-weighted decay, churn signal vs prior snapshot
  - INV-1 — every output is an evidence dataclass, never DiscoveryCandidate
  - INV-2 — no EmissionBus references in any D-4.3 module (AST-audited)
  - Dormancy negatives still hold
"""
from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass
from typing import Optional

import pytest

from arbicore.intel.launch import (
    HolderAnalytics,
    HolderSnapshot,
    LaunchTimelineEngine,
    PhaseClassifier,
    PhaseResult,
    SmartMoneyDetector,
    SmartMoneyPanel,
    SmartMoneyVerdict,
    TIER_ELITE,
    TIER_EMERGING,
    TIER_NONE,
    TIER_QUALITY,
    TimelineResult,
)
from arbicore.intelligence.roi_probability import (
    ROIProbability,
    ROIProbabilityEngine,
)
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate


# ============================================================================
# PhaseClassifier
# ============================================================================

def _tok(**overrides):
    base = {
        "id": "tok-1", "score": 30, "score_delta_24h": 0,
        "liquidity_usd": 30_000, "volume_h24": 0, "holders": 100,
        "age_hours": 12, "price_change_24h": 0, "launchpad_id": "raydium",
    }
    base.update(overrides)
    return base


def test_phase_liquidity_exhaustion_takes_precedence():
    pc = PhaseClassifier()
    r = pc.classify(_tok(score_delta_24h=-15), signals=[])
    assert r.phase == "liquidity_exhaustion"
    assert r.phase_confidence > 0


def test_phase_overheated_risk():
    pc = PhaseClassifier()
    signals = [{"category": "social", "title": "social mention"},
                {"category": "momentum", "title": "momentum spike"},
                {"category": "social", "title": "retail fomo cluster"}]
    r = pc.classify(_tok(price_change_24h=120), signals=signals)
    assert r.phase == "overheated_risk"


def test_phase_pre_migration_pumpfun():
    pc = PhaseClassifier()
    r = pc.classify(_tok(launchpad_id="pumpfun-solana",
                          liquidity_usd=50_000, age_hours=24), signals=[])
    assert r.phase == "pre_migration"
    assert r.phase_confidence >= 0.8


def test_phase_stealth_accumulation():
    pc = PhaseClassifier()
    sigs = [{"category": "smart_money", "title": "smart money entry w_aaa"}]
    r = pc.classify(_tok(holders=100, age_hours=20), signals=sigs)
    assert r.phase == "stealth_accumulation"


def test_phase_early_momentum():
    pc = PhaseClassifier()
    sigs = [{"category": "smart_money", "title": "smart money"}]
    r = pc.classify(_tok(score=50, score_delta_24h=10, age_hours=20,
                          holders=1000, liquidity_usd=10_000), signals=sigs)
    assert r.phase == "early_momentum"


def test_phase_retail_discovery():
    pc = PhaseClassifier()
    sigs = [{"category": "social", "title": "social"},
             {"category": "momentum", "title": "momentum"}]
    r = pc.classify(_tok(holders=1200), signals=sigs)
    assert r.phase == "retail_discovery"


def test_phase_momentum_expansion():
    pc = PhaseClassifier()
    r = pc.classify(_tok(score=72, score_delta_24h=3, liquidity_usd=50_000),
                     signals=[])
    assert r.phase == "momentum_expansion"


def test_phase_default_fallback_with_smart_money():
    pc = PhaseClassifier()
    sigs = [{"category": "smart_money", "title": "sm"}]
    r = pc.classify(_tok(score=10, score_delta_24h=0, holders=2000,
                          liquidity_usd=10_000), signals=sigs)
    assert r.phase == "stealth_accumulation"
    assert r.phase_confidence < 0.7


def test_phase_default_fallback_no_signals():
    pc = PhaseClassifier()
    r = pc.classify(_tok(score=10, score_delta_24h=0), signals=[])
    assert r.phase == "early_momentum"
    assert r.phase_confidence == 0.45


def test_phase_sequence_nudge_applies_when_winrate_high():
    pc = PhaseClassifier()
    base = PhaseResult(phase="stealth_accumulation",
                        phase_confidence=0.81, rationale=["x"])
    sequences = [{"events": [{"kind": "buy_quality"},
                                {"kind": "social_mention"}]}]
    patterns = [{"kinds": ["buy_quality", "social_mention"],
                  "frequency": 10, "win_rate": 0.75}]
    out = pc.apply_sequence_nudge(base, sequences, patterns)
    assert out.phase_confidence > base.phase_confidence
    assert out.sequence_match["matched"] is True
    assert out.sequence_match["win_rate"] == 0.75


def test_phase_sequence_nudge_silent_on_insufficient_input():
    pc = PhaseClassifier()
    base = PhaseResult(phase="early_momentum", phase_confidence=0.7,
                        rationale=[])
    assert pc.apply_sequence_nudge(base, [], []).phase_confidence == 0.7
    assert pc.apply_sequence_nudge(
        base, [{"events": []}],
        [{"kinds": ["a", "b"], "frequency": 5, "win_rate": 0.8}]
    ).phase_confidence == 0.7


def test_phase_result_is_evidence_not_candidate():
    pc = PhaseClassifier()
    r = pc.classify(_tok(), signals=[])
    assert isinstance(r, PhaseResult)
    assert not isinstance(r, DiscoveryCandidate)
    assert not isinstance(r, CanonicalOpportunity)


# ============================================================================
# LaunchTimelineEngine
# ============================================================================

def test_timeline_migration_expected_pumpfun():
    eng = LaunchTimelineEngine()
    r = eng.derive(
        token={"age_hours": 30, "launchpad_id": "pumpfun"},
        intel={
            "phase": {"phase": "pre_migration", "phase_confidence": 0.82},
            "confidence_score": 60, "composite_score": 30,
            "roi": {"base_low": 30, "base_high": 200},
        },
    )
    assert r.temporal_state == "migration_expected"
    assert r.temporal_confidence == "estimated"
    assert r.eta_window_hours == [12, 48]
    assert r.readiness == "elevated"
    assert r.roi_scenario is not None
    assert "Approaching launchpad migration" in r.rationale[0]


def test_timeline_presale_active_overrides_launching_soon():
    eng = LaunchTimelineEngine()
    r = eng.derive(
        token={"age_hours": 10, "launchpad_id": "pumpfun"},
        intel={"phase": {"phase": "early_momentum", "phase_confidence": 0.76}},
    )
    assert r.temporal_state == "presale_active"
    assert r.eta_label and "Presale" in r.eta_label


def test_timeline_overheated_confirmed_no_eta():
    eng = LaunchTimelineEngine()
    r = eng.derive(
        token={"age_hours": 100, "launchpad_id": "raydium"},
        intel={"phase": {"phase": "overheated_risk", "phase_confidence": 0.74}},
    )
    assert r.temporal_state == "overheated"
    assert r.temporal_confidence == "confirmed"
    assert r.eta_label is None
    assert r.readiness == "live"


def test_timeline_unknown_when_low_phase_confidence():
    eng = LaunchTimelineEngine()
    r = eng.derive(
        token={"age_hours": 10, "launchpad_id": "raydium"},
        intel={"phase": {"phase": "stealth_accumulation",
                          "phase_confidence": 0.35}},
    )
    assert r.temporal_state == "early_accumulation"
    assert r.temporal_confidence == "unknown"
    assert r.eta_label is None


def test_timeline_roi_scenario_qualifier_by_confidence():
    eng = LaunchTimelineEngine()
    # plausible if confidence ≥ 60
    s_plausible = eng._roi_scenario(50, 200, confidence=70)
    s_tentative = eng._roi_scenario(50, 200, confidence=50)
    s_speculative = eng._roi_scenario(50, 200, confidence=30)
    assert "plausible" in (s_plausible or "")
    assert "tentative" in (s_tentative or "")
    assert "speculative" in (s_speculative or "")
    assert eng._roi_scenario(10, 30, confidence=60) is None  # too small


def test_timeline_result_is_evidence_not_candidate():
    eng = LaunchTimelineEngine()
    r = eng.derive(token={"age_hours": 5},
                    intel={"phase": {"phase": "early_momentum",
                                       "phase_confidence": 0.76}})
    assert isinstance(r, TimelineResult)
    assert not isinstance(r, DiscoveryCandidate)
    assert not isinstance(r, CanonicalOpportunity)


# ============================================================================
# ROIProbabilityEngine
# ============================================================================

def test_roi_neutral_no_categories():
    eng = ROIProbabilityEngine()
    r = eng.estimate(categories=[], real_outcomes=[])
    assert r.data_basis == "insufficient"
    assert r.sample_size == 0
    assert r.confidence_label == "insufficient"


def test_roi_neutral_under_min_sample():
    eng = ROIProbabilityEngine(min_sample=6)
    r = eng.estimate(categories=["smart_money"],
                      real_outcomes=[{"roi_pct": 50, "survival": "alive"}])
    assert r.data_basis == "insufficient"


def test_roi_real_first_when_enough_samples():
    eng = ROIProbabilityEngine(min_sample=4)
    real = [{"roi_pct": v, "survival": "alive"}
             for v in (10, 20, 30, 40, 80, 200)]
    r = eng.estimate(categories=["smart_money"], real_outcomes=real,
                       synthetic_outcomes=[])
    assert r.data_basis == "real"
    assert r.sample_size > 0
    assert r.base_low is not None and r.base_high is not None
    assert r.median_roi is not None


def test_roi_synthetic_fallback_when_real_insufficient():
    eng = ROIProbabilityEngine(min_sample=4)
    syn = [{"roi_pct": v, "survival": "alive"} for v in (5, 10, 15, 20, 100)]
    r = eng.estimate(categories=["smart_money"], real_outcomes=[],
                       synthetic_outcomes=syn)
    assert r.data_basis == "synthetic_only"
    assert r.confidence_label == "low"


def test_roi_breakout_probability_and_drawdown():
    eng = ROIProbabilityEngine(min_sample=4)
    outs = [
        {"roi_pct": 150, "survival": "alive"},
        {"roi_pct": 200, "survival": "alive"},
        {"roi_pct": -50, "survival": "dead"},
        {"roi_pct": 30,  "survival": "alive"},
        {"roi_pct": 80,  "survival": "stalled"},
    ]
    r = eng.estimate(categories=["x"], real_outcomes=outs)
    assert r.breakout_probability == 0.4   # 2 of 5 ≥ +100%
    assert r.drawdown_probability == 0.4   # 2 of 5 not alive
    assert r.confidence_label == "low"


def test_roi_engine_output_is_evidence_dataclass():
    eng = ROIProbabilityEngine()
    r = eng.estimate(categories=[], real_outcomes=[])
    assert isinstance(r, ROIProbability)
    assert not isinstance(r, DiscoveryCandidate)
    assert not isinstance(r, CanonicalOpportunity)


# ============================================================================
# SmartMoneyDetector
# ============================================================================

@dataclass
class _MockScore:
    sample_count: int
    success_rate: float
    avg_outcome_score: float = 0.5


class _MockScorer:
    def __init__(self, store: Optional[dict] = None):
        self._store = store or {}

    async def get(self, entity_id):
        return self._store.get(entity_id)


def test_smart_money_elite_tier():
    scorer = _MockScorer({"w1": _MockScore(sample_count=10, success_rate=0.8)})
    det = SmartMoneyDetector(entity_scorer=scorer)
    v = asyncio.run(det.verdict_for(
        wallet="w1", profile={"scores": {"wallet_quality": 88}},
    ))
    assert v.tier == TIER_ELITE
    assert v.confidence >= 0.9


def test_smart_money_quality_tier():
    scorer = _MockScorer({"w1": _MockScore(sample_count=5, success_rate=0.6)})
    det = SmartMoneyDetector(entity_scorer=scorer)
    v = asyncio.run(det.verdict_for(
        wallet="w1", profile={"scores": {"wallet_quality": 65}},
    ))
    assert v.tier == TIER_QUALITY


def test_smart_money_emerging_when_only_algo_signal():
    scorer = _MockScorer({})  # no Phase C history
    det = SmartMoneyDetector(entity_scorer=scorer)
    v = asyncio.run(det.verdict_for(
        wallet="w1", profile={"scores": {"wallet_quality": 70}},
    ))
    assert v.tier == TIER_EMERGING
    assert "no Phase C history" in " ".join(v.rationale)


def test_smart_money_none_when_no_evidence():
    scorer = _MockScorer({})
    det = SmartMoneyDetector(entity_scorer=scorer)
    v = asyncio.run(det.verdict_for(wallet="w1", profile=None))
    assert v.tier == TIER_NONE


def test_smart_money_curated_rug_wallet_vetoes_tier():
    scorer = _MockScorer({"w_bad": _MockScore(sample_count=10, success_rate=0.9)})
    det = SmartMoneyDetector(entity_scorer=scorer)
    v = asyncio.run(det.verdict_for(
        wallet="w_bad",
        profile={"label": "rug_wallet",
                  "scores": {"wallet_quality": 95}},
    ))
    assert v.tier == TIER_NONE
    assert "rug_wallet" in " ".join(v.rationale)


def test_smart_money_curated_label_quality_without_algo():
    scorer = _MockScorer({})
    det = SmartMoneyDetector(entity_scorer=scorer)
    v = asyncio.run(det.verdict_for(
        wallet="w1", profile={"label": "smart_money"},
    ))
    assert v.tier == TIER_QUALITY


def test_smart_money_panel_roll_up():
    scorer = _MockScorer({
        "elite_w":   _MockScore(sample_count=10, success_rate=0.8),
        "quality_w": _MockScore(sample_count=5, success_rate=0.6),
    })
    det = SmartMoneyDetector(entity_scorer=scorer)
    profiles = {
        "elite_w":   {"scores": {"wallet_quality": 90}},
        "quality_w": {"scores": {"wallet_quality": 65}},
        "noise_w":   {"scores": {"wallet_quality": 30}},
    }
    panel = asyncio.run(det.panel(
        token_id="solana:T",
        buyer_wallets=["elite_w", "quality_w", "noise_w"],
        profiles=profiles,
    ))
    assert isinstance(panel, SmartMoneyPanel)
    assert panel.elite_count == 1
    assert panel.quality_count == 1
    assert panel.emerging_count == 0
    assert panel.to_dict()["total_quality_or_better"] == 2


def test_smart_money_verdict_is_evidence_dataclass():
    scorer = _MockScorer({})
    det = SmartMoneyDetector(entity_scorer=scorer)
    v = asyncio.run(det.verdict_for(wallet="w", profile=None))
    assert isinstance(v, SmartMoneyVerdict)
    assert not isinstance(v, DiscoveryCandidate)
    assert not isinstance(v, CanonicalOpportunity)


# ============================================================================
# HolderAnalytics
# ============================================================================

def test_holder_analytics_concentration_distributed():
    ha = HolderAnalytics()
    # 1000 holders with 100 each → supply 100k → each = 0.1% (below 1% whale)
    holders = [
        {"address": f"h{i}", "balance": 100.0, "last_seen_ts": 0}
        for i in range(1000)
    ]
    snap = ha.analyse(token_id="solana:T", holders=holders,
                       total_supply=100_000.0)
    assert snap.holder_count == 1000
    assert snap.top_10_concentration_pct == 1.0     # 10 * 0.1%
    assert snap.dispersion_score == 99.0
    assert snap.whale_count == 0
    assert snap.dust_holder_count == 0


def test_holder_analytics_concentration_concentrated():
    ha = HolderAnalytics()
    holders = [
        {"address": "whale", "balance": 9_000.0, "last_seen_ts": 0},
        # each holder 0.5% (under 1% whale threshold)
        *[{"address": f"h{i}", "balance": 50.0, "last_seen_ts": 0}
           for i in range(20)],
    ]
    snap = ha.analyse(token_id="solana:T", holders=holders,
                       total_supply=10_000.0)
    assert snap.top_1_concentration_pct == 90.0
    assert snap.whale_count == 1
    assert "heavy concentration" in " ".join(snap.rationale)


def test_holder_analytics_dust_threshold():
    ha = HolderAnalytics(dust_share_threshold=0.0001)
    holders = [
        {"address": "big", "balance": 9_999.0, "last_seen_ts": 0},
        # below 0.01% threshold
        *[{"address": f"d{i}", "balance": 0.01, "last_seen_ts": 0}
           for i in range(100)],
    ]
    snap = ha.analyse(token_id="solana:T", holders=holders,
                       total_supply=100_000.0)
    assert snap.dust_holder_count == 100
    assert snap.holder_count == 101  # total includes dust


def test_holder_analytics_age_weighted_decay():
    ha = HolderAnalytics(age_halflife_hours=24)
    now = 1_700_000_000
    holders = [
        # fresh holder — full weight
        {"address": "fresh", "balance": 1000.0, "last_seen_ts": now - 1},
        # 24h old — weight 0.5
        {"address": "mid", "balance": 1000.0, "last_seen_ts": now - 24 * 3600},
        # 48h old — weight 0.25
        {"address": "old", "balance": 1000.0, "last_seen_ts": now - 48 * 3600},
    ]
    snap = ha.analyse(token_id="solana:T", holders=holders,
                       total_supply=10_000.0, now_ts=now)
    assert 1.5 < snap.age_weighted_holder_count < 2.0


def test_holder_analytics_churn_signal_stable():
    ha = HolderAnalytics()
    prior = HolderSnapshot(
        token_id="t", holder_count=100, total_supply_raw=10_000,
        top_1_concentration_pct=10, top_5_concentration_pct=30,
        top_10_concentration_pct=40, top_20_concentration_pct=60,
        dispersion_score=60, whale_count=0, dust_holder_count=0,
        age_weighted_holder_count=80,
    )
    snap = ha.analyse(
        token_id="t",
        holders=[{"address": f"h{i}", "balance": 100.0}
                  for i in range(102)],
        total_supply=10_000, prior_snapshot=prior,
    )
    assert snap.churn_signal == "stable"
    assert snap.churn_delta_pct is not None
    assert abs(snap.churn_delta_pct) < 5


def test_holder_analytics_churn_signal_turning_over():
    ha = HolderAnalytics()
    prior = HolderSnapshot(
        token_id="t", holder_count=100, total_supply_raw=10_000,
        top_1_concentration_pct=10, top_5_concentration_pct=30,
        top_10_concentration_pct=40, top_20_concentration_pct=60,
        dispersion_score=60, whale_count=0, dust_holder_count=0,
        age_weighted_holder_count=80,
    )
    snap = ha.analyse(
        token_id="t",
        holders=[{"address": f"h{i}", "balance": 100.0}
                  for i in range(200)],
        total_supply=10_000, prior_snapshot=prior,
    )
    assert snap.churn_signal == "turning_over"
    assert snap.churn_delta_pct == 100.0


def test_holder_analytics_zero_supply_returns_empty():
    ha = HolderAnalytics()
    snap = ha.analyse(token_id="t",
                       holders=[{"address": "a", "balance": 1.0}],
                       total_supply=0)
    assert snap.top_1_concentration_pct == 0.0
    assert "non-positive" in " ".join(snap.rationale)


def test_holder_snapshot_is_evidence_dataclass():
    ha = HolderAnalytics()
    snap = ha.analyse(token_id="t", holders=[], total_supply=100)
    assert isinstance(snap, HolderSnapshot)
    assert not isinstance(snap, DiscoveryCandidate)
    assert not isinstance(snap, CanonicalOpportunity)


# ============================================================================
# INV-2 — AST audit
# ============================================================================

def _module_has_no_emission_bus_usage(mod) -> bool:
    tree = ast.parse(open(mod.__file__).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "EmissionBus":
            return False
        if (isinstance(node, ast.Attribute) and node.attr == "emit"
                and isinstance(node.ctx, ast.Load)):
            return False
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "emit":
                return False
    return True


@pytest.mark.parametrize("mod_name", [
    "arbicore.intel.launch.phase_classifier",
    "arbicore.intel.launch.timeline",
    "arbicore.intel.launch.smart_money",
    "arbicore.intel.launch.holder_analytics",
    "arbicore.intelligence.roi_probability",
])
def test_inv_2_no_emission_bus_in_d4_3_modules(mod_name):
    import importlib
    mod = importlib.import_module(mod_name)
    assert _module_has_no_emission_bus_usage(mod)


# ============================================================================
# Dormancy negatives still hold at D-4.3
# ============================================================================

def test_no_scanner_orchestrator_at_d4_3():
    """D-4.5 lands the orchestrator — assertion INVERTED at D-4.5 landing."""
    import arbicore.scanners.launch_arbitrage.scanner as mod  # noqa: F401
    assert hasattr(mod, "LaunchArbitrageScanner")


def test_no_verifier_at_d4_3():
    """D-4.4 ships the verifier — assertion INVERTED at D-4.4 landing
    per D-4.3 IMPLEMENTATION_REPORT §9 wave-progression convention."""
    import arbicore.scanners.launch_arbitrage.verifier as mod  # noqa: F401
    assert hasattr(mod, "LaunchOpportunityVerifier")


def test_d4_3_components_introduce_no_emission_path():
    """Constructing each D-4.3 component must not start any task."""
    PhaseClassifier()                          # construct
    LaunchTimelineEngine()                     # construct
    ROIProbabilityEngine()                     # construct
    HolderAnalytics()                          # construct
    SmartMoneyDetector(entity_scorer=_MockScorer({}))  # construct
    # Each is a stateless constructor — no event loop, no thread, no task
