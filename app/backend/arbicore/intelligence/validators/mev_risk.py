"""ArbiCore X — MEV Risk Validation / classification.

Migrated from ArbitrageX MEV_RISK_LEVELS + tagging (server.py L187, L2090-2102).

IMPORTANT: the ArbitrageX implementation derived "volatility" from a crude
``abs(spread% - 0.5)`` proxy. Here volatility is an explicit input so a real
rolling-volatility signal can be supplied. A helper proxy is provided but is
clearly labelled and must not be treated as a real measurement.

Example:
    >>> c = MevRiskClassifier()
    >>> c.classify(liquidity_usd=800_000, volatility=0.01).level.value
    'LOW'
"""
from __future__ import annotations

from dataclasses import dataclass

from ...models.enums import MevRiskLevel


@dataclass(frozen=True)
class MevRiskBand:
    max_volatility: float
    min_liquidity: float
    description: str


@dataclass(frozen=True)
class MevRiskResult:
    level: MevRiskLevel
    reason: str


DEFAULT_BANDS = {
    MevRiskLevel.LOW: MevRiskBand(0.02, 500_000, "Deep liquidity, stable spread"),
    MevRiskLevel.MEDIUM: MevRiskBand(0.05, 100_000, "Volatile but persistent"),
    MevRiskLevel.HIGH: MevRiskBand(1.0, 0, "Low liquidity or sudden spike"),
}


class MevRiskClassifier:
    def __init__(self, bands: dict | None = None) -> None:
        self.bands = bands or DEFAULT_BANDS

    @staticmethod
    def volatility_proxy(spread_percent: float) -> float:
        """Crude fallback only. NOT a real volatility measurement — do not feed
        learning models with values derived from this."""
        return abs(spread_percent - 0.5) / 100

    def classify(self, *, liquidity_usd: float, volatility: float) -> MevRiskResult:
        low = self.bands[MevRiskLevel.LOW]
        med = self.bands[MevRiskLevel.MEDIUM]

        if liquidity_usd >= low.min_liquidity and volatility <= low.max_volatility:
            return MevRiskResult(MevRiskLevel.LOW, low.description)
        if liquidity_usd >= med.min_liquidity and volatility <= med.max_volatility:
            return MevRiskResult(MevRiskLevel.MEDIUM, med.description)
        return MevRiskResult(MevRiskLevel.HIGH, self.bands[MevRiskLevel.HIGH].description)
