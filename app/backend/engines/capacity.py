"""Capacity Engine — MIN / RECOMMENDED / MAX SAFE / OPTIMAL buy sizes."""
from typing import List, Optional


def compute_capacity(curve: List[dict], buy_price: float, taker_fee_pct: float,
                     volume_24h_base: Optional[float], risk: dict) -> dict:
    """All sizes in base-asset units. `curve` from engines.spread.slippage_curve."""
    if not curve or buy_price <= 0:
        return {"min_buy": None, "recommended_raw": None, "max_safe": None, "optimal": None,
                "q_book": None, "q_volume": None, "assumptions": {}}

    max_slip = risk.get("max_slippage_pct", 1.0)
    part_cap = risk.get("participation_cap_pct", 2.0) / 100
    fee_share_cap = risk.get("fee_share_cap", 0.25)
    fixed_fees_quote = risk.get("fixed_fees_quote", 1.0)

    # Q_book: largest size with slippage within budget
    q_book = None
    for pt in curve:
        if pt["slippage_pct"] <= max_slip:
            q_book = pt["q_base"]
        else:
            break
    q_volume = volume_24h_base * part_cap if volume_24h_base else None
    candidates = [q for q in (q_book, q_volume) if q]
    max_safe = min(candidates) if candidates else None

    # MIN_BUY: smallest size where fixed fees consume <= fee_share_cap of gross edge
    min_buy = None
    for pt in curve:
        gross_edge = pt["q_base"] * max(pt["vwap"] - buy_price, 0)
        if gross_edge > 0 and fixed_fees_quote <= fee_share_cap * gross_edge:
            min_buy = pt["q_base"]
            break

    # OPTIMAL: argmax of net profit over the curve (concave in size)
    optimal, best_profit = None, None
    for pt in curve:
        profit = pt["q_base"] * pt["vwap"] * (1 - taker_fee_pct / 100) - pt["q_base"] * buy_price - fixed_fees_quote
        if best_profit is None or profit > best_profit:
            best_profit, optimal = profit, pt["q_base"]

    rec_raw = None
    if optimal is not None:
        rec_raw = min(optimal, max_safe) if max_safe else optimal

    return {
        "min_buy": min_buy, "recommended_raw": rec_raw, "max_safe": max_safe, "optimal": optimal,
        "q_book": q_book, "q_volume": q_volume, "best_profit_quote": best_profit,
        "assumptions": {
            "max_slippage_pct": max_slip, "participation_cap_pct": part_cap * 100,
            "fee_share_cap": fee_share_cap, "fixed_fees_quote": fixed_fees_quote,
            "taker_fee_pct": taker_fee_pct,
        },
    }


def safety_multiplier(overall_score: float) -> float:
    """1.0 at score>=85, linear down to 0.25 at score 50, floor 0.25."""
    if overall_score >= 85:
        return 1.0
    if overall_score <= 50:
        return 0.25
    return 0.25 + (overall_score - 50) / 35 * 0.75
