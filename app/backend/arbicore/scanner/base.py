"""ArbiCore X — Universal Opportunity Scanner contracts (Phase 4 prep).

Design only — NO concrete scanners and NO execution. Establishes the single
interface that every opportunity source (CEX, DEX, funding, cross-chain,
launch, flash-loan) must implement, all emitting the canonical model.

Lifecycle the pipeline enforces:
    Scanner -> Validation -> Confidence -> Approval -> Learning -> (Future Execution)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from ..models.canonical import CanonicalOpportunity
from ..models.enums import OpportunityType


class OpportunitySource(ABC):
    """Common contract for all opportunity discovery plugins.

    Every implementation returns CanonicalOpportunity objects in ``candidate``
    status. Sources perform detection only — never execution.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def opportunity_type(self) -> OpportunityType: ...

    @abstractmethod
    def discover(self) -> List[CanonicalOpportunity]:
        """Return freshly detected candidate opportunities."""


class OpportunityPipeline(ABC):
    """Contract for the shared processing pipeline that all opportunity types
    flow through. Concrete implementation is Phase 4 work."""

    @abstractmethod
    def validate(self, opportunity: CanonicalOpportunity) -> CanonicalOpportunity: ...

    @abstractmethod
    def score(self, opportunity: CanonicalOpportunity) -> CanonicalOpportunity: ...

    @abstractmethod
    def rank(self, opportunities: List[CanonicalOpportunity]) -> List[CanonicalOpportunity]: ...
