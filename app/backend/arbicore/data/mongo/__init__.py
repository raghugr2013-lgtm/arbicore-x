"""ArbiCore X — Mongo adapters for Phase B data layer.

Concrete Motor implementations of:
  - OpportunityRepository
  - OutcomeRepository
  - MetricsRepository
  - RegimeSnapshotRepository

Discipline:
  - No raw _id leaks (we exclude _id with projection / persistence via opportunity_id).
  - ensure_indexes() is idempotent and called from the composition root.
  - All collection names live in arbicore_collections.py.
"""
from .arbicore_collections import COLLECTION_NAMES, ensure_indexes

__all__ = ["COLLECTION_NAMES", "ensure_indexes"]
