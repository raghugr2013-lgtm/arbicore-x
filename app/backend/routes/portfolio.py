"""Portfolio & Real Account Intelligence endpoints (Sprint 4) — READ-ONLY.
Balances, deployable capital, allocation analysis, exchange health, quality."""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from engines import deployable as deployable_engine
from engines import quality as quality_engine
from services import db, health_analytics
from services.auth import require_auth
from services.balances import balance_service
from services.collector import collector

router = APIRouter(prefix="/api", tags=["portfolio"], dependencies=[Depends(require_auth)])


def _cutoff(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


async def _route(route_id: Optional[str]):
    q = {"id": route_id} if route_id else {"active": True}
    route = await db.routes_col.find_one(q, {"_id": 0})
    if not route:
        raise HTTPException(404, "Route not found")
    return route


async def _latest_eval(rid):
    ev = (collector.cache.get(rid) or {}).get("_evaluation")
    if ev:
        return ev
    return await db.evaluations.find_one({"route_id": rid}, {"_id": 0}, sort=[("ts", -1)])


# ---------------- balances ----------------

@router.get("/portfolio/balances")
async def portfolio_balances():
    return balance_service.status_full()


@router.post("/portfolio/refresh")
async def portfolio_refresh():
    if balance_service.refresh_now():
        return {"ok": True, "message": "Refresh triggered — polling all configured exchanges now"}
    return {"ok": False, "message": "A poll just ran — try again in a few seconds"}


# ---------------- deployable capital ----------------

@router.get("/portfolio/deployable")
async def portfolio_deployable(route_id: Optional[str] = None):
    route = await _route(route_id)
    ev = await _latest_eval(route["id"])
    if not ev:
        raise HTTPException(404, "No evaluation available yet")
    base = route["exit"]["base"]
    quote = route["exit"]["quote"]
    price = (ev.get("market") or {}).get("mid") or (ev.get("market") or {}).get("last") \
        or (ev.get("inputs") or {}).get("buy_price")
    caps = {c["exchange"]: c for c in await db.capabilities_col.find(
        {"currency": base.upper()}, {"_id": 0}).to_list(50)}
    venues = []
    for entry in ev.get("venue_matrix", []):
        ex = entry["exchange"]
        balance = {"has_key": balance_service.has_key(ex),
                   "free_base": balance_service.get_free(ex, base),
                   "free_quote": balance_service.get_free(ex, quote)}
        venues.append(deployable_engine.compute_venue(entry, balance, caps.get(ex), price))
    order = {"LIQUIDITY_LIMITED": 0, "CAPITAL_LIMITED": 1, "WITHDRAWAL_GATE_LIMITED": 2,
             "DEPOSIT_GATE_LIMITED": 3, "NO_KEY": 4, "ROUTE_LIMITED": 5}
    venues.sort(key=lambda v: order.get(v["limiting_factor"], 9))
    return {"route_id": route["id"], "ts": ev.get("ts"), "base": base, "quote": quote,
            "price": price, "venues": venues,
            "note": "Informational analysis only — no transfers or execution exist in this build."}


# ---------------- capital allocation ----------------

@router.get("/portfolio/allocation")
async def portfolio_allocation(route_id: Optional[str] = None, hours: float = 24):
    hours = max(1.0, min(hours, 168))
    route = await _route(route_id)
    min_net = route.get("risk_profile", {}).get("min_net_spread_pct", 2.0)
    docs = await db.evaluations.find(
        {"route_id": route["id"], "ts": {"$gte": _cutoff(hours)},
         "mode": route.get("mode", "live")},
        {"_id": 0, "venue_matrix.exchange": 1, "venue_matrix.verdict": 1,
         "venue_matrix.net_spread_pct": 1},
    ).sort("ts", -1).to_list(50000)

    go_counts, raw_counts = {}, {}
    for d in docs:
        for e in d.get("venue_matrix", []):
            ex = e["exchange"]
            if e.get("verdict") == "GO":
                go_counts[ex] = go_counts.get(ex, 0) + 1
            net = e.get("net_spread_pct")
            if net is not None and net >= min_net:
                raw_counts[ex] = raw_counts.get(ex, 0) + 1

    total_go = sum(go_counts.values())
    totals = balance_service.totals()
    known = {ex: v for ex, v in totals.items() if v is not None}
    total_cap = round(sum(known.values()), 2) if known else None

    venues = []
    for ex in route.get("comparison_exchanges", []):
        cap_usd = totals.get(ex)
        venues.append({
            "exchange": ex,
            "capital_usd": cap_usd,
            "capital_pct": round(cap_usd / total_cap * 100, 1) if (cap_usd is not None and total_cap) else None,
            "go_minutes": round(go_counts.get(ex, 0) * 10 / 60, 1),
            "raw_minutes": round(raw_counts.get(ex, 0) * 10 / 60, 1),
            "opportunity_pct": round(go_counts.get(ex, 0) / total_go * 100, 1) if total_go else None,
        })

    recommendations = []
    if total_cap is None or total_cap == 0:
        recommendations.append("No balance data yet — add read-only API keys in Settings → "
                               "Vault to unlock capital-vs-opportunity analysis.")
    elif total_go == 0:
        recommendations.append("No executable (GO) minutes in the window — nothing to allocate against yet.")
    else:
        for v in venues:
            if v["opportunity_pct"] is None:
                continue
            cap_pct = v["capital_pct"] if v["capital_pct"] is not None else 0.0
            gap = v["opportunity_pct"] - cap_pct
            if gap >= 15 and v["go_minutes"] > 0:
                recommendations.append(
                    f"{v['opportunity_pct']:.0f}% of executable (GO) minutes occurred on "
                    f"{v['exchange'].upper()} but only {cap_pct:.0f}% of tracked capital is there.")
            elif gap <= -30 and cap_pct > 0:
                recommendations.append(
                    f"{cap_pct:.0f}% of capital sits on {v['exchange'].upper()} which produced "
                    f"only {v['opportunity_pct']:.0f}% of executable minutes in the window.")
        if not recommendations:
            recommendations.append("Capital distribution roughly matches where opportunities occur.")

    return {"route_id": route["id"], "hours": hours, "evaluations": len(docs),
            "total_capital_usd": total_cap, "total_go_minutes": round(total_go * 10 / 60, 1),
            "venues": venues, "recommendations": recommendations,
            "note": "Informational only — ArbiCore performs no transfers or rebalancing."}


# ---------------- exchange health analytics ----------------

@router.get("/health/exchanges")
async def health_exchanges(hours: float = 24, currency: str = "BDAG"):
    from core import healthstats
    hours = max(1.0, min(hours, 720))
    return {"hours": hours, "currency": currency.upper(),
            "live_counters_since_last_flush": healthstats.current(),
            "exchanges": await health_analytics.exchange_health(hours, currency.upper())}


# ---------------- opportunity quality / automation readiness ----------------

@router.get("/quality")
async def opportunity_quality(route_id: Optional[str] = None, hours: float = 24):
    hours = max(1.0, min(hours, 720))
    route = await _route(route_id)
    min_net = route.get("risk_profile", {}).get("min_net_spread_pct", 2.0)
    base = route["exit"]["base"]

    docs = await db.evaluations.find(
        {"route_id": route["id"], "ts": {"$gte": _cutoff(hours)},
         "mode": route.get("mode", "live")},
        {"_id": 0, "ts": 1, "inputs.buy_price": 1, "venue_matrix": 1},
    ).sort("ts", -1).to_list(50000)
    docs.reverse()  # ascending; capped at the most recent 50k evaluations

    health = {h["exchange"]: h for h in await health_analytics.exchange_health(hours)}

    venues = []
    for ex in route.get("comparison_exchanges", []):
        series = []
        for d in docs:
            entry = next((e for e in d.get("venue_matrix", []) if e["exchange"] == ex), None)
            if entry:
                series.append((d["ts"], entry, (d.get("inputs") or {}).get("buy_price")))
        venues.append(quality_engine.venue_quality(
            ex, series, hours, min_net, health.get(ex),
            balance_service.get_free(ex, base)))
    venues.sort(key=lambda v: -(v["readiness_score"] or -1))

    return {"route_id": route["id"], "route_name": route.get("name"), "hours": hours,
            "min_net_spread_pct": min_net, "evaluations": len(docs), "venues": venues,
            "weights": quality_engine.WEIGHTS,
            "note": "Automation Readiness identifies which opportunities may justify FUTURE "
                    "automation. No execution capability exists in this build."}
