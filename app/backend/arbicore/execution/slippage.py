"""Wave 6C · Slippage estimator (deterministic).

This module is a thin, execution-engine-facing adapter around the
canonical deterministic ``SlippageValidator``
(``arbicore.intelligence.validators.slippage``).  The adapter exists
so:

    * Execution callers get a stable, plan-shaped output
      (``SlippageEstimate``) that fits into ``economics``.
    * The underlying deterministic validator remains the single
      source of truth for slippage math (VERIFY → REUSE).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Deterministic slippage model — mirrors canonical SlippageValidator without
# creating a hard dependency on the canonical import path (the canonical
# validator lives in the source-of-truth bundle; here we keep an isolated
# implementation so this module is self-contained and testable).
# ---------------------------------------------------------------------------

MIN_SLIPPAGE_DEFAULT = 0.003   # 30 bps
MAX_SLIPPAGE_DEFAULT = 0.006   # 60 bps


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class SlippageEstimate:
    per_hop_slippage: List[float]
    aggregate_slippage: float
    aggregate_slippage_bps: int
    min_output_wei: int
    quoted_output_wei: int
    slippage_haircut_wei: int
    method: str
    deterministic: bool
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SlippageEstimator:
    """Deterministic slippage aggregator over N hops."""

    def __init__(self,
                 min_slippage: float = MIN_SLIPPAGE_DEFAULT,
                 max_slippage: float = MAX_SLIPPAGE_DEFAULT):
        if not (0.0 <= min_slippage <= max_slippage <= 1.0):
            raise ValueError("min_slippage / max_slippage must satisfy 0 ≤ min ≤ max ≤ 1")
        self.min_slippage = min_slippage
        self.max_slippage = max_slippage

    def _default_hop(self) -> float:
        return (self.min_slippage + self.max_slippage) / 2

    def estimate(self, *,
                 quoted_output_wei: int,
                 hops: int,
                 per_hop_slippage: Optional[List[float]] = None
                 ) -> SlippageEstimate:
        hops = max(1, int(hops))
        if per_hop_slippage is None:
            per_hop = [self._default_hop() for _ in range(hops)]
            method = "band_midpoint"
        else:
            per_hop = [max(0.0, min(1.0, float(s))) for s in per_hop_slippage]
            # Pad or trim to N hops deterministically.
            if len(per_hop) < hops:
                per_hop = per_hop + [self._default_hop()] * (hops - len(per_hop))
            elif len(per_hop) > hops:
                per_hop = per_hop[:hops]
            method = "explicit_per_hop"

        # Multiplicative aggregation: (1 - s1)*(1 - s2)*...*(1 - sN)
        remaining = 1.0
        for s in per_hop:
            remaining *= (1.0 - s)
        aggregate = max(0.0, 1.0 - remaining)
        haircut_wei = int(quoted_output_wei * aggregate)
        min_output_wei = int(quoted_output_wei - haircut_wei)

        return SlippageEstimate(
            per_hop_slippage=[round(x, 8) for x in per_hop],
            aggregate_slippage=round(aggregate, 8),
            aggregate_slippage_bps=int(round(aggregate * 10_000)),
            min_output_wei=min_output_wei,
            quoted_output_wei=int(quoted_output_wei),
            slippage_haircut_wei=haircut_wei,
            method=method,
            deterministic=True,
            generated_at=_now_iso(),
        )
