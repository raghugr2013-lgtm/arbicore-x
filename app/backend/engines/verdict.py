"""GO / NO-GO Engine — hard gates first, score thresholds second.
Every verdict carries machine-readable reasons.
"""
from typing import List, Optional


def evaluate_gates(deposit_enabled: Optional[bool], market_online: bool,
                   ticker_age_s: Optional[float], depth_age_s: Optional[float],
                   net_spread_at_min: Optional[float]) -> List[dict]:
    gates = []
    if deposit_enabled is False:
        gates.append({"id": "G1_DEPOSIT", "passed": False,
                      "detail": "Asset deposits DISABLED on exit exchange — transfer leg blocked"})
    else:
        detail = "Deposits enabled" if deposit_enabled else "Deposit status unknown (no public flag; verify in Phase 2)"
        gates.append({"id": "G1_DEPOSIT", "passed": True, "detail": detail})

    gates.append({"id": "G2_MARKET", "passed": market_online,
                  "detail": "Market online" if market_online else "Pair not listed / trading unavailable"})

    stale = (ticker_age_s is not None and ticker_age_s > 60) or (depth_age_s is not None and depth_age_s > 90)
    no_data = ticker_age_s is None or depth_age_s is None
    gates.append({"id": "G3_FRESHNESS", "passed": not (stale or no_data),
                  "detail": "Data fresh" if not (stale or no_data)
                  else f"Stale/missing data (ticker {ticker_age_s}s, depth {depth_age_s}s)"})

    profitable = net_spread_at_min is not None and net_spread_at_min > 0
    gates.append({"id": "G4_PROFITABLE", "passed": profitable,
                  "detail": "Profitable at minimum size" if profitable
                  else "Net spread <= 0 at minimum size — unprofitable at any size"})
    return gates


def verdict(gates: List[dict], overall_score: float, subscores: dict, risk: dict) -> dict:
    go_t = risk.get("go_threshold", 70)
    wait_t = risk.get("wait_threshold", 45)
    floor = risk.get("subscore_floor", 40)

    reasons = []
    failed = [g for g in gates if not g["passed"]]
    if failed:
        for g in failed:
            reasons.append(f"GATE {g['id']}: {g['detail']}")
        return {"verdict": "NO_GO", "reasons": reasons}

    low_subs = [k for k, v in subscores.items() if v < floor]
    if overall_score >= go_t and not low_subs:
        reasons.append(f"Overall safety {overall_score:.0f} >= {go_t}, all subscores above floor")
        return {"verdict": "GO", "reasons": reasons}
    if overall_score >= wait_t:
        if low_subs:
            reasons.append(f"Subscores below floor ({floor}): {', '.join(low_subs)}")
        reasons.append(f"Overall safety {overall_score:.0f} in WAIT band [{wait_t}, {go_t})")
        return {"verdict": "WAIT", "reasons": reasons}
    reasons.append(f"Overall safety {overall_score:.0f} < {wait_t}")
    if low_subs:
        reasons.append(f"Weak subscores: {', '.join(low_subs)}")
    return {"verdict": "NO_GO", "reasons": reasons}
