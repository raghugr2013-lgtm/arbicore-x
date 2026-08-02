"""Tests for D-3.4 — DEXArbitrageScanner orchestrator.

Covers:
  - Scanner construction (sources + quoters + verifier registry)
  - DISABLED state at boot — _tick() does nothing
  - Composition wiring: source registry has 9 entries (8 venue + 1 hint)
  - INV-2: this scanner module IS the single emit caller for DEX_ARBITRAGE
  - INV-2: pre-existing scanner invariant test still recognizes exactly N
    emit call sites (cex_arb, funding_arb, dex_arb = 3)
  - Stats / gate-rejection structure
  - Verifier registry registered with DEX_ARBITRAGE type
  - DexScreener HINT source present (INV-3 telemetry only)
"""
from __future__ import annotations

import asyncio
import ast
import inspect

import pytest

from arbicore.models.enums import OpportunityType
from arbicore.scanners.dex_arbitrage import DEXArbitrageScanner
from arbicore.scanners.dex_arbitrage.scanner import DEXArbitrageScanner as DEXScanner


# ============================================================================
# Stubs
# ============================================================================

class _StubBus:
    def __init__(self):
        self.emitted = []
    async def emit(self, opp, *, venue_ids, actor):
        self.emitted.append((opp, venue_ids, actor))


class _StubQueue:
    def __init__(self):
        self.upserted = []
        self.processed = []
    async def upsert_many(self, cands):
        self.upserted.extend(cands)
    async def claim_batch(self, worker_id, batch_size=32):
        return []
    async def mark_processed(self, candidate_id, outcome,
                              opportunity_id=None, observed_at=None):
        self.processed.append((candidate_id, outcome, opportunity_id))


class _StubCaps:
    async def is_gate_3_pass(self, vid, b, q):
        return True, "ok"


def _make_scanner(*, enabled=False, cfg=None):
    cfg = cfg or {
        "default_notional_usd": 1000.0,
        "tier_a_pairs": ["WETH/USDC@arbitrum"],
        "gate_thresholds": {"default": {
            "min_net_spread_after_slip_after_gas_pct": 0.30,
            "min_depth_usd": 5000, "min_confidence": 55,
        }},
        "discovery_sources": {},
        "venue_fees": {"uniswap_v3": {"taker_bps": 5}},
        "mev_risk_factor": {"LOW": 0.0, "MEDIUM": 0.5, "HIGH": 1.5},
    }
    state = {"enabled": enabled}
    return DEXArbitrageScanner(
        emission_bus=_StubBus(),
        discovery_queue=_StubQueue(),
        venue_capability_repo=_StubCaps(),
        config_loader=lambda: cfg,
        state_loader=lambda: state,
    )


# ============================================================================
# Construction
# ============================================================================

def test_scanner_construction():
    s = _make_scanner()
    # 8 venue sources + 1 DexScreener HINT
    assert len(s._sources) == 9
    source_ids = sorted(src.source_id for src in s._sources)
    assert "dexscreener_hint" in source_ids
    assert "venue_dex_pool:uniswap_v3:ethereum" in source_ids
    assert "venue_dex_pool:raydium:solana" in source_ids


def test_scanner_verifier_registered_for_dex_arbitrage():
    s = _make_scanner()
    v = s.verifier_registry.get(OpportunityType.DEX_ARBITRAGE)
    assert v is not None
    assert v.opportunity_type == OpportunityType.DEX_ARBITRAGE


def test_scanner_stats_initial_shape():
    s = _make_scanner()
    assert s.stats == {
        "iterations": 0, "rows_emitted": 0,
        "verifier_confirmed": 0, "verifier_denied": 0,
        "verifier_errors": 0, "candidates_claimed": 0,
        "gate_rejections": {
            "economics": 0, "liquidity": 0,
            "venue_capability": 0, "confidence": 0, "provenance": 0,
        },
        "last_run_at": None, "last_error": None,
    }


# ============================================================================
# Default-disabled behaviour
# ============================================================================

def test_scanner_disabled_by_default():
    s = _make_scanner(enabled=False)
    assert s.is_enabled() is False


def test_scanner_tick_no_op_when_disabled():
    s = _make_scanner(enabled=False)
    asyncio.run(s._tick())
    # No iterations counted; queue untouched
    assert s.stats["iterations"] == 0
    assert s._queue.upserted == []  # type: ignore[attr-defined]


def test_scanner_tick_increments_iterations_when_enabled(monkeypatch):
    # D-3.6: DexScreener HINT is now live. For this offline scanner unit test
    # we stub the network fetch to [] so we observe the all-stubs scenario.
    from arbicore.scanners.discovery.dexscreener_hint import DexScreenerHintSource
    async def _no_net(self, pair_canonical):
        return []
    monkeypatch.setattr(DexScreenerHintSource, "_fetch_pair_dex_quotes", _no_net)
    s = _make_scanner(enabled=True)
    asyncio.run(s._tick())
    assert s.stats["iterations"] == 1
    # All venue sources return [] (D-3.1 stubs); HINT returns []; no candidates
    assert s._queue.upserted == []  # type: ignore[attr-defined]
    # No emission attempted
    assert s._bus.emitted == []  # type: ignore[attr-defined]


# ============================================================================
# INV-2: emit call site discipline
# ============================================================================

def test_inv2_dex_scanner_module_has_exactly_one_emit_call():
    """The DEX scanner module must contain exactly ONE `.emit(` call —
    the orchestrator's single emission point."""
    import arbicore.scanners.dex_arbitrage.scanner as mod
    src = open(mod.__file__).read()
    emit_calls = [ln for ln in src.split("\n")
                  if ".emit(" in ln and "self._bus.emit" in ln]
    assert len(emit_calls) == 1


def test_inv2_dex_scanner_emit_uses_actor_tag():
    """The single emit call must carry actor='dex_arb_scanner' for audit."""
    import arbicore.scanners.dex_arbitrage.scanner as mod
    src = open(mod.__file__).read()
    assert 'actor="dex_arb_scanner"' in src


# ============================================================================
# DexScreener HINT source presence (INV-3 telemetry only)
# ============================================================================

def test_scanner_registers_dexscreener_hint_source():
    s = _make_scanner()
    from arbicore.scanners.discovery.dexscreener_hint import DexScreenerHintSource
    hint_sources = [src for src in s._sources
                    if isinstance(src, DexScreenerHintSource)]
    assert len(hint_sources) == 1
    # INV-3 contract — telemetry tier
    assert hint_sources[0].tier == 2
    assert hint_sources[0].source_id == "dexscreener_hint"


# ============================================================================
# Architectural check — module imports universal substrate
# ============================================================================

def test_dex_scanner_uses_universal_emission_bus_path():
    """The scanner's emit call must go through self._bus (EmissionBus),
    not directly persist to OpportunityRepository or any other path."""
    import arbicore.scanners.dex_arbitrage.scanner as mod
    src = inspect.getsource(mod)
    assert "self._bus.emit(" in src
    assert "OpportunityRepository" not in src   # never bypasses bus
