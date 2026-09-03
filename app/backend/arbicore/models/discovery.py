"""ArbiCore X — Phase D D-1: DiscoveryCandidate model.

Per PHASE_D_DISCOVERY_LAYER_SPEC.md §2.

INV-1: DiscoveryCandidate is a SEPARATE type from CanonicalOpportunity.
       No class hierarchy. No conversion utility. The two models live in
       different Mongo collections and the type system prevents accidental
       substitution at the EmissionBus boundary.
"""
from __future__ import annotations

import hashlib
import math
import os
import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .enums import OpportunityType


def _discovery_candidate_ttl_s() -> float:
    """Configurable candidate lifetime (seconds).

    ``expires_at = hint_observed_at + ttl`` and ``DiscoveryQueue.claim_batch``
    requires ``expires_at > now``. The previous hardcoded 60s was shorter than
    the per-tick discover()+upsert_many() latency at production scale, so fresh
    candidates expired before they could be claimed. Conservative default 900s
    (15 min) keeps candidates claimable long enough to drain the backlog while
    remaining well under the 24h queue TTL horizon. Read at call time so ops can
    tune without a code change; fail-safe to the default on bad input."""
    raw = os.environ.get("ARBICORE_DISCOVERY_CANDIDATE_TTL_S")
    if raw is None:
        return 900.0
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return 900.0
    return val if val > 0 else 900.0


class VerifiedOutcome(str):
    """Standard tags for DiscoveryCandidate.verified_outcome (see Spec §6.1)."""

    CONFIRMED_PREFIX = "confirmed_canonical:"   # confirmed_canonical:<opportunity_id>
    DENIED_VENUE_DISAGREES = "denied:venue_disagrees"
    DENIED_VENUE_UNREADABLE = "denied:venue_unreadable"
    DENIED_NO_VERIFIER = "denied:no_verifier_registered"
    DENIED_GATE_PREFIX = "denied:gate_rejection:"  # denied:gate_rejection:<gate_name>
    # denied:quote_invalid:<reason> — quote integrity failure (partial /
    # reverted hop / missing output / malformed gross / non-cyclic route).
    # A quote that is not economically calculable MUST fail closed here and
    # never reach economics, Gate 7 or CONFIRMED.
    DENIED_QUOTE_INVALID_PREFIX = "denied:quote_invalid:"
    ERROR_PREFIX = "error:"
    EXPIRED_UNCLAIMED = "expired_unclaimed"


class DiscoveryCandidate(BaseModel):
    """Lightweight hint from a DiscoverySource. NEVER directly persisted into
    arbicore_opportunities. NEVER consumed by Confidence / Learning / Approval.

    Only a registered OpportunityVerifier can produce a CanonicalOpportunity
    from this hint, after issuing an authoritative venue read.
    """

    candidate_id: str
    opportunity_type: OpportunityType
    hint_source: str
    hint_observed_at: float = Field(default_factory=lambda: time.time())
    subject_id: str
    asset: Optional[str] = None
    candidate_venues: List[str] = Field(default_factory=list)
    hint_metric: Dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
    expires_at: Optional[float] = None
    # Claim-lock fields (cooperative queue — see Spec §5.1)
    claimed_at: Optional[float] = None
    claimed_by: Optional[str] = None
    claimed_until: Optional[float] = None
    # Outcome fields (verifier writes these)
    verified_outcome: Optional[str] = None
    verified_at: Optional[float] = None
    verification_latency_ms: Optional[int] = None
    emitted_opportunity_id: Optional[str] = None

    def __init__(self, **data):
        if "expires_at" not in data or data["expires_at"] is None:
            data["expires_at"] = data.get(
                "hint_observed_at", time.time()
            ) + _discovery_candidate_ttl_s()
        super().__init__(**data)


def make_candidate_id(*, hint_source: str,
                      opportunity_type: OpportunityType,
                      subject_id: str,
                      asset: Optional[str],
                      candidate_venues: List[str],
                      hint_observed_at: float) -> str:
    """Deterministic candidate_id per Spec §2.1."""
    window = int(math.floor(hint_observed_at / 60.0))
    parts = "|".join([
        hint_source,
        opportunity_type.value,
        subject_id,
        asset or "",
        ",".join(sorted(candidate_venues)),
        str(window),
    ])
    return hashlib.sha1(parts.encode("utf-8")).hexdigest()[:20]


class SourceHealth(BaseModel):
    """Connector health probe shape (per Spec §3)."""
    source_id: str
    ok: bool
    latency_ms: int = 0
    last_emission_at: Optional[float] = None
    last_error: Optional[str] = None
    probed_at: float = Field(default_factory=lambda: time.time())
