"""ArbiCore X — consolidated production-readiness CORE (pure, stdlib-only).

Zero I/O, zero arbicore imports → deterministic and unit-testable offline. The
runtime collectors in ``production_readiness.py`` build ``ReadinessItem`` values
and hand them to :func:`aggregate` for the single consolidated report.

Contract (matches the operator spec §14):
  * Every item has a Status: READY | BLOCKED | DEGRADED | UNKNOWN
  * Every non-READY item has a Category: CODE | ENVIRONMENT | INFRASTRUCTURE | MARKET
    plus what/why/where/required so the operator knows the exact next action.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class Status:
    READY = "READY"
    BLOCKED = "BLOCKED"
    DEGRADED = "DEGRADED"
    UNKNOWN = "UNKNOWN"


class Category:
    CODE = "CODE"
    ENVIRONMENT = "ENVIRONMENT"
    INFRASTRUCTURE = "INFRASTRUCTURE"
    MARKET = "MARKET"
    NONE = "NONE"          # used only for READY items


_ALL_STATUS = (Status.READY, Status.BLOCKED, Status.DEGRADED, Status.UNKNOWN)
_ALL_CATEGORY = (Category.CODE, Category.ENVIRONMENT, Category.INFRASTRUCTURE,
                 Category.MARKET, Category.NONE)

# Worst-first precedence for rolling a group of items up to one verdict.
# BLOCKED dominates, then UNKNOWN, then DEGRADED, then READY.
_SEVERITY = {Status.BLOCKED: 3, Status.UNKNOWN: 2, Status.DEGRADED: 1,
             Status.READY: 0}


@dataclass
class ReadinessItem:
    """One readiness dimension for one subject.

    ``subject`` is the axis coordinate, e.g. ``chain=base`` or
    ``chain=base/provider=balancer_v2/venue=uniswap_v3``.
    """
    domain: str                         # e.g. "RPC", "PROVIDER", "VENUE", "SAFETY"
    subject: str                        # e.g. "base", "base/balancer_v2"
    status: str                         # Status.*
    category: str = Category.NONE       # Category.* (NONE only when READY)
    what_missing: str = ""
    why_blocked: str = ""
    where_configured: str = ""          # env var / mongo doc / contract
    required_value: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in _ALL_STATUS:
            raise ValueError(f"invalid status {self.status!r}")
        if self.status == Status.READY:
            # READY items carry no blocker category.
            self.category = Category.NONE
        else:
            if self.category not in _ALL_CATEGORY or self.category == Category.NONE:
                raise ValueError(
                    f"non-READY item {self.domain}/{self.subject} needs a real "
                    f"category, got {self.category!r}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def roll_up(statuses: List[str]) -> str:
    """Worst-first group verdict. Empty ⇒ UNKNOWN (nothing observed)."""
    if not statuses:
        return Status.UNKNOWN
    return max(statuses, key=lambda s: _SEVERITY.get(s, 2))


def aggregate(items: List[ReadinessItem],
              *, head_sha: str = "", generated_by: str = "production_readiness"
              ) -> Dict[str, Any]:
    """Compose items into the single consolidated report.

    Produces: overall verdict, per-domain rollup, per-category counts, the
    ordered blocker list (actionable non-READY items, BLOCKED first), and the
    full item list. Pure — safe to snapshot/persist as evidence.
    """
    by_domain: Dict[str, List[str]] = {}
    by_category: Dict[str, int] = {c: 0 for c in _ALL_CATEGORY if c != Category.NONE}
    counts: Dict[str, int] = {s: 0 for s in _ALL_STATUS}

    for it in items:
        by_domain.setdefault(it.domain, []).append(it.status)
        counts[it.status] += 1
        if it.status != Status.READY:
            by_category[it.category] = by_category.get(it.category, 0) + 1

    domain_verdict = {d: roll_up(s) for d, s in sorted(by_domain.items())}
    overall = roll_up([it.status for it in items])

    blockers = [it.to_dict() for it in sorted(
        (i for i in items if i.status != Status.READY),
        key=lambda i: (-_SEVERITY.get(i.status, 2), i.domain, i.subject))]

    # Actionability split: what the OPERATOR can clear now vs what needs Emergent
    # code vs what only the market can produce.
    operator_actionable = [b for b in blockers
                           if b["category"] in (Category.ENVIRONMENT,
                                                Category.INFRASTRUCTURE)]
    code_remainder = [b for b in blockers if b["category"] == Category.CODE]
    market_pending = [b for b in blockers if b["category"] == Category.MARKET]

    return {
        "schema": "arbicore.production_readiness/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "head_sha": head_sha,
        "overall": overall,
        "counts": counts,
        "by_domain": domain_verdict,
        "by_category_blocked": by_category,
        "operator_actionable": operator_actionable,
        "code_remainder": code_remainder,
        "market_pending": market_pending,
        "blockers": blockers,
        "items": [it.to_dict() for it in items],
        "full_live_ready": overall == Status.READY,
    }


__all__ = ["Status", "Category", "ReadinessItem", "roll_up", "aggregate"]
