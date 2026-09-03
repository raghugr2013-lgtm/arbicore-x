"""Candidate-level EXECUTOR CAPABILITY proof (fail-closed).

Produces explicit, persistable evidence that the deployed flash-loan executor
can actually execute a candidate's route — rather than *inferring* "UniV3-only
⇒ executable". Mirrors the authoritative M3 restriction in
``runtime.composition`` (the executor supports Balancer V2 borrow + Uniswap V3
swap hops only) but is STRICTER for eligibility: unknown/missing venue metadata
is UNVERIFIABLE (never silently treated as supported).

Status ladder:
    SUPPORTED     every route pool is an executor-supported venue
    UNSUPPORTED   at least one pool is an explicitly-unsupported venue
                  (e.g. Aerodrome/Slipstream) — remains DENIED
    UNVERIFIABLE  a pool's venue cannot be determined ⇒ fail closed
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


class ExecutorCapabilityStatus(str, enum.Enum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNVERIFIABLE = "UNVERIFIABLE"


# The deployed executor can only encode Uniswap V3 swap hops today.
SUPPORTED_DEXES = frozenset({"uniswap_v3"})


@dataclass
class ExecutorCapability:
    status: ExecutorCapabilityStatus
    supported_pools: List[str]
    unsupported_pools: List[str]
    unverifiable_pools: List[str]
    executor_address: Optional[str] = None
    reason: str = ""

    @property
    def is_supported(self) -> bool:
        return self.status == ExecutorCapabilityStatus.SUPPORTED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "supported_pools": self.supported_pools,
            "unsupported_pools": self.unsupported_pools,
            "unverifiable_pools": self.unverifiable_pools,
            "executor_address": self.executor_address,
            "supported_dexes": sorted(SUPPORTED_DEXES),
            "reason": self.reason,
        }


def evaluate_executor_capability(
    *,
    route_pools: List[str],
    pool_specs: Dict[str, Dict[str, Any]],
    executor_address: Optional[str] = None,
) -> ExecutorCapability:
    """Classify a route's executor compatibility from its pool venues.

    ``pool_specs`` maps pool-id → spec dict carrying a ``dex`` field. A pool
    absent from ``pool_specs`` or with an empty/unknown ``dex`` is UNVERIFIABLE
    (fail closed). Any explicitly-unsupported venue ⇒ UNSUPPORTED. Only when
    EVERY pool is an explicitly supported venue ⇒ SUPPORTED.
    """
    supported: List[str] = []
    unsupported: List[str] = []
    unverifiable: List[str] = []

    if not route_pools:
        return ExecutorCapability(
            status=ExecutorCapabilityStatus.UNVERIFIABLE,
            supported_pools=[], unsupported_pools=[], unverifiable_pools=[],
            executor_address=executor_address, reason="empty_route")

    for pid in route_pools:
        spec = pool_specs.get(pid)
        dex = (spec or {}).get("dex")
        # Normalise casing/whitespace so a genuine UniV3 venue is not spuriously
        # denied on venue-metadata drift; an unsupported venue still can't match.
        norm = dex.strip().lower() if isinstance(dex, str) else dex
        if spec is None or norm in (None, ""):
            unverifiable.append(pid)
        elif norm in SUPPORTED_DEXES:
            supported.append(pid)
        else:
            unsupported.append(pid)

    if unsupported:
        status = ExecutorCapabilityStatus.UNSUPPORTED
        reason = f"unsupported_venues:{sorted({(pool_specs.get(p) or {}).get('dex') for p in unsupported})}"
    elif unverifiable:
        status = ExecutorCapabilityStatus.UNVERIFIABLE
        reason = "venue_metadata_missing"
    else:
        status = ExecutorCapabilityStatus.SUPPORTED
        reason = "all_pools_executor_supported"

    return ExecutorCapability(
        status=status, supported_pools=supported,
        unsupported_pools=unsupported, unverifiable_pools=unverifiable,
        executor_address=executor_address, reason=reason)


__all__ = ["ExecutorCapabilityStatus", "ExecutorCapability",
           "evaluate_executor_capability", "SUPPORTED_DEXES"]
