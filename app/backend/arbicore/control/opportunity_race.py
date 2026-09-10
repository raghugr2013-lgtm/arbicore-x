"""Chain-agnostic Opportunity Race (fail-closed, SHADOW).

Selects the FIRST qualifying real edge across ALL activated six-chain cells,
using the EXISTING economic/profit gate — never a hardcoded chain preference.
A candidate qualifies ONLY when:
  * its chain-scoped execution-readiness reaches at least the required stage
    (default ECONOMICS PASS — a genuine exact-quote all-in evaluation), AND
  * its evidenced net profit clears the UNCHANGED Gate-7 floor
    (``FlashLoanGate7AtomicProfit`` — $25, never weakened here).

The race NEVER signs, broadcasts, executes, or promotes. It returns the winning
candidate's readiness verdict (or None). Ordering is by SUBMISSION order only —
no chain is ranked ahead of another; Base/Arbitrum receive no preference.
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional

from .chain_execution_readiness import (
    PASS, STAGE_ORDER, evaluate_chain_execution_readiness,
)

# Minimum ladder stage a candidate must PASS to enter the race. ECONOMICS PASS
# means a genuine exact-quote all-in cost with real evidence (never a probe).
DEFAULT_QUALIFYING_STAGE = "ECONOMICS"


def _stage_index(name: str) -> int:
    return STAGE_ORDER.index(name)


async def _reaches_stage(readiness: Dict[str, Any], stage: str) -> bool:
    """True iff EVERY ladder stage up to and including ``stage`` is PASS."""
    stages = readiness.get("stages") or {}
    upto = _stage_index(stage)
    return all(stages.get(STAGE_ORDER[i], {}).get("status") == PASS
               for i in range(upto + 1))


async def run_opportunity_race(
    candidates: List[Dict[str, Any]],
    *,
    qualifying_stage: str = DEFAULT_QUALIFYING_STAGE,
    profit_gate: Optional[Any] = None,
    evaluate_fn: Callable[..., Awaitable[Dict[str, Any]]] = evaluate_chain_execution_readiness,
    **eval_kw: Any,
) -> Dict[str, Any]:
    """Race ``candidates`` (each ``{"chain": str, "candidate": {...}, ...}``).

    Returns ``{winner, winner_readiness, evaluated, entrants, note}``. Fail-closed:
    a candidate that does not reach ``qualifying_stage`` OR fails the profit gate
    is skipped (never a fabricated win). No chain preference — first submitted
    qualifier wins."""
    if profit_gate is None:
        from ..scanners.flash_loan_arbitrage.filter import FlashLoanGate7AtomicProfit
        profit_gate = FlashLoanGate7AtomicProfit(thresholds={})

    evaluated: List[Dict[str, Any]] = []
    winner = None
    winner_readiness = None
    entrants = 0

    for entry in candidates:
        chain = str(entry.get("chain") or "").lower()
        cand = entry.get("candidate")
        readiness = await evaluate_fn(chain, candidate=cand, **eval_kw)
        rec = {"chain": chain, "reached_stage": readiness.get("reached_stage"),
               "terminal_blocker": readiness.get("terminal_blocker"),
               "qualified": False, "net_profit_usd": None}

        if await _reaches_stage(readiness, qualifying_stage):
            entrants += 1
            econ = (readiness.get("stages") or {}).get("ECONOMICS", {})
            net = (econ.get("evidence") or {}).get("net_profit_usd")
            rec["net_profit_usd"] = net
            # UNCHANGED Gate-7 profit floor — never weakened by the race.
            g7 = profit_gate.evaluate(
                atomic_profit_usd=float(net) if net is not None else 0.0,
                borrow_amount_usd=float(
                    (cand or {}).get("borrow_amount_usd") or 0.0))
            rec["qualified"] = bool(getattr(g7, "passed", False))
            if rec["qualified"] and winner is None:
                winner = entry
                winner_readiness = readiness
        evaluated.append(rec)

    return {
        "winner": winner,
        "winner_readiness": winner_readiness,
        "evaluated": evaluated,
        "entrants": entrants,
        "qualifying_stage": qualifying_stage,
        "signed": False, "broadcast": False, "executed": False,
        "note": ("first-submitted qualifying edge across all activated cells; "
                 "no chain preference; Gate-7 profit floor unchanged; SHADOW."),
    }


__all__ = ["DEFAULT_QUALIFYING_STAGE", "run_opportunity_race"]
