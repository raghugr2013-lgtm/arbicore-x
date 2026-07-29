"""ArbiCore X — Phase D D-3.3 DEX-arb gate filter (economics-aware).

Composes the real DEX-specific Gate 1 (mev_adjusted_net_pct) with the
universal Gates 2-5.

D-3.3 replaces the D-3.2 placeholder Gate 1 with an economics-driven check:

   ``mev_adjusted_net_pct >= min_net_spread_after_slip_after_gas_pct``

The assessment is precomputed by the verifier (via DEXEconomicsAssessor)
and threaded into the gate via ``DEXGateContext.assessment``. When no
assessment is supplied we fall back to the placeholder (gross spread vs
threshold) so that callers without an economics layer still work — this
keeps the gate pipeline shape stable for backward-compat tests.

INV-2/3 preserved by construction — no EmissionBus, no provenance overwrite.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

from ..economics import EconomicAssessment
from ...models.canonical import CanonicalOpportunity
from ..gates.types import GateContext
from ..gates.universal import run_universal_gates


@dataclass
class DEXGateContext(GateContext):
    """GateContext extension carrying optional precomputed economics."""
    assessment: Optional[EconomicAssessment] = None


def _thresholds_for(cfg: Dict[str, Any], pair_canonical: str) -> Dict[str, Any]:
    """Resolve per-asset thresholds with default fallback (mirror of D-1)."""
    table = (cfg or {}).get("gate_thresholds") or {}
    default = dict(table.get("default", {}))
    override = table.get(pair_canonical) or {}
    default.update(override)
    return default


async def run_dex_gates(opp: CanonicalOpportunity,
                        ctx: GateContext,
                        ) -> Tuple[bool, int, str]:
    """Run Gate 1 then delegate Gates 2-5 to universal.

    Gate 1 prefers ``ctx.assessment.mev_adjusted_net_pct`` when supplied
    (D-3.3+ verifier path). Falls back to ``opp.spread_pct`` (D-3.2
    placeholder behaviour) when assessment is absent — preserves backward
    compatibility for tests built before D-3.3.
    """
    cfg = ctx.cfg or {}
    pair = opp.subject_id or ""
    th = _thresholds_for(cfg, pair)
    min_net = float(th.get("min_net_spread_after_slip_after_gas_pct", 0.30))

    assessment: Optional[EconomicAssessment] = getattr(ctx, "assessment", None)
    if assessment is not None:
        measured = float(assessment.mev_adjusted_net_pct)
        if measured < min_net:
            return False, 1, (
                f"economics:mev_adjusted_net_{measured:.4f}pct"
                f"_below_min_{min_net:.4f}pct"
            )
    else:
        # D-3.2 placeholder fallback path
        gross = float(opp.spread_pct or 0.0)
        if gross < min_net:
            return False, 1, (
                f"economics:gross_spread_{gross:.4f}pct_below_min_{min_net:.4f}pct"
                f"_placeholder_D-3.2"
            )

    # Gates 2-5 delegated to universal pipeline (unchanged)
    return await run_universal_gates(opp, ctx, th)


__all__ = ["DEXGateContext", "run_dex_gates"]
