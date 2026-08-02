"""ArbiCore X — Phase D D-2.0 Funding Differential Verifier tests.

Organised around the five evidence categories the operator requested:
  1. Symbol mapping coverage across all supported venues.
  2. Annualized funding calculations for 1h and 8h intervals.
  3. Funding direction correctness examples.
  4. Timestamp freshness safeguards.
  5. Differential verification examples (deterministic + live).

Plus INV-2 / INV-3 static guards (the engine must contain zero references
to CanonicalOpportunity / EmissionBus / source_data_quality, ignoring
docstrings).
"""
from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Dict, List

import pytest

from arbicore.scanners.funding_arbitrage.sources import (
    FundingObservation, VENUE_FUNDING_SOURCE_CLASSES, _BaseFundingSource,
)
from arbicore.scanners.funding_arbitrage.verifier import (
    FundingDifferential,
    FundingDifferentialEvidence,
    FundingDifferentialVerifier,
    KNOWN_FUNDING_INTERVALS_H,
    VenueFundingRead,
    _normalise_observation,
    annualise_funding,
    validate_funding_interval,
    validate_symbol_mapping,
)


# ============================================================================
# Test fixtures and helpers
# ============================================================================

def _obs(*, venue, base, rate_pct, interval_h=8, observed_at=None,
         venue_symbol=None):
    """Construct a FundingObservation in test."""
    return FundingObservation(
        venue=venue,
        venue_symbol=venue_symbol or f"{base}TEST",
        subject_id=base,
        canonical_asset=f"{base}-PERP",
        funding_rate_pct=rate_pct,
        funding_interval_h=interval_h,
        next_funding_ts=time.time() + 3600.0,
        mark_price=65000.0 if base == "BTC" else 3000.0,
        source_observed_at_ts=observed_at or time.time(),
        raw={"_stub": True},
    )


class _StubSource(_BaseFundingSource):
    """Test source that returns a fixed list of observations."""
    source_id = ""

    def __init__(self, *, venue, observations, provenance_id):
        super().__init__(config_loader=lambda: {"discovery_sources": {}})
        self.source_id = f"venue_funding:{venue}"
        self.venue_id = venue
        self.venue_provenance_id = provenance_id
        self._observations = observations

    async def _fetch_observations(self):
        return list(self._observations)


def _verifier_cfg(max_age=180.0, min_eligible=2):
    return lambda: {"max_funding_age_s": max_age,
                    "min_eligible_venues_for_diff": min_eligible}


# ============================================================================
# Evidence Category 1 — Symbol mapping coverage across all venues
# ============================================================================

@pytest.mark.parametrize("vid,cls", list(VENUE_FUNDING_SOURCE_CLASSES.items()))
def test_symbol_mapping_round_trip_for_each_venue(vid, cls):
    """For each venue, validate that the source's _symbol_to_base() + the
    verifier's symbol-mapping validator agree on a canonical observation."""
    # Pick a representative native symbol for each venue
    examples = {
        "bybit":       "BTCUSDT",
        "okx":         "BTC-USDT-SWAP",
        "gate":        "BTC_USDT",
        "bitget":      "BTCUSDT",
        "mexc":        "BTC_USDT",
        "kucoin":      "XBTUSDTM",       # canonical-mapping test (XBT → BTC)
        "hyperliquid": "BTC",
    }
    venue_symbol = examples[vid]
    base = cls._symbol_to_base(venue_symbol)
    assert base == "BTC", f"{vid}: {venue_symbol} → {base}, expected BTC"

    obs = _obs(venue=vid, base=base, rate_pct=0.01,
                interval_h=cls.default_funding_interval_h,
                venue_symbol=venue_symbol)
    notes = validate_symbol_mapping(obs)
    assert notes == [], f"{vid}: unexpected normalisation notes {notes}"


def test_symbol_mapping_flags_non_canonical_subject_id():
    obs = _obs(venue="bybit", base="BTC-PERP", rate_pct=0.01)  # invalid
    notes = validate_symbol_mapping(obs)
    assert any("non_canonical_subject_id" in n for n in notes)


def test_symbol_mapping_flags_canonical_asset_mismatch():
    obs = _obs(venue="bybit", base="BTC", rate_pct=0.01)
    obs.canonical_asset = "BTC/USDT-PERP"   # tamper
    notes = validate_symbol_mapping(obs)
    assert any("canonical_asset_mismatch" in n for n in notes)


def test_symbol_mapping_flags_empty_venue_symbol():
    obs = _obs(venue="bybit", base="BTC", rate_pct=0.01)
    obs.venue_symbol = ""
    notes = validate_symbol_mapping(obs)
    assert "empty_venue_symbol" in notes


# ============================================================================
# Evidence Category 2 — Annualised funding for 1h and 8h
# ============================================================================

def test_annualise_8h_exact():
    # 0.01% per 8h → 0.01 × (24/8) × 365 = 10.95%
    assert annualise_funding(0.01, 8) == pytest.approx(10.95)


def test_annualise_1h_exact():
    # 0.001% per 1h → 0.001 × 24 × 365 = 8.76%
    assert annualise_funding(0.001, 1) == pytest.approx(8.76)


def test_annualise_4h_future_proof():
    # 0.005% per 4h → 0.005 × 6 × 365 = 10.95%
    assert annualise_funding(0.005, 4) == pytest.approx(10.95)


def test_annualise_negative_rate_preserves_sign():
    assert annualise_funding(-0.01, 8) == pytest.approx(-10.95)
    assert annualise_funding(-0.001, 1) == pytest.approx(-8.76)


def test_annualise_zero_or_negative_interval_safe():
    assert annualise_funding(0.05, 0) == 0.0
    assert annualise_funding(0.05, -8) == 0.0
    assert annualise_funding(0.05, None) == 0.0   # type: ignore[arg-type]


def test_known_funding_intervals_includes_1_and_8():
    assert 1 in KNOWN_FUNDING_INTERVALS_H
    assert 8 in KNOWN_FUNDING_INTERVALS_H


def test_validate_funding_interval_unknown_is_noted_not_dropped():
    notes = validate_funding_interval(3)        # unconventional but parseable
    assert notes and "unknown_funding_interval_h" in notes[0]
    notes = validate_funding_interval(0)
    assert "invalid_funding_interval_h" in notes[0]
    notes = validate_funding_interval(8)
    assert notes == []


# ============================================================================
# Evidence Category 3 — Funding direction correctness
# ============================================================================

def test_long_venue_is_min_apr_short_venue_is_max_apr():
    """Long the LOW-APR venue (capital earns funding by going long);
    short the HIGH-APR venue (capital earns funding by going short)."""
    bybit = _StubSource(venue="bybit",
                        provenance_id="bybit_futures_public",
                        observations=[_obs(venue="bybit", base="BTC",
                                            rate_pct=-0.005, interval_h=8)])
    okx = _StubSource(venue="okx",
                      provenance_id="okx_futures_public",
                      observations=[_obs(venue="okx", base="BTC",
                                          rate_pct=+0.015, interval_h=8)])
    v = FundingDifferentialVerifier(sources=[bybit, okx],
                                     config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("BTC"))
    d = ev.differential
    assert d is not None
    assert d.long_venue == "bybit"     # most-negative APR
    assert d.short_venue == "okx"      # most-positive APR
    # APRs: bybit -5.475%, okx +16.425%, diff 21.9 (≥0 by construction)
    assert d.long_funding_apr_pct == pytest.approx(-5.475)
    assert d.short_funding_apr_pct == pytest.approx(+16.425)
    assert d.differential_apr_pct == pytest.approx(21.9)
    assert d.differential_apr_pct >= 0


def test_direction_correct_for_both_positive():
    """Both venues positive: lower-positive is the long venue."""
    a = _StubSource(venue="a", provenance_id="a_futures_public",
                    observations=[_obs(venue="a", base="ETH", rate_pct=0.002)])
    b = _StubSource(venue="b", provenance_id="b_futures_public",
                    observations=[_obs(venue="b", base="ETH", rate_pct=0.008)])
    v = FundingDifferentialVerifier(sources=[a, b], config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("ETH"))
    assert ev.differential.long_venue == "a"
    assert ev.differential.short_venue == "b"
    assert ev.differential.differential_apr_pct > 0


def test_direction_correct_for_both_negative():
    """Both venues negative: less-negative is the short venue."""
    a = _StubSource(venue="a", provenance_id="a_futures_public",
                    observations=[_obs(venue="a", base="SOL", rate_pct=-0.010)])
    b = _StubSource(venue="b", provenance_id="b_futures_public",
                    observations=[_obs(venue="b", base="SOL", rate_pct=-0.003)])
    v = FundingDifferentialVerifier(sources=[a, b], config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("SOL"))
    assert ev.differential.long_venue == "a"      # more-negative
    assert ev.differential.short_venue == "b"     # less-negative
    assert ev.differential.differential_apr_pct > 0


def test_direction_correct_when_intervals_differ_across_venues():
    """Cross-interval differential must use APR (not raw per-interval rate)
    for direction. A small per-hour rate on Hyperliquid can dominate a
    larger per-8h rate elsewhere."""
    hl = _StubSource(venue="hyperliquid",
                     provenance_id="hyperliquid_public",
                     observations=[_obs(venue="hyperliquid", base="BTC",
                                         rate_pct=+0.002, interval_h=1)])
    bybit = _StubSource(venue="bybit",
                        provenance_id="bybit_futures_public",
                        observations=[_obs(venue="bybit", base="BTC",
                                            rate_pct=+0.005, interval_h=8)])
    v = FundingDifferentialVerifier(sources=[hl, bybit],
                                     config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("BTC"))
    # HL APR: 0.002 × 24 × 365 = 17.52%  (per hour → annual)
    # Bybit APR: 0.005 × 3 × 365 = 5.475%
    # ⇒ HL is short_venue (higher APR), Bybit is long_venue
    assert ev.differential.long_venue == "bybit"
    assert ev.differential.short_venue == "hyperliquid"
    assert ev.differential.short_funding_apr_pct == pytest.approx(17.52)
    assert ev.differential.long_funding_apr_pct == pytest.approx(5.475)


# ============================================================================
# Evidence Category 4 — Timestamp freshness safeguards
# ============================================================================

def test_freshness_gate_filters_stale_reads():
    fresh = _StubSource(venue="fresh", provenance_id="fresh_futures_public",
                        observations=[_obs(venue="fresh", base="BTC",
                                            rate_pct=0.002,
                                            observed_at=time.time())])
    stale = _StubSource(venue="stale", provenance_id="stale_futures_public",
                        observations=[_obs(venue="stale", base="BTC",
                                            rate_pct=0.010,
                                            observed_at=time.time() - 600.0)])
    v = FundingDifferentialVerifier(sources=[fresh, stale],
                                     config_loader=_verifier_cfg(max_age=180.0))
    ev = asyncio.run(v.compute_differential("BTC"))
    assert {r.venue for r in ev.stale_reads} == {"stale"}
    assert {r.venue for r in ev.eligible_reads} == {"fresh"}
    # Only one eligible → no differential, and the reason is noted.
    assert ev.differential is None
    assert any("insufficient_eligible_venues" in n for n in ev.verifier_notes)


def test_freshness_threshold_configurable():
    a = _StubSource(venue="a", provenance_id="a_futures_public",
                    observations=[_obs(venue="a", base="BTC",
                                        rate_pct=0.002,
                                        observed_at=time.time() - 90.0)])
    b = _StubSource(venue="b", provenance_id="b_futures_public",
                    observations=[_obs(venue="b", base="BTC",
                                        rate_pct=0.008,
                                        observed_at=time.time() - 90.0)])
    # Tight threshold: both stale → no differential
    v_strict = FundingDifferentialVerifier(sources=[a, b],
                                            config_loader=_verifier_cfg(max_age=30.0))
    ev_strict = asyncio.run(v_strict.compute_differential("BTC"))
    assert ev_strict.differential is None
    assert len(ev_strict.stale_reads) == 2
    # Lax threshold: both fresh → differential emitted
    v_lax = FundingDifferentialVerifier(sources=[a, b],
                                         config_loader=_verifier_cfg(max_age=120.0))
    ev_lax = asyncio.run(v_lax.compute_differential("BTC"))
    assert ev_lax.differential is not None


def test_age_s_populated_on_every_read():
    src = _StubSource(venue="x", provenance_id="x_futures_public",
                      observations=[_obs(venue="x", base="BTC",
                                          rate_pct=0.001,
                                          observed_at=time.time() - 45.0)])
    v = FundingDifferentialVerifier(sources=[src], config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("BTC"))
    assert len(ev.venue_reads) == 1
    r = ev.venue_reads[0]
    assert r.age_s >= 44.0 and r.age_s <= 50.0
    assert r.freshness_ok is True


# ============================================================================
# Evidence Category 5 — Differential evidence shape (deterministic)
# ============================================================================

def test_evidence_records_all_attempted_reads_including_failures():
    ok = _StubSource(venue="ok", provenance_id="ok_futures_public",
                     observations=[_obs(venue="ok", base="BTC", rate_pct=0.002)])
    empty = _StubSource(venue="empty", provenance_id="empty_futures_public",
                        observations=[])    # no BTC

    class _Boom(_BaseFundingSource):
        source_id = "venue_funding:boom"
        venue_id = "boom"
        venue_provenance_id = "boom_futures_public"
        async def _fetch_observations(self):
            raise RuntimeError("kaboom")
    boom = _Boom(config_loader=lambda: {"discovery_sources": {}})

    v = FundingDifferentialVerifier(sources=[ok, empty, boom],
                                     config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("BTC"))
    # Only the "ok" venue produces a read; the other two are recorded in notes.
    assert {r.venue for r in ev.venue_reads} == {"ok"}
    assert any("venue_funding:empty" in n for n in ev.verifier_notes)
    assert any("venue_funding:boom" in n and "exception" in n
                for n in ev.verifier_notes)


def test_evidence_to_dict_serialisable():
    src = _StubSource(venue="x", provenance_id="x_futures_public",
                      observations=[_obs(venue="x", base="BTC", rate_pct=0.001)])
    v = FundingDifferentialVerifier(sources=[src], config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("BTC"))
    d = ev.to_dict()
    assert isinstance(d, dict)
    assert d["asset_base"] == "BTC"
    assert d["canonical_asset"] == "BTC-PERP"
    assert isinstance(d["venue_reads"], list)


def test_min_eligible_venues_configurable():
    a = _StubSource(venue="a", provenance_id="a_futures_public",
                    observations=[_obs(venue="a", base="BTC", rate_pct=0.002)])
    b = _StubSource(venue="b", provenance_id="b_futures_public",
                    observations=[_obs(venue="b", base="BTC", rate_pct=0.008)])
    # Require 3 eligible venues — 2 reads → no differential
    v = FundingDifferentialVerifier(sources=[a, b],
                                     config_loader=_verifier_cfg(min_eligible=3))
    ev = asyncio.run(v.compute_differential("BTC"))
    assert ev.differential is None
    assert any("insufficient_eligible_venues" in n for n in ev.verifier_notes)


def test_invalid_asset_base_raises():
    v = FundingDifferentialVerifier(sources=[], config_loader=_verifier_cfg())
    with pytest.raises(ValueError):
        asyncio.run(v.compute_differential(""))


def test_asset_base_normalised_to_uppercase():
    src = _StubSource(venue="x", provenance_id="x_futures_public",
                      observations=[_obs(venue="x", base="BTC", rate_pct=0.001)])
    v = FundingDifferentialVerifier(sources=[src], config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("btc"))
    assert ev.asset_base == "BTC"
    assert ev.canonical_asset == "BTC-PERP"


# ============================================================================
# Normalisation notes propagate from sources through the verifier
# ============================================================================

def test_normalisation_notes_propagate_on_unconventional_interval():
    src = _StubSource(venue="weird", provenance_id="weird_futures_public",
                      observations=[_obs(venue="weird", base="BTC",
                                          rate_pct=0.002, interval_h=3)])
    v = FundingDifferentialVerifier(sources=[src], config_loader=_verifier_cfg())
    ev = asyncio.run(v.compute_differential("BTC"))
    r = ev.venue_reads[0]
    assert any("unknown_funding_interval_h" in n for n in r.normalization_notes)


# ============================================================================
# INV-2 / INV-3 static guards (AST-stripped: docstrings + comments removed)
# ============================================================================

def _code_without_docs_and_comments(mod) -> str:
    import ast, io, tokenize
    src = inspect.getsource(mod)
    tree = ast.parse(src)
    drop = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef,
                              ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                drop.append((body[0].lineno, body[0].end_lineno))
    lines = src.splitlines(keepends=True)
    keep = [True] * len(lines)
    for lo, hi in drop:
        for i in range(lo - 1, hi):
            if 0 <= i < len(keep):
                keep[i] = False
    stripped = "".join(l for l, k in zip(lines, keep) if k)
    tokens = [t for t in tokenize.generate_tokens(io.StringIO(stripped).readline)
              if t.type != tokenize.COMMENT]
    return tokenize.untokenize(tokens)


def test_inv2_engine_does_not_construct_canonical_opportunity():
    import arbicore.scanners.funding_arbitrage.verifier as mod
    code = _code_without_docs_and_comments(mod)
    assert "CanonicalOpportunity" not in code
    assert "EmissionBus" not in code
    assert "emission_bus" not in code


def test_inv3_engine_does_not_touch_source_data_quality():
    import arbicore.scanners.funding_arbitrage.verifier as mod
    code = _code_without_docs_and_comments(mod)
    assert "source_data_quality" not in code


# ============================================================================
# Evidence Category 5b — Differential with live venue data (best-effort,
# auto-skips if fewer than 2 venues respond).
# ============================================================================

@pytest.mark.asyncio_compat   # marker (not enforced) — keep visible to readers
def test_live_differential_btc_across_reachable_venues():
    from arbicore.scanners.funding_arbitrage.sources import (
        build_all_funding_sources,
    )
    sources = build_all_funding_sources(
        config_loader=lambda: {"discovery_sources": {}})
    v = FundingDifferentialVerifier(sources=sources, config_loader=_verifier_cfg())
    try:
        ev = asyncio.run(v.compute_differential("BTC"))
    finally:
        for s in sources:
            try: asyncio.run(s.close())
            except Exception: pass
    # The test is "best effort" — if fewer than 2 venues reach our cluster
    # we skip rather than fail (environmental, not a defect).
    if ev.eligible_count < 2:
        pytest.skip(f"only {ev.eligible_count} venue(s) reachable: "
                    f"{[r.venue for r in ev.eligible_reads]}")
    d = ev.differential
    assert d is not None
    assert d.long_venue != d.short_venue
    assert d.differential_apr_pct >= 0
    assert d.long_funding_apr_pct <= d.short_funding_apr_pct
