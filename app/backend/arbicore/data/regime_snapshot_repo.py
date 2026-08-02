"""ArbiCore X — RegimeSnapshotRepository ABC (Phase B, Adjustment A3).

Stores periodic regime classifications + multi-label tags. Consumed by
HDA, ConfidenceEngine, and the SequenceMiner. Concrete impl arrives in
Phase C wave 3.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RegimeSnapshot:
    captured_at: float
    dominant_regime: str            # MarketRegime.value
    tags: List[str] = field(default_factory=list)   # multi-label context (Adj. B1b)
    confidence: float = 0.0
    source: str = ""
    extras: Dict[str, Any] = field(default_factory=dict)


class RegimeSnapshotRepository(ABC):
    @abstractmethod
    async def append(self, snapshot: RegimeSnapshot) -> bool:
        ...

    @abstractmethod
    async def latest(self) -> Optional[RegimeSnapshot]:
        ...

    @abstractmethod
    async def list_since(self, t0: float, limit: int = 500) -> List[RegimeSnapshot]:
        ...

    @abstractmethod
    async def count(self) -> int:
        ...
