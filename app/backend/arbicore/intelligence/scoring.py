"""ArbiCore X — Chain / Opportunity Scoring Engine.

Migrated from ArbitrageX ``calculate_*_score`` (server.py L1965-1998).
Pure, stateless, execution-free.

Dependency map:
    - stdlib only (dataclasses)
    - consumes a ChainProfile (decoupled from global CHAIN_CONFIG)
    - weights are injectable so the future learning engine can make them adaptive

Example:
    >>> engine = ScoringEngine()
    >>> profile = ChainProfile("polygon", min_spread_percent=0.6,
    ...                         gas_score=1, mev_risk_score=1.5, min_chain_score=8)
    >>> b = engine.score(spread_percent=1.2, duration_seconds=45,
    ...                  available_liquidity=1_000_000, trade_amount=10_000,
    ...                  profile=profile)
    >>> b.chain_score > 0
    True
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChainProfile:
    name: str
    min_spread_percent: float
    gas_score: float        # gas penalty weight (denominator)
    mev_risk_score: float   # mev penalty weight (denominator)
    min_chain_score: float


@dataclass(frozen=True)
class ScoringWeights:
    """Injectable weights. Defaults reproduce ArbitrageX behaviour exactly."""

    spread_multiplier: float = 5.0
    spread_score_cap: float = 10.0
    liquidity_score_cap: float = 10.0
    required_liquidity_multiplier: float = 2.0  # required = trade_amount * 2
    # persistence step thresholds (seconds) -> score
    persistence_steps: tuple = ((10, 1.0), (30, 4.0), (60, 7.0))
    persistence_max: float = 10.0


@dataclass(frozen=True)
class ScoreBreakdown:
    spread_score: float
    persistence_score: float
    liquidity_score: float
    gas_penalty: float
    mev_penalty: float
    chain_score: float
    meets_threshold: bool

    def as_dict(self) -> dict:
        return {
            "spread_score": self.spread_score,
            "persistence_score": self.persistence_score,
            "liquidity_score": self.liquidity_score,
            "gas_penalty": self.gas_penalty,
            "mev_penalty": self.mev_penalty,
            "chain_score": self.chain_score,
            "meets_threshold": self.meets_threshold,
        }


class ScoringEngine:
    def __init__(self, weights: ScoringWeights | None = None) -> None:
        self.weights = weights or ScoringWeights()

    def spread_score(self, spread_percent: float, profile: ChainProfile) -> float:
        if profile.min_spread_percent <= 0:
            return 0.0
        raw = (spread_percent / profile.min_spread_percent) * self.weights.spread_multiplier
        return round(min(raw, self.weights.spread_score_cap), 2)

    def persistence_score(self, duration_seconds: float) -> float:
        for threshold, value in self.weights.persistence_steps:
            if duration_seconds < threshold:
                return value
        return self.weights.persistence_max

    def liquidity_score(self, available_liquidity: float, required_liquidity: float) -> float:
        if required_liquidity <= 0:
            return 0.0
        return round(min(available_liquidity / required_liquidity, self.weights.liquidity_score_cap), 4)

    def score(
        self,
        *,
        spread_percent: float,
        duration_seconds: float,
        available_liquidity: float,
        trade_amount: float,
        profile: ChainProfile,
    ) -> ScoreBreakdown:
        s = self.spread_score(spread_percent, profile)
        p = self.persistence_score(duration_seconds)
        liq = self.liquidity_score(
            available_liquidity, trade_amount * self.weights.required_liquidity_multiplier
        )
        gas_penalty = profile.gas_score
        mev_penalty = profile.mev_risk_score

        denominator = gas_penalty * mev_penalty
        chain_score = round((s * p * liq) / denominator, 2) if denominator > 0 else 0.0

        return ScoreBreakdown(
            spread_score=s,
            persistence_score=p,
            liquidity_score=liq,
            gas_penalty=gas_penalty,
            mev_penalty=mev_penalty,
            chain_score=chain_score,
            meets_threshold=chain_score >= profile.min_chain_score,
        )
