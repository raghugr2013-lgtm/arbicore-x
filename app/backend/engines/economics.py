"""Opportunity economics primitives — episode detection over evaluation series.
Shared by the economics endpoint (api.py) and the quality engine (Sprint 4)."""
from datetime import datetime


def ts_secs(a: str, b: str) -> float:
    try:
        return (datetime.fromisoformat(b) - datetime.fromisoformat(a)).total_seconds()
    except ValueError:
        return 0.0


def episodes(docs, flag_fn, gap_s=60):
    """Group consecutive flagged evaluations into episodes.
    docs: [{ts, verdict, spread.net_pct, capacity.recommended, inputs.buy_price, gates}]"""
    eps, cur = [], None
    for d in docs:
        if not flag_fn(d):
            if cur:
                eps.append(cur)
                cur = None
            continue
        ts = d["ts"]
        if cur and ts_secs(cur["end"], ts) > gap_s:
            eps.append(cur)
            cur = None
        if cur is None:
            cur = {"start": ts, "end": ts, "evals": 0, "nets": [], "recs": [],
                   "profits": [], "go_evals": 0, "gate_fails": {}}
        cur["end"] = ts
        cur["evals"] += 1
        net = (d.get("spread") or {}).get("net_pct")
        rec = (d.get("capacity") or {}).get("recommended")
        bp = (d.get("inputs") or {}).get("buy_price")
        if net is not None:
            cur["nets"].append(net)
        if rec:
            cur["recs"].append(rec)
        if net is not None and rec and bp:
            cur["profits"].append(rec * bp * net / 100)
        if d.get("verdict") == "GO":
            cur["go_evals"] += 1
        for g in d.get("gates", []):
            if not g.get("passed"):
                cur["gate_fails"][g["id"]] = cur["gate_fails"].get(g["id"], 0) + 1
    if cur:
        eps.append(cur)
    return eps


def final_episode(ep, cadence_s=10):
    nets, recs, profits = ep["nets"], ep["recs"], ep["profits"]
    return {"start": ep["start"], "end": ep["end"],
            "duration_min": round((ts_secs(ep["start"], ep["end"]) + cadence_s) / 60, 1),
            "evals": ep["evals"],
            "avg_net_pct": round(sum(nets) / len(nets), 3) if nets else None,
            "peak_net_pct": round(max(nets), 3) if nets else None,
            "avg_recommended": round(sum(recs) / len(recs), 1) if recs else None,
            "est_profit_quote": round(sum(profits) / len(profits), 2) if profits else None,
            "had_go": ep["go_evals"] > 0, "gate_fails": ep["gate_fails"]}


def summary(finals):
    total_min = round(sum(e["duration_min"] for e in finals), 1)
    nets = [e["avg_net_pct"] for e in finals if e["avg_net_pct"] is not None]
    peaks = [e["peak_net_pct"] for e in finals if e["peak_net_pct"] is not None]
    recs = [e["avg_recommended"] for e in finals if e["avg_recommended"]]
    profits = [e["est_profit_quote"] for e in finals if e["est_profit_quote"] is not None]
    return {"episodes": len(finals), "total_minutes": total_min,
            "avg_duration_min": round(total_min / len(finals), 1) if finals else 0,
            "avg_net_pct": round(sum(nets) / len(nets), 3) if nets else None,
            "best_net_pct": round(max(peaks), 3) if peaks else None,
            "avg_recommended": round(sum(recs) / len(recs), 1) if recs else None,
            "est_profit_quote": round(sum(profits), 2) if profits else None}
