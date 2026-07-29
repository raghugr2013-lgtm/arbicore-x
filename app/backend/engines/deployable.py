"""Deployable Capital Engine (Sprint 4) — pure read-only analysis.
For every venue opportunity it sizes what could actually be deployed and
identifies the BINDING CONSTRAINT:
  CAPITAL_LIMITED · LIQUIDITY_LIMITED · DEPOSIT_GATE_LIMITED ·
  WITHDRAWAL_GATE_LIMITED · ROUTE_LIMITED · NO_KEY (capital unknown)
No execution, transfers, or rebalancing — informational only."""


def compute_venue(venue: dict, balance: dict, capability: dict, price: float):
    """venue: venue_matrix entry {exchange, listed, verdict, net_spread_pct, recommended, confidence}
    balance: {has_key: bool, free_base: float|None, free_quote: float|None}
    capability: {deposit_enabled, withdraw_enabled} | None
    price: current base asset price in quote terms"""
    ex = venue.get("exchange")
    listed = venue.get("listed")
    cap_qty = venue.get("recommended")
    net = venue.get("net_spread_pct")
    dep_open = (capability or {}).get("deposit_enabled")
    wd_open = (capability or {}).get("withdraw_enabled")

    out = {"exchange": ex, "listed": listed, "verdict": venue.get("verdict"),
           "net_spread_pct": net, "liquidity_capacity_base": cap_qty,
           "free_base": balance.get("free_base"), "free_quote": balance.get("free_quote"),
           "has_key": balance.get("has_key", False),
           "deposit_enabled": dep_open, "withdraw_enabled": wd_open,
           "deployable_base": None, "deployable_quote_value": None,
           "est_profit_quote": None, "potential_profit_quote": None,
           "limiting_factor": None, "reason": None, "secondary_factors": []}

    if wd_open is False:
        out["secondary_factors"].append("withdrawals closed — proceeds would be locked on venue")
    if dep_open is False:
        out["secondary_factors"].append("deposits closed — cannot top up this venue")

    if not listed:
        out.update(limiting_factor="ROUTE_LIMITED", reason="pair not listed on venue")
        return out
    if cap_qty is None:
        out.update(limiting_factor="ROUTE_LIMITED", reason="no market/capacity data for venue")
        return out

    if price and net is not None:
        out["potential_profit_quote"] = round(cap_qty * price * net / 100, 2)

    if not balance.get("has_key"):
        out.update(limiting_factor="NO_KEY",
                   reason="no read-only API key configured — capital side unknown, liquidity view only")
        return out

    free_base = balance.get("free_base") or 0.0
    if free_base >= cap_qty * 0.999:
        deployable = cap_qty
        out.update(limiting_factor="LIQUIDITY_LIMITED",
                   reason=f"order-book capacity ({cap_qty:,.0f}) is the binding constraint; "
                          f"balance covers it ({free_base:,.0f} free)")
        if wd_open is False and dep_open is not False:
            out["limiting_factor"] = "WITHDRAWAL_GATE_LIMITED"
            out["reason"] = ("capital and liquidity suffice, but withdrawals are closed — "
                             "proceeds cannot leave the venue to recycle the route")
    else:
        deployable = free_base
        if dep_open is False:
            out.update(limiting_factor="DEPOSIT_GATE_LIMITED",
                       reason=f"only {free_base:,.0f} free on venue and deposits are closed — "
                              f"cannot top up toward the {cap_qty:,.0f} capacity")
        else:
            out.update(limiting_factor="CAPITAL_LIMITED",
                       reason=f"free balance ({free_base:,.0f}) below order-book capacity "
                              f"({cap_qty:,.0f}); deposits open — more capital would deploy")

    out["deployable_base"] = round(deployable, 1)
    if price:
        out["deployable_quote_value"] = round(deployable * price, 2)
        if net is not None:
            out["est_profit_quote"] = round(deployable * price * net / 100, 2)
    return out
