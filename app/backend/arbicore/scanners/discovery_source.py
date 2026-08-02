"""ArbiCore X — Phase D D-1: DiscoverySource ABC + registry.

Per PHASE_D_DISCOVERY_LAYER_SPEC.md §3.

Sources are hint providers ONLY. They MUST NOT:
  - Emit CanonicalOpportunity directly
  - Touch arbicore_opportunities
  - Read/modify arbicore_outcomes or arbicore_signal_metrics
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Set

from ..models.discovery import DiscoveryCandidate, SourceHealth
from ..models.enums import DataProvenance, OpportunityType


class DiscoverySource(ABC):
    """Emits DiscoveryCandidates from any external feed."""

    source_id: str = ""
    cadence_s: int = 30
    opportunity_types: Set[OpportunityType] = set()
    tier: int = 1                       # 1 (venue / Tier-1), 2, or 3 per Spec §11
    provenance_of_hint: DataProvenance = DataProvenance.REAL

    @abstractmethod
    async def discover(self) -> List[DiscoveryCandidate]:
        """Pull / poll the source and return any new candidates."""

    @abstractmethod
    async def health(self) -> SourceHealth:
        """Latency + reachability + last-emission probe."""


class DiscoverySourceRegistry:
    """Process-wide registry of DiscoverySources, keyed by source_id."""

    def __init__(self) -> None:
        self._sources: Dict[str, DiscoverySource] = {}

    def register(self, source: DiscoverySource) -> None:
        if not source.source_id:
            raise ValueError("DiscoverySource.source_id must be non-empty")
        self._sources[source.source_id] = source

    def get(self, source_id: str) -> DiscoverySource:
        return self._sources[source_id]

    def all(self) -> List[DiscoverySource]:
        return list(self._sources.values())

    def ids(self) -> List[str]:
        return sorted(self._sources.keys())

    def clear(self) -> None:
        self._sources.clear()
