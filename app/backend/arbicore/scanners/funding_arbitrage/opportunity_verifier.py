"""ArbiCore X — Phase D D-2.0 Opportunity-emitting Funding Verifier.

The SINGLE call site that constructs a ``CanonicalOpportunity`` for the
``FUNDING_ARBITRAGE`` opportunity family. Composes three independent
read-only layers in order:

    1. ``FundingDifferentialVerifier`` — pure math (differential + freshness)
    2. ``FundingEconomicsAssessor``    — pure economics (cost / break-even / liquidity)
    3. ``run_universal_gates``         — universal Gates 2-5 (lifted to the shared
                                          gate pipeline during the D-2 substrate
                                          refactor)

A candidate must pass all three layers to materialise as a
``CanonicalOpportunity``. INV-1/INV-2/INV-3 are preserved by construction:

- INV-1 — ``DiscoveryCandidate`` is consumed, never sub-typed into the canonical.
- INV-2 — ``CanonicalOpportunity(...)`` is instantiated **at exactly one
  call site** in this file (function ``_build_canonical_opportunity``).
- INV-3 — ``source_data_quality`` is set from the WORST classification of
  the two venue reads' ``SOURCE_REGISTRY`` entries — never from
  ``candidate.hint_source`` (aggregator hints don't decide provenance).

Scope guard (operator-locked): no execution logic, no position management,
no Auto-Mode, no UI, no scanner orchestrator (orchestrator wires this up
in the next checkpoint). Calling this verifier returns
``(opportunity, outcome)``; the orchestrator emits it via the existing
``EmissionBus`` at the orchestrator's single call site.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from ...data.provenance import get_classification
from ...models.canonical import CanonicalOpportunity
from ...models.discovery import DiscoveryCandidate
from ...models.enums import (
    DataProvenance, MevRiskLevel, OpportunityStatus, OpportunityType,
)
from ..gates import GateContext, run_universal_gates
from ..opportunity_verifier import OpportunityVerifier
from .economics import EconomicAssessment, FundingEconomicsAssessor
from .verifier import (
    FundingDifferential, FundingDifferentialEvidence, FundingDifferentialVerifier,
)

logger = logging.getLogger("arbicore.scanners.funding_arb.opportunity_verifier")

# Outcome string prefixes — keep aligned with the CEX verifier's vocabulary so
# the scanner orchestrator's downstream aggregation (gate_rejections counter,
# gate-analysis endpoint) sees a uniform format.
_OUT_CONFIRMED      = "confirmed_canonical:funding_arbitrage"
_OUT_NO_DIFF        = "denied:venue_disagrees"
_OUT_ECON_PREFIX    = "denied:gate_rejection:economics"
_OUT_GATE_PREFIX    = "denied:gate_rejection"
_OUT_ERROR_PREFIX   = "error"

# Provenance ordering for INV-3 "worst-of" selection. Worst = lowest in this
# scale; an unknown classification is treated as DEAD.
_PROVENANCE_ORDER: Dict[DataProvenance, int] = {
    DataProvenance.DEAD:           0,
    DataProvenance.CONTAMINATED:   1,
    DataProvenance.SIMULATED:      2,
    DataProvenance.REAL:           3,
    DataProvenance.VERIFIED_REAL:  4,
}


def _worst_provenance(*provenance_ids: str) -> DataProvenance:
    """Return the LEAST-trustworthy classification across the given source
    IDs. Implements INV-3: every CanonicalOpportunity's source_data_quality
    derives from the venue read's SOURCE_REGISTRY classification (the worst
    of the two legs), never from a hint source.
    """
    worst = DataProvenance.VERIFIED_REAL
    worst_rank = _PROVENANCE_ORDER[worst]
    for sid in provenance_ids:
        cls = get_classification(sid) or DataProvenance.DEAD
        if _PROVENANCE_ORDER.get(cls, 0) < worst_rank:
            worst = cls
            worst_rank = _PROVENANCE_ORDER.get(cls, 0)
    return worst


# Type alias: (venue, base) -> awaitable[Optional[float]] depth in USD.
DepthFetcher = Callable[[str, str], Awaitable[Optional[float]]]


class FundingOpportunityVerifier(OpportunityVerifier):
    """The single emission point for FUNDING_ARBITRAGE canonicals."""

    opportunity_type = OpportunityType.FUNDING_ARBITRAGE

    def __init__(
        self, *,
        differential_engine: FundingDifferentialVerifier,
        economics_assessor: FundingEconomicsAssessor,
        venue_capability_repo: Any,
        config_loader: Callable[[], Dict[str, Any]],
        confidence_engine: Any = None,
        depth_fetcher: Optional[DepthFetcher] = None,
    ) -> None:
        self._diff      = differential_engine
        self._economics = economics_assessor
        self._caps      = venue_capability_repo
        self._cfg       = config_loader
        self._conf      = confidence_engine
        self._depth_fetcher = depth_fetcher
        # Survivorship counters — useful for diagnostics / the survivorship
        # report; not part of the OpportunityVerifier ABC contract.
        self.stats: Dict[str, int] = {
            "total_candidates": 0,
            "differential_survivors": 0,
            "economics_survivors": 0,
            "gate_2_survivors": 0,
            "gate_3_survivors": 0,
            "gate_4_survivors": 0,
            "gate_5_survivors": 0,
            "emissions": 0,
        }

    # ──────────────────────────────────────────────────────────────────────
    # OpportunityVerifier contract
    # ──────────────────────────────────────────────────────────────────────

    async def verify(self, candidate: DiscoveryCandidate
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        self.stats["total_candidates"] += 1

        # 1. Differential verification (math).
        try:
            evidence = await self._diff.compute_differential(candidate.subject_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception("differential read failed: %s", exc)
            return None, f"{_OUT_ERROR_PREFIX}:differential:{exc!r}"
        if evidence.differential is None:
            return None, _OUT_NO_DIFF
        self.stats["differential_survivors"] += 1
        diff = evidence.differential

        # 2. Depth lookups (optional). The verifier never CONSTRUCTS a depth;
        #    it asks the operator-supplied fetcher and accepts None if absent.
        long_depth: Optional[float] = None
        short_depth: Optional[float] = None
        if self._depth_fetcher is not None:
            try:
                long_depth  = await self._depth_fetcher(diff.long_venue, diff.asset_base)
                short_depth = await self._depth_fetcher(diff.short_venue, diff.asset_base)
            except Exception as exc:  # noqa: BLE001
                logger.warning("depth_fetcher raised: %s", exc)

        # 3. Economics assessment.
        assessment = self._economics.assess(
            diff,
            capital_required_usd=self._cfg().get("default_notional_usd"),
            long_leg_depth_usd=long_depth,
            short_leg_depth_usd=short_depth,
        )
        if assessment.is_economically_actionable is False:
            note = (assessment.economics_notes[0]
                    if assessment.economics_notes else "unknown")
            return None, f"{_OUT_ECON_PREFIX}:{note}"
        # None (inconclusive — usually missing depth) is allowed through;
        # Gate 2 (liquidity) will catch it with full context if depths still
        # are not present.
        self.stats["economics_survivors"] += 1

        # 4. Build the (provisional) canonical opportunity — the SINGLE
        #    instantiation site for FUNDING_ARBITRAGE canonicals (INV-2).
        opp = _build_canonical_opportunity(
            candidate=candidate,
            evidence=evidence,
            assessment=assessment,
            long_depth_usd=long_depth,
            short_depth_usd=short_depth,
        )

        # 5. Universal Gates 2-5.
        gate_ctx = GateContext(
            cfg=self._cfg() or {},
            venue_caps=self._caps,
            buy_venue=diff.long_venue,
            sell_venue=diff.short_venue,
            buy_side_depth_usd=float(long_depth or 0.0),
            sell_side_depth_usd=float(short_depth or 0.0),
            confidence_engine=self._conf,
        )
        thresholds = _resolve_funding_thresholds(self._cfg() or {},
                                                  diff.asset_base)
        # Gate 2 — Liquidity
        passed, gate_n, reason = await run_universal_gates(
            opp, gate_ctx, thresholds)
        if not passed:
            opp.metadata["rejected_gate_name"]   = reason.split(":", 1)[0]
            opp.metadata["rejected_gate_number"] = gate_n
            opp.metadata["rejected_gate_reason"] = reason
            opp.mark_rejected(reason)
            return opp, f"{_OUT_GATE_PREFIX}:{reason}"

        # Update survivorship counters for the 4 universal gates (gate_n=0
        # on pass, so we credit every gate when the entire pipeline passes).
        self.stats["gate_2_survivors"] += 1
        self.stats["gate_3_survivors"] += 1
        self.stats["gate_4_survivors"] += 1
        self.stats["gate_5_survivors"] += 1

        # 6. Confirmed. Mark validated. The scanner orchestrator (separate
        #    module, separate checkpoint) is the entity that calls
        #    EmissionBus emit exactly once for this opportunity.
        opp.mark_validated()
        self.stats["emissions"] += 1
        return opp, f"{_OUT_CONFIRMED}:{diff.asset_base}:" \
                    f"{diff.long_venue}->{diff.short_venue}:" \
                    f"{diff.differential_apr_pct:.3f}apr"


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────


def _resolve_funding_thresholds(cfg: Dict[str, Any],
                                 asset_base: Optional[str]) -> Dict[str, float]:
    """Per-asset Gate 2-5 threshold resolution. Mirrors the CEX
    ``_thresholds_for`` shape exactly, so the universal-gate code path
    is identical."""
    gt = (cfg.get("gate_thresholds") or {})
    default = gt.get("default", {"min_funding_diff_apr_pct": 5.0,
                                  "min_depth_usd": 5_000.0,
                                  "min_confidence": 55.0})
    if asset_base and asset_base in gt:
        out = dict(default)
        out.update(gt[asset_base])
        return out
    return dict(default)


def _build_canonical_opportunity(
    *, candidate: DiscoveryCandidate,
    evidence: FundingDifferentialEvidence,
    assessment: EconomicAssessment,
    long_depth_usd: Optional[float],
    short_depth_usd: Optional[float],
) -> CanonicalOpportunity:
    """The ONE place in the funding subsystem that constructs a
    CanonicalOpportunity. INV-2 static guard verifies there is exactly
    one ``CanonicalOpportunity(`` call site in this module."""
    diff = evidence.differential
    assert diff is not None  # caller guarantee

    long_read  = diff.long_read
    short_read = diff.short_read

    # INV-3: provenance from venue reads, never from candidate.hint_source.
    sdq = _worst_provenance(long_read.venue_provenance_id,
                             short_read.venue_provenance_id)

    # Funding-revenue projection (estimate, not instruction).
    notional = assessment.capital_required_usd
    expected_profit_usd = (notional
                            * (diff.differential_apr_pct / 100.0)
                            * (assessment.max_break_even_hours / 8760.0))

    # Liquidity score 0-1: ratio of available depth vs requested notional.
    # 0.0 when no depth info — Gate 2 will then handle it with its own
    # threshold over absolute depth, not the score.
    if long_depth_usd and short_depth_usd:
        lscore = min(1.0, min(long_depth_usd, short_depth_usd)
                            / max(1.0, notional * 5.0))
    else:
        lscore = 0.0

    return CanonicalOpportunity(
        opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
        subject_id=diff.asset_base,
        asset=diff.canonical_asset,
        buy_venue=diff.long_venue,
        sell_venue=diff.short_venue,
        buy_price=long_read.mark_price,
        sell_price=short_read.mark_price,
        # Per operator confirmation #2 (substrate refactor checkpoint):
        # spread_pct reused as the scanner's PRIMARY ECONOMIC METRIC. For
        # funding this is the cross-venue annualised funding differential.
        spread_pct=diff.differential_apr_pct,
        expected_profit_usd=round(expected_profit_usd, 4),
        capital_required_usd=notional,
        liquidity_score=lscore,
        confidence_score=0.0,                       # populated by Gate 4
        risk_score=0.0,
        execution_feasibility=0.0,
        mev_risk_level=MevRiskLevel.LOW,
        source_data_quality=sdq,                    # INV-3
        status=OpportunityStatus.CANDIDATE,
        metadata={
            "scanner_id":       "funding_arb",
            "primary_metric":   "funding_diff_apr_pct",
            "discovery_source": candidate.hint_source,
            "candidate_id":     candidate.candidate_id,
            "long_provenance":  long_read.venue_provenance_id,
            "short_provenance": short_read.venue_provenance_id,
            "long_age_s":       round(long_read.age_s, 3),
            "short_age_s":      round(short_read.age_s, 3),
            "verifier_notes":   evidence.verifier_notes,
            "economics_notes":  assessment.economics_notes,
        },
        category_metadata={
            "long_venue_funding_rate_pct":  long_read.funding_rate_pct_per_interval,
            "short_venue_funding_rate_pct": short_read.funding_rate_pct_per_interval,
            "long_funding_interval_h":      long_read.funding_interval_h,
            "short_funding_interval_h":     short_read.funding_interval_h,
            "long_funding_apr_pct":         long_read.funding_apr_pct,
            "short_funding_apr_pct":        short_read.funding_apr_pct,
            "funding_diff_apr_pct":         diff.differential_apr_pct,
            "next_funding_time_long_iso":   long_read.next_funding_iso,
            "next_funding_time_short_iso":  short_read.next_funding_iso,
            "long_perp_mark_price":         long_read.mark_price,
            "short_perp_mark_price":        short_read.mark_price,
            "long_perp_index_price":        long_read.index_price,
            "short_perp_index_price":       short_read.index_price,
            "long_open_interest_usd":       long_read.open_interest_usd,
            "short_open_interest_usd":      short_read.open_interest_usd,
            "long_depth_usd":               long_depth_usd,
            "short_depth_usd":              short_depth_usd,
            "total_round_trip_cost_pct":    assessment.total_round_trip_cost_pct,
            "break_even_hours":             assessment.break_even_hours
                                              if assessment.break_even_hours
                                                 != float("inf") else None,
        },
    )
