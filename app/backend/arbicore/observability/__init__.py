"""Phase 0 strategy intelligence and economics observability.

Read-only projection of stored m2.3 verifier bundles and discovery
candidates. Nothing in this package is imported by the verifier, the
economics assessor, the gates, or the scanner runtime.
"""
from __future__ import annotations

from .fields import CLASSIFIER_VERSION
from .record import observe_strategy_intelligence
from .taxonomy import FAMILIES

__all__ = [
    "CLASSIFIER_VERSION",
    "FAMILIES",
    "observe_strategy_intelligence",
]
