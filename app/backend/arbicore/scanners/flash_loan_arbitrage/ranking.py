"""T1 · Opportunity ranking kernel.

Ranks opportunities by risk-adjusted *executable* value — NOT by raw apparent
spread. Score blends expected net profit with execution probability,
confidence, liquidity headroom and quote freshness; a negative worst-case net
profit is penalised. Pure / deterministic.

INV: a large apparent spread with poor execution probability MUST rank below
a smaller spread with high execution probability (the §20 contract).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def score_opportunity(
    *,
    expected_net_profit_usd: float,
    execution_probability: float,
    confidence: float,                       # 0..1
    min_route_tvl_usd: Optional[float] = None,
    quote_age_sec: Optional[float] = None,
    quote_max_age_sec: float = 12.0,
    worst_case_net_profit_usd: Optional[float] = None,
    liquidity_ref_usd: float = 250_000.0,
) -> Dict[str, Any]:
    p = _clamp(execution_probability)
    c = _clamp(confidence)
    fresh = 1.0 if quote_age_sec is None else \
        1.0 - _clamp(float(quote_age_sec) / max(quote_max_age_sec, 1e-6))
    if min_route_tvl_usd is None:
        liq = 0.0  # unverifiable liquidity contributes nothing (fail-closed)
    else:
        liq = _clamp(float(min_route_tvl_usd) / max(liquidity_ref_usd, 1e-6))

    base = float(expected_net_profit_usd) * p * c
    freshness_factor = 0.5 + 0.5 * fresh          # never fully zero out on freshness
    liquidity_factor = 0.5 + 0.5 * liq
    score = base * freshness_factor * liquidity_factor
    if worst_case_net_profit_usd is not None and worst_case_net_profit_usd < 0:
        score += float(worst_case_net_profit_usd)  # penalise downside risk

    return {
        "score": round(score, 6),
        "components": {
            "expected_net_profit_usd": float(expected_net_profit_usd),
            "execution_probability": round(p, 4),
            "confidence": round(c, 4),
            "freshness_factor": round(freshness_factor, 4),
            "liquidity_factor": round(liquidity_factor, 4),
            "worst_case_net_profit_usd": worst_case_net_profit_usd,
        },
    }


@dataclass
class RankedOpportunity:
    opportunity_id: str
    score: float
    components: Dict[str, Any] = field(default_factory=dict)


def rank_opportunities(items: List[Dict[str, Any]]) -> List[RankedOpportunity]:
    """items: list of dicts with 'opportunity_id' + score_opportunity kwargs."""
    ranked: List[RankedOpportunity] = []
    for it in items:
        oid = it.get("opportunity_id", "?")
        kwargs = {k: v for k, v in it.items() if k != "opportunity_id"}
        s = score_opportunity(**kwargs)
        ranked.append(RankedOpportunity(oid, s["score"], s["components"]))
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


__all__ = ["RankedOpportunity", "score_opportunity", "rank_opportunities"]
