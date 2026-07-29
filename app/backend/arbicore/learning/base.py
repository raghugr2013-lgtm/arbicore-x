"""ArbiCore X — Learning subsystem contracts (Phase 3 prep).

INTERFACES ONLY. The full learning loop is intentionally NOT implemented yet.
These abstract base classes define the contracts that future learning engines
must satisfy. Every learning input is gated through ``ensure_real`` so that only
REAL-provenance opportunities can ever train or update a model.
"""
from __future__ import annotations

from ..data.provenance import assert_learning_eligible
from ..models.canonical import CanonicalOpportunity


def ensure_real(opportunity: CanonicalOpportunity) -> None:
    """Guard: reject any opportunity not backed by REAL data."""
    assert_learning_eligible(opportunity.source_data_quality)
