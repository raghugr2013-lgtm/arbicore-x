"""D-4.4 — Launch Verifier + Economics + Gates tests.

Covers:
  - LaunchEconomicsAssessor (legs, gas drag, ROI integration, metadata projection)
  - LaunchGate1Filter (pass / each of 6 failure modes / per-launchpad override)
  - LaunchGate6RugRiskFilter (pass / each of 4 failure modes / config off-switches)
  - LaunchOpportunityVerifier
      - confirms canonical when all gates pass
      - denied when venue_provider returns None / raises
      - denied by Gate 1 (composite too low)
      - denied by Gate 6 (rug-risk)
      - INV-1 — output is CanonicalOpportunity built fresh via universal substrate
      - INV-2 — verifier module has no EmissionBus references
      - INV-3 — source_data_quality derived from leg source_id (helius_token_rpc)
      - category_metadata folds D-4.3 outputs into D-4.0 vocabulary keys only
  - Dormancy: launch_arb still disabled; no orchestrator yet (D-4.5)
"""
from __future__ import annotations

import ast
import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest

from arbicore.intel.launch.holder_analytics import HolderAnalytics
from arbicore.intel.launch.phase_classifier import PhaseClassifier
from arbicore.intel.launch.smart_money import SmartMoneyDetector
from arbicore.intel.launch.timeline import LaunchTimelineEngine
from arbicore.intelligence.roi_probability import ROIProbabilityEngine
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.category_metadata import KNOWN_CATEGORY_METADATA_KEYS
from arbicore.models.discovery import DiscoveryCandidate, make_candidate_id
from arbicore.models.enums import DataProvenance, OpportunityType
from arbicore.scanners.launch_arbitrage import (
    LaunchEconomicsAssessor,
    LaunchGate1Filter,
    LaunchGate6RugRiskFilter,
    LaunchOpportunityVerifier,
)


# ============================================================================
# Fixtures
# ============================================================================

@dataclass
class _MockScore:
    sample_count: int
    success_rate: float
    avg_outcome_score: float = 0.5


class _MockScorer:
    def __init__(self, store=None):
        self._store = store or {}

    async def get(self, entity_id):
        return self._store.get(entity_id)


def _make_assessor(min_sample: int = 4):
    return LaunchEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=min_sample),
        default_notional_usd=250.0,
    )


def _make_verifier(*, venue_provider,
                    gate_1_thresholds=None, gate_6_cfg=None,
                    scorer_store=None):
    gate_1 = LaunchGate1Filter(
        thresholds=gate_1_thresholds or {
            "min_composite_launch_score": 25.0,
            "min_bonding_curve_progress_pct": 0.0,
            "min_holders": 10,
            "min_smart_money_entries": 0,
            "max_holder_concentration_top10_pct": 80.0,
            "min_confidence": 0.0,
        },
        per_launchpad={"pumpfun": {"min_bonding_curve_progress_pct": 5.0}},
    )
    gate_6 = LaunchGate6RugRiskFilter(gate_6_cfg or {
        "require_mint_authority_revoked": True,
        "require_freeze_authority_revoked": True,
        "min_lp_burned_or_locked_pct": 80.0,
        "max_holder_concentration_top10_pct": 60.0,
    })
    return LaunchOpportunityVerifier(
        venue_provider=venue_provider,
        phase_classifier=PhaseClassifier(),
        timeline_engine=LaunchTimelineEngine(),
        smart_money_detector=SmartMoneyDetector(
            entity_scorer=_MockScorer(scorer_store or {})),
        holder_analytics=HolderAnalytics(),
        economics_assessor=_make_assessor(),
        gate_1=gate_1, gate_6=gate_6,
    )


def _candidate() -> DiscoveryCandidate:
    return DiscoveryCandidate(
        candidate_id=make_candidate_id(
            hint_source="launch_intel:smart_money_entry",
            opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
            subject_id="solana:MintXYZ", asset="BONK",
            candidate_venues=["pumpfun:solana"],
            hint_observed_at=1_700_000_000.0,
        ),
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source="launch_intel:smart_money_entry",
        hint_observed_at=1_700_000_000.0,
        subject_id="solana:MintXYZ",
        asset="BONK",
        candidate_venues=["pumpfun:solana"],
        hint_metric={"wallet": "w_smart"},
        reason="smart-money entry observed",
    )


def _venue_facts(**overrides) -> Dict[str, Any]:
    """A green-path facts payload — every gate will pass by default."""
    facts: Dict[str, Any] = {
        "primary_venue_id": "pumpfun:solana:MintXYZ",
        "secondary_venue_id": "raydium:solana:PoolXYZ",
        "chain": "solana",
        "source_id": "helius_token_rpc",
        "listing_price_usd": 0.000_05,
        "liquidity_usd": 50_000.0,
        "primary_fee_bps": 30,
        "secondary_fee_bps": 30,
        "slippage_primary_pct": 0.5,
        "slippage_secondary_pct": 0.5,
        "mint_authority_revoked": True,
        "freeze_authority_revoked": True,
        "lp_burned_or_locked_pct": 95.0,
        "total_supply": 1_000_000_000.0,
        "holders": [{"address": f"h{i}", "balance": 1_000.0,
                      "last_seen_ts": 1_700_000_000 - 600}
                     for i in range(200)],
        "launchpad": "pumpfun",
        "age_hours": 4.0,
        "bonding_curve_progress_pct": 60.0,
        "buyer_wallets": ["w_smart", "w_other"],
        "wallet_profiles": {
            "w_smart": {"label": "smart_money",
                         "scores": {"wallet_quality": 90}},
            "w_other": {"scores": {"wallet_quality": 35}},
        },
        "signal_categories": ["smart_money"],
        "real_outcomes": [
            {"roi_pct": v, "survival": "alive"}
            for v in (40, 60, 80, 120, 150, 220)
        ],
        "synthetic_outcomes": [],
        "token_intel": {"id": "solana:MintXYZ", "score": 65,
                          "score_delta_24h": 8, "liquidity_usd": 50_000,
                          "holders": 200, "age_hours": 4,
                          "launchpad_id": "pumpfun", "price_change_24h": 20},
        "signals": [{"category": "smart_money",
                      "title": "smart money entry w_smart"}],
        "composite_score": 70.0,
        "confidence_score": 70.0,
        "token_address": "MintXYZ",
    }
    facts.update(overrides)
    return facts


def _provider(facts: Optional[Dict[str, Any]] = None,
               *, raise_exc: bool = False):
    async def _p(candidate):
        if raise_exc:
            raise RuntimeError("upstream down")
        return facts
    return _p


# ============================================================================
# LaunchGate1Filter
# ============================================================================

def test_gate_1_passes_with_defaults():
    g = LaunchGate1Filter({
        "min_composite_launch_score": 25.0,
        "min_bonding_curve_progress_pct": 0.0,
        "min_holders": 10,
        "min_smart_money_entries": 0,
        "max_holder_concentration_top10_pct": 80.0,
        "min_confidence": 0.0,
    })
    r = g.evaluate(composite_launch_score=60, bonding_curve_progress_pct=10,
                    holder_count=200, smart_money_entry_count=2,
                    holder_concentration_top10_pct=20, confidence_score=70)
    assert r.passed is True
    assert r.gate_id == "gate_1_launch_composite"


def test_gate_1_fails_composite_below_threshold():
    g = LaunchGate1Filter({"min_composite_launch_score": 55.0})
    r = g.evaluate(composite_launch_score=20, bonding_curve_progress_pct=10,
                    holder_count=100, smart_money_entry_count=2,
                    holder_concentration_top10_pct=20, confidence_score=70)
    assert r.passed is False
    assert "composite" in r.reason


def test_gate_1_per_launchpad_override():
    g = LaunchGate1Filter(
        thresholds={"min_bonding_curve_progress_pct": 1.0},
        per_launchpad={"pumpfun": {"min_bonding_curve_progress_pct": 10.0}},
    )
    # Without launchpad: passes
    r1 = g.evaluate(composite_launch_score=99, bonding_curve_progress_pct=5,
                     holder_count=999, smart_money_entry_count=99,
                     holder_concentration_top10_pct=5, confidence_score=99)
    assert r1.passed
    # With launchpad="pumpfun": stricter override fails
    r2 = g.evaluate(composite_launch_score=99, bonding_curve_progress_pct=5,
                     holder_count=999, smart_money_entry_count=99,
                     holder_concentration_top10_pct=5, confidence_score=99,
                     launchpad="pumpfun")
    assert not r2.passed
    assert "bonding-curve" in r2.reason


# ============================================================================
# LaunchGate6RugRiskFilter
# ============================================================================

def test_gate_6_passes_when_clean():
    g = LaunchGate6RugRiskFilter({})
    r = g.evaluate(mint_authority_revoked=True,
                    freeze_authority_revoked=True,
                    lp_burned_or_locked_pct=95,
                    holder_concentration_top10_pct=20)
    assert r.passed


@pytest.mark.parametrize("missing", [
    "mint_authority_revoked", "freeze_authority_revoked",
])
def test_gate_6_fails_when_authority_not_revoked(missing):
    g = LaunchGate6RugRiskFilter({})
    kwargs = {"mint_authority_revoked": True,
              "freeze_authority_revoked": True,
              "lp_burned_or_locked_pct": 95,
              "holder_concentration_top10_pct": 20,
              missing: False}
    r = g.evaluate(**kwargs)
    assert not r.passed
    assert "NOT revoked" in r.reason


def test_gate_6_fails_lp_below_threshold():
    g = LaunchGate6RugRiskFilter({"min_lp_burned_or_locked_pct": 80.0})
    r = g.evaluate(mint_authority_revoked=True,
                    freeze_authority_revoked=True,
                    lp_burned_or_locked_pct=50,
                    holder_concentration_top10_pct=20)
    assert not r.passed
    assert "LP burn/lock" in r.reason


def test_gate_6_fails_concentration_too_high():
    g = LaunchGate6RugRiskFilter({"max_holder_concentration_top10_pct": 50.0})
    r = g.evaluate(mint_authority_revoked=True,
                    freeze_authority_revoked=True,
                    lp_burned_or_locked_pct=95,
                    holder_concentration_top10_pct=70)
    assert not r.passed
    assert "concentration" in r.reason


def test_gate_6_can_disable_authority_requirements():
    g = LaunchGate6RugRiskFilter({
        "require_mint_authority_revoked": False,
        "require_freeze_authority_revoked": False,
    })
    r = g.evaluate(mint_authority_revoked=False,
                    freeze_authority_revoked=False,
                    lp_burned_or_locked_pct=95,
                    holder_concentration_top10_pct=20)
    assert r.passed


# ============================================================================
# LaunchEconomicsAssessor
# ============================================================================

def test_economics_assessor_computes_gas_drag():
    a = _make_assessor(min_sample=4)
    r = a.assess(
        chain="solana",
        primary_venue_id="pumpfun:solana:m",
        secondary_venue_id="raydium:solana:p",
        listing_price_usd=0.0001,
        primary_fee_bps=30, secondary_fee_bps=30,
        slippage_primary_pct=0.5, slippage_secondary_pct=0.5,
        signal_categories=["smart_money"],
        real_outcomes=[{"roi_pct": v, "survival": "alive"}
                         for v in (40, 60, 80, 120, 150, 220)],
        notional_usd=250.0,
    )
    # Solana per-leg gas is $0.005 ($0.01 total) → drag = 0.004%
    assert 0.0 < r.economics.gas_drag_pct < 0.01
    # Fees 60 bps + slippage 1% → total cost ~1.6%
    assert r.economics.total_fee_pct == 0.6
    assert r.economics.total_slippage_pct == 1.0
    assert r.roi.data_basis == "real"
    assert r.roi.base_low is not None


def test_economics_assessor_metadata_projection_keys_subset():
    a = _make_assessor(min_sample=4)
    r = a.assess(
        chain="solana",
        primary_venue_id="x", secondary_venue_id="y",
        listing_price_usd=0.01, primary_fee_bps=30, secondary_fee_bps=30,
        slippage_primary_pct=0.5, slippage_secondary_pct=0.5,
        signal_categories=["smart_money"],
        real_outcomes=[{"roi_pct": 50, "survival": "alive"}] * 6,
        holder_count=100, bonding_curve_progress_pct=40.0,
    )
    meta = r.to_metadata()
    # Every key projected must be in the D-4.0 vocabulary
    allowed = KNOWN_CATEGORY_METADATA_KEYS[OpportunityType.LAUNCH_ARBITRAGE]
    for k in meta.keys():
        assert k in allowed, f"unknown vocab key projected: {k}"


# ============================================================================
# LaunchOpportunityVerifier — happy path
# ============================================================================

def test_verifier_confirms_canonical_on_happy_path():
    facts = _venue_facts()
    v = _make_verifier(
        venue_provider=_provider(facts),
        scorer_store={"w_smart": _MockScore(sample_count=10,
                                              success_rate=0.8)},
    )
    canonical, outcome = asyncio.run(v.verify(_candidate()))
    assert outcome.startswith("confirmed_canonical:")
    assert isinstance(canonical, CanonicalOpportunity)
    assert canonical.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE
    assert canonical.subject_id == "solana:MintXYZ"
    # INV-3: source_data_quality derives from helius_token_rpc → REAL
    assert canonical.source_data_quality == DataProvenance.REAL
    # category_metadata folded
    cm = canonical.category_metadata
    assert cm["launch_phase"] in (
        "stealth_accumulation", "early_momentum", "pre_migration",
        "retail_discovery", "momentum_expansion",
    )
    assert "phase_confidence" in cm
    assert cm["mint_authority_revoked"] is True
    assert cm["freeze_authority_revoked"] is True
    assert cm["lp_burned_pct"] == 95.0
    assert cm["chain"] == "solana"
    assert cm["launchpad"] == "pumpfun"
    assert "smart_money_entry_count" in cm
    assert "holder_concentration_top10_pct" in cm
    # composite present in canonical metadata
    assert "composite_launch_score" in canonical.metadata
    # leg_count == 2 (primary + secondary)
    assert canonical.metadata["leg_count"] == 2
    # discovery candidate fingerprint preserved
    assert canonical.metadata["discovery_candidate_id"] != ""
    assert canonical.metadata["discovery_source"] == "launch_intel:smart_money_entry"


def test_verifier_category_metadata_uses_only_vocabulary_keys():
    facts = _venue_facts()
    v = _make_verifier(venue_provider=_provider(facts),
                        scorer_store={"w_smart": _MockScore(10, 0.8)})
    canonical, _ = asyncio.run(v.verify(_candidate()))
    allowed = KNOWN_CATEGORY_METADATA_KEYS[OpportunityType.LAUNCH_ARBITRAGE]
    for k in canonical.category_metadata.keys():
        assert k in allowed, f"verifier emitted unknown vocab key: {k}"


# ============================================================================
# Verifier — denied paths
# ============================================================================

def test_verifier_denies_when_venue_unreadable():
    v = _make_verifier(venue_provider=_provider(None))
    canonical, outcome = asyncio.run(v.verify(_candidate()))
    assert canonical is None
    # VerifiedOutcome.DENIED_VENUE_UNREADABLE — locked Spec §6.1 vocabulary
    assert outcome == "denied:venue_unreadable"


def test_verifier_denies_when_provider_raises():
    v = _make_verifier(venue_provider=_provider(raise_exc=True))
    canonical, outcome = asyncio.run(v.verify(_candidate()))
    assert canonical is None
    # VerifiedOutcome.DENIED_VENUE_UNREADABLE + ":<ExceptionType>" suffix
    assert outcome.startswith("denied:venue_unreadable")
    assert "RuntimeError" in outcome


def test_verifier_denies_at_gate_1_composite_too_low():
    facts = _venue_facts(
        composite_score=10.0,
        signal_categories=[],
        real_outcomes=[],
        synthetic_outcomes=[],
        token_intel={"id": "x", "score": 0, "score_delta_24h": 0,
                      "liquidity_usd": 1_000, "holders": 5,
                      "age_hours": 5, "launchpad_id": "pumpfun"},
        signals=[],
        wallet_profiles={},
        buyer_wallets=[],
        holders=[{"address": "h1", "balance": 1, "last_seen_ts": 0}],
        bonding_curve_progress_pct=0.5,
    )
    v = _make_verifier(
        venue_provider=_provider(facts),
        gate_1_thresholds={
            "min_composite_launch_score": 60.0,
            "min_bonding_curve_progress_pct": 0.0,
            "min_holders": 0,
            "min_smart_money_entries": 0,
            "max_holder_concentration_top10_pct": 100.0,
            "min_confidence": 0.0,
        },
    )
    canonical, outcome = asyncio.run(v.verify(_candidate()))
    assert canonical is None
    # VerifiedOutcome.DENIED_GATE_PREFIX = "denied:gate_rejection:"
    assert outcome.startswith("denied:gate_rejection:gate_1:")


def test_verifier_denies_at_gate_6_mint_not_revoked():
    facts = _venue_facts(mint_authority_revoked=False)
    v = _make_verifier(
        venue_provider=_provider(facts),
        scorer_store={"w_smart": _MockScore(10, 0.8)},
    )
    canonical, outcome = asyncio.run(v.verify(_candidate()))
    assert canonical is None
    # VerifiedOutcome.DENIED_GATE_PREFIX = "denied:gate_rejection:"
    assert outcome.startswith("denied:gate_rejection:gate_6:")
    assert "mint_authority NOT revoked" in outcome


def test_verifier_denies_at_gate_6_lp_too_low():
    facts = _venue_facts(lp_burned_or_locked_pct=10.0)
    v = _make_verifier(
        venue_provider=_provider(facts),
        scorer_store={"w_smart": _MockScore(10, 0.8)},
    )
    canonical, outcome = asyncio.run(v.verify(_candidate()))
    assert canonical is None
    assert "LP burn/lock" in outcome


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
    "arbicore.scanners.launch_arbitrage.verifier",
    "arbicore.scanners.launch_arbitrage.economics",
    "arbicore.scanners.launch_arbitrage.filter",
])
def test_inv_2_no_emission_bus_in_d4_4_modules(mod_name):
    import importlib
    mod = importlib.import_module(mod_name)
    assert _module_has_no_emission_bus_usage(mod)


# ============================================================================
# Dormancy — D-4.5 still doesn't ship
# ============================================================================

def test_no_scanner_orchestrator_at_d4_4():
    """D-4.5 lands the orchestrator — assertion INVERTED at D-4.5 landing."""
    import arbicore.scanners.launch_arbitrage.scanner as mod  # noqa: F401
    assert hasattr(mod, "LaunchArbitrageScanner")


def test_verifier_is_importable_now_at_d4_4():
    """The negative assertion from D-4.0/D-4.3 is INVERTED at D-4.4."""
    import arbicore.scanners.launch_arbitrage.verifier  # noqa: F401


def test_constructing_verifier_does_not_start_any_task():
    v = _make_verifier(venue_provider=_provider({}))
    assert v.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE
    # No emit hook, no task — verifier is stateless construction
    assert v.verifier_id == "launch_opportunity_verifier"
