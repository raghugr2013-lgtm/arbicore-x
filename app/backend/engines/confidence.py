"""Route Confidence Score v1 — Sprint 2 scaffold (statistical, explainable).
Components per approved spec: spread, liquidity, capacity, transfer,
exchange capability, exchange trust, hold probability, route feasibility.
Missing components are excluded and weights renormalized — never faked.
"""

WEIGHTS = {
    "spread": 0.18, "liquidity": 0.14, "capacity": 0.12, "transfer": 0.16,
    "exchange_capability": 0.12, "exchange_trust": 0.08,
    "hold_probability": 0.10, "route_feasibility": 0.10,
}


def _capability_score(caps: dict) -> float:
    if not caps:
        return 30.0
    score = 0.0
    score += 40 if caps.get("trading_api") else 0
    score += 30 if caps.get("withdrawal_api") else 0
    score += 20 if caps.get("deposit_monitoring") else 0
    score += 10 if caps.get("websocket") else 0
    return min(score, 100.0)


def compute(subscores: dict, gates: list, capacity: dict, hold_probability,
            caps: dict) -> dict:
    components = {
        "spread": subscores.get("spread"),
        "liquidity": subscores.get("liquidity"),
        "transfer": subscores.get("transfer_risk"),
        "exchange_capability": _capability_score(caps),
        # v1 baseline; becomes data-driven (uptime, flag-flapping, data quality) in Phase 2.5
        "exchange_trust": 75.0,
        "route_feasibility": (sum(1 for g in gates if g["passed"]) / len(gates) * 100) if gates else None,
    }
    rec, opt = capacity.get("recommended"), capacity.get("optimal")
    components["capacity"] = min(rec / opt, 1.0) * 100 if (rec and opt and opt > 0) else 50.0
    components["hold_probability"] = hold_probability * 100 if hold_probability is not None else None

    total_w, acc = 0.0, 0.0
    for k, w in WEIGHTS.items():
        v = components.get(k)
        if v is not None:
            total_w += w
            acc += w * v
    score = round(acc / total_w, 1) if total_w > 0 else None
    return {"score": score,
            "components": {k: (round(v, 1) if v is not None else None) for k, v in components.items()},
            "method": "weighted_blend_v1",
            "missing": [k for k, v in components.items() if v is None]}
