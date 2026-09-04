"""Wave 6D · Capital Allocation Policy.

Conservative, deterministic sizing policy that binds every SHADOW /
LIMITED_LIVE / FULL_LIVE plan.  Encodes three independent hard limits
per strategy — the smallest wins.

Reuse notice (VERIFY → REUSE):

    The canonical repo ships a ``CapitalSizer`` at
    ``arbicore/intelligence/capital.py`` that computes exactly the
    pool-percent / wallet-percent / per-trade sizing binding logic
    described here.  This module intentionally mirrors that math so
    the execution engine has a self-contained, testable copy that
    can evolve independently of the intelligence-side sizer.  When
    both sizers disagree, the execution-side ``CapitalAllocator`` is
    the *binding* authority for plan-time sizing decisions.

Persistence:

    The allocator persists per-strategy policy documents to
    ``db.capital_policy`` (append-audit trail lives in
    ``db.capital_policy_audit``).  Reads never surface secrets.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("arbicore.execution.capital_policy")


DEFAULT_POLICY: Dict[str, Any] = {
    "max_pool_percent":        0.005,      # 0.5% of borrow-pool liquidity
    "max_wallet_percent":      0.20,       # 20% of gas-wallet native balance (USD-equiv)
    "max_per_plan_usd":        2_500.0,    # $2.5k per single plan
    "daily_notional_usd":      10_000.0,   # $10k rolling daily notional
    "max_concurrent_plans":    3,
    "min_net_profit_usd":      0.50,       # abort if net < 50c
    "max_daily_loss_usd":      100.0,      # STOP-LOSS: halt strategy once
                                           # cumulative realized loss today
                                           # (e.g. reverted-tx gas) hits this
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class AllocationDecision:
    strategy: str
    proposed_usd: float
    approved_usd: float
    binding_constraint: str      # "pool" | "wallet" | "per_plan_cap" | "daily_notional" | "min_profit" | "daily_loss_limit" | "policy_missing"
    pool_limit_usd: float
    wallet_limit_usd: float
    per_plan_cap_usd: float
    daily_notional_usd: float
    daily_used_usd: float
    daily_remaining_usd: float
    min_net_profit_usd: float
    reasons: List[str]
    approved: bool
    deterministic: bool
    generated_at: str
    # Stop-loss (additive; defaulted for backward-compatible construction).
    max_daily_loss_usd: float = 0.0
    daily_loss_used_usd: float = 0.0
    daily_loss_remaining_usd: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CapitalPolicyRepo:
    def __init__(self, db,
                 collection: str = "capital_policy",
                 audit_collection: str = "capital_policy_audit"):
        self._db = db
        self._coll = db[collection]
        self._audit = db[audit_collection]
        self._indexes_ready = False

    async def ensure_indexes(self) -> None:
        if self._indexes_ready:
            return
        await self._coll.create_index("strategy", unique=True)
        await self._audit.create_index([("strategy", 1), ("at", -1)])
        self._indexes_ready = True

    async def ensure_defaults(self, strategies: List[str]) -> None:
        """Seed missing per-strategy policies with the conservative default.
        Never overwrites existing rows — idempotent."""
        for strategy in strategies:
            existing = await self._coll.find_one({"strategy": strategy}, {"_id": 0})
            if existing:
                continue
            now = _now_iso()
            doc = {"strategy": strategy, **DEFAULT_POLICY,
                   "seeded": True, "created_at": now, "updated_at": now}
            await self._coll.insert_one(doc)
            await self._audit.insert_one({
                "strategy": strategy, "action": "seed",
                "policy": {k: DEFAULT_POLICY[k] for k in DEFAULT_POLICY},
                "actor": "system_bootstrap", "at": now, "reason": "deployment default",
            })

    async def get(self, strategy: str) -> Optional[Dict[str, Any]]:
        return await self._coll.find_one({"strategy": strategy}, {"_id": 0})

    async def list_all(self) -> List[Dict[str, Any]]:
        cur = self._coll.find({}, {"_id": 0}).sort("strategy", 1)
        return await cur.to_list(100)

    async def update(self, strategy: str, patch: Dict[str, Any],
                     actor: str = "operator", reason: str = "") -> Dict[str, Any]:
        allowed = set(DEFAULT_POLICY.keys())
        clean = {k: v for k, v in (patch or {}).items() if k in allowed}
        if not clean:
            raise ValueError(
                f"no valid fields in patch; allowed: {sorted(allowed)}"
            )
        # Basic sanity constraints — reject negative / obviously insane values.
        for k, v in clean.items():
            if isinstance(v, (int, float)) and v < 0:
                raise ValueError(f"'{k}' must be non-negative")
        now = _now_iso()
        clean_with_meta = {**clean, "updated_at": now, "seeded": False}
        await self._coll.update_one(
            {"strategy": strategy},
            {"$set": clean_with_meta,
             "$setOnInsert": {"strategy": strategy, "created_at": now}},
            upsert=True,
        )
        await self._audit.insert_one({
            "strategy": strategy, "action": "update", "patch": clean,
            "actor": actor, "at": now, "reason": reason,
        })
        return await self.get(strategy) or {}


class CapitalAllocator:
    """Binding sizing authority for execution plans."""

    def __init__(self, repo: CapitalPolicyRepo, plans_repo=None):
        self._repo = repo
        self._plans_repo = plans_repo

    async def _daily_used_usd(self, strategy: str) -> float:
        if self._plans_repo is None:
            return 0.0
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        try:
            # Sum borrow_amount_usd for plans created today for this strategy.
            cur = self._plans_repo._coll.find(  # noqa: SLF001 — controlled access
                {"strategy": strategy, "created_at": {"$gte": start}},
                {"borrow_amount_usd": 1, "_id": 0},
            )
            total = 0.0
            async for d in cur:
                try:
                    total += float(d.get("borrow_amount_usd") or 0)
                except (TypeError, ValueError):
                    pass
            return round(total, 2)
        except Exception:  # noqa: BLE001
            return 0.0

    async def _daily_realized_loss_usd(self, strategy: str) -> Optional[float]:
        """Cumulative REALIZED loss (USD) booked today for ``strategy``.

        Sums ``realized_loss_usd`` from plans created today (a reverted atomic
        flash-loan loses only gas — booked here as realized loss). Returns:
          * 0.0  when there is no plans repo (no execution capability yet ⇒
            nothing has been lost);
          * the summed loss when readable;
          * ``None`` when a repo IS present but the read fails — the caller
            treats None as a FAIL-CLOSED stop (deny), never as zero-loss.
        """
        if self._plans_repo is None:
            return 0.0
        start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()
        try:
            cur = self._plans_repo._coll.find(  # noqa: SLF001 — controlled access
                {"strategy": strategy, "created_at": {"$gte": start}},
                {"realized_loss_usd": 1, "_id": 0},
            )
            total = 0.0
            async for d in cur:
                try:
                    total += float(d.get("realized_loss_usd") or 0)
                except (TypeError, ValueError):
                    pass
            return round(total, 2)
        except Exception:  # noqa: BLE001 — fail closed: unknown loss ⇒ deny
            return None

    async def evaluate(self, *,
                       strategy: str,
                       proposed_usd: float,
                       available_liquidity_usd: float = 1_000_000.0,
                       reference_capital_usd: Optional[float] = None,
                       expected_net_profit_usd: Optional[float] = None,
                       ) -> AllocationDecision:
        policy = await self._repo.get(strategy)
        reasons: List[str] = []
        if not policy:
            return AllocationDecision(
                strategy=strategy, proposed_usd=float(proposed_usd),
                approved_usd=0.0, binding_constraint="policy_missing",
                pool_limit_usd=0.0, wallet_limit_usd=0.0,
                per_plan_cap_usd=0.0, daily_notional_usd=0.0,
                daily_used_usd=0.0, daily_remaining_usd=0.0,
                min_net_profit_usd=0.0,
                reasons=[f"no capital policy for strategy '{strategy}'"],
                approved=False, deterministic=True,
                generated_at=_now_iso(),
            )
        # Dynamic capital: the live wallet balance is the SOURCE OF TRUTH. There
        # is NO fixed initial-capital fallback — if the caller did not supply the
        # current operating balance, plan-time sizing fails closed.
        if reference_capital_usd is None:
            return AllocationDecision(
                strategy=strategy, proposed_usd=float(proposed_usd),
                approved_usd=0.0, binding_constraint="wallet_balance_unavailable",
                pool_limit_usd=0.0, wallet_limit_usd=0.0,
                per_plan_cap_usd=0.0, daily_notional_usd=0.0,
                daily_used_usd=0.0, daily_remaining_usd=0.0,
                min_net_profit_usd=0.0,
                reasons=["live wallet balance required for plan-time sizing "
                         "(no fixed-capital fallback)"],
                approved=False, deterministic=True,
                generated_at=_now_iso(),
            )
        pool_pct = float(policy.get("max_pool_percent") or DEFAULT_POLICY["max_pool_percent"])
        wallet_pct = float(policy.get("max_wallet_percent") or DEFAULT_POLICY["max_wallet_percent"])
        per_cap = float(policy.get("max_per_plan_usd") or DEFAULT_POLICY["max_per_plan_usd"])
        daily_cap = float(policy.get("daily_notional_usd") or DEFAULT_POLICY["daily_notional_usd"])
        min_profit = float(policy.get("min_net_profit_usd") or DEFAULT_POLICY["min_net_profit_usd"])
        max_loss = float(policy.get("max_daily_loss_usd") or DEFAULT_POLICY["max_daily_loss_usd"])

        pool_limit = max(0.0, available_liquidity_usd * pool_pct)
        wallet_limit = max(0.0, reference_capital_usd * wallet_pct)
        daily_used = await self._daily_used_usd(strategy)
        daily_remaining = max(0.0, daily_cap - daily_used)

        candidates = {
            "pool": pool_limit,
            "wallet": wallet_limit,
            "per_plan_cap": per_cap,
            "daily_notional": daily_remaining,
        }
        binding = min(candidates, key=candidates.get)
        binding_limit = candidates[binding]
        approved_usd = min(float(proposed_usd), binding_limit)
        if binding_limit <= 0:
            reasons.append(f"binding constraint '{binding}' allows $0 — plan blocked")
        elif approved_usd < float(proposed_usd):
            reasons.append(
                f"proposed ${proposed_usd:.2f} capped at ${approved_usd:.2f} by '{binding}'"
            )
        approved = approved_usd > 0
        # Enforce min-profit constraint if operator supplied an estimate.
        if approved and expected_net_profit_usd is not None:
            if float(expected_net_profit_usd) < min_profit:
                approved = False
                binding = "min_profit"
                reasons.append(
                    f"expected net profit ${expected_net_profit_usd:.2f} below floor ${min_profit:.2f}"
                )
        # STOP-LOSS (final, overriding safety gate). Once cumulative realized
        # loss today reaches the operator cap, the strategy is halted regardless
        # of notional/profit. Fail-closed: an unreadable loss ledger ⇒ deny.
        loss_read = await self._daily_realized_loss_usd(strategy)
        if loss_read is None:
            loss_used = max_loss
            loss_remaining = 0.0
            approved = False
            approved_usd = 0.0
            binding = "daily_loss_limit"
            reasons.append("realized-loss ledger unreadable — halted (fail-closed)")
        else:
            loss_used = loss_read
            loss_remaining = max(0.0, max_loss - loss_used)
            if max_loss > 0 and loss_used >= max_loss:
                approved = False
                approved_usd = 0.0
                binding = "daily_loss_limit"
                reasons.append(
                    f"daily realized loss ${loss_used:.2f} reached stop-loss "
                    f"${max_loss:.2f} — strategy halted"
                )
        return AllocationDecision(
            strategy=strategy, proposed_usd=float(proposed_usd),
            approved_usd=round(approved_usd, 2),
            binding_constraint=binding,
            pool_limit_usd=round(pool_limit, 2),
            wallet_limit_usd=round(wallet_limit, 2),
            per_plan_cap_usd=round(per_cap, 2),
            daily_notional_usd=round(daily_cap, 2),
            daily_used_usd=round(daily_used, 2),
            daily_remaining_usd=round(daily_remaining, 2),
            min_net_profit_usd=round(min_profit, 2),
            reasons=reasons,
            approved=approved,
            deterministic=True,
            generated_at=_now_iso(),
            max_daily_loss_usd=round(max_loss, 2),
            daily_loss_used_usd=round(loss_used, 2),
            daily_loss_remaining_usd=round(loss_remaining, 2),
        )
