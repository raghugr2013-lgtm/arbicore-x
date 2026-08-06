"""Paper Validation — Liquidity check stage (v2.11.8 · Slice B).

Verifies the opportunity's swap hops carry enough on-chain reserves to
absorb the intended borrow size.  The stage is *fail-fast* — a single
under-liquid hop rejects the whole opportunity with
:data:`arbicore.paper.PaperOutcome.LIQUIDITY_FAILURE`.

Implementation
--------------
The check runs against the ``pool_liquidity_usd`` field the scanner
attaches to each hop when it can source pool reserves (see the
``ContinuousDiscovery`` / ``LiveMarketScanner`` reserve-populating
adapters).  When a hop does NOT carry that field the stage is
permissive — it does not synthesise a value.  This preserves the "no
fabricated data" contract: absence of data is not evidence of a
failure.

Threshold
---------
Default safety ratio is ``5x`` — a hop is considered adequately
liquid when ``pool_liquidity_usd >= borrow_amount_usd * 5``.  The
ratio is configurable via the ``ARBICORE_PAPER_LIQUIDITY_SAFETY_RATIO``
env var so operators can tighten / loosen it without a code change.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _env_ratio(default: float = 5.0) -> float:
    raw = (os.environ.get("ARBICORE_PAPER_LIQUIDITY_SAFETY_RATIO") or "").strip()
    if not raw:
        return default
    try:
        v = float(raw)
        return v if v > 0 else default
    except ValueError:
        return default


@dataclass(frozen=True)
class LiquidityCheckResult:
    """Outcome of the liquidity-depth check for one opportunity."""

    ok: bool
    detail: str
    checked_hops: int = 0
    skipped_hops: int = 0
    safety_ratio: float = 5.0
    min_ratio_seen: Optional[float] = None
    failing_hop_index: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_stage_payload(self) -> Dict[str, Any]:
        return {
            "checked_hops":     self.checked_hops,
            "skipped_hops":     self.skipped_hops,
            "safety_ratio":     self.safety_ratio,
            "min_ratio_seen":   self.min_ratio_seen,
            "failing_hop_index": self.failing_hop_index,
            **self.payload,
        }


def check_liquidity(opp: Dict[str, Any],
                     *,
                     safety_ratio: Optional[float] = None,
                     ) -> LiquidityCheckResult:
    """Evaluate ``opp.swap_hops`` against the safety-ratio threshold.

    The check is fail-fast — the FIRST hop that fails returns
    ``ok=False`` with the hop index and observed ratio recorded.
    """
    ratio = safety_ratio if safety_ratio is not None else _env_ratio()
    hops: List[Dict[str, Any]] = list(opp.get("swap_hops") or [])
    borrow_usd = float(opp.get("borrow_amount_usd") or opp.get("capital_required_usd") or 0.0)

    if not hops:
        # No hops → route stage will have already rejected the opp;
        # be permissive here (this stage never fires for a route-failed
        # opp).
        return LiquidityCheckResult(ok=True,
                                     detail="no hops — deferred to route stage",
                                     safety_ratio=ratio)

    if borrow_usd <= 0:
        return LiquidityCheckResult(ok=True,
                                     detail="borrow amount not specified — check skipped",
                                     safety_ratio=ratio,
                                     skipped_hops=len(hops))

    threshold_usd = borrow_usd * ratio
    checked = 0
    skipped = 0
    min_seen: Optional[float] = None

    for i, hop in enumerate(hops):
        liq = hop.get("pool_liquidity_usd")
        if liq is None:
            skipped += 1
            continue
        try:
            liq_f = float(liq)
        except (TypeError, ValueError):
            skipped += 1
            continue
        checked += 1
        seen_ratio = liq_f / borrow_usd if borrow_usd > 0 else 0.0
        if min_seen is None or seen_ratio < min_seen:
            min_seen = seen_ratio
        if liq_f < threshold_usd:
            return LiquidityCheckResult(
                ok=False,
                detail=(f"hop #{i} pool_liquidity_usd={liq_f:,.0f} "
                        f"< borrow*{ratio:g} ({threshold_usd:,.0f})"),
                checked_hops=checked, skipped_hops=skipped,
                safety_ratio=ratio,
                min_ratio_seen=seen_ratio,
                failing_hop_index=i,
                payload={"borrow_usd": borrow_usd,
                         "hop_liquidity_usd": liq_f,
                         "threshold_usd": threshold_usd,
                         "hop_dex": hop.get("dex")},
            )

    if checked == 0:
        return LiquidityCheckResult(
            ok=True,
            detail="no hops carried pool_liquidity_usd — check skipped",
            skipped_hops=skipped, safety_ratio=ratio,
        )

    return LiquidityCheckResult(
        ok=True,
        detail=(f"all {checked} liquidity-annotated hop(s) exceed "
                f"borrow*{ratio:g} (min ratio seen: "
                f"{min_seen:.2f})") if min_seen is not None else "ok",
        checked_hops=checked, skipped_hops=skipped,
        safety_ratio=ratio, min_ratio_seen=min_seen,
    )
