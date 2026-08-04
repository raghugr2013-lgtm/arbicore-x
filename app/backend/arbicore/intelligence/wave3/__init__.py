"""Phase 3 — Opportunity Memory & Learning.

Read-side aggregation over Phase 2's ``mid_opportunity_lifetime`` and
the Sprint 1B MID domains (``mid_confidence``, ``mid_routes``,
``mid_providers``, ``mid_opportunities``). Never writes; produces
derived insights the operator and future Phases (Paper Engine,
Dashboard) consume.

Design invariants:
  * Zero new collections. Zero new writers. Everything comes from
    existing MID data.
  * Every method returns plain dicts safe for JSON serialisation.
  * All queries are bounded (``limit`` + time-window arguments) so the
    aggregations stay cheap.
  * All time windows are UTC ISO strings.

Consumers:
  * ``/api/arbicore/memory/*`` endpoints (Phase 3).
  * Phase 4 dashboard.
  * Phase 6 paper engine.
"""
from .memory import OpportunityMemory

__all__ = ["OpportunityMemory"]
