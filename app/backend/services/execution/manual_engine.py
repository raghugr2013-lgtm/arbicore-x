"""Manual Opportunity Engine (E2) — surfaces profitable BDAG opportunities for
MANUAL execution even when full automation is unavailable.

Reads the live evaluation venue matrix + portal price (read-only). For every
venue whose net spread clears the floor it emits an opportunity card: buy/sell
venue, quantity, expected profit, available liquidity, time window, route
classification, and the explicit manual action steps. No execution.
"""
from services import db
from services.collector import collector
from services.execution import classification, venue_registry
from services.portal_price import portal_price


def _liquidity_quote(ob):
    if not ob or not ob.get("bids"):
        return None, None
    best_bid = ob["bids"][0][0]
    liq = round(sum(p * q for p, q in ob["bids"] if p >= best_bid * 0.98), 2)
    return best_bid, liq


async def opportunities(route_id: str, min_net=None) -> dict:
    route = await db.routes_col.find_one({"id": route_id}, {"_id": 0})
    if not route:
        return {"route_id": route_id, "opportunities": [], "count": 0, "note": "route not found"}
    rcache = collector.cache.get(route_id, {})
    ev = rcache.get("_evaluation") or {}
    matrix = ev.get("venue_matrix", [])
    floor = min_net if min_net is not None else route.get("risk_profile", {}).get("min_net_spread_pct", 2.0)
    portal = portal_price.current_bdag_price()
    bp = (ev.get("inputs") or {}).get("buy_price") or portal
    role_map = await venue_registry.get_role_map()

    out = []
    for entry in matrix:
        ex = entry["exchange"]
        net = entry.get("net_spread_pct")
        if net is None or net < floor:
            continue
        rec = entry.get("recommended")
        best_bid, liq = _liquidity_quote((rcache.get(ex) or {}).get("orderbook"))
        est_profit = round(rec * bp * net / 100, 2) if (rec and bp) else None
        cls = await classification.classify(route, ex)
        manual_actions = [{"leg": l["leg"], "action": l["manual_action"]}
                          for l in cls["legs"] if not l["automatable"]]
        out.append({
            "buy_venue": "BlockDAG Portal", "buy_price": bp,
            "sell_venue": ex.upper(), "sell_price": best_bid,
            "venue_role": role_map.get(ex, "watch"),
            "qty_base": rec,
            "net_spread_pct": round(net, 3),
            "gross_spread_pct": round((best_bid - bp) / bp * 100, 3) if (best_bid and bp) else None,
            "est_profit_quote": est_profit,
            "liquidity_quote": liq,
            "time_window": "live — recompute each cycle",
            "classification": cls["classification"],
            "classification_label": cls["classification_label"],
            "automation_coverage_pct": cls["automation_coverage_pct"],
            "deposit_gate_open": entry.get("deposit_enabled"),
            "manual_actions": manual_actions,
        })
    out.sort(key=lambda o: -(o["est_profit_quote"] or 0))
    return {"route_id": route_id, "min_net_spread_pct": floor, "portal_price": portal,
            "count": len(out), "opportunities": out,
            "note": "Read-only opportunity surfacing — manual actions only, no automated execution."}
