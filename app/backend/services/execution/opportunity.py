"""Portal vs Exchange Opportunity computation (E2) — read-only widget data.

For a route: live Portal Price, Best Exchange Price, Gross / Net Spread,
Liquidity, Max Safe Size, Expected Profit, and the GO / WAIT / NO-GO verdict for
the configured exit venue. Sourced from the live evaluation + portal connector.
No execution.
"""
from services import db
from services.collector import collector
from services.execution import venue_registry
from services.portal_price import portal_price


def _bid_depth_2pct(ob):
    if not ob or not ob.get("bids"):
        return None
    best = ob["bids"][0][0]
    return round(sum(p * q for p, q in ob["bids"] if p >= best * 0.98), 2)


async def portal_vs_exchange(route_id: str) -> dict:
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        return {"route_id": route_id, "available": False, "note": "route not found"}
    rcache = collector.cache.get(route_id, {})
    ev = rcache.get("_evaluation") or {}
    portal = portal_price.current_bdag_price()
    exit_ex = route["exit"]["exchange"]
    role_map = await venue_registry.get_role_map()

    # best exchange by best bid across listed venues
    best = None
    for ex in route.get("comparison_exchanges", []):
        ob = (rcache.get(ex) or {}).get("orderbook")
        if ob and ob.get("bids"):
            bid = ob["bids"][0][0]
            if best is None or bid > best["bid"]:
                best = {"exchange": ex, "bid": bid}

    exit_ob = (rcache.get(exit_ex) or {}).get("orderbook")
    exit_bid = exit_ob["bids"][0][0] if (exit_ob and exit_ob.get("bids")) else None
    net = (ev.get("spread") or {}).get("net_pct")
    cap = ev.get("capacity") or {}
    max_safe = cap.get("max_safe")
    recommended = cap.get("recommended")
    bp = (ev.get("inputs") or {}).get("buy_price") or portal
    gross = round((exit_bid - bp) / bp * 100, 3) if (exit_bid and bp) else None
    expected_profit = round(recommended * bp * net / 100, 2) if (recommended and bp and net is not None) else None
    max_safe_quote = round(max_safe * bp, 2) if (max_safe and bp) else None

    return {
        "route_id": route_id, "available": bool(ev),
        "portal_price": portal, "portal_stale": portal is None,
        "buy_price_used": bp, "price_source": (ev.get("inputs") or {}).get("price_source"),
        "exit_venue": exit_ex, "exit_venue_role": role_map.get(exit_ex, "watch"),
        "best_exchange": (best or {}).get("exchange"),
        "best_exchange_price": (best or {}).get("bid"),
        "exit_best_bid": exit_bid,
        "gross_spread_pct": gross,
        "net_spread_pct": round(net, 3) if net is not None else None,
        "liquidity_quote_2pct": _bid_depth_2pct(exit_ob),
        "max_safe_size_base": max_safe, "max_safe_size_quote": max_safe_quote,
        "recommended_size_base": recommended,
        "expected_profit_quote": expected_profit,
        "verdict": ev.get("verdict"),
        "note": "Read-only intelligence — no execution.",
    }
