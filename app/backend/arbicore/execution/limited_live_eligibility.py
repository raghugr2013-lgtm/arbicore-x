"""ArbiCore X — the single, explicit LIMITED-LIVE ELIGIBILITY decision.

CONFIRMED evidence is NECESSARY but NOT sufficient for execution. This module
is the one place that decides whether a candidate may become eligible for a
Limited-Live execution ATTEMPT. It is pure and STRICTLY fail-closed: every
mandatory control must be an explicit PASS; any missing / unknown /
unverifiable / insufficient / stale / mismatched result ⇒ DENY.

It NEVER enables Limited-Live, NEVER signs, NEVER broadcasts. It only computes
"would this candidate be *permitted* to attempt execution if the operator had
enabled Limited-Live?" — the authority to actually enable execution remains
entirely outside this module (mode ladder + kill switch + signer vault).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# The complete set of mandatory controls, in canonical order. Every one must
# resolve to PASS for a candidate to be Limited-Live ELIGIBLE.
MANDATORY_CONTROLS = (
    "quote_complete",           # valid complete quote + closed token cycle
    "economics_ok",             # net/atomic profit ≥ required floor
    "gate_7",                   # atomic-profit gate PASS
    # NOTE: liquidity_verified and gate_8 are intentionally BOTH listed — the
    # mission enumerates "verified liquidity" and "Gate 8" as distinct
    # mandatory controls. They currently both derive from the Gate-8 result
    # (route-liquidity), so they move together; this is a deliberate
    # fail-closed pairing, not 15 independent proofs (14 distinct today).
    "liquidity_verified",       # Gate 8 route-liquidity PASS
    "gate_8",
    "executor_capability",      # SUPPORTED (proven, not inferred)
    "gate_9",                   # MEV gate PASS
    "borrow_size_feasible",     # a profitable AND executable size was selected
    "balancer_liquidity",       # candidate-level flash-loan liquidity CONFIRMED
    "atomic_simulation",        # exact-tx atomic sim available AND passed
    "freshness_ok",             # quote/block/state within freshness policy
    "provenance_complete",      # exact audit_run_id + scanner_tick_id + candidate_id
    "verification_confirmed",   # source=flash_loan_arb_verifier, status=CONFIRMED
    "mode_allows",              # mode ladder permits a Limited-Live attempt
    "kill_switch_ok",           # kill switch not engaged
)


@dataclass
class ControlResult:
    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {"control": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class LimitedLiveDecision:
    eligible: bool
    decision: str                       # "ELIGIBLE" | "DENY"
    controls: List[ControlResult] = field(default_factory=list)
    deny_reasons: List[str] = field(default_factory=list)
    # Invariants surfaced for auditors — always false here.
    signed: bool = False
    broadcast: bool = False
    limited_live_enabled: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "eligible": self.eligible, "decision": self.decision,
            "controls": [c.to_dict() for c in self.controls],
            "deny_reasons": self.deny_reasons,
            "signed": self.signed, "broadcast": self.broadcast,
            "limited_live_enabled": self.limited_live_enabled,
            "note": ("eligibility only — CONFIRMED != EXECUTABLE; enabling "
                     "Limited-Live/signing/broadcast remains a separate, "
                     "operator-gated authority"),
        }


def _as_pass(value: Any) -> Optional[bool]:
    """Coerce a control input to an explicit True/False, or None when the
    result is unknown/ambiguous (⇒ fail closed). Strings are matched against a
    small allow/deny vocabulary; anything else that is not a clean bool ⇒ None.
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        v = value.strip().upper()
        pass_words = {"PASS", "PASSED", "OK", "SUPPORTED", "CONFIRMED",
                      "ON_CHAIN_CONFIRMED", "AVAILABLE_SUFFICIENT", "SELECTED",
                      "TRUE", "ELIGIBLE", "FRESH"}
        deny_words = {"FAIL", "FAILED", "DENY", "DENIED", "UNSUPPORTED",
                      "UNVERIFIABLE", "UNKNOWN", "UNAVAILABLE", "INSUFFICIENT",
                      "INFEASIBLE", "STALE", "NOT_EVALUATED", "FALSE", "PENDING"}
        if v in pass_words:
            return True
        if v in deny_words:
            return False
        return None  # unrecognised ⇒ fail closed
    return None


def evaluate_limited_live_eligibility(
    controls: Dict[str, Any],
) -> LimitedLiveDecision:
    """Aggregate the mandatory controls into one fail-closed decision.

    ``controls`` maps each name in :data:`MANDATORY_CONTROLS` to a bool or a
    recognised status string. A missing key, ``None``, or an unrecognised value
    is treated as NOT PASS (DENY) — unknown is never success.
    """
    results: List[ControlResult] = []
    deny: List[str] = []
    for name in MANDATORY_CONTROLS:
        raw = controls.get(name)
        verdict = _as_pass(raw)
        passed = verdict is True
        if not passed:
            if name not in controls:
                detail = "missing (fail closed)"
            elif verdict is None:
                detail = f"unknown/unverifiable: {raw!r} (fail closed)"
            else:
                detail = f"failed: {raw!r}"
            deny.append(f"{name}:{detail}")
        else:
            detail = str(raw)
        results.append(ControlResult(name=name, passed=passed, detail=detail))

    eligible = len(deny) == 0
    return LimitedLiveDecision(
        eligible=eligible,
        decision="ELIGIBLE" if eligible else "DENY",
        controls=results, deny_reasons=deny)


__all__ = ["MANDATORY_CONTROLS", "ControlResult", "LimitedLiveDecision",
           "evaluate_limited_live_eligibility"]
