"""Exchange Health Analytics (Sprint 4) — read-only telemetry aggregation.
Per exchange: API uptime %, deposit/withdraw gate uptime %, average gate-open
duration, capability flip frequency, composite reliability score."""
from datetime import datetime, timedelta, timezone

from services import db
from services.ws_manager import ws_manager

EXCHANGES = ("xt", "mexc", "gate", "bitmart", "coinstore")
WEIGHTS = {"api": 0.35, "deposit": 0.25, "withdraw": 0.20, "stability": 0.20}


def _cutoff(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()


def _pct(flags):
    vals = [f for f in flags if f is not None]
    if not vals:
        return None
    return round(sum(1 for f in vals if f) / len(vals) * 100, 1)


def _avg_open_minutes(flips, current_open, hours):
    """Average duration deposit gate stayed open, from flip history."""
    opens = []
    open_since = None
    for f in flips:  # ascending ts
        if f["field"] != "deposit_enabled":
            continue
        if f["to"] is True:
            open_since = f["ts"]
        elif f["to"] is False and open_since:
            try:
                d = (datetime.fromisoformat(f["ts"]) - datetime.fromisoformat(open_since))
                opens.append(d.total_seconds() / 60)
            except ValueError:
                pass
            open_since = None
    if not opens:
        if current_open and not any(f["field"] == "deposit_enabled" for f in flips):
            return round(hours * 60, 1)  # open the whole window — stable
        return None
    return round(sum(opens) / len(opens), 1)


async def exchange_health(hours: float = 24, currency: str = "BDAG"):
    cutoff = _cutoff(hours)
    ws = ws_manager.status()
    out = []
    for ex in EXCHANGES:
        # API uptime (REST request success rate, 5-min buckets)
        snaps = await db.exchange_health_snaps.find(
            {"exchange": ex, "ts": {"$gte": cutoff}}, {"_id": 0}).to_list(5000)
        req = sum(s.get("requests", 0) for s in snaps)
        errs = sum(s.get("errors", 0) for s in snaps)
        api_uptime = round((1 - errs / req) * 100, 1) if req else None
        lat = [s["avg_latency_ms"] * s["requests"] for s in snaps if s.get("avg_latency_ms")]
        avg_latency = round(sum(lat) / req, 1) if req and lat else None

        # gate uptime from LIVE fee snapshots (collected every ~4 min; sim excluded)
        fees = await db.fee_snapshots.find(
            {"exchange": ex, "currency": currency, "ts": {"$gte": cutoff}, "mode": "live"},
            {"_id": 0, "deposit_enabled": 1, "withdraw_enabled": 1}).to_list(20000)
        dep_uptime = _pct([f.get("deposit_enabled") for f in fees])
        wd_uptime = _pct([f.get("withdraw_enabled") for f in fees])

        # capability flips
        flips = await db.capability_history.find(
            {"exchange": ex, "ts": {"$gte": cutoff}}, {"_id": 0}).sort("ts", 1).to_list(2000)
        flips_per_day = round(len(flips) / max(hours / 24, 1 / 24), 2)
        stability = round((1 - min(flips_per_day / 10, 1)) * 100, 1)

        cap = await db.capabilities_col.find_one({"exchange": ex, "currency": currency}, {"_id": 0})
        avg_open = _avg_open_minutes(flips, (cap or {}).get("deposit_enabled"), hours)

        components = {"api": api_uptime, "deposit": dep_uptime,
                      "withdraw": wd_uptime, "stability": stability}
        total_w = acc = 0.0
        for k, w in WEIGHTS.items():
            if components[k] is not None:
                total_w += w
                acc += w * components[k]
        reliability = round(acc / total_w, 1) if total_w >= 0.5 else None

        out.append({"exchange": ex,
                    "api_uptime_pct": api_uptime, "avg_latency_ms": avg_latency,
                    "requests": req,
                    "deposit_uptime_pct": dep_uptime, "withdraw_uptime_pct": wd_uptime,
                    "avg_gate_open_min": avg_open, "flips_per_day": flips_per_day,
                    "flips_in_window": len(flips),
                    "stability_pct": stability, "reliability_score": reliability,
                    "ws_mode": (ws.get(ex) or {}).get("mode"),
                    "samples": {"api_buckets": len(snaps), "gate_snapshots": len(fees)}})
    return out
