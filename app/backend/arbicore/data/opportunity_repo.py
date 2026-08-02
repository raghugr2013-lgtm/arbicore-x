"""ArbiCore X — OpportunityRepository ABC (Phase B).

Universal write/read contract for canonical opportunities. Concrete impls:
  - Mongo (arbicore/data/mongo/opportunity_repo_mongo.py)
  - In-memory (arbicore/data/_inmemory.py) — test fixture

Write-path invariants (enforced inside upsert):
  1. opp.source_data_quality must resolve through SOURCE_REGISTRY for the
     declared source tier. DEAD provenance is rejected with ValueError.
  2. If opp.opportunity_id is empty, generate via uuid.uuid4().hex.
  3. category_metadata validation runs (soft-typed; warns but never raises).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from ..models.canonical import CanonicalOpportunity
from ..models.enums import DataProvenance, OpportunityStatus, OpportunityType


class OpportunityRepository(ABC):
    @abstractmethod
    async def upsert(self, opp: CanonicalOpportunity) -> bool:
        """Insert or update a canonical opportunity. Returns True on write."""

    @abstractmethod
    async def get(self, opportunity_id: str) -> Optional[CanonicalOpportunity]:
        """Fetch by opportunity_id. Returns None if absent."""

    @abstractmethod
    async def list_for_subject(self,
                               subject_id: str,
                               limit: int = 50,
                               provenance_filter: Optional[frozenset] = None,
                               ) -> List[CanonicalOpportunity]:
        """All opportunities for a subject_id, newest first.

        provenance_filter (Adj. A5): if provided, only return opportunities
        whose source_data_quality is in the set. None = no filter.
        """

    @abstractmethod
    async def find(self,
                   filter: dict,
                   limit: int = 100,
                   provenance_filter: Optional[frozenset] = None,
                   ) -> List[CanonicalOpportunity]:
        """Generic find — honours Mongo-style filter dict.

        Recognised soft keys: ``opportunity_type``, ``status``, ``subject_id``,
        ``since`` (epoch seconds — applied to lifecycle_at/created_at).
        """

    @abstractmethod
    async def count_by_type_status(self) -> dict:
        """Aggregate counts: {(opportunity_type, status): n} as nested dict."""


def validate_for_upsert(opp: CanonicalOpportunity) -> None:
    """Phase B write-path invariant check. Raises ValueError on violation."""
    if opp.source_data_quality is DataProvenance.DEAD:
        raise ValueError(
            "OpportunityRepository.upsert rejected: source_data_quality=DEAD",
        )
    if not isinstance(opp.opportunity_type, OpportunityType):
        raise ValueError("opportunity_type must be an OpportunityType")
    if not isinstance(opp.status, OpportunityStatus):
        raise ValueError("status must be an OpportunityStatus")
