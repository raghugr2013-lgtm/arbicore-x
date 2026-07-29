"""ArbiCore X — Phase D D-1: OpportunityVerifier ABC + registry.

Per PHASE_D_DISCOVERY_LAYER_SPEC.md §4.

INV-2: Only OpportunityVerifier.verify() returns a CanonicalOpportunity
       derived from a DiscoveryCandidate. The worker dispatches each
       candidate to the verifier registered for candidate.opportunity_type.
INV-3: CanonicalOpportunity.source_data_quality is sourced from the
       VENUE READ's provenance — never from candidate.hint_source.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

from ..models.canonical import CanonicalOpportunity
from ..models.discovery import DiscoveryCandidate
from ..models.enums import OpportunityType


class OpportunityVerifier(ABC):
    """Per-OpportunityType verifier. Reads authoritative venue data and
    emits a CanonicalOpportunity ONLY when venue truth confirms the hint."""

    opportunity_type: OpportunityType

    @abstractmethod
    async def verify(self, candidate: DiscoveryCandidate
                     ) -> Tuple[Optional[CanonicalOpportunity], str]:
        """Returns (opp, outcome_tag).

        - opp: CanonicalOpportunity if venue confirms, else None.
        - outcome_tag: from VerifiedOutcome vocabulary in models/discovery.py.
        """


class OpportunityVerifierRegistry:
    """Process-wide registry of verifiers, keyed by OpportunityType."""

    def __init__(self) -> None:
        self._verifiers: Dict[OpportunityType, OpportunityVerifier] = {}

    def register(self, verifier: OpportunityVerifier) -> None:
        ot = verifier.opportunity_type
        self._verifiers[ot] = verifier

    def get(self, opportunity_type: OpportunityType
            ) -> Optional[OpportunityVerifier]:
        return self._verifiers.get(opportunity_type)

    def types(self) -> List[str]:
        return sorted(t.value for t in self._verifiers.keys())

    def clear(self) -> None:
        self._verifiers.clear()
