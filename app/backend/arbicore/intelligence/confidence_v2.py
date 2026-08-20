"""ArbiCore X — Confidence engine v2 (P0-7).

Explainable 0-100 confidence built from weighted factor sub-scores. Each
factor is 0-100; the result exposes every component so the UI can render:

    CONFIDENCE = 96
      quote_freshness   98
      liquidity_depth   94
      gas_certainty     97
      simulation        100
      mev_risk          82
      ...

IMPORTANT: confidence is an ADVISORY score. It NEVER overrides hard safety
gates (kill switch, allowlists, slippage guard, simulation failure, signer
restrictions). This module returns a number + explanation only.

Pure / deterministic. No I/O.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional


def _clamp100(x: float) -> float:
    return max(0.0, min(100.0, float(x)))


# Positive factors reward quality; risk factors are inverted (higher raw
# risk → lower sub-score). Weights sum to 1.0.
FACTOR_WEIGHTS: Dict[str, float] = {
    "quote_freshness": 0.14,
    "liquidity_depth": 0.13,
    "route_stability": 0.09,
    "price_discrepancy": 0.09,
    "slippage_confidence": 0.11,
    "gas_certainty": 0.08,
    "flash_availability": 0.06,
    "simulation_result": 0.14,
    "venue_reliability": 0.05,
    "historical_success": 0.06,
    "mev_risk": 0.03,          # risk factor (inverted upstream)
    "profit_margin": 0.02,
}


@dataclass
class ConfidenceResult:
    score: float                         # 0-100
    components: Dict[str, float] = field(default_factory=dict)
    weights: Dict[str, float] = field(default_factory=dict)
    missing_factors: list = field(default_factory=list)
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def compute_confidence(*, components: Dict[str, Optional[float]]) -> ConfidenceResult:
    """``components`` maps factor name → 0-100 sub-score (or None if unknown).

    Unknown factors are dropped from the weighted mean and reported in
    ``missing_factors`` so the operator can see the score is partial.
    """
    present: Dict[str, float] = {}
    missing = []
    total_w = 0.0
    acc = 0.0
    for name, weight in FACTOR_WEIGHTS.items():
        val = components.get(name)
        if val is None:
            missing.append(name)
            continue
        v = _clamp100(val)
        present[name] = round(v, 2)
        acc += weight * v
        total_w += weight
    score = round(acc / total_w, 2) if total_w > 1e-9 else 0.0
    top = sorted(present.items(), key=lambda kv: kv[1])
    weakest = top[0][0] if top else "n/a"
    strongest = top[-1][0] if top else "n/a"
    expl = (f"weighted over {len(present)}/{len(FACTOR_WEIGHTS)} factors; "
            f"strongest={strongest}, weakest={weakest}"
            + (f"; missing={','.join(missing)}" if missing else ""))
    return ConfidenceResult(score=score, components=present,
                            weights={k: FACTOR_WEIGHTS[k] for k in present},
                            missing_factors=missing, explanation=expl)


def confidence_from_signals(
    *, quote_age_sec: Optional[float] = None, quote_max_age_sec: float = 12.0,
    liquidity_ratio: Optional[float] = None, route_stability: Optional[float] = None,
    price_discrepancy_bps: Optional[float] = None, slippage_bps: Optional[float] = None,
    max_slippage_bps: float = 150.0, gas_certainty: Optional[float] = None,
    flash_available: Optional[bool] = None, simulation_passed: Optional[bool] = None,
    venue_reliability: Optional[float] = None, historical_success: Optional[float] = None,
    mev_risk: Optional[float] = None, net_profit_bps: Optional[float] = None,
) -> ConfidenceResult:
    """Map raw measurable signals → 0-100 factor sub-scores → confidence."""
    def fresh():
        if quote_age_sec is None:
            return None
        return 100.0 * (1.0 - min(1.0, quote_age_sec / max(quote_max_age_sec, 1e-6)))

    comps: Dict[str, Optional[float]] = {
        "quote_freshness": fresh(),
        "liquidity_depth": None if liquidity_ratio is None else 100.0 * (1.0 - min(1.0, liquidity_ratio / 0.20)),
        "route_stability": None if route_stability is None else 100.0 * route_stability,
        "price_discrepancy": None if price_discrepancy_bps is None else min(100.0, abs(price_discrepancy_bps)),
        "slippage_confidence": None if slippage_bps is None else 100.0 * (1.0 - min(1.0, slippage_bps / max(max_slippage_bps, 1e-6))),
        "gas_certainty": None if gas_certainty is None else 100.0 * gas_certainty,
        "flash_availability": None if flash_available is None else (100.0 if flash_available else 0.0),
        "simulation_result": None if simulation_passed is None else (100.0 if simulation_passed else 0.0),
        "venue_reliability": None if venue_reliability is None else 100.0 * venue_reliability,
        "historical_success": None if historical_success is None else 100.0 * historical_success,
        "mev_risk": None if mev_risk is None else 100.0 * (1.0 - min(1.0, mev_risk)),
        "profit_margin": None if net_profit_bps is None else max(0.0, min(100.0, net_profit_bps)),
    }
    return compute_confidence(components=comps)


__all__ = ["ConfidenceResult", "compute_confidence", "confidence_from_signals",
           "FACTOR_WEIGHTS"]
