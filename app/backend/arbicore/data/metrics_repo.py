"""ArbiCore X — MetricsRepository ABC (Phase B, Adjustment A1).

Signal-quality + wallet-quality long-horizon metrics. Concrete consumer is
Phase C wave 1 (GemHunter outcomes/metrics.py migration).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SignalMetric:
    signal_id: str
    subject_id: Optional[str]
    horizon_label: str
    sample_count: int
    score_impact_sum: float           # may be negative (signals can reduce confidence)
    score_impact_mean: float
    win_rate: float                   # 0.0–1.0
    aggregated_at: float
    extras: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WalletMetric:
    wallet_id: str
    entity_id: Optional[str]
    sample_count: int
    success_rate: float
    avg_outcome_score: float
    updated_at: float
    extras: Dict[str, Any] = field(default_factory=dict)


class MetricsRepository(ABC):
    """Aggregated metrics store — signals + wallets."""

    @abstractmethod
    async def upsert_signal_metric(self, metric: SignalMetric) -> bool:
        ...

    @abstractmethod
    async def list_signal_metrics(self,
                                  signal_id: Optional[str] = None,
                                  subject_id: Optional[str] = None,
                                  limit: int = 200,
                                  ) -> List[SignalMetric]:
        ...

    @abstractmethod
    async def upsert_wallet_metric(self, metric: WalletMetric) -> bool:
        ...

    @abstractmethod
    async def list_wallet_metrics(self,
                                  entity_id: Optional[str] = None,
                                  limit: int = 200,
                                  ) -> List[WalletMetric]:
        ...

    @abstractmethod
    async def counts(self) -> Dict[str, int]:
        """Top-level counts for /api/arbicore/health."""
