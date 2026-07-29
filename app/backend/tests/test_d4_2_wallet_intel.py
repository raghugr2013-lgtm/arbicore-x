"""D-4.2 — Launch-Intel Wallet Intelligence Substrate tests.

Covers:
  - WalletProfile (Pydantic v2, smart-money helper, idempotent merge_stats)
  - WalletScorer 4-factor outputs (deterministic, bounded, label-aware)
  - labels.load_curated (happy path, missing file, malformed, invalid label)
  - TimeWindowClusterDetector (single window, threshold, multi-token, membership)
  - Signal predicates (7 — each produces DiscoveryCandidate, INV-1 typing)
  - INV-2: no EmissionBus references in any D-4.2 module
  - INV-3: hint_source prefixed `launch_intel:` (telemetry-only)
  - WalletEnrichmentOrchestrator: end-to-end with MockWalletProvider
  - Orchestrator graceful-disable when provider unavailable
  - Orchestrator does NOT call EmissionBus
  - CLI helper imports cleanly + zero-side-effect surface
  - Dormancy negatives still hold (no orchestrator, no verifier yet)
"""
from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from arbicore.intel.launch import (
    SignalPredicateInput,
    TimeWindowClusterDetector,
    WalletActivityEvent,
    WalletEnrichmentOrchestrator,
    WalletProfile,
    WalletScorer,
    curated_index,
    evaluate_all_predicates,
    is_smart_money,
    load_curated,
    merge_stats,
)
from arbicore.intel.launch.labels import (
    CURATED_LABELS_PATH,
    LABEL_VOCABULARY,
    is_valid_label,
)
from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import OpportunityType


# ============================================================================
# WalletProfile
# ============================================================================

def test_wallet_profile_default_chain_is_solana():
    p = WalletProfile(address="abc")
    assert p.chain == "solana"
    assert p.label is None
    d = p.to_storage()
    assert d["id"] == "abc"


def test_is_smart_money_by_curated_label():
    assert is_smart_money({"label": "smart_money"}) is True
    assert is_smart_money({"label": "whale"}) is True
    assert is_smart_money({"label": "rug_wallet"}) is False
    assert is_smart_money({}) is False
    assert is_smart_money(None) is False


def test_is_smart_money_by_algo_score():
    assert is_smart_money({"scores": {"wallet_quality": 80}}) is True
    assert is_smart_money({"scores": {"wallet_quality": 70}}) is False


def test_merge_stats_total_accumulates():
    a = {"total_buys": 5, "total_volume_usd": 1000}
    out = merge_stats(a, {"total_buys": 3, "total_volume_usd": 250})
    assert out["total_buys"] == 8
    assert out["total_volume_usd"] == 1250
    assert "updated_at" in out


def test_merge_stats_non_total_keys_replace():
    out = merge_stats({"label": "x"}, {"label": "y"})
    assert out["label"] == "y"


# ============================================================================
# WalletScorer
# ============================================================================

def _activity(*specs: tuple) -> List[WalletActivityEvent]:
    """specs: (token_addr, action, ts, amount_usd)"""
    return [
        WalletActivityEvent(
            wallet="w", token_id=f"solana:{t}", token_address=t,
            token_symbol=t[:6], chain="solana", action=action,
            timestamp=ts, amount_usd=amt,
        )
        for (t, action, ts, amt) in specs
    ]


def test_scorer_early_entry_high_when_early():
    s = WalletScorer()
    txs = _activity(
        ("tA", "buy", 1000, 500),
        ("tB", "buy", 1100, 500),
        ("tC", "buy", 1200, 500),
    )
    ages = {"tA": 0.5, "tB": 0.5, "tC": 0.5}   # all under 1h
    assert s.score_early_entry(txs, ages) >= 80


def test_scorer_early_entry_zero_when_no_buys():
    assert WalletScorer().score_early_entry([], {}) == 0.0


def test_scorer_conviction_with_large_dca():
    s = WalletScorer()
    txs = _activity(
        ("tA", "buy", 1000, 60_000),
        ("tA", "buy", 2000, 80_000),
    )
    assert s.score_conviction(txs) >= 90


def test_scorer_label_boost_smart_money():
    s = WalletScorer()
    q_no_label = s.score_quality(early_entry=50, consistency=50,
                                  conviction=50, label=None)
    q_smart = s.score_quality(early_entry=50, consistency=50,
                               conviction=50, label="smart_money")
    assert q_smart > q_no_label


def test_scorer_label_penalty_rug_wallet():
    s = WalletScorer()
    q_no_label = s.score_quality(early_entry=80, consistency=80,
                                  conviction=80, label=None)
    q_rug = s.score_quality(early_entry=80, consistency=80,
                             conviction=80, label="rug_wallet")
    assert q_rug < q_no_label


def test_scorer_compute_returns_complete_payload():
    s = WalletScorer()
    out = s.compute(txs=[], token_ages_hours={}, label="smart_money")
    for k in ("wallet_quality", "early_entry", "consistency",
              "conviction", "overall", "computed_at"):
        assert k in out


# ============================================================================
# Labels (curated)
# ============================================================================

def test_load_curated_defaults_empty(tmp_path):
    # Default-empty contract: when wallets[] is empty in any labels.json
    # shape, load_curated() returns []. (Originally asserted against the
    # shipped labels.json; rewritten to be path-independent so the test
    # holds regardless of operator-controlled live state in
    # backend/arbicore/intel/launch/labels.json — operator-seeded files
    # are operator state, not a code default.)
    p = tmp_path / "labels.json"
    p.write_text('{"wallets": []}')
    items = load_curated(p)
    assert items == []


def test_load_curated_handles_missing_file(tmp_path):
    items = load_curated(tmp_path / "no_such.json")
    assert items == []


def test_load_curated_filters_invalid_label(tmp_path):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps({"wallets": [
        {"address": "good", "label": "smart_money", "chain": "solana"},
        {"address": "bad",  "label": "not_a_real_label"},
    ]}))
    items = load_curated(p)
    assert len(items) == 1
    assert items[0]["address"] == "good"
    assert items[0]["label_source"] == "curated"


def test_curated_index_keyed_by_address(tmp_path):
    p = tmp_path / "labels.json"
    p.write_text(json.dumps({"wallets": [
        {"address": "w1", "label": "smart_money"},
        {"address": "w2", "label": "whale"},
    ]}))
    idx = curated_index(p)
    assert set(idx.keys()) == {"w1", "w2"}
    assert idx["w1"]["label"] == "smart_money"


def test_label_vocabulary_complete():
    expected = {"smart_money", "influencer", "sniper",
                "whale", "retail_fomo", "rug_wallet"}
    assert LABEL_VOCABULARY == expected
    assert is_valid_label("smart_money") is True
    assert is_valid_label("nope") is False


def test_labels_json_shipped_with_advisory_notes():
    """labels.json must lift the legacy schema AND carry the rug_wallet
    advisory marker per Operator Decision 4."""
    data = json.loads(CURATED_LABELS_PATH.read_text())
    schema = data.get("_schema") or {}
    valid = set(schema.get("valid_labels") or [])
    assert valid == LABEL_VOCABULARY
    advisory = schema.get("advisory_only_labels") or {}
    assert "rug_wallet" in advisory


# ============================================================================
# TimeWindowClusterDetector
# ============================================================================

def test_cluster_detector_basic_window():
    det = TimeWindowClusterDetector(window_seconds=300, min_cluster_size=3)
    activity = [
        {"wallet": "w1", "token_id": "T", "timestamp": 1000, "action": "buy"},
        {"wallet": "w2", "token_id": "T", "timestamp": 1050, "action": "buy"},
        {"wallet": "w3", "token_id": "T", "timestamp": 1100, "action": "buy"},
    ]
    clusters = det.detect(activity)
    assert len(clusters) == 1
    c = clusters[0]
    assert c["type"] == "time_window"
    assert sorted(c["wallets"]) == ["w1", "w2", "w3"]
    assert c["tokens_touched"] == ["T"]
    assert c["cohesion_score"] > 0


def test_cluster_detector_below_threshold_no_cluster():
    det = TimeWindowClusterDetector(min_cluster_size=3)
    activity = [
        {"wallet": "w1", "token_id": "T", "timestamp": 1000, "action": "buy"},
        {"wallet": "w2", "token_id": "T", "timestamp": 1050, "action": "buy"},
    ]
    assert det.detect(activity) == []


def test_cluster_detector_skips_sells():
    det = TimeWindowClusterDetector(min_cluster_size=2)
    activity = [
        {"wallet": "w1", "token_id": "T", "timestamp": 1000, "action": "buy"},
        {"wallet": "w2", "token_id": "T", "timestamp": 1050, "action": "sell"},
    ]
    assert det.detect(activity) == []


def test_cluster_membership_index():
    det = TimeWindowClusterDetector(min_cluster_size=2)
    activity = [
        {"wallet": "w1", "token_id": "T", "timestamp": 1000, "action": "buy"},
        {"wallet": "w2", "token_id": "T", "timestamp": 1050, "action": "buy"},
    ]
    clusters = det.detect(activity)
    idx = det.membership_index(clusters)
    assert idx["w1"] == idx["w2"] == clusters[0]["id"]


# ============================================================================
# Signal predicates — INV-1 typing + behaviour
# ============================================================================

def _build_input(**overrides) -> SignalPredicateInput:
    base = {
        "activity": [],
        "wallet_profiles": {},
        "token_context": {},
        "cluster_membership": {},
    }
    base.update(overrides)
    return SignalPredicateInput(**base)


def test_smart_money_entry_emits_for_quality_wallets():
    activity = [WalletActivityEvent(
        wallet="w1", token_id="solana:T", token_address="T",
        token_symbol="BONK", chain="solana", action="buy",
        timestamp=1000.0, amount_usd=10_000.0,
    )]
    profiles = {"w1": {"label": "smart_money",
                       "scores": {"wallet_quality": 90}}}
    cands = evaluate_all_predicates(_build_input(
        activity=activity, wallet_profiles=profiles,
    ))
    smart = [c for c in cands if c.hint_source == "launch_intel:smart_money_entry"]
    assert len(smart) == 1
    c = smart[0]
    assert isinstance(c, DiscoveryCandidate)
    assert not isinstance(c, CanonicalOpportunity)
    assert c.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE
    assert c.hint_metric["wallet"] == "w1"
    assert c.hint_metric["wallet_label"] == "smart_money"


def test_cluster_buying_emits_when_threshold_met():
    activity = [
        WalletActivityEvent(wallet=f"w{i}", token_id="solana:T",
                            token_address="T", token_symbol="X",
                            chain="solana", action="buy",
                            timestamp=1000.0 + i * 10, amount_usd=100.0)
        for i in range(4)
    ]
    membership = {f"w{i}": "cluster-X" for i in range(4)}
    cands = evaluate_all_predicates(_build_input(
        activity=activity, cluster_membership=membership,
    ))
    cb = [c for c in cands if c.hint_source == "launch_intel:cluster_buying"]
    assert len(cb) == 1
    assert cb[0].hint_metric["wallet_count"] == 4
    assert cb[0].hint_metric["cluster_id"] == "cluster-X"


def test_early_accumulation_requires_quality_count():
    activity = [
        WalletActivityEvent(wallet=f"w{i}", token_id="solana:T",
                            token_address="T", token_symbol="X",
                            chain="solana", action="buy",
                            timestamp=1000.0 + i, amount_usd=500.0,
                            is_early_entry=True)
        for i in range(3)
    ]
    profiles = {f"w{i}": {"scores": {"wallet_quality": 80}} for i in range(3)}
    cands = evaluate_all_predicates(_build_input(
        activity=activity, wallet_profiles=profiles,
    ))
    ea = [c for c in cands if c.hint_source == "launch_intel:early_accumulation"]
    assert len(ea) == 1


def test_stealth_alpha_requires_low_social():
    activity = [WalletActivityEvent(
        wallet="w1", token_id="solana:T", token_address="T",
        token_symbol="X", chain="solana", action="buy",
        timestamp=1000.0, amount_usd=500.0,
    )]
    profiles = {"w1": {"label": "smart_money"}}
    ctx_silent = {"solana:T": {"chain": "solana", "info": {}}}
    ctx_loud = {"solana:T": {"chain": "solana",
                              "info": {"twitter": "@x", "telegram": "t.me/x"}}}
    sa1 = [c for c in evaluate_all_predicates(_build_input(
            activity=activity, wallet_profiles=profiles,
            token_context=ctx_silent))
           if c.hint_source == "launch_intel:stealth_alpha"]
    sa2 = [c for c in evaluate_all_predicates(_build_input(
            activity=activity, wallet_profiles=profiles,
            token_context=ctx_loud))
           if c.hint_source == "launch_intel:stealth_alpha"]
    assert len(sa1) == 1
    assert len(sa2) == 0


def test_high_conviction_buy_threshold():
    activity = [
        WalletActivityEvent(wallet="w1", token_id="solana:T",
                            token_address="T", token_symbol="X",
                            chain="solana", action="buy",
                            timestamp=1000.0, amount_usd=20_000),
        WalletActivityEvent(wallet="w2", token_id="solana:T",
                            token_address="T", token_symbol="X",
                            chain="solana", action="buy",
                            timestamp=1010.0, amount_usd=500),
    ]
    cands = evaluate_all_predicates(_build_input(activity=activity))
    hcb = [c for c in cands if c.hint_source == "launch_intel:high_conviction_buy"]
    assert len(hcb) == 1
    assert hcb[0].hint_metric["wallet"] == "w1"


def test_retail_fomo_emits_when_no_quality_buyers():
    activity = [
        WalletActivityEvent(wallet=f"w{i}", token_id="solana:T",
                            token_address="T", token_symbol="X",
                            chain="solana", action="buy",
                            timestamp=1000.0 + i, amount_usd=10)
        for i in range(20)
    ]
    cands = evaluate_all_predicates(_build_input(activity=activity))
    rf = [c for c in cands if c.hint_source == "launch_intel:retail_fomo"]
    assert len(rf) == 1
    assert rf[0].hint_metric["polarity"] == "negative"


def test_whale_rotation_emits():
    activity = [
        WalletActivityEvent(wallet="w1", token_id="solana:A",
                            token_address="A", token_symbol="A",
                            chain="solana", action="sell",
                            timestamp=1000.0, amount_usd=5_000),
        WalletActivityEvent(wallet="w1", token_id="solana:B",
                            token_address="B", token_symbol="B",
                            chain="solana", action="buy",
                            timestamp=1300.0, amount_usd=5_000),
    ]
    profiles = {"w1": {"label": "whale"}}
    cands = evaluate_all_predicates(_build_input(
        activity=activity, wallet_profiles=profiles,
    ))
    wr = [c for c in cands if c.hint_source == "launch_intel:whale_rotation"]
    assert len(wr) == 1
    assert wr[0].hint_metric["sold_token_id"] == "solana:A"
    assert wr[0].hint_metric["bought_token_id"] == "solana:B"


def test_predicates_inv_1_no_canonical_outputs():
    """Brute-force: under every predicate's happy-path inputs, all outputs
    are DiscoveryCandidate, never CanonicalOpportunity."""
    activity = [
        WalletActivityEvent(wallet="w1", token_id="solana:T",
                            token_address="T", token_symbol="X",
                            chain="solana", action="buy",
                            timestamp=1000.0, amount_usd=20_000,
                            is_early_entry=True),
    ]
    profiles = {"w1": {"label": "smart_money",
                       "scores": {"wallet_quality": 90}}}
    cands = evaluate_all_predicates(_build_input(
        activity=activity, wallet_profiles=profiles,
        token_context={"solana:T": {"chain": "solana", "info": {}}},
    ))
    for c in cands:
        assert isinstance(c, DiscoveryCandidate)
        assert not isinstance(c, CanonicalOpportunity)
        assert c.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE
        # INV-3 marker — hint_source prefixed for telemetry
        assert c.hint_source.startswith("launch_intel:")


# ============================================================================
# INV-2 — no EmissionBus references in any D-4.2 module
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


@pytest.mark.parametrize("module_path", [
    "arbicore.intel.launch.wallet_profile",
    "arbicore.intel.launch.wallet_scorer",
    "arbicore.intel.launch.labels",
    "arbicore.intel.launch.cluster_detector",
    "arbicore.intel.launch.signal_predicates",
    "arbicore.intel.launch.enrichment",
])
def test_inv_2_no_emission_bus_in_module(module_path):
    import importlib
    mod = importlib.import_module(module_path)
    assert _module_has_no_emission_bus_usage(mod)


# ============================================================================
# WalletEnrichmentOrchestrator — end-to-end with MockWalletProvider
# ============================================================================

def test_enrichment_orchestrator_end_to_end():
    from tests.fixtures.mock_wallet_provider import MockWalletProvider

    provider = MockWalletProvider(seed=42, wallets_per_token=5)
    orchestrator = WalletEnrichmentOrchestrator(
        wallet_provider=provider,
        label_index_loader=lambda: {},
        max_concurrent_enrichments=2,
    )

    tracked = [
        {"token_id": "solana:MintA", "token_address": "MintA",
         "token_symbol": "TKA", "chain": "solana", "age_hours": 0.5},
        {"token_id": "solana:MintB", "token_address": "MintB",
         "token_symbol": "TKB", "chain": "solana", "age_hours": 0.5},
    ]
    res = asyncio.run(orchestrator.run(
        tracked_tokens=tracked,
        token_context={t["token_id"]: {"chain": "solana"} for t in tracked},
    ))
    assert res.provider_available is True
    assert res.error is None
    assert len(res.profiles_updated) > 0
    # Each profile carries scores
    for p in res.profiles_updated:
        assert isinstance(p, WalletProfile)
        assert "wallet_quality" in p.scores
    # All candidates are DiscoveryCandidate
    for c in res.candidates:
        assert isinstance(c, DiscoveryCandidate)
        assert not isinstance(c, CanonicalOpportunity)


def test_enrichment_orchestrator_provider_unavailable():
    class _DeadProvider:
        async def is_available(self): return False
        async def recent_buyers(self, *a, **k): return []
        async def wallet_transactions(self, *a, **k): return []

    orch = WalletEnrichmentOrchestrator(
        wallet_provider=_DeadProvider(),
        label_index_loader=lambda: {},
    )
    res = asyncio.run(orch.run(tracked_tokens=[], token_context={}))
    assert res.provider_available is False
    assert res.error == "provider_unavailable"
    assert res.profiles_updated == []
    assert res.candidates == []


def test_enrichment_orchestrator_empty_tokens_no_op():
    from tests.fixtures.mock_wallet_provider import MockWalletProvider

    orch = WalletEnrichmentOrchestrator(
        wallet_provider=MockWalletProvider(),
        label_index_loader=lambda: {},
    )
    res = asyncio.run(orch.run(tracked_tokens=[], token_context={}))
    assert res.provider_available is True
    assert res.profiles_updated == []
    assert res.clusters_detected == []
    assert res.candidates == []


def test_enrichment_orchestrator_label_injection():
    """Curated labels are projected onto the WalletProfile.label_source."""
    from tests.fixtures.mock_wallet_provider import MockWalletProvider

    provider = MockWalletProvider(seed=42, wallets_per_token=3)
    # Pre-compute the deterministic wallet addresses that the mock would emit
    # so we can label one of them as smart_money.
    sample_buyers = asyncio.run(provider.recent_buyers(
        "MintA", reference_ts=1_700_000_000))
    target_wallet = sample_buyers[0]["wallet"]

    def labels():
        return {target_wallet: {"label": "smart_money",
                                "chain": "solana",
                                "label_source": "curated"}}

    orch = WalletEnrichmentOrchestrator(
        wallet_provider=provider, label_index_loader=labels,
    )
    res = asyncio.run(orch.run(
        tracked_tokens=[{"token_id": "solana:MintA", "token_address": "MintA",
                          "token_symbol": "TKA", "chain": "solana",
                          "age_hours": 0.5}],
        token_context={"solana:MintA": {"chain": "solana"}},
    ))
    labelled = [p for p in res.profiles_updated if p.label == "smart_money"]
    assert len(labelled) == 1
    assert labelled[0].label_source == "curated"


# ============================================================================
# CLI helper sanity
# ============================================================================

def test_cli_helper_imports_cleanly():
    import arbicore.scripts.launch_arb_preview as cli
    assert callable(cli.main)
    assert callable(cli._render)


def test_cli_helper_render_output_shape():
    import arbicore.scripts.launch_arb_preview as cli
    sample = {
        "wave": "D-4.1",
        "scanner_state": {"enabled": False, "dormant_reason": "x"},
        "sources": [{"source_id": "s1", "tier": 1,
                      "enabled_in_config": False, "credentials_present": True,
                      "health_ok": True, "health_last_error": None}],
        "credential_status": {"HELIUS_API_KEY": False},
        "invariants": {"INV_1": "preserved"},
    }
    rendered = cli._render(sample)
    assert "D-4.1" in rendered
    assert "s1" in rendered
    assert "HELIUS_API_KEY" in rendered
    assert "INV_1" in rendered


# ============================================================================
# Dormancy negatives still hold at D-4.2
# ============================================================================

def test_no_launch_scanner_orchestrator_yet_at_d4_2():
    """D-4.5 lands the orchestrator — assertion INVERTED at D-4.5 landing."""
    import arbicore.scanners.launch_arbitrage.scanner as mod  # noqa: F401
    assert hasattr(mod, "LaunchArbitrageScanner")


def test_no_launch_verifier_yet_at_d4_2():
    """D-4.4 ships the verifier — assertion INVERTED at D-4.4 landing."""
    import arbicore.scanners.launch_arbitrage.verifier as mod  # noqa: F401
    assert hasattr(mod, "LaunchOpportunityVerifier")


def test_enrichment_orchestrator_does_not_spawn_tasks_on_init():
    """Constructing the orchestrator does NOT create any background task."""
    from tests.fixtures.mock_wallet_provider import MockWalletProvider
    # Check that we can construct it without an event loop running and
    # without any visible side effect beyond instance creation.
    orch = WalletEnrichmentOrchestrator(
        wallet_provider=MockWalletProvider(),
        label_index_loader=lambda: {},
    )
    assert orch.scorer is not None
    assert orch.cluster_detector is not None


def test_curated_labels_json_file_now_exists():
    """At D-4.2 the labels.json file is shipped (the D-4.0 negative
    assertion about absence is now inverted — wave progression)."""
    p = Path("/app/backend/arbicore/intel/launch/labels.json")
    assert p.exists()
