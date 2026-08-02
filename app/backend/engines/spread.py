"""Spread, breakeven and slippage-curve math. Pure functions, unit-testable."""
from typing import List, Optional


def slippage_curve(bids: List[List[float]], points: int = 30) -> List[dict]:
    """Cumulative VWAP curve over the bid ladder at a geometric size grid."""
    if not bids:
        return []
    best = bids[0][0]
    total_qty = sum(q for _, q in bids)
    if total_qty <= 0 or best <= 0:
        return []
    min_q = max(total_qty * 0.002, 1e-12)
    curve = []
    for i in range(points):
        q_target = min_q * (total_qty / min_q) ** (i / (points - 1)) if points > 1 else total_qty
        filled, cost = 0.0, 0.0
        for price, qty in bids:
            take = min(qty, q_target - filled)
            filled += take
            cost += take * price
            if filled >= q_target - 1e-12:
                break
        if filled <= 0:
            continue
        vwap = cost / filled
        curve.append({
            "q_base": filled,
            "vwap": vwap,
            "slippage_pct": (best - vwap) / best * 100,
        })
    return curve


def vwap_for_qty(bids: List[List[float]], qty: float) -> Optional[float]:
    """Executable VWAP selling `qty` into the bids. None if book too thin."""
    if not bids or qty <= 0:
        return None
    filled, cost = 0.0, 0.0
    for price, q in bids:
        take = min(q, qty - filled)
        filled += take
        cost += take * price
        if filled >= qty - 1e-12:
            break
    if filled < qty * 0.999:  # book exhausted
        return None
    return cost / filled


def spread_metrics(buy_price: float, qty: float, bids: List[List[float]],
                   taker_fee_pct: float, transfer_gas_asset: float = 0.0,
                   fixed_fees_quote: float = 0.0) -> dict:
    """Gross and net spread for selling `qty` (bought at buy_price) into bids."""
    best_bid = bids[0][0] if bids else None
    qty_net = max(qty - transfer_gas_asset, 0.0)
    vwap = vwap_for_qty(bids, qty_net)
    exec_price = vwap if vwap is not None else best_bid
    if exec_price is None or buy_price <= 0:
        return {"gross_pct": None, "net_pct": None, "vwap": None, "best_bid": best_bid}
    cost_basis = buy_price * qty
    proceeds = qty_net * exec_price * (1 - taker_fee_pct / 100) - fixed_fees_quote
    return {
        "gross_pct": (exec_price - buy_price) / buy_price * 100,
        "net_pct": (proceeds - cost_basis) / cost_basis * 100 if cost_basis > 0 else None,
        "vwap": exec_price,
        "best_bid": best_bid,
        "proceeds_quote": proceeds,
        "cost_basis_quote": cost_basis,
        "book_exhausted": vwap is None,
    }


def breakeven(buy_price: float, qty: float, taker_fee_pct: float,
              transfer_gas_asset: float = 0.0, fixed_fees_quote: float = 0.0,
              best_bid: Optional[float] = None) -> dict:
    """Sell price at which net PnL == 0, and cushion vs current best bid."""
    qty_net = max(qty - transfer_gas_asset, 0.0)
    if qty_net <= 0 or buy_price <= 0:
        return {"price": None, "distance_pct": None}
    be = (buy_price * qty + fixed_fees_quote) / (qty_net * (1 - taker_fee_pct / 100))
    dist = (best_bid - be) / be * 100 if best_bid else None
    return {"price": be, "distance_pct": dist}
