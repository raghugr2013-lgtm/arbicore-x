"""ArbiCore X — Signal Confidence Engine.

Migrated from ArbitrageX ``SignalConfidence`` + ``update_signal_confidence``
(server.py L354, L1905). Tracks per-route persistence statistics over time and
derives a confidence score.

Key migration fix: the original ArbitrageX ``opportunity_trackers`` lived only
in memory and was lost on every restart. Here persistence is delegated to a
``ConfidenceStore`` interface so it can be backed by an in-memory dict (tests /
default) or a database (production) without changing the engine.

Dependency map:
    - stdlib only (dataclasses, datetime)
    - ConfidenceStore (pluggable persistence)

Example:
    >>> engine = SignalConfidenceEngine()
    >>> for _ in range(4):
    ...     _ = engine.record_signal(opportunity_type="DEX_ARBITRAGE",
    ...             asset="WETH/USDC", route="uniswap->sushi",
    ...             duration_seconds=45, spread_percent=1.1)
    >>> round(engine.get_confidence("DEX_ARBITRAGE", "WETH/USDC", "uniswap->sushi"))
    100
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Protocol


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RouteStats:
    key: str
    opportunity_type: str
    asset: str
    route: str
    total_signals: int = 0
    persistent_signals: int = 0
    ephemeral_signals: int = 0
    avg_spread_percent: float = 0.0
    max_spread_percent: float = 0.0
    avg_duration_seconds: float = 0.0
    last_signal: Optional[str] = None
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)

    @property
    def persistence_rate(self) -> float:
        if self.total_signals <= 0:
            return 0.0
        return round((self.persistent_signals / self.total_signals) * 100, 2)

    @property
    def confidence_score(self) -> float:
        """0–100. Currently equals persistence rate; the learning engine will
        later replace this with a calibrated probability."""
        return self.persistence_rate

    def as_dict(self) -> dict:
        d = asdict(self)
        d["persistence_rate"] = self.persistence_rate
        d["confidence_score"] = self.confidence_score
        return d


class ConfidenceStore(Protocol):
    def get(self, key: str) -> Optional[RouteStats]: ...
    def save(self, stats: RouteStats) -> None: ...
    def all(self) -> List[RouteStats]: ...


class InMemoryConfidenceStore:
    def __init__(self) -> None:
        self._data: Dict[str, RouteStats] = {}

    def get(self, key: str) -> Optional[RouteStats]:
        return self._data.get(key)

    def save(self, stats: RouteStats) -> None:
        self._data[stats.key] = stats

    def all(self) -> List[RouteStats]:
        return list(self._data.values())


class SignalConfidenceEngine:
    PERSISTENT_THRESHOLD_S = 30
    EPHEMERAL_THRESHOLD_S = 10

    def __init__(self, store: Optional[ConfidenceStore] = None) -> None:
        self.store: ConfidenceStore = store or InMemoryConfidenceStore()

    @staticmethod
    def _key(opportunity_type: str, asset: str, route: str) -> str:
        return f"{opportunity_type}:{asset}:{route}"

    def record_signal(
        self,
        *,
        opportunity_type: str,
        asset: str,
        route: str,
        duration_seconds: float,
        spread_percent: float,
    ) -> RouteStats:
        key = self._key(opportunity_type, asset, route)
        stats = self.store.get(key)
        if stats is None:
            stats = RouteStats(key=key, opportunity_type=opportunity_type, asset=asset, route=route)

        total = stats.total_signals + 1
        if duration_seconds >= self.PERSISTENT_THRESHOLD_S:
            stats.persistent_signals += 1
        elif duration_seconds < self.EPHEMERAL_THRESHOLD_S:
            stats.ephemeral_signals += 1

        # running averages
        stats.avg_spread_percent = round(
            (stats.avg_spread_percent * (total - 1) + spread_percent) / total, 4
        )
        stats.avg_duration_seconds = round(
            (stats.avg_duration_seconds * (total - 1) + duration_seconds) / total, 2
        )
        stats.max_spread_percent = round(max(stats.max_spread_percent, spread_percent), 4)
        stats.total_signals = total
        stats.last_signal = _utc_now()
        stats.updated_at = _utc_now()

        self.store.save(stats)
        return stats

    def get_confidence(self, opportunity_type: str, asset: str, route: str) -> float:
        stats = self.store.get(self._key(opportunity_type, asset, route))
        return stats.confidence_score if stats else 0.0
