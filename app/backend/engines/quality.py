"""Opportunity Quality & Automation Readiness scoring (Sprint 4).
Per venue: frequency, duration, spread, capacity, confidence, route stability,
exchange health, gate reliability → weighted 0–100 readiness score.
Purpose: identify which opportunities justify FUTURE automation. Read-only."""
from engines import economics

WEIGHTS = {"frequency": 0.15, "duration": 0.15, "spread": 0.15, "capacity": 0.10,
           "confidence": 0.10, "stability": 0.10, "exchange_health": 0.15,
           "gate_reliability": 0.10}

# normalization targets ("full marks" thresholds)
TARGET_EPISODES_PER_DAY = 6.0
TARGET_DURATION_MIN = 10.0
TARGET_NET_PCT = 5.0
TARGET_CAPACITY_QUOTE = 500.0
FLIPS_PER_DAY_CEILING = 20.0


def _label(score):
    if score is None:
        return "INSUFFICIENT DATA"
    if score >= 70:
        return "READY"
    if score >= 45:
        return "PROMISING"
    return "NOT READY"


def venue_quality(exchange: str, series: list, hours: float, min_net: float,
                  health: dict, free_base) -> dict:
    """series: [(ts, venue_matrix_entry, buy_price)] in ascending ts order."""
    days = max(hours / 24, 1 / 24)
    docs = [{"ts": ts,
             "verdict": e.get("verdict"),
             "spread": {"net_pct": e.get("net_spread_pct")},
             "capacity": {"recommended": e.get("recommended")},
             "inputs": {"buy_price": bp},
             "gates": []} for ts, e, bp in series]

    raw_eps = [economics.final_episode(x) for x in economics.episodes(
        docs, lambda d: d["spread"]["net_pct"] is not None and d["spread"]["net_pct"] >= min_net)]
    go_eps = [economics.final_episode(x) for x in economics.episodes(
        docs, lambda d: d.get("verdict") == "GO")]
    raw, go = economics.summary(raw_eps), economics.summary(go_eps)

    confs = [e.get("confidence") for _, e, _ in series if e.get("confidence") is not None]
    avg_conf = round(sum(confs) / len(confs), 1) if confs else None

    # route stability: venue verdict flip rate
    flips = 0
    prev = None
    for _, e, _ in series:
        v = e.get("verdict")
        if v and prev and v != prev:
            flips += 1
        if v:
            prev = v
    flips_per_day = round(flips / days, 2)

    price = next((bp for _, _, bp in reversed(series) if bp), None)
    cap_quote = round(raw["avg_recommended"] * price, 2) if (raw["avg_recommended"] and price) else None

    eps_per_day = round(raw["episodes"] / days, 2)
    profit_day = round(raw["est_profit_quote"] / days, 2) if raw["est_profit_quote"] is not None else None

    deployable = None
    deploy_ratio = None
    if free_base is not None and raw["avg_recommended"]:
        deployable = round(min(free_base, raw["avg_recommended"]), 1)
        deploy_ratio = min(free_base / raw["avg_recommended"], 1.0) if raw["avg_recommended"] > 0 else None
    deployable_profit_day = (round(profit_day * deploy_ratio, 2)
                             if (profit_day is not None and deploy_ratio is not None) else None)

    # ---- factor scores (0-100, None = missing → weight renormalized) ----
    factors = {
        "frequency": min(eps_per_day / TARGET_EPISODES_PER_DAY, 1) * 100 if raw["episodes"] or docs else None,
        "duration": (min(raw["avg_duration_min"] / TARGET_DURATION_MIN, 1) * 100
                     if raw["episodes"] else (0.0 if docs else None)),
        "spread": (min(max(raw["avg_net_pct"], 0) / TARGET_NET_PCT, 1) * 100
                   if raw["avg_net_pct"] is not None else (0.0 if docs else None)),
        "capacity": min(cap_quote / TARGET_CAPACITY_QUOTE, 1) * 100 if cap_quote else None,
        "confidence": avg_conf,
        "stability": (1 - min(flips_per_day / FLIPS_PER_DAY_CEILING, 1)) * 100 if docs else None,
        "exchange_health": (health or {}).get("reliability_score"),
        "gate_reliability": (health or {}).get("deposit_uptime_pct"),
    }

    total_w = acc = 0.0
    for k, w in WEIGHTS.items():
        v = factors.get(k)
        if v is not None:
            total_w += w
            acc += w * v
    score = round(acc / total_w, 1) if total_w >= 0.5 else None

    return {"exchange": exchange, "samples": len(docs),
            "metrics": {
                "episodes": raw["episodes"], "episodes_per_day": eps_per_day,
                "avg_duration_min": raw["avg_duration_min"],
                "avg_net_spread_pct": raw["avg_net_pct"], "best_net_spread_pct": raw["best_net_pct"],
                "avg_capacity_base": raw["avg_recommended"], "avg_capacity_quote": cap_quote,
                "avg_confidence": avg_conf,
                "go_episodes": go["episodes"], "go_minutes": go["total_minutes"],
                "verdict_flips_per_day": flips_per_day,
                "est_deployable_base": deployable, "free_base": free_base,
                "est_profit_per_day_quote": profit_day,
                "est_deployable_profit_per_day_quote": deployable_profit_day,
            },
            "factors": {k: (round(v, 1) if v is not None else None) for k, v in factors.items()},
            "readiness_score": score, "readiness_label": _label(score)}


async def route_quality_report(route: dict, hours: float) -> dict:
    """Full per-venue quality report for a route — shared by the /quality
    endpoint and the hourly observation recorder (readiness snapshots)."""
    from datetime import datetime, timedelta, timezone

    from services import db, health_analytics
    from services.balances import balance_service

    min_net = route.get("risk_profile", {}).get("min_net_spread_pct", 2.0)
    base = route["exit"]["base"]
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    docs = await db.evaluations.find(
        {"route_id": route["id"], "ts": {"$gte": cutoff}, "mode": route.get("mode", "live")},
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
        venues.append(venue_quality(ex, series, hours, min_net, health.get(ex),
                                    balance_service.get_free(ex, base)))
    venues.sort(key=lambda v: -(v["readiness_score"] or -1))
    return {"min_net": min_net, "evaluations": len(docs), "venues": venues, "health": health}
