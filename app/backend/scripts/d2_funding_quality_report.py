"""Funding Opportunity Quality Report — one-shot offline analysis.

Polls every D-2 funding source once, computes per-asset differentials,
runs the economics assessor against each, and aggregates statistics.

Operator-requested deliverable (no opportunity emission — read-only).
"""
import asyncio
import json
import math
import statistics
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List

from arbicore.scanners.funding_arbitrage.sources import (
    build_all_funding_sources, FundingObservation,
)
from arbicore.scanners.funding_arbitrage.verifier import (
    FundingDifferentialVerifier, FundingDifferential, _normalise_observation,
)
from arbicore.scanners.funding_arbitrage.economics import (
    FundingEconomicsAssessor,
)


def _verifier_cfg(): return {"max_funding_age_s": 600.0,
                              "min_eligible_venues_for_diff": 2}


ECONOMICS_CFG = {
    "min_diff_apr_pct":       5.0,
    "max_break_even_hours":   24.0,
    "default_notional_usd":   1_000.0,
    "depth_safety_factor":    5.0,
    "min_position_usd":       100.0,
}


async def collect_universe(sources):
    """Single poll of every venue. Returns dict: base → {venue: VenueFundingRead}."""
    universe: Dict[str, Dict[str, Any]] = defaultdict(dict)
    raw_counts: Dict[str, int] = {}
    errors: Dict[str, str] = {}
    for src in sources:
        try:
            obs_list = await src._fetch_observations()
        except Exception as exc:
            errors[src.source_id] = repr(exc)
            obs_list = []
        raw_counts[src.source_id] = len(obs_list)
        if src._last_error and src.source_id not in errors:
            errors[src.source_id] = src._last_error
        for obs in obs_list:
            vr = _normalise_observation(obs, src.venue_provenance_id)
            universe[obs.subject_id][src.venue_id] = vr
    return universe, raw_counts, errors


def compute_differentials(universe):
    """For each asset with ≥2 venues, compute the differential.
    Returns list of FundingDifferential."""
    diffs: List[FundingDifferential] = []
    for base, by_venue in universe.items():
        if len(by_venue) < 2:
            continue
        reads = list(by_venue.values())
        # Apply freshness gate (use verifier's default 600s — generous for report)
        now = time.time()
        eligible = [r for r in reads if (now - r.venue_observed_at_ts) <= 600.0]
        if len(eligible) < 2:
            continue
        ordered = sorted(eligible, key=lambda r: r.funding_apr_pct)
        lo, hi = ordered[0], ordered[-1]
        if lo.venue == hi.venue:
            continue
        diffs.append(FundingDifferential(
            asset_base=base, canonical_asset=f"{base}-PERP",
            long_venue=lo.venue, long_funding_apr_pct=lo.funding_apr_pct,
            short_venue=hi.venue, short_funding_apr_pct=hi.funding_apr_pct,
            differential_apr_pct=hi.funding_apr_pct - lo.funding_apr_pct,
            captured_at_ts=now, long_read=lo, short_read=hi,
        ))
    return diffs


def assess_all(diffs, *, with_depth_usd=None):
    """Run economics assessor against every differential."""
    assessor = FundingEconomicsAssessor(config_loader=lambda: ECONOMICS_CFG)
    rows = []
    for d in diffs:
        kwargs = {}
        if with_depth_usd is not None:
            kwargs["long_leg_depth_usd"] = with_depth_usd
            kwargs["short_leg_depth_usd"] = with_depth_usd
        ea = assessor.assess(d, **kwargs)
        rows.append((d, ea))
    return rows


def histogram(values, edges):
    """Simple bucket histogram. edges: ascending list; returns labelled counts."""
    buckets = [0] * (len(edges) - 1)
    overflow = 0
    for v in values:
        if v == math.inf:
            overflow += 1
            continue
        placed = False
        for i in range(len(edges) - 1):
            if edges[i] <= v < edges[i + 1]:
                buckets[i] += 1
                placed = True
                break
        if not placed:
            overflow += 1
    out = []
    for i in range(len(edges) - 1):
        label = f"[{edges[i]:g}, {edges[i+1]:g})"
        out.append((label, buckets[i]))
    out.append(("[overflow / inf]", overflow))
    return out


async def main():
    sources = build_all_funding_sources(
        config_loader=lambda: {"discovery_sources": {}})
    try:
        universe, raw_counts, errors = await collect_universe(sources)
    finally:
        for s in sources:
            try: await s.close()
            except Exception: pass

    diffs = compute_differentials(universe)
    rows_no_depth   = assess_all(diffs)                                  # liq inconclusive
    rows_depth_10k  = assess_all(diffs, with_depth_usd=10_000.0)
    rows_depth_50k  = assess_all(diffs, with_depth_usd=50_000.0)

    # --- Universe summary ----------------------------------------------------
    print("=" * 72)
    print("FUNDING OPPORTUNITY QUALITY REPORT")
    print(f"Captured at unix={int(time.time())}")
    print("=" * 72)

    print(f"\nVenue raw observation counts (this poll):")
    for sid, n in sorted(raw_counts.items()):
        e = errors.get(sid, "")
        print(f"  {sid:<35s} {n:>5d}   {e}")
    print(f"\nUnique base assets seen across all venues : {len(universe)}")
    multi = {b: v for b, v in universe.items() if len(v) >= 2}
    print(f"Assets present on ≥2 venues               : {len(multi)}")
    print(f"Differentials computed                    : {len(diffs)}")

    # --- Top 20 by APR ------------------------------------------------------
    print("\n" + "=" * 72)
    print("TOP 20 APR DIFFERENTIALS (assets present on ≥2 venues)")
    print("=" * 72)
    top = sorted(rows_no_depth, key=lambda x: x[0].differential_apr_pct, reverse=True)[:20]
    print(f"{'#':<3}{'asset':<10}{'diff_apr%':>10}  {'long':>12} {'l_apr%':>9}  "
          f"{'short':>12} {'s_apr%':>9}  {'BE_h':>9}")
    for i, (d, ea) in enumerate(top, 1):
        be = "inf" if ea.break_even_hours == math.inf else f"{ea.break_even_hours:.1f}"
        print(f"{i:<3}{d.asset_base:<10}{d.differential_apr_pct:>10.3f}  "
              f"{d.long_venue:>12} {d.long_funding_apr_pct:>9.3f}  "
              f"{d.short_venue:>12} {d.short_funding_apr_pct:>9.3f}  {be:>9s}")

    # --- Break-even distribution -------------------------------------------
    print("\n" + "=" * 72)
    print("BREAK-EVEN DISTRIBUTION (over all differentials)")
    print("=" * 72)
    bes = [ea.break_even_hours for _, ea in rows_no_depth]
    finite = [b for b in bes if b != math.inf]
    if finite:
        print(f"  min      : {min(finite):.2f} h")
        print(f"  median   : {statistics.median(finite):.2f} h")
        print(f"  mean     : {statistics.mean(finite):.2f} h")
        print(f"  max      : {max(finite):.2f} h")
        print(f"  inf count: {sum(1 for b in bes if b == math.inf)}")
    else:
        print("  (no finite break-evens)")
    print("\n  Histogram (hours):")
    for lbl, n in histogram(bes, [0, 6, 12, 24, 48, 96, 168, 336, 720, 2160]):
        bar = "#" * min(40, n)
        print(f"    {lbl:<20s} {n:>5d}  {bar}")

    # --- Max position by liquidity (with assumed depth) -------------------
    print("\n" + "=" * 72)
    print("LIQUIDITY-ADJUSTED MAX POSITION (synthetic depth assumption)")
    print("=" * 72)
    print("NOTE: D-2 sources do not yet poll order-book depth. The next")
    print("      checkpoint adds that. This section shows what max-pos")
    print("      looks like under uniform synthetic depth assumptions.")
    for label, depth, rows in (("$10,000 per leg", 10_000.0, rows_depth_10k),
                               ("$50,000 per leg", 50_000.0, rows_depth_50k)):
        max_pos = [ea.max_position_usd_by_liquidity for _, ea in rows
                    if ea.max_position_usd_by_liquidity is not None]
        if max_pos:
            print(f"  depth={label:<20s} → max_pos = ${max_pos[0]:.0f} per opportunity "
                  f"(safety_factor=5×)")

    # --- Rejection-rule breakdown ------------------------------------------
    for header, rows in (
        ("REJECTION BREAKDOWN — no depth info supplied",   rows_no_depth),
        ("REJECTION BREAKDOWN — assuming $10,000 depth per leg", rows_depth_10k),
        ("REJECTION BREAKDOWN — assuming $50,000 depth per leg", rows_depth_50k),
    ):
        print("\n" + "=" * 72)
        print(header)
        print("=" * 72)
        total = len(rows)
        n_diff_fail   = sum(1 for _, ea in rows if ea.meets_min_diff_threshold is False)
        n_be_fail     = sum(1 for _, ea in rows if ea.meets_break_even_horizon is False)
        n_liq_fail    = sum(1 for _, ea in rows if ea.meets_liquidity_threshold is False)
        n_liq_unknown = sum(1 for _, ea in rows if ea.meets_liquidity_threshold is None)
        n_actionable  = sum(1 for _, ea in rows if ea.is_economically_actionable is True)
        n_inconcl     = sum(1 for _, ea in rows if ea.is_economically_actionable is None)
        n_rejected    = sum(1 for _, ea in rows if ea.is_economically_actionable is False)
        print(f"  total differentials                : {total}")
        print(f"  ❌ fail Gate-A (min APR diff)     : {n_diff_fail:>5d}  "
              f"({100*n_diff_fail/total:>5.1f} %)")
        print(f"  ❌ fail Gate-B (break-even ≤ 24h) : {n_be_fail:>5d}  "
              f"({100*n_be_fail/total:>5.1f} %)")
        print(f"  ❌ fail Gate-C (liquidity)        : {n_liq_fail:>5d}  "
              f"({100*n_liq_fail/total:>5.1f} %)")
        print(f"  ⓘ  Gate-C inconclusive            : {n_liq_unknown:>5d}  "
              f"({100*n_liq_unknown/total:>5.1f} %)")
        print(f"  ✅ economically actionable        : {n_actionable:>5d}  "
              f"({100*n_actionable/total:>5.1f} %)")
        print(f"  ❌ rejected (any failure)         : {n_rejected:>5d}  "
              f"({100*n_rejected/total:>5.1f} %)")
        print(f"  ⓘ  inconclusive (only liq missing): {n_inconcl:>5d}  "
              f"({100*n_inconcl/total:>5.1f} %)")

    # --- Survivors ---------------------------------------------------------
    print("\n" + "=" * 72)
    print("OPPORTUNITIES PASSING ALL CURRENT ECONOMICS THRESHOLDS")
    print(f"  (min_diff_apr_pct=5.0, max_break_even_hours=24.0,")
    print(f"   default_notional_usd=1000, depth_safety_factor=5)")
    print("=" * 72)
    for label, depth, rows in (("$10,000 depth per leg", 10_000.0, rows_depth_10k),
                               ("$50,000 depth per leg", 50_000.0, rows_depth_50k)):
        survivors = [(d, ea) for d, ea in rows
                      if ea.is_economically_actionable is True]
        print(f"\n  With assumed {label}: {len(survivors)} survivor(s)")
        if survivors:
            print(f"    {'asset':<10}{'diff_apr%':>10}  {'long':>12} {'short':>12}  "
                  f"{'BE_h':>9}  {'max_pos$':>10}")
            for d, ea in sorted(survivors,
                                key=lambda x: x[0].differential_apr_pct,
                                reverse=True)[:30]:
                print(f"    {d.asset_base:<10}{d.differential_apr_pct:>10.3f}  "
                      f"{d.long_venue:>12} {d.short_venue:>12}  "
                      f"{ea.break_even_hours:>9.1f}  "
                      f"{ea.max_position_usd_by_liquidity or 0:>10.0f}")


if __name__ == "__main__":
    asyncio.run(main())
