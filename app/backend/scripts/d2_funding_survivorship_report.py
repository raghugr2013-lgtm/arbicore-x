"""Funding Opportunity Survivorship Report — D-2 final-step validation.

Polls every D-2 funding source once, builds a DiscoveryCandidate per
asset present on ≥2 venues, runs the FULL FundingOpportunityVerifier
pipeline (differential → economics → universal Gates 2-5), and reports
the funnel with per-asset and per-venue-pair breakdowns.

The venue capability repo is pre-populated FROM the live observations
themselves — every (venue, base) we actually polled is positive
evidence of a listed perp; absent (venue, base) ⇒ Gate-3 fails.

NOT yet wired into the live event-bus; this is the final D-2 validation
deliverable before the scanner orchestrator wires the verifier into
EmissionBus emission in a separate checkpoint.
"""
import asyncio
import time
from collections import Counter, defaultdict
from typing import Any, Dict, Optional

from arbicore.models.discovery import DiscoveryCandidate
from arbicore.models.enums import OpportunityType
from arbicore.scanners.funding_arbitrage.economics import FundingEconomicsAssessor
from arbicore.scanners.funding_arbitrage.opportunity_verifier import (
    FundingOpportunityVerifier,
)
from arbicore.scanners.funding_arbitrage.sources import (
    build_all_funding_sources, FundingObservation, _BaseFundingSource,
)
from arbicore.scanners.funding_arbitrage.verifier import (
    FundingDifferentialVerifier,
)


# ── Synthetic depth assumption (real depths arrive in next checkpoint) ──
SYNTHETIC_DEPTH_USD = 50_000.0


# ── Synthetic capability repo populated from live observations ──

class _InMemoryCaps:
    """Funding capability repo backed by the live observations we already
    polled — every (venue, base) actually returned is evidence of a perp
    listing. is_gate_3_pass returns True iff BOTH legs were observed."""
    def __init__(self):
        self.listings: Dict[str, set] = defaultdict(set)   # venue → {base, …}
    def absorb(self, observations):
        for o in observations:
            self.listings[o.venue].add(o.subject_id)
    async def is_gate_3_pass(self, venue, asset_base, _quote="USDT"):
        if asset_base not in self.listings.get(venue, set()):
            return False, f"perp_not_listed:{asset_base}"
        return True, "ok"


class _AllInOnePollSources:
    """Wraps the real venue sources but serves observations from a single
    poll cached at construction. Avoids hammering every venue for every
    asset across the entire universe."""
    def __init__(self, base_source: _BaseFundingSource,
                 cached_observations):
        self._base = base_source
        self._cache = cached_observations
    @property
    def source_id(self):     return self._base.source_id
    @property
    def venue_id(self):      return self._base.venue_id
    @property
    def venue_provenance_id(self): return self._base.venue_provenance_id
    async def _fetch_observations(self):
        return list(self._cache)
    @property
    def _last_verifier_read_error(self):
        return getattr(self._base, "_last_verifier_read_error", None)
    @_last_verifier_read_error.setter
    def _last_verifier_read_error(self, v):
        setattr(self._base, "_last_verifier_read_error", v)


async def poll_universe():
    sources = build_all_funding_sources(
        config_loader=lambda: {"discovery_sources": {}})
    by_venue: Dict[str, list] = {}
    try:
        for s in sources:
            try:
                obs = await s._fetch_observations()
            except Exception:
                obs = []
            by_venue[s.venue_id] = obs
    finally:
        for s in sources:
            try: await s.close()
            except Exception: pass
    return sources, by_venue


def build_universe(by_venue):
    universe: Dict[str, Dict[str, FundingObservation]] = defaultdict(dict)
    for v, obs_list in by_venue.items():
        for o in obs_list:
            universe[o.subject_id][v] = o
    return universe


async def run_funnel():
    sources, by_venue = await poll_universe()
    universe = build_universe(by_venue)

    # Pre-populate capability repo from live observations.
    caps = _InMemoryCaps()
    for v, obs_list in by_venue.items():
        caps.absorb(obs_list)

    # Wrap sources so each can serve its cached observations to the verifier
    # without re-polling for every asset.
    wrapped = [
        _AllInOnePollSources(s, by_venue[s.venue_id])
        for s in sources
    ]
    diff_engine = FundingDifferentialVerifier(
        sources=wrapped,
        config_loader=lambda: {"max_funding_age_s": 600.0,
                                "min_eligible_venues_for_diff": 2})
    econ = FundingEconomicsAssessor(config_loader=lambda: {
        "min_diff_apr_pct": 5.0, "max_break_even_hours": 24.0,
        "default_notional_usd": 1000.0, "depth_safety_factor": 5.0,
        "min_position_usd": 100.0,
    })

    async def _depth_fetcher(venue, base):
        return SYNTHETIC_DEPTH_USD   # uniform synthetic depth

    verifier = FundingOpportunityVerifier(
        differential_engine=diff_engine,
        economics_assessor=econ,
        venue_capability_repo=caps,
        config_loader=lambda: {
            "default_notional_usd": 1000.0,
            "gate_thresholds": {"default": {
                "min_funding_diff_apr_pct": 5.0,
                "min_depth_usd": 5000.0,
                "min_confidence": 55.0}},
        },
        depth_fetcher=_depth_fetcher,
    )

    # Build one candidate per asset present on ≥2 venues.
    candidates = []
    for base, by_v in universe.items():
        if len(by_v) < 2:
            continue
        candidates.append(DiscoveryCandidate(
            candidate_id=f"funnel:{base}:{int(time.time())}",
            opportunity_type=OpportunityType.FUNDING_ARBITRAGE,
            hint_source="venue_funding:internal",
            hint_observed_at=time.time(),
            subject_id=base, asset=f"{base}-PERP",
            candidate_venues=list(by_v.keys()),
            hint_metric={}, reason="funnel",
        ))

    # Run verifier on every candidate.
    per_outcome = Counter()
    per_venue_pair: Counter = Counter()
    per_asset_outcome: Dict[str, str] = {}
    emissions = []
    for c in candidates:
        opp, outcome = await verifier.verify(c)
        outcome_token = outcome.split(":", 2)[1] if outcome.startswith("denied:") \
                          else outcome.split(":", 1)[0]
        per_outcome[outcome] += 1
        per_asset_outcome[c.subject_id] = outcome
        if opp is not None and outcome.startswith("confirmed_canonical"):
            pair = f"{opp.buy_venue}->{opp.sell_venue}"
            per_venue_pair[pair] += 1
            emissions.append((c.subject_id, opp))

    return verifier, candidates, per_outcome, per_venue_pair, emissions, by_venue, caps


def print_report(verifier, candidates, per_outcome, per_venue_pair, emissions,
                  by_venue, caps):
    print("=" * 72)
    print("D-2 FUNDING OPPORTUNITY SURVIVORSHIP REPORT")
    print(f"Captured at unix={int(time.time())}")
    print("=" * 72)
    print(f"\nVenue raw observations this poll:")
    for v in sorted(by_venue):
        print(f"  {v:<15s} {len(by_venue[v]):>5d}")
    total_listings = sum(len(s) for s in caps.listings.values())
    print(f"\nLive perp listings absorbed into capability repo: {total_listings}")

    print("\n" + "=" * 72)
    print("FUNNEL — system-wide counters from FundingOpportunityVerifier.stats")
    print("=" * 72)
    print(f"  total_candidates        : {verifier.stats['total_candidates']}")
    print(f"  differential_survivors  : {verifier.stats['differential_survivors']}")
    print(f"  economics_survivors     : {verifier.stats['economics_survivors']}")
    print(f"  gate_2_survivors        : {verifier.stats['gate_2_survivors']}")
    print(f"  gate_3_survivors        : {verifier.stats['gate_3_survivors']}")
    print(f"  gate_4_survivors        : {verifier.stats['gate_4_survivors']}")
    print(f"  gate_5_survivors        : {verifier.stats['gate_5_survivors']}")
    print(f"  emissions               : {verifier.stats['emissions']}")

    print("\n" + "=" * 72)
    print("OUTCOME BREAKDOWN")
    print("=" * 72)
    for outcome, n in sorted(per_outcome.items(), key=lambda x: -x[1])[:30]:
        # Truncate noisy long outcome strings.
        short = outcome if len(outcome) < 78 else outcome[:75] + "..."
        print(f"  {short:<78s} {n:>5d}")
    if len(per_outcome) > 30:
        print(f"  ... ({len(per_outcome) - 30} more outcome variants)")

    print("\n" + "=" * 72)
    print("EMISSIONS BY VENUE PAIR (top 30)")
    print("=" * 72)
    if not per_venue_pair:
        print("  (no emissions this run — see funnel above)")
    for pair, n in per_venue_pair.most_common(30):
        print(f"  {pair:<40s} {n:>5d}")

    print("\n" + "=" * 72)
    print("EMITTED CANONICAL OPPORTUNITIES (top 30 by diff APR)")
    print("=" * 72)
    emissions_sorted = sorted(emissions,
                                key=lambda x: x[1].spread_pct or 0,
                                reverse=True)[:30]
    if not emissions_sorted:
        print("  (no emissions)")
    print(f"  {'asset':<10}{'diff_apr%':>10}  {'buy':<14}{'sell':<14}"
          f"  {'BE_h':>8}  {'sdq':<6}")
    for base, opp in emissions_sorted:
        be = opp.category_metadata.get("break_even_hours")
        be_str = f"{be:.1f}" if be is not None else "—"
        sdq = (opp.source_data_quality.value
                if hasattr(opp.source_data_quality, "value")
                else str(opp.source_data_quality))
        print(f"  {base:<10}{(opp.spread_pct or 0):>10.3f}  "
              f"{(opp.buy_venue or ''):<14}{(opp.sell_venue or ''):<14}  "
              f"{be_str:>8s}  {sdq:<6}")


async def main():
    artifacts = await run_funnel()
    print_report(*artifacts)


if __name__ == "__main__":
    asyncio.run(main())
