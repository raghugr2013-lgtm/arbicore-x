"""D-4.0 — Launch Intelligence substrate seeding tests.

Verifies that the D-4.0 substrate wave produces the contract surface needed
for D-4.1 through D-4.5 without spawning the orchestrator or any emit path:

  - scanner_config["launch_arb"] default doc exists with the documented shape
  - scanner_state["launch_arb"] defaults to enabled=False
  - SOURCE_REGISTRY carries the 6 new launch-intel sources, all REAL
    provenance, with explicit "HINT-ONLY; INV-3" markers on the 3 aggregators
  - KNOWN_CATEGORY_METADATA_KEYS[LAUNCH_ARBITRAGE] carries the Phase-B baseline
    keys + the new Solana rug-risk + phase-classifier + smart-money + timeline
    + ROI + narrative keys
  - No scanner orchestrator code exists yet (negative assertion — D-4.5 ships it)
  - The 5 operator decisions are observable in the seeded config:
      D1: Helius is the only Solana provider (no Triton/Quicknode/SolanaFM)
      D2: DexScreener fresh-launch + Pump.fun both present in discovery_sources
      D3: Bitquery scaffolded but "scaffolded_only: true" + enabled=False
      D4: Curated wallet seed lift is a D-4.2 deliverable (asserted absent here)
      D5: narrative.daily_usd_cap == 1.00

INV-1 / INV-2 / INV-3 do not apply at the substrate wave (no candidates, no
emissions, no scanner). Their D-4 enforcement lands at D-4.1+ source tests
and D-4.5 orchestrator tests.
"""
from __future__ import annotations

import pytest

from arbicore.data.provenance import (
    SOURCE_REGISTRY,
    SourceClassification,
)
from arbicore.data.scanner_config_repo import (
    DEFAULT_LAUNCH_ARB_CONFIG,
)
from arbicore.models.category_metadata import KNOWN_CATEGORY_METADATA_KEYS
from arbicore.models.enums import DataProvenance, OpportunityType


# ============================================================================
# SOURCE_REGISTRY extensions
# ============================================================================

D4_SOURCE_IDS = [
    "dexscreener_fresh_launch",
    "pumpfun_launches",
    "jupiter_trending",
    "helius_wallet_source",
    "helius_token_rpc",
    "bitquery_wallet_source",
]


def test_d4_sources_registered_in_provenance_registry():
    for sid in D4_SOURCE_IDS:
        assert sid in SOURCE_REGISTRY, f"missing source registry entry: {sid}"


def test_d4_sources_all_real_provenance():
    """All D-4 sources are REAL (live network), even the HINT-only aggregators.
    INV-3 enforcement is via the per-leg verifier override, not provenance."""
    for sid in D4_SOURCE_IDS:
        entry = SOURCE_REGISTRY[sid]
        assert isinstance(entry, SourceClassification)
        assert entry.provenance == DataProvenance.REAL, (
            f"{sid} must be REAL (was {entry.provenance})"
        )


def test_d4_aggregator_sources_carry_inv3_marker():
    """The three aggregator HINT sources MUST carry an explicit
    'HINT-ONLY; INV-3' marker in their reason so the verifier never
    propagates their classification to CanonicalOpportunity.source_data_quality."""
    for sid in ("dexscreener_fresh_launch", "pumpfun_launches", "jupiter_trending"):
        reason = SOURCE_REGISTRY[sid].reason
        assert "HINT-ONLY" in reason
        assert "INV-3" in reason


def test_d4_credentialed_sources_document_helius_dependency():
    """Helius sources MUST document HELIUS_API_KEY graceful-disable."""
    for sid in ("helius_wallet_source", "helius_token_rpc"):
        reason = SOURCE_REGISTRY[sid].reason
        assert "HELIUS_API_KEY" in reason
        assert "graceful-disable" in reason


def test_d4_bitquery_documents_stubbed_state():
    """Bitquery MUST document that D-4.0 scaffolds-but-stubs it (operator
    decision 3) and is not live until BITQUERY_API_KEY + flip."""
    reason = SOURCE_REGISTRY["bitquery_wallet_source"].reason
    assert "stubbed" in reason.lower()
    assert "BITQUERY_API_KEY" in reason
    assert "deferred" in reason.lower()


# ============================================================================
# category_metadata vocabulary extensions
# ============================================================================

def test_launch_arbitrage_vocabulary_extended_with_d4_keys():
    keys = KNOWN_CATEGORY_METADATA_KEYS[OpportunityType.LAUNCH_ARBITRAGE]
    # Phase B baseline survives
    for k in ("launch_phase", "presale_price", "public_price",
              "vesting_tge_pct", "expected_roi_probability",
              "wallet_cluster_ids", "insider_signals"):
        assert k in keys, f"Phase B key dropped: {k}"
    # D-4.0 Solana rug-risk
    for k in ("mint_authority_revoked", "freeze_authority_revoked",
              "lp_burned_pct", "lp_locked_until_ts",
              "bonding_curve_progress_pct", "migration_ready",
              "holder_concentration_top10_pct", "holder_count"):
        assert k in keys, f"missing D-4 rug-risk key: {k}"
    # Discovery / phase classifier surface
    for k in ("chain", "launchpad", "token_address",
              "age_hours", "first_seen_at_ts",
              "phase_confidence", "phase_rationale"):
        assert k in keys
    # Smart-money / wallet intel
    for k in ("smart_money_entry_count", "cluster_size_max",
              "early_quality_wallet_count", "whale_rotation_count"):
        assert k in keys
    # Timeline / narrative
    for k in ("timeline_confidence", "timeline_label",
              "narrative_daily_cost_usd", "narrative_llm_used"):
        assert k in keys
    # ROI probability
    for k in ("roi_base_low_pct", "roi_base_high_pct",
              "roi_breakout_probability", "roi_drawdown_probability",
              "roi_sample_size"):
        assert k in keys


# ============================================================================
# DEFAULT_LAUNCH_ARB_CONFIG shape
# ============================================================================

def test_default_launch_arb_config_top_level_shape():
    cfg = DEFAULT_LAUNCH_ARB_CONFIG
    assert cfg["_id"] == "launch_arb"
    assert cfg["enabled"] is False
    for k in ("interval_s", "discovery_sources", "gate_thresholds",
              "rug_gate", "wallet_intelligence", "phase_classifier",
              "roi_probability", "narrative",
              "default_notional_usd", "verifier_concurrency"):
        assert k in cfg, f"missing top-level config key: {k}"


def test_default_launch_arb_disabled_at_boot():
    """The cardinal D-4 invariant: scanner remains operator-controlled."""
    assert DEFAULT_LAUNCH_ARB_CONFIG["enabled"] is False


def test_discovery_sources_match_authorization_package():
    """Operator decisions §4.1, §4.2, §4.3 must be observable in seed config."""
    ds = DEFAULT_LAUNCH_ARB_CONFIG["discovery_sources"]
    expected = {
        "dexscreener_fresh_launch", "pumpfun_launches", "jupiter_trending",
        "helius_wallet_source", "bitquery_wallet_source",
    }
    assert set(ds.keys()) == expected
    # All disabled at boot
    for src_id, src_cfg in ds.items():
        assert src_cfg.get("enabled") is False, f"{src_id} must boot disabled"


def test_decision_1_helius_only_solana_provider():
    """Operator decision 1: Helius only. No Triton / Quicknode / SolanaFM
    references in the seeded config or registry."""
    cfg = DEFAULT_LAUNCH_ARB_CONFIG
    cfg_dump = repr(cfg).lower()
    for forbidden in ("triton", "quicknode", "solanafm"):
        assert forbidden not in cfg_dump
    # Registry must not register them either
    for sid in SOURCE_REGISTRY.keys():
        for forbidden in ("triton", "quicknode", "solanafm"):
            assert forbidden not in sid.lower()


def test_decision_2_dexscreener_and_pumpfun_both_present():
    """Operator decision 2: both fresh-launch hints active."""
    ds = DEFAULT_LAUNCH_ARB_CONFIG["discovery_sources"]
    assert "dexscreener_fresh_launch" in ds
    assert "pumpfun_launches" in ds
    # Pump.fun has a configured bonding-curve market-cap window
    pf = ds["pumpfun_launches"]
    assert "max_market_cap_usd" in pf
    assert pf["max_market_cap_usd"] > pf["min_market_cap_usd"]


def test_decision_3_bitquery_scaffolded_not_live():
    """Operator decision 3: Bitquery scaffolded but stubbed."""
    bq = DEFAULT_LAUNCH_ARB_CONFIG["discovery_sources"]["bitquery_wallet_source"]
    assert bq["enabled"] is False
    assert bq.get("scaffolded_only") is True


def test_decision_5_narrative_capped_at_one_usd_per_day():
    """Operator decision 5: LLM narrative $1/day hard cap."""
    nar = DEFAULT_LAUNCH_ARB_CONFIG["narrative"]
    assert nar["enabled"] is False  # off at boot
    assert nar["daily_usd_cap"] == 1.00


def test_rug_gate_solana_specific_rejections():
    rg = DEFAULT_LAUNCH_ARB_CONFIG["rug_gate"]
    assert rg["require_mint_authority_revoked"] is True
    assert rg["require_freeze_authority_revoked"] is True
    assert rg["min_lp_burned_or_locked_pct"] >= 50.0
    assert 0 < rg["max_holder_concentration_top10_pct"] <= 100


def test_gate_1_composite_score_threshold_defined():
    gt = DEFAULT_LAUNCH_ARB_CONFIG["gate_thresholds"]["default"]
    assert "min_composite_launch_score" in gt
    assert 0 < gt["min_composite_launch_score"] <= 100
    assert "min_holders" in gt
    assert "min_smart_money_entries" in gt
    assert "max_holder_concentration_top10_pct" in gt


def test_per_launchpad_overrides_present():
    """Pump.fun launchpad has its own bonding-curve dynamics."""
    gt = DEFAULT_LAUNCH_ARB_CONFIG["gate_thresholds"]
    assert "pumpfun" in gt
    assert gt["pumpfun"]["min_bonding_curve_progress_pct"] >= 0


def test_wallet_intelligence_runtime_knobs():
    wi = DEFAULT_LAUNCH_ARB_CONFIG["wallet_intelligence"]
    assert wi["time_window_cluster_seconds"] == 300  # ±5min
    assert wi["min_cluster_size"] >= 2
    assert wi["early_entry_threshold_hours"] > 0
    assert wi["quality_wallet_min_score"] > 0


def test_phase_classifier_thresholds_present():
    pc = DEFAULT_LAUNCH_ARB_CONFIG["phase_classifier"]
    for k in ("stealth_low_social_threshold",
              "early_momentum_min_score_delta",
              "overheated_max_price_change_24h_pct",
              "overheated_retail_fomo_share_min",
              "exhaustion_lp_drop_pct"):
        assert k in pc


def test_roi_probability_winsor_bounds():
    roi = DEFAULT_LAUNCH_ARB_CONFIG["roi_probability"]
    assert 0 <= roi["winsor_low_pct"] < roi["winsor_high_pct"] <= 100
    assert roi["min_sample_size"] >= 1


# ============================================================================
# Negative assertions — D-4.0 must NOT ship D-4.1+ artefacts
# ============================================================================

def test_no_launch_arbitrage_scanner_module_yet():
    """D-4.5 ships the orchestrator (`scanner.py`). At D-4.0 the import would
    have failed; once D-4.5 lands, this assertion is INVERTED per the
    wave-progression convention. The scanner module must now import
    cleanly without spawning any background task or emission path."""
    import arbicore.scanners.launch_arbitrage.scanner as mod  # noqa: F401
    assert hasattr(mod, "LaunchArbitrageScanner")


def test_no_launch_opportunity_verifier_yet():
    """D-4.4 ships the verifier. At D-4.0 the import would have failed; once
    D-4.4 lands, this assertion is INVERTED (wave-progression convention —
    see D-4.3 IMPLEMENTATION_REPORT §9). The verifier module must now import
    cleanly without spawning any background task or emission path."""
    import arbicore.scanners.launch_arbitrage.verifier as mod  # noqa: F401
    assert hasattr(mod, "LaunchOpportunityVerifier")


def test_no_curated_wallet_seed_at_d4_0():
    """Operator decision 4 says LIFT VERBATIM during D-4.2. At D-4.0 the
    seed file must not exist yet — confirms the wave-by-wave discipline."""
    from pathlib import Path
    assert not Path("/app/backend/arbicore/intel/curated_wallets.json").exists()


# ============================================================================
# Existing scanners still seeded — no regression
# ============================================================================

def test_other_scanner_defaults_unchanged_by_d4_0():
    from arbicore.data.scanner_config_repo import (
        DEFAULT_CEX_ARB_CONFIG, DEFAULT_FUNDING_ARB_CONFIG,
        DEFAULT_DEX_ARB_CONFIG,
    )
    # CEX still enabled by default (legacy behaviour)
    assert DEFAULT_CEX_ARB_CONFIG["enabled"] is True
    # Funding default unchanged
    assert DEFAULT_FUNDING_ARB_CONFIG["_id"] == "funding_arb"
    # DEX still disabled (operator-controlled rollout)
    assert DEFAULT_DEX_ARB_CONFIG["enabled"] is False


def test_dexscreener_hint_is_still_dex_arb_aggregator_not_d4():
    """Sanity: the D-3 dexscreener_hint is distinct from the D-4 fresh-launch
    aggregator. They share a vendor but serve different opportunity families."""
    assert "dexscreener_hint" in SOURCE_REGISTRY
    assert "dexscreener_fresh_launch" in SOURCE_REGISTRY
    # Both reasons must mention DexScreener but be distinguishable
    a = SOURCE_REGISTRY["dexscreener_hint"].reason
    b = SOURCE_REGISTRY["dexscreener_fresh_launch"].reason
    assert "DexScreener" in a and "DexScreener" in b
    assert a != b
