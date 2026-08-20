"""ArbiCore X — Expected-Value engine (P0-9).

EV = P(success) * net_profit - P(failure) * maximum_loss.

Success probability is **evidence-based**: it is built from measurable
signals (simulation result, quote freshness, liquidity headroom, gas
certainty, MEV risk, historical route success). When evidence is missing
we do NOT invent confidence — we penalise the estimate toward uncertainty.

Pure / deterministic. No I/O, no RPC. Never a safety gate.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any, Dict, Optional


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


@dataclass
class ExpectedValueResult:
    net_profit_usd: float
    maximum_loss_usd: float
    success_probability: float
    failure_probability: float
    expected_value_usd: float
    uncertainty_penalty: float
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Weight of each evidence signal in the success-probability estimate.
_P_WEIGHTS = {
    "simulation_passed": 0.30,
    "quote_fresh": 0.20,
    "liquidity_headroom": 0.15,
    "gas_certainty": 0.10,
    "mev_safety": 0.10,
    "historical_success": 0.15,
}


def estimate_success_probability(
    *,
    simulation_passed: Optional[bool] = None,
    quote_age_sec: Optional[float] = None,
    quote_max_age_sec: float = 12.0,
    liquidity_ratio: Optional[float] = None,   # notional / pool_liquidity
    gas_certainty: Optional[float] = None,      # 0..1
    mev_risk: Optional[float] = None,           # 0..1 (higher = riskier)
    historical_success_rate: Optional[float] = None,  # 0..1
) -> Dict[str, Any]:
    """Return {'probability', 'uncertainty_penalty', 'signals'} in [0,1].

    Missing signals contribute their weight to an uncertainty penalty
    rather than a neutral 0.5 — absence of evidence lowers confidence.
    A failed simulation hard-caps the probability at 0.10.
    """
    signals: Dict[str, float] = {}
    missing_weight = 0.0
    acc = 0.0

    def _apply(key: str, value: Optional[float]):
        nonlocal acc, missing_weight
        w = _P_WEIGHTS[key]
        if value is None:
            missing_weight += w
            return
        v = _clamp(value)
        signals[key] = round(v, 4)
        acc += w * v

    _apply("simulation_passed",
            None if simulation_passed is None else (1.0 if simulation_passed else 0.0))
    if quote_age_sec is None:
        _apply("quote_fresh", None)
    else:
        fresh = 1.0 - _clamp(float(quote_age_sec) / max(quote_max_age_sec, 1e-6))
        _apply("quote_fresh", fresh)
    if liquidity_ratio is None:
        _apply("liquidity_headroom", None)
    else:
        # 1% of pool → ~high headroom; 20%+ → low.
        _apply("liquidity_headroom", 1.0 - _clamp(float(liquidity_ratio) / 0.20))
    _apply("gas_certainty", gas_certainty)
    _apply("mev_safety", None if mev_risk is None else 1.0 - _clamp(mev_risk))
    _apply("historical_success", historical_success_rate)

    # Normalise over present weight, then penalise for missing evidence.
    present_weight = 1.0 - missing_weight
    base = (acc / present_weight) if present_weight > 1e-9 else 0.0
    uncertainty_penalty = round(missing_weight, 4)          # 0..1
    probability = _clamp(base * (1.0 - 0.5 * missing_weight))
    if simulation_passed is False:
        probability = min(probability, 0.10)
    return {"probability": round(probability, 4),
            "uncertainty_penalty": uncertainty_penalty,
            "signals": signals}


def compute_expected_value(
    *, net_profit_usd: float, maximum_loss_usd: float,
    success_probability: float,
    evidence: Optional[Dict[str, Any]] = None,
) -> ExpectedValueResult:
    p = _clamp(success_probability)
    q = 1.0 - p
    ev = p * float(net_profit_usd) - q * abs(float(maximum_loss_usd))
    return ExpectedValueResult(
        net_profit_usd=round(float(net_profit_usd), 6),
        maximum_loss_usd=round(abs(float(maximum_loss_usd)), 6),
        success_probability=round(p, 4),
        failure_probability=round(q, 4),
        expected_value_usd=round(ev, 6),
        uncertainty_penalty=float((evidence or {}).get("uncertainty_penalty", 0.0)),
        evidence=evidence or {},
    )


def evaluate_expected_value(
    *, net_profit_usd: float, maximum_loss_usd: float, **prob_kwargs: Any,
) -> ExpectedValueResult:
    est = estimate_success_probability(**prob_kwargs)
    return compute_expected_value(
        net_profit_usd=net_profit_usd, maximum_loss_usd=maximum_loss_usd,
        success_probability=est["probability"], evidence=est)


__all__ = [
    "ExpectedValueResult", "estimate_success_probability",
    "compute_expected_value", "evaluate_expected_value",
]
