"""ArbiCore X — Phase D D-1: CEX-arb 5-gate filter (thin facade after the
D-2 substrate refactor).

Gate 1 (Spread — CEX-specific primary metric) stays here. Gates 2-5
(Liquidity, Venue Capability, Confidence, Provenance) are universal and
delegated to `arbicore.scanners.gates.run_universal_gates`. Behaviour,
return tuple, gate numbering, and reason-string formatting are preserved
bit-for-bit so D-1 telemetry remains unchanged.

`GateContext` is re-exported from `..gates.types` so existing callers
(`cex_arbitrage.verifier`) keep working with the original
`from .filter import GateContext, run_five_gates` import.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from ...models.canonical import CanonicalOpportunity
from ..gates import run_universal_gates
from ..gates.types import GateContext  # re-exported for back-compat

# Re-export name preserved for downstream imports.
__all__ = ["GateContext", "run_five_gates"]

# Scanner primary-metric identifier (exposed in scanner.status.primary_metric)
PRIMARY_METRIC_NAME = "spread_pct"


def _thresholds_for(cfg: Dict[str, Any], asset: Optional[str]) -> Dict[str, float]:
    gt = (cfg.get("gate_thresholds") or {})
    default = gt.get("default", {"min_spread_pct": 0.30,
                                  "min_depth_usd": 5000,
                                  "min_confidence": 55})
    if asset and asset in gt:
        out = dict(default)
        out.update(gt[asset])
        return out
    return dict(default)


async def run_five_gates(opp: CanonicalOpportunity, ctx: GateContext
                          ) -> Tuple[bool, int, str]:
    """Run all 5 gates in order. Returns (passed, gate_number, reason).

    Gate 1 (Spread) is CEX-specific and stays here. Gates 2-5 are universal
    and dispatched to `run_universal_gates`.
    """
    th = _thresholds_for(ctx.cfg, opp.asset)

    # Gate 1 — Spread (CEX primary economic metric)
    if opp.spread_pct is None or opp.spread_pct < th["min_spread_pct"]:
        return False, 1, (
            f"spread:below_threshold_"
            f"{opp.spread_pct or 0:.3f}pct_vs_min_{th['min_spread_pct']:.3f}pct"
        )

    # Gates 2-5 — universal
    return await run_universal_gates(opp, ctx, th)
