"""ArbiCore X — Universal gate pipeline (shared across all scanners).

D-2 substrate refactor: Gates 2-5 (Liquidity, Venue Capability, Confidence,
Provenance) are universal — they reason over `CanonicalOpportunity` fields
and a `GateContext` and are identical for every opportunity family.

Gate 1 (primary economic metric) is fundamentally type-specific:
  - CEX arb        → spread_pct           >= min_spread_pct
  - Funding arb    → spread_pct           >= min_funding_diff_apr_pct  (reused)
  - DEX arb        → spread_pct           >= min_dex_spread_pct
  - Launch         → primary metric TBD per category

Each scanner provides its own Gate 1 wrapper that calls
`run_universal_gates(opp, ctx, thresholds)` for the remaining four.

Numbering convention is preserved across scanners so the
`metadata.rejected_at_gate` integer is consistent in gate-analysis:
    1 = primary metric (scanner-specific)
    2 = liquidity
    3 = venue capability
    4 = confidence
    5 = provenance

Reason strings keep their leading token (`liquidity:`, `venue_capability:`,
`confidence:`, `provenance:`) — the gate-analysis aggregator groups by this
token, so downstream telemetry shape is unchanged.
"""
from .types import GateContext
from .universal import run_universal_gates

__all__ = ["GateContext", "run_universal_gates"]
