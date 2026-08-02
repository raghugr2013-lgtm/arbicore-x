"""Wave 6A · Per-Strategy Execution Mode Ladder.

Approved 5-stage ladder (no direct promotion allowed):

    OBSERVE → PAPER → SHADOW → LIMITED_LIVE → FULL_LIVE

Rules:
    * Every strategy carries its own ``mode`` — the platform never has
      a single "global execution" switch.
    * Transitions may go one step forward or any number of steps
      backward (rollback is always allowed and immediate).
    * Every transition emits an audit-trail row and — when signing is
      configured — a Wave-5 signed evidence bundle stamping the change.
    * The deployment defaults (see :func:`default_mode_map`) match the
      approved posture: discovery / learning / calibration / evidence
      LIVE; every trading strategy PAPER or SHADOW; flash-loan starts
      in SHADOW.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enum + ladder helpers
# ---------------------------------------------------------------------------

MODES: tuple = ("OBSERVE", "PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE")


def _idx(mode: str) -> int:
    try:
        return MODES.index(mode)
    except ValueError as e:
        raise ValueError(f"unknown mode '{mode}'; must be one of {MODES}") from e


def validate_transition(current: str, proposed: str) -> None:
    """Raises ``ValueError`` if the transition is not allowed.

    Forward transitions must advance exactly one step.  Backward
    transitions (rollbacks) may skip any number of steps.  A no-op
    transition is also allowed (idempotent).
    """
    if current == proposed:
        return
    c, p = _idx(current), _idx(proposed)
    if p < c:
        # Rollback — always allowed.
        return
    if p - c > 1:
        raise ValueError(
            f"invalid promotion — '{current}' → '{proposed}' skips the ladder; "
            f"must promote one step at a time (next allowed: '{MODES[c + 1]}')"
        )


def is_broadcast_allowed(mode: str) -> bool:
    """Only ``LIMITED_LIVE`` and ``FULL_LIVE`` may broadcast on-chain
    transactions or submit real orders."""
    return mode in ("LIMITED_LIVE", "FULL_LIVE")


# ---------------------------------------------------------------------------
# Deployment defaults (approved posture)
# ---------------------------------------------------------------------------

# Strategies that carry the execution ladder (per §Deployment Defaults).
TRADING_STRATEGIES: tuple = (
    "flash_loan_arbitrage",
    "cex_arbitrage",
    "dex_capital_arbitrage",
    "cross_chain_arbitrage",
    "portfolio_rebalance",
    "treasury_movement",
    "position_management",
)


def default_mode_map() -> Dict[str, str]:
    """Approved deploy-time defaults.

    Flash-loan → SHADOW (continuously builds transactions, estimates
    gas, validates profitability, runs full simulations, generates
    evidence, and learns; no broadcasts).  Every other trading
    strategy → PAPER.  Discovery / learning / calibration / evidence
    are handled by their own always-on workers and are intentionally
    NOT part of the execution ladder.
    """
    return {
        "flash_loan_arbitrage": "SHADOW",
        "cex_arbitrage": "PAPER",
        "dex_capital_arbitrage": "PAPER",
        "cross_chain_arbitrage": "PAPER",
        "portfolio_rebalance": "PAPER",
        "treasury_movement": "PAPER",
        "position_management": "PAPER",
    }


# ---------------------------------------------------------------------------
# Persistence-friendly value objects
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ModeTransition:
    strategy: str
    from_mode: str
    to_mode: str
    reason: str
    proposed_at: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Repository — append-only transition log + one-doc-per-strategy state
# ---------------------------------------------------------------------------

class ExecutionModeRepo:
    """Mongo-backed per-strategy execution mode registry."""

    def __init__(self, db, state_collection: str = "execution_mode_state",
                 audit_collection: str = "execution_mode_audit"):
        self._db = db
        self._state = db[state_collection]
        self._audit = db[audit_collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._state.create_index("strategy", unique=True)
        await self._audit.create_index([("strategy", 1), ("at", -1)])
        self._indexes_ready = True

    async def ensure_defaults(self) -> None:
        """Seed missing strategies with the approved deploy defaults.
        Never overwrites an existing row — idempotent."""
        defaults = default_mode_map()
        for strategy, mode in defaults.items():
            existing = await self._state.find_one({"strategy": strategy}, {"_id": 0})
            if existing:
                continue
            now = _now_iso()
            await self._state.insert_one({
                "strategy": strategy,
                "mode": mode,
                "seeded": True,
                "created_at": now,
                "updated_at": now,
            })
            await self._audit.insert_one({
                "strategy": strategy,
                "from_mode": None,
                "to_mode": mode,
                "reason": "deployment default",
                "at": now,
                "actor": "system_bootstrap",
            })

    # --- reads ---

    async def get(self, strategy: str) -> Optional[Dict[str, Any]]:
        return await self._state.find_one({"strategy": strategy}, {"_id": 0})

    async def list_all(self) -> List[Dict[str, Any]]:
        cur = self._state.find({}, {"_id": 0}).sort("strategy", 1)
        return await cur.to_list(200)

    async def audit_history(self, strategy: Optional[str] = None,
                            limit: int = 50) -> List[Dict[str, Any]]:
        q = {"strategy": strategy} if strategy else {}
        cur = self._audit.find(q, {"_id": 0}).sort("at", -1).limit(limit)
        return await cur.to_list(limit)

    # --- writes ---

    async def transition(self, strategy: str, to_mode: str, reason: str,
                         actor: str = "operator") -> Dict[str, Any]:
        """Validate + apply a transition.  Raises ``ValueError`` if the
        transition violates the ladder."""
        if to_mode not in MODES:
            raise ValueError(f"unknown mode '{to_mode}'")
        if strategy not in TRADING_STRATEGIES:
            raise ValueError(
                f"unknown strategy '{strategy}'; known: {TRADING_STRATEGIES}"
            )
        current = await self.get(strategy)
        from_mode = (current or {}).get("mode") or "OBSERVE"
        validate_transition(from_mode, to_mode)
        now = _now_iso()
        await self._state.update_one(
            {"strategy": strategy},
            {"$set": {"strategy": strategy, "mode": to_mode,
                      "updated_at": now, "seeded": False},
             "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        await self._audit.insert_one({
            "strategy": strategy,
            "from_mode": from_mode,
            "to_mode": to_mode,
            "reason": reason or "",
            "at": now,
            "actor": actor,
        })
        return await self.get(strategy) or {}
