"""ArbiCore X — Universal gate pipeline: Gates 2-5 (Liquidity, Venue
Capability, Confidence, Provenance).

These four gates are universal across every opportunity family. Each scanner
keeps a thin type-specific wrapper that runs its own Gate 1 (primary
economic metric) and then calls `run_universal_gates` for the rest.

Behaviour and reason-string formatting are identical to the original
`cex_arbitrage.filter.run_five_gates` for Gates 2-5 — preserved bit-for-bit
so D-1 telemetry shape (gate-rejection counters, gate-analysis
`metadata.rejected_gate_name` partitioning) is unchanged.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from ...data.provenance import is_learning_eligible
from ...models.canonical import CanonicalOpportunity
from .types import GateContext


async def run_universal_gates(opp: CanonicalOpportunity,
                              ctx: GateContext,
                              thresholds: Dict[str, Any],
                              ) -> Tuple[bool, int, str]:
    """Run Gates 2-5 in order. Returns (passed, gate_number, reason).

    Args:
        opp        — the CanonicalOpportunity under evaluation
        ctx        — universal gate context (venue depths, capability repo,
                     confidence engine)
        thresholds — already-resolved per-asset thresholds dict carrying
                     at minimum: min_depth_usd, min_confidence

    Returns:
        (True, 0, "ok") on pass; (False, n, "<token>:<detail>") on rejection
        where n ∈ {2, 3, 4, 5} and token ∈
        {liquidity, venue_capability, confidence, provenance}.

    On pass, `opp.confidence_score` is populated from the confidence engine
    (default 60.0 when engine is None). This matches the pre-refactor
    behaviour of `run_five_gates` exactly.
    """
    # Gate 2 — Liquidity
    min_depth = min(ctx.buy_side_depth_usd, ctx.sell_side_depth_usd)
    if min_depth < thresholds["min_depth_usd"]:
        return False, 2, (
            f"liquidity:depth_{min_depth:.0f}usd_vs_min_{thresholds['min_depth_usd']:.0f}usd"
        )

    # Gate 3 — Venue Capability
    base = opp.subject_id or ""
    quote = "USDT"
    for vid in (ctx.buy_venue, ctx.sell_venue):
        try:
            ok, why = await ctx.venue_caps.is_gate_3_pass(vid, base, quote)
        except Exception as exc:  # noqa: BLE001
            ok, why = True, f"capability_repo_error:{exc!r}"
        if not ok:
            return False, 3, f"venue_capability:{vid}:{why}"

    # Gate 4 — Confidence
    confidence = 60.0  # default optimistic when no engine wired
    if ctx.confidence_engine is not None:
        try:
            res = await ctx.confidence_engine.score_with_breakdown(opp)
            confidence = float(res.get("overall", confidence))
        except Exception:  # noqa: BLE001
            pass
    opp.confidence_score = confidence
    if confidence < thresholds["min_confidence"]:
        return False, 4, (
            f"confidence:{confidence:.1f}_vs_min_{thresholds['min_confidence']:.1f}"
        )

    # Gate 5 — Provenance
    if not is_learning_eligible(opp.source_data_quality):
        return False, 5, f"provenance:not_learning_eligible:{opp.source_data_quality}"

    return True, 0, "ok"
