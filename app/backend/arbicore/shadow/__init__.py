"""ArbiCore X — Phase C Wave 5: Shadow Binding layer.

Read-only adapter that maps legacy ``approval_workflow.build_proposals()``
outputs into ``CanonicalOpportunity`` objects and feeds them into the
Phase B/C learning loop **without** touching the legacy execution path.

Hard guarantees (master architecture §13):
  - No mutation of legacy code paths.
  - No execution / signing / fund movement.
  - All writes are flagged with ``provenance=REAL`` and stamped
    ``category_metadata.shadow_binding=True`` for full auditability.
"""
from .mapper import LegacyProposalMapper, map_proposal_to_canonical
from .observer import ShadowBindingObserver

__all__ = [
    "LegacyProposalMapper",
    "ShadowBindingObserver",
    "map_proposal_to_canonical",
]
