"""ArbiCore X — Phase D D-2.0 Opportunity-emitting Funding Verifier tests."""
from __future__ import annotations

import asyncio
import inspect
import time
from typing import Optional

import pytest

from arbicore.models.canonical import CanonicalOpportunity
from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import DataProvenance, OpportunityStatus, OpportunityType
from arbicore.scanners.funding_arbitrage.economics import FundingEconomicsAssessor
from arbicore.scanners.funding_arbitrage.opportunity_verifier import (
    FundingOpportunityVerifier,
    _build_canonical_opportunity,
    _worst_provenance,
)
from arbicore.scanners.funding_arbitrage.sources import (
    FundingObservation, _BaseFundingSource,
)
from arbicore.scanners.funding_arbitrage.verifier import (
    FundingDifferentialVerifier,
)


# ──────────────────────── fixtures ────────────────────────

class _StubSource(_BaseFundingSource):
    source_id = ""
    def __init__(self, *, venue, observations, provenance_id):
        super().__init__(config_loader=lambda: {"discovery_sources": {}})
        self.source_id = f"venue_funding:{venue}"
        self.venue_id = venue
        self.venue_provenance_id = provenance_id
        self._observations = observations
    async def _fetch_observations(self):
        return list(self._observations)


def _obs(venue, base, rate_pct, interval_h=8):
    return FundingObservation(
        venue=venue, venue_symbol=f"{base}{venue.upper()}",
        subject_id=base, canonical_asset=f"{base}-PERP",
        funding_rate_pct=rate_pct, funding_interval_h=interval_h,
        next_funding_ts=time.time()+3600.0, mark_price=65000.0,
        index_price=65005.0, open_interest_usd=1_000_000.0,
        source_observed_at_ts=time.time(), raw={"_t": True},
    )


class _StubCaps:
    """Permissive funding capability stub — both venues always pass Gate 3."""
    def __init__(self, listed=True):
        self._listed = listed
    async def is_gate_3_pass(self, venue, base, quote):
        return self._listed, "ok" if self._listed else "no_perp_market"


def _candidate(base="BTC"):
    return DiscoveryCandidate(
        candidate_id="test:funding:BTC:1",
        opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        hint_source="venue_funding:gate",
        hint_observed_at=time.time(),
        subject_id=base, asset=f"{base}-PERP",
        candidate_venues=["gate"],
        hint_metric={}, reason="test_hint",
    )


def _build_verifier(*, sources, depths=None, conf=None, cfg=None):
    diff_engine = FundingDifferentialVerifier(
        sources=sources,
        config_loader=lambda: {"max_funding_age_s": 180.0,
                                "min_eligible_venues_for_diff": 2})
    econ = FundingEconomicsAssessor(config_loader=lambda: {
        "min_diff_apr_pct": 5.0, "max_break_even_hours": 200.0,
        "default_notional_usd": 1000.0, "depth_safety_factor": 5.0,
        "min_position_usd": 100.0,
    })
    async def _fetcher(venue, base):
        return (depths or {}).get(venue)
    return FundingOpportunityVerifier(
        differential_engine=diff_engine,
        economics_assessor=econ,
        venue_capability_repo=_StubCaps(),
        config_loader=lambda: cfg or {
            "default_notional_usd": 1000.0,
            "gate_thresholds": {"default": {"min_funding_diff_apr_pct": 5.0,
                                              "min_depth_usd": 5000.0,
                                              "min_confidence": 55.0}},
        },
        confidence_engine=conf,
        depth_fetcher=_fetcher if depths is not None else None,
    )


# ──────────────────────── happy path ────────────────────────

def test_full_pipeline_emits_canonical_when_all_gates_pass():
    sources = [
        _StubSource(venue="okx", provenance_id="okx_futures_public",
                    observations=[_obs("okx", "BTC", -0.005)]),     # APR -5.475
        _StubSource(venue="hyperliquid", provenance_id="hyperliquid_public",
                    observations=[_obs("hyperliquid", "BTC", 0.001, interval_h=1)]),  # APR 8.76
    ]
    v = _build_verifier(sources=sources,
                         depths={"okx": 50_000.0, "hyperliquid": 60_000.0})
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is not None
    assert opp.opportunity_type is OpportunityType.FUNDING_ARBITRAGE
    assert opp.subject_id == "BTC"
    assert opp.asset == "BTC-PERP"
    assert opp.buy_venue == "okx"
    assert opp.sell_venue == "hyperliquid"
    assert opp.spread_pct == pytest.approx(8.76 - (-5.475))
    assert opp.status is OpportunityStatus.VALIDATED
    assert opp.source_data_quality is DataProvenance.REAL
    assert outcome.startswith("confirmed_canonical:funding_arbitrage:BTC:")
    # Counters
    assert v.stats == {"total_candidates": 1, "differential_survivors": 1,
                        "economics_survivors": 1, "gate_2_survivors": 1,
                        "gate_3_survivors": 1, "gate_4_survivors": 1,
                        "gate_5_survivors": 1, "emissions": 1}
    # category_metadata carries every expected key
    cm = opp.category_metadata
    for k in ("long_venue_funding_rate_pct", "short_venue_funding_rate_pct",
              "long_funding_interval_h", "short_funding_interval_h",
              "funding_diff_apr_pct", "total_round_trip_cost_pct",
              "break_even_hours"):
        assert k in cm


# ──────────────────────── differential gate ────────────────────────

def test_returns_no_diff_when_only_one_venue_responds():
    sources = [
        _StubSource(venue="gate", provenance_id="gate_futures_public",
                    observations=[_obs("gate", "BTC", 0.01)]),
        # empty venue
        _StubSource(venue="empty", provenance_id="okx_futures_public",
                    observations=[]),
    ]
    v = _build_verifier(sources=sources)
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is None
    assert outcome == "denied:venue_disagrees"
    assert v.stats["differential_survivors"] == 0


# ──────────────────────── economics gate ────────────────────────

def test_rejects_when_break_even_too_long():
    sources = [
        _StubSource(venue="okx", provenance_id="okx_futures_public",
                    observations=[_obs("okx", "BTC", 0.001)]),     # APR 1.1
        _StubSource(venue="gate", provenance_id="gate_futures_public",
                    observations=[_obs("gate", "BTC", 0.006)]),    # APR 6.57
        # Diff ≈ 5.475% — passes min, but with 0.20% RT cost ⇒ BE ≈ 320h
    ]
    v = _build_verifier(sources=sources,
                         depths={"okx": 50_000.0, "gate": 50_000.0},
                         cfg={"default_notional_usd": 1000.0,
                              "gate_thresholds": {"default": {
                                  "min_funding_diff_apr_pct": 5.0,
                                  "min_depth_usd": 5000.0,
                                  "min_confidence": 55.0}}})
    # Override econ config to be strict on BE.
    v._economics = FundingEconomicsAssessor(config_loader=lambda: {
        "min_diff_apr_pct": 5.0, "max_break_even_hours": 24.0,
        "default_notional_usd": 1000.0, "depth_safety_factor": 5.0,
        "min_position_usd": 100.0,
    })
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is None
    assert outcome.startswith("denied:gate_rejection:economics:break_even_too_long")
    assert v.stats["economics_survivors"] == 0


def test_rejects_on_min_diff_threshold():
    sources = [
        _StubSource(venue="okx", provenance_id="okx_futures_public",
                    observations=[_obs("okx", "BTC", 0.001)]),
        _StubSource(venue="gate", provenance_id="gate_futures_public",
                    observations=[_obs("gate", "BTC", 0.0015)]),  # tiny diff
    ]
    v = _build_verifier(sources=sources, depths={"okx": 50_000.0, "gate": 50_000.0})
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is None
    assert "min_diff_threshold" in outcome


# ──────────────────────── universal gate rejections ────────────────────────

def test_gate_2_liquidity_rejection_when_depth_below_threshold():
    sources = [
        _StubSource(venue="okx", provenance_id="okx_futures_public",
                    observations=[_obs("okx", "BTC", -0.005)]),
        _StubSource(venue="hyperliquid", provenance_id="hyperliquid_public",
                    observations=[_obs("hyperliquid", "BTC", 0.001, interval_h=1)]),
    ]
    # Pass economics with $50k depths so we reach the gate stage,
    # but Gate-2 will see thin order book depth via the gate context.
    v = _build_verifier(sources=sources,
                         depths={"okx": 50_000.0, "hyperliquid": 50_000.0},
                         cfg={"default_notional_usd": 1000.0,
                              "gate_thresholds": {"default": {
                                  "min_funding_diff_apr_pct": 5.0,
                                  "min_depth_usd": 100_000.0,  # very high
                                  "min_confidence": 55.0}}})
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is not None         # built but rejected
    assert opp.status is OpportunityStatus.REJECTED
    assert outcome.startswith("denied:gate_rejection:liquidity")
    assert opp.metadata["rejected_gate_number"] == 2


def test_gate_3_venue_capability_rejection():
    sources = [
        _StubSource(venue="okx", provenance_id="okx_futures_public",
                    observations=[_obs("okx", "BTC", -0.005)]),
        _StubSource(venue="hyperliquid", provenance_id="hyperliquid_public",
                    observations=[_obs("hyperliquid", "BTC", 0.001, interval_h=1)]),
    ]
    v = _build_verifier(sources=sources,
                         depths={"okx": 50_000.0, "hyperliquid": 50_000.0})
    v._caps = _StubCaps(listed=False)
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is not None
    assert opp.status is OpportunityStatus.REJECTED
    assert outcome.startswith("denied:gate_rejection:venue_capability")
    assert opp.metadata["rejected_gate_number"] == 3


def test_gate_4_confidence_rejection_with_low_score_engine():
    class _BadConf:
        async def score_with_breakdown(self, opp):
            return {"overall": 30.0}
    sources = [
        _StubSource(venue="okx", provenance_id="okx_futures_public",
                    observations=[_obs("okx", "BTC", -0.005)]),
        _StubSource(venue="hyperliquid", provenance_id="hyperliquid_public",
                    observations=[_obs("hyperliquid", "BTC", 0.001, interval_h=1)]),
    ]
    v = _build_verifier(sources=sources,
                         depths={"okx": 50_000.0, "hyperliquid": 50_000.0},
                         conf=_BadConf())
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is not None
    assert opp.status is OpportunityStatus.REJECTED
    assert outcome.startswith("denied:gate_rejection:confidence")
    assert opp.metadata["rejected_gate_number"] == 4


# ──────────────────────── INV-3: worst-of provenance ────────────────────────

def test_worst_of_provenance_selects_lower_trust():
    # All D-2 venue futures sources are REAL → worst = REAL.
    assert _worst_provenance("bybit_futures_public",
                              "okx_futures_public") is DataProvenance.REAL
    # If one of them somehow returned None (unknown source), we
    # conservatively treat it as DEAD.
    assert _worst_provenance("nonexistent_source",
                              "okx_futures_public") is DataProvenance.DEAD


def test_source_data_quality_does_NOT_come_from_hint_source():
    """INV-3: even if the candidate's hint_source is an aggregator (e.g.
    coinglass_funding_public), the canonical's source_data_quality comes
    from the venue read provenance ids, not the hint."""
    sources = [
        _StubSource(venue="okx", provenance_id="okx_futures_public",
                    observations=[_obs("okx", "BTC", -0.005)]),
        _StubSource(venue="hyperliquid", provenance_id="hyperliquid_public",
                    observations=[_obs("hyperliquid", "BTC", 0.001, interval_h=1)]),
    ]
    v = _build_verifier(sources=sources,
                         depths={"okx": 50_000.0, "hyperliquid": 50_000.0})
    cand = _candidate()
    cand.hint_source = "coinglass_funding_public"   # aggregator hint
    opp, _ = asyncio.run(v.verify(cand))
    # If hint_source had decided provenance, it would still be REAL anyway;
    # the better test is that long/short provenance ids appear in metadata
    # AND the hint_source is recorded separately under 'discovery_source'.
    assert opp.metadata["discovery_source"] == "coinglass_funding_public"
    assert opp.metadata["long_provenance"]  == "okx_futures_public"
    assert opp.metadata["short_provenance"] == "hyperliquid_public"
    assert opp.source_data_quality is DataProvenance.REAL


# ──────────────────────── INV-2: single emission call site ────────────────────────

def _strip(mod) -> str:
    import ast, io, tokenize
    src = inspect.getsource(mod)
    tree = ast.parse(src); drop = []
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.FunctionDef,
                           ast.AsyncFunctionDef, ast.ClassDef)):
            b = getattr(n, "body", None)
            if b and isinstance(b[0], ast.Expr) and \
               isinstance(b[0].value, ast.Constant) and \
               isinstance(b[0].value.value, str):
                drop.append((b[0].lineno, b[0].end_lineno))
    lines = src.splitlines(keepends=True)
    keep = [True]*len(lines)
    for lo, hi in drop:
        for i in range(lo-1, hi):
            if 0 <= i < len(keep): keep[i] = False
    stripped = "".join(l for l, k in zip(lines, keep) if k)
    toks = [t for t in tokenize.generate_tokens(io.StringIO(stripped).readline)
            if t.type != tokenize.COMMENT]
    return tokenize.untokenize(toks)


def test_inv2_single_canonical_opportunity_call_site():
    """The opportunity-verifier module must construct a CanonicalOpportunity
    in exactly ONE place. Detected by counting `CanonicalOpportunity(`
    occurrences in the code (docstrings + comments stripped)."""
    import arbicore.scanners.funding_arbitrage.opportunity_verifier as mod
    code = _strip(mod)
    assert code.count("CanonicalOpportunity(") == 1, (
        "INV-2 violated: multiple CanonicalOpportunity construction sites")


def test_inv2_no_emission_bus_in_verifier_module():
    """The verifier returns the canonical; the orchestrator emits it. The
    verifier itself must not touch EmissionBus directly."""
    import arbicore.scanners.funding_arbitrage.opportunity_verifier as mod
    code = _strip(mod)
    assert "EmissionBus" not in code
    assert "emission_bus" not in code


# ──────────────────────── error path ────────────────────────

def test_differential_engine_exception_returns_error_outcome():
    class _Boom:
        async def compute_differential(self, base):
            raise RuntimeError("kaboom")
    econ = FundingEconomicsAssessor(config_loader=lambda: {})
    v = FundingOpportunityVerifier(
        differential_engine=_Boom(),
        economics_assessor=econ,
        venue_capability_repo=_StubCaps(),
        config_loader=lambda: {},
    )
    opp, outcome = asyncio.run(v.verify(_candidate()))
    assert opp is None
    assert outcome.startswith("error:differential:")
