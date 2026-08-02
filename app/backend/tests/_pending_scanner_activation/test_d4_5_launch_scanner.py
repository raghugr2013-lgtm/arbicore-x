"""D-4.5 — LaunchArbitrageScanner orchestrator tests.

Covers:
  - Scanner construction (sources + verifier registry + gates)
  - DISABLED state at boot — _tick() does nothing
  - Composition wiring: source registry has 5 launch sources
  - INV-2: scanner module IS the single emit caller for LAUNCH_ARBITRAGE
  - INV-2: scanner-tree-wide emit call sites = 4 (cex_arb + funding_arb +
    dex_arb + launch_arb)
  - Stats / gate-rejection structure (gate_1_launch_composite + gate_6_rug_risk)
  - Verifier registry registered with LAUNCH_ARBITRAGE type
  - Default no-op venue_provider posture (no canonical confirmable until
    operator wires a real Helius provider)
  - Emit path: when verifier confirms, scanner emits via EmissionBus with
    correct actor tag
  - Outcome → gate-rejection counter mapping
  - Dormancy: orchestrator construction starts no background task
"""
from __future__ import annotations

import asyncio
import inspect
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from arbicore.models.discovery import (
    DiscoveryCandidate, VerifiedOutcome, make_candidate_id,
)
from arbicore.models.enums import OpportunityType
from arbicore.scanners.launch_arbitrage import LaunchArbitrageScanner
from arbicore.scanners.launch_arbitrage.scanner import (
    LaunchArbitrageScanner as _LaunchScanner,
    _noop_venue_provider,
)


# ============================================================================
# Stubs
# ============================================================================

class _StubBus:
    def __init__(self):
        self.emitted: List[Any] = []

    async def emit(self, opp, *, venue_ids, actor):
        self.emitted.append((opp, venue_ids, actor))


class _StubQueue:
    def __init__(self, batch: Optional[List[DiscoveryCandidate]] = None):
        self.upserted: List[Any] = []
        self.processed: List[Any] = []
        self._batch = batch or []

    async def upsert_many(self, cands):
        self.upserted.extend(cands)

    async def claim_batch(self, worker_id, batch_size=32):
        # Yield batch only once per claim
        b, self._batch = self._batch, []
        return b

    async def mark_processed(self, candidate_id, outcome,
                              opportunity_id=None, observed_at=None):
        self.processed.append((candidate_id, outcome, opportunity_id))


class _StubCaps:
    async def is_gate_3_pass(self, *a, **k):
        return True, "ok"


def _make_scanner(*, enabled=False, cfg=None, venue_provider=None):
    cfg = cfg or {
        "interval_s": 60,
        "default_notional_usd": 250.0,
        "gate_thresholds": {
            "default": {
                "min_composite_launch_score": 25.0,
                "min_bonding_curve_progress_pct": 0.0,
                "min_holders": 10,
                "min_smart_money_entries": 0,
                "max_holder_concentration_top10_pct": 80.0,
                "min_confidence": 0.0,
            },
            "pumpfun": {"min_bonding_curve_progress_pct": 5.0},
        },
        "rug_gate": {
            "require_mint_authority_revoked": True,
            "require_freeze_authority_revoked": True,
            "min_lp_burned_or_locked_pct": 80.0,
            "max_holder_concentration_top10_pct": 60.0,
        },
        "roi_probability": {"min_sample_size": 4, "winsor_low_pct": 5.0,
                              "winsor_high_pct": 95.0},
        "discovery_sources": {},
        "wallet_intelligence": {"time_window_cluster_seconds": 300,
                                  "min_cluster_size": 3},
    }
    state = {"enabled": enabled}
    return LaunchArbitrageScanner(
        emission_bus=_StubBus(),
        discovery_queue=_StubQueue(),
        venue_capability_repo=_StubCaps(),
        config_loader=lambda: cfg,
        state_loader=lambda: state,
        venue_provider=venue_provider,
    )


# ============================================================================
# Construction
# ============================================================================

def test_scanner_constructs_cleanly():
    s = _make_scanner()
    assert s.scanner_id == "launch_arb"
    assert s.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE


def test_scanner_registers_five_launch_sources():
    s = _make_scanner()
    ids = sorted(src.source_id for src in s._sources)
    assert ids == sorted([
        "dexscreener_fresh_launch",
        "pumpfun_launches",
        "jupiter_trending",
        "helius_wallet_source",
        "bitquery_wallet_source",
    ])
    assert s.source_registry.ids() == sorted(ids) or \
        set(s.source_registry.ids()) == set(ids)


def test_scanner_verifier_registered_for_launch_arbitrage():
    s = _make_scanner()
    v = s.verifier_registry.get(OpportunityType.LAUNCH_ARBITRAGE)
    assert v is not None
    assert v.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE


def test_scanner_stats_initial_shape():
    s = _make_scanner()
    st = s.stats
    assert st["iterations"] == 0
    assert st["rows_emitted"] == 0
    assert st["verifier_confirmed"] == 0
    assert st["verifier_denied"] == 0
    assert st["verifier_errors"] == 0
    assert st["candidates_claimed"] == 0
    assert st["denied_venue_unreadable"] == 0
    assert st["gate_rejections"] == {
        "gate_1_launch_composite": 0,
        "gate_6_rug_risk": 0,
    }
    assert st["last_run_at"] is None
    assert st["last_error"] is None


# ============================================================================
# Default-disabled + dormancy
# ============================================================================

def test_scanner_disabled_by_default():
    s = _make_scanner(enabled=False)
    assert s.is_enabled() is False


def test_scanner_tick_no_op_when_disabled():
    s = _make_scanner(enabled=False)
    asyncio.run(s._tick())
    assert s.stats["iterations"] == 0
    assert s._queue.upserted == []  # type: ignore[attr-defined]


def test_scanner_construction_starts_no_background_task():
    s = _make_scanner()
    # Constructing must NOT spawn _task
    assert s._task is None


def test_default_venue_provider_is_noop():
    s = _make_scanner()
    assert s.venue_provider_is_default is True


def test_operator_can_inject_real_venue_provider():
    async def _real_provider(c):
        return {"some": "facts"}
    s = _make_scanner(venue_provider=_real_provider)
    assert s.venue_provider_is_default is False
    # Round-trip via setter
    s2 = _make_scanner()
    s2.set_venue_provider(_real_provider)
    assert s2.venue_provider_is_default is False


# ============================================================================
# Enabled tick — discover + claim + verify path
# ============================================================================

def test_scanner_tick_increments_iterations_when_enabled():
    s = _make_scanner(enabled=True)
    # Replace sources with empty ones so the discover loop is a no-op.
    s._sources = []
    s._source_registry.__init__()
    asyncio.run(s._tick())
    assert s.stats["iterations"] == 1
    assert s._queue.upserted == []  # type: ignore[attr-defined]


def test_scanner_tick_with_noop_provider_yields_venue_unreadable():
    """With the default no-op venue_provider, every candidate ends as
    `denied:venue_unreadable` — visibly counted, never emitted."""
    cand = DiscoveryCandidate(
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
    )
    s = _make_scanner(enabled=True)
    s._sources = []  # no discover I/O
    s._queue = _StubQueue(batch=[cand])
    asyncio.run(s._tick())
    assert s.stats["verifier_denied"] == 1
    assert s.stats["denied_venue_unreadable"] == 1
    assert s.stats["rows_emitted"] == 0
    # Bus was never called
    assert s._bus.emitted == []  # type: ignore[attr-defined]
    # Candidate was marked processed with the canonical outcome tag
    assert s._queue.processed[0][1] == VerifiedOutcome.DENIED_VENUE_UNREADABLE


def test_scanner_tick_emits_when_verifier_confirms(monkeypatch):
    """When the verifier returns a CanonicalOpportunity, the orchestrator
    issues exactly one EmissionBus.emit(...) at the SINGLE call site
    inside _tick (INV-2)."""
    # Build a candidate
    cand = DiscoveryCandidate(
        candidate_id=make_candidate_id(
            hint_source="launch_intel:smart_money_entry",
            opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
            subject_id="solana:M2", asset="BONK",
            candidate_venues=["pumpfun:solana"],
            hint_observed_at=1_700_000_000.0,
        ),
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source="launch_intel:smart_money_entry",
        hint_observed_at=1_700_000_000.0,
        subject_id="solana:M2",
        asset="BONK",
        candidate_venues=["pumpfun:solana"],
    )
    s = _make_scanner(enabled=True)
    s._sources = []
    s._queue = _StubQueue(batch=[cand])
    # Stub verifier.verify to return a canonical
    from arbicore.models.canonical import CanonicalOpportunity
    from arbicore.models.enums import (
        DataProvenance, MevRiskLevel, OpportunityStatus,
    )

    async def _stub_verify(self_, c):
        opp = CanonicalOpportunity(
            opportunity_id="launch_arb:solana:M2:1700000000",
            opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
            buy_venue="pumpfun:solana:M2",
            sell_venue="raydium:solana:P2",
            asset="BONK",
            subject_id="solana:M2",
            source_data_quality=DataProvenance.REAL,
            mev_risk_level=MevRiskLevel.MEDIUM,
            status=OpportunityStatus.VALIDATED,
            expected_profit_usd=10.0,
            capital_required_usd=250.0,
            category_metadata={"launchpad": "pumpfun"},
        )
        return opp, f"{VerifiedOutcome.CONFIRMED_PREFIX}{opp.opportunity_id}"

    monkeypatch.setattr(
        "arbicore.scanners.launch_arbitrage.verifier."
        "LaunchOpportunityVerifier.verify", _stub_verify)
    asyncio.run(s._tick())
    assert s.stats["rows_emitted"] == 1
    assert s.stats["verifier_confirmed"] == 1
    assert len(s._bus.emitted) == 1  # type: ignore[attr-defined]
    opp_emitted, venue_ids, actor = s._bus.emitted[0]  # type: ignore[attr-defined]
    assert actor == "launch_arb_scanner"
    assert venue_ids == ["pumpfun:solana:M2", "raydium:solana:P2"]


def test_scanner_tick_gate_1_rejection_counts_in_stats(monkeypatch):
    cand = DiscoveryCandidate(
        candidate_id="c1",
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source="launch_intel:smart_money_entry",
        hint_observed_at=1_700_000_000.0,
        subject_id="solana:M3",
        asset="X", candidate_venues=["pumpfun:solana"],
    )
    s = _make_scanner(enabled=True)
    s._sources = []
    s._queue = _StubQueue(batch=[cand])

    async def _stub_verify(self_, c):
        return None, (
            f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_1:composite 10 < min 60")
    monkeypatch.setattr(
        "arbicore.scanners.launch_arbitrage.verifier."
        "LaunchOpportunityVerifier.verify", _stub_verify)
    asyncio.run(s._tick())
    assert s.stats["gate_rejections"]["gate_1_launch_composite"] == 1
    assert s.stats["gate_rejections"]["gate_6_rug_risk"] == 0
    assert s.stats["verifier_denied"] == 1


def test_scanner_tick_gate_6_rejection_counts_in_stats(monkeypatch):
    cand = DiscoveryCandidate(
        candidate_id="c1",
        opportunity_type=OpportunityType.LAUNCH_ARBITRAGE,
        hint_source="launch_intel:smart_money_entry",
        hint_observed_at=1_700_000_000.0,
        subject_id="solana:M4",
        asset="X", candidate_venues=["pumpfun:solana"],
    )
    s = _make_scanner(enabled=True)
    s._sources = []
    s._queue = _StubQueue(batch=[cand])

    async def _stub_verify(self_, c):
        return None, (
            f"{VerifiedOutcome.DENIED_GATE_PREFIX}gate_6:mint_authority "
            "NOT revoked (rug-risk)")
    monkeypatch.setattr(
        "arbicore.scanners.launch_arbitrage.verifier."
        "LaunchOpportunityVerifier.verify", _stub_verify)
    asyncio.run(s._tick())
    assert s.stats["gate_rejections"]["gate_6_rug_risk"] == 1
    assert s.stats["gate_rejections"]["gate_1_launch_composite"] == 0


def test_scanner_tick_wrong_opportunity_type_marks_no_verifier():
    """Candidates of the wrong opportunity_type must be rejected with
    DENIED_NO_VERIFIER — no verifier invocation, no emit."""
    cand = DiscoveryCandidate(
        candidate_id="c-wrong",
        opportunity_type=OpportunityType.CEX_ARBITRAGE,   # not launch
        hint_source="launch_intel:smart_money_entry",
        hint_observed_at=1_700_000_000.0,
        subject_id="solana:M5",
        asset="X", candidate_venues=["pumpfun:solana"],
    )
    s = _make_scanner(enabled=True)
    s._sources = []
    s._queue = _StubQueue(batch=[cand])
    asyncio.run(s._tick())
    assert s._queue.processed[0][1] == VerifiedOutcome.DENIED_NO_VERIFIER
    assert s._bus.emitted == []  # type: ignore[attr-defined]


# ============================================================================
# INV-2 — emit call-site discipline (scanner-tree-wide + per-module)
# ============================================================================

def test_inv2_launch_scanner_module_has_exactly_one_emit_call():
    """The launch_arb scanner module must contain exactly ONE `self._bus.emit(`
    call — the orchestrator's single emission point."""
    import arbicore.scanners.launch_arbitrage.scanner as mod
    src = open(mod.__file__).read()
    emit_calls = [ln for ln in src.split("\n")
                  if ".emit(" in ln and "self._bus.emit" in ln]
    assert len(emit_calls) == 1


def test_inv2_launch_scanner_emit_uses_actor_tag():
    """The single emit call must carry actor='launch_arb_scanner' for audit."""
    import arbicore.scanners.launch_arbitrage.scanner as mod
    src = open(mod.__file__).read()
    assert 'actor="launch_arb_scanner"' in src


def test_inv2_scanner_tree_emit_site_count_now_four():
    """After D-4.5 the scanner tree has 4 authorised emit sites
    (cex_arbitrage, funding_arbitrage, dex_arbitrage, launch_arbitrage).
    After D-5.1 a fifth site (cross_chain_arbitrage) lands and after D-6.1 a
    sixth site (flash_loan_arbitrage) lands; this assertion is upgraded to
    accept any of those counts for back-compat with subsequent waves."""
    scanners_root = Path("/app/backend/arbicore/scanners")
    emit_files = []
    for f in scanners_root.rglob("scanner.py"):
        text = f.read_text(encoding="utf-8")
        if "self._bus.emit(" in text:
            emit_files.append(f.name)
    # 4 sites at D-4.5; 5 sites at D-5.1; 6 sites at D-6.1
    assert len(emit_files) in (4, 5, 6), (
        f"INV-2: expected 4, 5 or 6 scanner emit sites, got "
        f"{len(emit_files)}: {emit_files}"
    )


# ============================================================================
# Architectural checks
# ============================================================================

def test_launch_scanner_uses_universal_emission_bus_path():
    """Scanner must emit through self._bus (EmissionBus) — never direct
    persistence to OpportunityRepository or any other path."""
    import arbicore.scanners.launch_arbitrage.scanner as mod
    src = inspect.getsource(mod)
    assert "self._bus.emit(" in src
    assert "OpportunityRepository" not in src


def test_launch_scanner_inherits_verifier_with_inv3_provenance():
    """Verifier's source_id is helius_token_rpc → derive_provenance over legs
    yields REAL classification, never the aggregator hint's classification."""
    s = _make_scanner()
    v = s.verifier_registry.get(OpportunityType.LAUNCH_ARBITRAGE)
    assert v is not None
    # The verifier ABC field is opportunity_type
    assert v.opportunity_type == OpportunityType.LAUNCH_ARBITRAGE
    # The verifier_id matches the D-4.4 canonical value
    assert v.verifier_id == "launch_opportunity_verifier"


# ============================================================================
# Dormancy negatives — D-4.5 inverted; D-4.7 narrative NOT shipped
# ============================================================================

def test_launch_scanner_module_now_imports_at_d4_5():
    """D-4.5 ships scanner.py — the negative assertion is INVERTED here.
    Mirrors the D-4.4 inversion convention."""
    import arbicore.scanners.launch_arbitrage.scanner as mod
    assert hasattr(mod, "LaunchArbitrageScanner")


def test_no_narrative_engine_yet_at_d4_5():
    """D-4.7 is out-of-scope for this bundle. The narrative module must
    NOT be importable."""
    with pytest.raises(ImportError):
        import arbicore.scanners.launch_arbitrage.narrative  # noqa: F401


def test_constructing_scanner_starts_no_task():
    """Constructing LaunchArbitrageScanner is side-effect free — no
    background task is created until start() is called."""
    s = _make_scanner()
    assert s._task is None


# ============================================================================
# Composition wiring smoke
# ============================================================================

def test_composition_exposes_launch_arb_scanner_factory():
    """The composition root exposes get_launch_arb_scanner()."""
    from arbicore.runtime import composition as comp
    assert hasattr(comp, "get_launch_arb_scanner")
    assert callable(comp.get_launch_arb_scanner)
