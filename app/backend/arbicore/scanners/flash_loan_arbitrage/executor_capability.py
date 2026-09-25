"""Candidate-level EXECUTOR CAPABILITY proof (fail-closed).

Produces explicit, persistable evidence that the deployed flash-loan executor
can actually execute a candidate's route — rather than *inferring* "UniV3-only
⇒ executable". Mirrors the authoritative M3 restriction in
``runtime.composition`` (the deployed receiver borrows via Balancer V2 or Aave
V3 flash and settles Uniswap V3 swap hops only) but is STRICTER for eligibility:
unknown/missing venue metadata
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


# The deployed executor can only encode Uniswap V3 swap hops today (v1).
# NOTE: this module-level constant is the CANONICAL v1 (currently-deployed)
# capability and is intentionally unchanged — the live execution path must never
# admit a venue the deployed receiver cannot settle (that would broadcast a
# known-reverting trade). Version-aware profiles (v2, ready for Executor V2) live
# in RECEIVER_CAPABILITY_PROFILES and are consumed ONLY when a receiver of that
# version is deployed + on-chain-verified.
SUPPORTED_DEXES = frozenset({"uniswap_v3"})

# The deployed FlashLoanReceiver's flash-loan heads, reconciled to the on-chain
# ABI (E1): Balancer V2 (`execute`/`receiveFlashLoan`) AND Aave V3
# (`executeAave`/`executeOperation`). This is the canonical single source of
# truth consumed by the Executor V2 settlement dispatcher and the offline
# capability audit — keep the two in lock-step (asserted by tests).
SUPPORTED_FLASH_PROVIDERS = frozenset({"balancer_v2", "aave_v3"})


# ---------------------------------------------------------------------------
# V-3 · Version-aware receiver capability registry (backward-compatible).
#
# Each deployed FlashLoanReceiver version declares EXACTLY which swap venues and
# flash-loan heads it can settle on-chain. The gate consults the profile of the
# receiver version that is actually deployed + verified — so when the operator
# deploys Executor V2 (INFRA), the routable/executable venue set expands with NO
# further code change. Until then, "v1" is authoritative and identical to the
# historical UniV3-only behaviour. Widening a profile does NOT widen execution
# unless a receiver of that version is genuinely on-chain.
# ---------------------------------------------------------------------------
RECEIVER_CAPABILITY_PROFILES: Dict[str, Dict[str, frozenset]] = {
    # Currently deployed. Do NOT change — mirrors the on-chain FlashLoanReceiver.
    "v1": {
        "dexes": frozenset({"uniswap_v3"}),
        "flash_providers": frozenset({"balancer_v2", "aave_v3"}),
    },
    # Executor V2 target (Solidity + encoders delivered for audit+deploy). Becomes
    # effective ONLY when a v2 receiver is deployed and version-verified on-chain.
    # Every venue here has a live QuoterRegistry adapter at HEAD (uniswap_v3,
    # aerodrome, aerodrome_slipstream, camelot_v3/quickswap_v3=algebra). Solidly &
    # Curve are deliberately excluded until their quoter adapters exist (CODE).
    "v2": {
        "dexes": frozenset({
            "uniswap_v3", "sushiswap_v3", "pancakeswap_v3",
            "aerodrome", "aerodrome_slipstream",
            "camelot_v3", "quickswap_v3",
        }),
        "flash_providers": frozenset({"balancer_v2", "aave_v3", "morpho_blue"}),
    },
}

# Fail-closed default when a receiver version is unknown/unverifiable.
DEFAULT_RECEIVER_VERSION = "v1"


def capability_profile_for(version: Optional[str]) -> Dict[str, frozenset]:
    """Return the capability profile for a deployed receiver version.

    Unknown/None version ⇒ v1 (fail-closed to the narrowest live capability).
    """
    return RECEIVER_CAPABILITY_PROFILES.get(
        (version or DEFAULT_RECEIVER_VERSION), RECEIVER_CAPABILITY_PROFILES["v1"])


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
    receiver_version: Optional[str] = None,
    supported_dexes: Optional[frozenset] = None,
) -> ExecutorCapability:
    """Classify a route's executor compatibility from its pool venues.

    ``pool_specs`` maps pool-id → spec dict carrying a ``dex`` field. A pool
    absent from ``pool_specs`` or with an empty/unknown ``dex`` is UNVERIFIABLE
    (fail closed). Any explicitly-unsupported venue ⇒ UNSUPPORTED. Only when
    EVERY pool is an explicitly supported venue ⇒ SUPPORTED.

    V-3 (backward-compatible): the supported-venue set is resolved from, in order,
    an explicit ``supported_dexes`` override, else the ``receiver_version`` profile
    (``RECEIVER_CAPABILITY_PROFILES``), else the module default ``SUPPORTED_DEXES``
    (= v1, ``{uniswap_v3}``). Callers that pass neither get the historical
    UniV3-only behaviour EXACTLY — the live path is unchanged until a higher
    receiver version is deployed + verified and threaded through here.
    """
    if supported_dexes is None:
        if receiver_version is not None:
            supported_dexes = capability_profile_for(receiver_version)["dexes"]
        else:
            supported_dexes = SUPPORTED_DEXES
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
        elif norm in supported_dexes:
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
           "evaluate_executor_capability", "SUPPORTED_DEXES",
           "SUPPORTED_FLASH_PROVIDERS", "RECEIVER_CAPABILITY_PROFILES",
           "DEFAULT_RECEIVER_VERSION", "capability_profile_for"]
