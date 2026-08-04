"""ApprovalGate — advisory-only in Phase 8.

Returns a verdict (approve / deny / require_operator) with a reason.
No live execution consults this yet; the (future) executor will.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

from .config import PolicyConfig
from .kill_switch import KillSwitch


@dataclass
class ApprovalVerdict:
    approved: bool
    require_operator: bool
    reason: str
    gate: str = "phase8_approval"


class ApprovalGate:
    def __init__(self, cfg: PolicyConfig, kill: KillSwitch) -> None:
        self._cfg = cfg
        self._kill = kill

    def evaluate(self, opp: Dict[str, Any]) -> ApprovalVerdict:
        if self._kill.is_engaged():
            return ApprovalVerdict(
                approved=False, require_operator=True,
                reason=f"kill_switch_engaged: {self._kill.reason()}",
            )
        if not self._cfg.live_execution_enabled:
            return ApprovalVerdict(
                approved=False, require_operator=True,
                reason="live_execution_disabled_in_config",
            )
        if self._cfg.require_paper_validation and not opp.get(
                "paper_validation_passed"):
            return ApprovalVerdict(
                approved=False, require_operator=False,
                reason="paper_validation_required",
            )
        # cap checks
        cap = float(opp.get("capital_required_usd", 0.0))
        if cap > self._cfg.max_per_trade_usd:
            return ApprovalVerdict(
                approved=False, require_operator=True,
                reason=(f"exceeds_max_per_trade_usd "
                        f"{cap} > {self._cfg.max_per_trade_usd}"))
        return ApprovalVerdict(
            approved=True, require_operator=False,
            reason="within_policy",
        )
