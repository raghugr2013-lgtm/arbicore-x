"""Phase 8 — Production Readiness infrastructure.

Contains the safety primitives that gate every future execution
attempt. All classes are configurable via env; nothing is hardcoded.

  * :class:`KillSwitch` — a single global boolean guard with a reason
    string. Once engaged, every gate that consults it (paper engine,
    executor when it exists, flash-loan borrow when it exists) MUST
    refuse to act. Operator-only reset.

  * :class:`CapitalAllocationPolicy` — per-chain / per-opportunity-type
    caps on requested capital. Clips oversize requests instead of
    outright rejecting them; the paper engine records the clip in the
    ``inputs`` block.

  * :class:`ApprovalGate` — decides whether a given opportunity may
    proceed to execution. In Phase 8 the gate is *advisory only* — it
    returns a verdict which the (future) executor will honour. No live
    execution is enabled by this module.

  * :class:`AuditLog` — append-only MID-backed record of every safety
    decision. Reuses ``mid_opportunities`` (event_type prefix
    ``audit.``).
"""
from .config import PolicyConfig, load_policy_from_env
from .kill_switch import KillSwitch
from .capital import CapitalAllocationPolicy
from .approval import ApprovalGate, ApprovalVerdict
from .audit import AuditLog

__all__ = [
    "PolicyConfig", "load_policy_from_env",
    "KillSwitch", "CapitalAllocationPolicy",
    "ApprovalGate", "ApprovalVerdict", "AuditLog",
]
