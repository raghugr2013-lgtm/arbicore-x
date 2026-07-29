"""ArbiCore X — Universal gate pipeline: shared GateContext.

The same dataclass services every scanner's Gate 2-5 invocation. Scanner-
specific extensions (e.g., funding interval per leg) live in scanner-local
context objects that compose this one — they never need to modify this shape.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class GateContext:
    """Universal context object consumed by Gates 2-5.

    Fields:
        cfg                 — runtime scanner config (per-scanner; carries
                              gate_thresholds, etc.)
        venue_caps          — VenueCapabilityRepository instance
        buy_venue           — long / spot-buy / source venue identifier
        sell_venue          — short / spot-sell / destination venue identifier
        buy_side_depth_usd  — depth or notional on the buy/long leg
        sell_side_depth_usd — depth or notional on the sell/short leg
        confidence_engine   — optional AdaptiveConfidenceEngine reference
    """
    cfg: Dict[str, Any]
    venue_caps: Any
    buy_venue: str
    sell_venue: str
    buy_side_depth_usd: float
    sell_side_depth_usd: float
    confidence_engine: Any = None
