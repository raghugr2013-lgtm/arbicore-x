"""Borrow-size sensitivity selection (pure, fail-closed).

A route being profitable at one borrow size does NOT make an arbitrary size
executable. Given per-size evaluations (each already carrying the economics +
liquidity + executor + simulation feasibility computed from the existing
providers), this module selects the borrow size that is BOTH economically
profitable after all costs AND executable with verified liquidity / executor /
simulation — and fails closed with a full rationale when none qualifies.

This module performs NO I/O. The caller supplies, per candidate size, a
``BorrowSizeEval`` populated from the real economics/liquidity/executor/sim
stages; the selection logic here never fabricates any of those inputs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BorrowSizeEval:
    size_usd: float
    net_profit_usd: Optional[float] = None      # atomic/net after ALL costs
    gross_spread_pct: Optional[float] = None
    quote_complete: bool = False                # closed-cycle, all hops ok
    economics_ok: bool = False                  # net_profit_usd ≥ required floor
    liquidity_sufficient: bool = False          # Balancer/provider ON_CHAIN_CONFIRMED ≥ size
    executor_supported: bool = False
    atomic_sim_passed: bool = False
    reason: str = ""

    @property
    def feasible(self) -> bool:
        """Executable AND profitable. Every condition must be explicitly true;
        a missing/None ``net_profit_usd`` is never feasible (fail closed)."""
        return bool(
            self.quote_complete and self.economics_ok
            and self.net_profit_usd is not None and self.net_profit_usd > 0
            and self.liquidity_sufficient and self.executor_supported
            and self.atomic_sim_passed)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "size_usd": self.size_usd, "net_profit_usd": self.net_profit_usd,
            "gross_spread_pct": self.gross_spread_pct,
            "quote_complete": self.quote_complete,
            "economics_ok": self.economics_ok,
            "liquidity_sufficient": self.liquidity_sufficient,
            "executor_supported": self.executor_supported,
            "atomic_sim_passed": self.atomic_sim_passed,
            "feasible": self.feasible, "reason": self.reason,
        }


@dataclass
class BorrowSizeDecision:
    status: str                                  # SELECTED | INFEASIBLE
    selected: Optional[BorrowSizeEval]
    evaluated: List[BorrowSizeEval] = field(default_factory=list)
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "SELECTED" and self.selected is not None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "selected_size_usd": self.selected.size_usd if self.selected else None,
            "selected_net_profit_usd": (
                self.selected.net_profit_usd if self.selected else None),
            "evaluated": [e.to_dict() for e in self.evaluated],
            "reason": self.reason,
        }


def select_borrow_size(evals: List[BorrowSizeEval]) -> BorrowSizeDecision:
    """Pick the FEASIBLE size with the highest net profit; else fail closed.

    A size is chosen only if it is both profitable after all required costs and
    proven executable (verified liquidity + executor support + atomic sim). If
    no evaluated size is feasible the decision is INFEASIBLE (DENY) — never a
    "best-effort" pick.
    """
    if not evals:
        return BorrowSizeDecision(status="INFEASIBLE", selected=None,
                                  evaluated=[], reason="no_sizes_evaluated")
    feasible = [e for e in evals if e.feasible]
    if not feasible:
        return BorrowSizeDecision(
            status="INFEASIBLE", selected=None, evaluated=list(evals),
            reason="no_feasible_size (profitable+executable+liquidity+sim)")
    best = max(feasible, key=lambda e: e.net_profit_usd or float("-inf"))
    return BorrowSizeDecision(
        status="SELECTED", selected=best, evaluated=list(evals),
        reason=f"selected_size_usd={best.size_usd} net_usd={best.net_profit_usd}")


__all__ = ["BorrowSizeEval", "BorrowSizeDecision", "select_borrow_size"]
