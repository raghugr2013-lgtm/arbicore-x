"""ArbiCore X — StateObserver ABC + Registry + NullStateObserver (Phase B).

Per-OpportunityType state fetcher. Concrete impls (BDAGStateObserver,
CEXStateObserver, etc.) are Phase C scope. Phase B ships only the ABC and
the NullStateObserver fallback.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from ..models.canonical import CanonicalOpportunity
from ..models.enums import DataProvenance, OpportunityType


@dataclass
class OpportunityState:
    subject_id: str
    opportunity_type: OpportunityType
    captured_at_ts: float
    primary_metric: float
    secondary_metrics: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    provenance: DataProvenance = DataProvenance.REAL


class StateObserver(ABC):
    """ABC for per-OpportunityType state fetchers."""

    opportunity_type: OpportunityType

    @abstractmethod
    async def fetch_state(self, opp: CanonicalOpportunity) -> Optional[OpportunityState]:
        """Fetch the current state for an opportunity. None if unavailable."""


class NullStateObserver(StateObserver):
    """Phase B default — always returns None. Active when no concrete observer
    is registered for an OpportunityType. Never raises."""

    def __init__(self, opportunity_type: OpportunityType):
        self.opportunity_type = opportunity_type

    async def fetch_state(self, opp: CanonicalOpportunity) -> Optional[OpportunityState]:
        return None


class StateObserverRegistry:
    """Per-process registry of observers keyed by OpportunityType.

    ``get(unregistered_type)`` returns a NullStateObserver — never None,
    never raises (master architecture §6.1 contract).
    """

    def __init__(self) -> None:
        self._observers: Dict[OpportunityType, StateObserver] = {}

    def register(self, observer: StateObserver) -> None:
        if not isinstance(observer, StateObserver):
            raise TypeError("observer must be a StateObserver instance")
        self._observers[observer.opportunity_type] = observer

    def get(self, opportunity_type: OpportunityType) -> StateObserver:
        observer = self._observers.get(opportunity_type)
        if observer is None:
            return NullStateObserver(opportunity_type)
        return observer

    def is_registered(self, opportunity_type: OpportunityType) -> bool:
        return opportunity_type in self._observers

    def registered_types(self) -> list:
        return sorted([t.value for t in self._observers.keys()])
