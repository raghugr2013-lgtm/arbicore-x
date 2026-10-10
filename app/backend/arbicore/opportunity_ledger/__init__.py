"""Opportunity Ledger v1 — evidence projection.

Projects an existing discovery candidate, an optional m2.3 verifier bundle,
and the Phase 0 strategy observer into one ledger row. It does not quote,
size, gate, sign, or broadcast, and it does not recompute economics.
"""
from __future__ import annotations

from .identity import (
    DEFINED_MODES,
    OCTOBER_5_SHADOW_RUN_ID,
    ledger_id_for,
    opportunity_id_for,
)
from .project import project_opportunity_ledger
from .repo import COLLECTION, OpportunityLedgerRepo

__all__ = [
    "COLLECTION",
    "DEFINED_MODES",
    "OCTOBER_5_SHADOW_RUN_ID",
    "OpportunityLedgerRepo",
    "ledger_id_for",
    "opportunity_id_for",
    "project_opportunity_ledger",
]
