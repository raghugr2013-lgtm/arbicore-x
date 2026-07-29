"""Safety Score Engine — four explainable subscores, 0-100 each."""
import math
from typing import List, Optional


def _clamp(x):
    return max(0.0, min(100.0, x))


def spread_score(net_spread_pct: Optional[float]) -> float:
    """Piecewise-linear: <=0% -> 0, 2% -> 40, 5% -> 70, >=10% -> 100."""
    if net_spread_pct is None:
        return 0.0
    s = net_spread_pct
    if s <= 0:
        return 0.0
    if s <= 2:
        return _clamp(s / 2 * 40)
    if s <= 5:
        return _clamp(40 + (s - 2) / 3 * 30)
    if s <= 10:
        return _clamp(70 + (s - 5) / 5 * 30)
    return 100.0


def liquidity_score(depth_quote_2pct: Optional[float], volume_24h_quote: Optional[float],
                    spread_bps: Optional[float]) -> dict:
    """Weighted: depth within 2% of mid (50%), 24h volume (30%), top-of-book tightness (20%)."""
    depth_ref, vol_ref = 10000.0, 100000.0
    d = _clamp((depth_quote_2pct or 0) / depth_ref * 100)
    v = _clamp((volume_24h_quote or 0) / vol_ref * 100)
    if spread_bps is None:
        t = 0.0
    elif spread_bps <= 10:
        t = 100.0
    elif spread_bps >= 500:
        t = 0.0
    else:
        t = _clamp(100 - (spread_bps - 10) / 490 * 100)
    return {"score": _clamp(0.5 * d + 0.3 * v + 0.2 * t),
            "inputs": {"depth_quote_2pct": depth_quote_2pct, "volume_24h_quote": volume_24h_quote,
                       "spread_bps": spread_bps, "depth_sub": d, "volume_sub": v, "tightness_sub": t}}


def volatility_score(closes: List[float], interval_min: int,
                     breakeven_distance_pct: Optional[float],
                     transfer_minutes: float) -> dict:
    """Stddev of log returns scaled to the transfer window vs breakeven cushion."""
    if len(closes) < 10:
        return {"score": 40.0, "inputs": {"note": "insufficient candle history", "n": len(closes)}}
    rets = []
    for a, b in zip(closes[:-1], closes[1:]):
        if a > 0 and b > 0:
            rets.append(math.log(b / a))
    if len(rets) < 5:
        return {"score": 40.0, "inputs": {"note": "insufficient returns"}}
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / max(len(rets) - 1, 1)
    sigma = math.sqrt(var)
    vol_window_pct = sigma * math.sqrt(max(transfer_minutes, 1) / interval_min) * 100
    if breakeven_distance_pct is None or vol_window_pct <= 0:
        ratio = 0.0
    else:
        ratio = breakeven_distance_pct / vol_window_pct
    # ratio >=3 -> 100, <=0.5 -> 0, linear between
    if ratio >= 3:
        score = 100.0
    elif ratio <= 0.5:
        score = 0.0
    else:
        score = _clamp((ratio - 0.5) / 2.5 * 100)
    return {"score": score, "inputs": {"sigma_per_candle": sigma, "vol_window_pct": vol_window_pct,
                                       "breakeven_distance_pct": breakeven_distance_pct,
                                       "cushion_ratio": ratio, "transfer_minutes": transfer_minutes}}


def transfer_risk_score(deposit_enabled: Optional[bool], withdraw_enabled: Optional[bool],
                        confirmations: Optional[int], est_transfer_minutes: float,
                        rpc_healthy: Optional[bool], has_transfer_history: bool) -> dict:
    inputs = {"deposit_enabled": deposit_enabled, "withdraw_enabled": withdraw_enabled,
              "confirmations": confirmations, "est_transfer_minutes": est_transfer_minutes,
              "rpc_healthy": rpc_healthy, "has_transfer_history": has_transfer_history}
    if deposit_enabled is False:
        return {"score": 0.0, "inputs": inputs, "note": "deposits disabled on exit exchange"}
    score = 100.0 if deposit_enabled is True else 55.0  # unknown status
    if rpc_healthy is False:
        score -= 20
    if est_transfer_minutes > 30:
        score -= 15
    if not has_transfer_history:
        score -= 10
    if withdraw_enabled is False:
        score -= 10  # settlement leg friction (asset withdrawal from exchange)
    return {"score": _clamp(score), "inputs": inputs}


def overall(sub: dict, weights: dict) -> float:
    return _clamp(
        weights.get("spread", 0.30) * sub["spread"]
        + weights.get("liquidity", 0.25) * sub["liquidity"]
        + weights.get("volatility", 0.20) * sub["volatility"]
        + weights.get("transfer", 0.25) * sub["transfer_risk"]
    )
