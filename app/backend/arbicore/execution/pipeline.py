"""ArbiCore X — Unified Opportunity Pipeline (P0-C).

Single-loop coordinator that walks every discovered opportunity through
the canonical stages already implemented in the platform, journaling
each stage:

    DISCOVERED
      → QUOTED
      → GAS_ESTIMATED
      → PROFITED
      → CERTIFIED  ─┐
                    ├── POLICY_DENIED  (kill switch / mode / capital)
      → policy      │
                    └── SHADOW_RECORDED (SHADOW mode terminates here)
      → (LIMITED_LIVE+) BROADCAST_SENT / BROADCAST_FAILED
      → (post-trade) COMPLETED

Every stage writes to the Opportunity Journal (P0-A). Terminal rows are
picked up by the Learning Ledger (P0-B) at the next emit tick.

Design invariants:
  * NEVER broadcasts unless the strategy's ``mode`` has been promoted by
    an explicit operator action to ``LIMITED_LIVE`` or ``FULL_LIVE``. The
    mode registry (``arbicore/execution/mode.py``) is the *only* gate
    that authorises automatic broadcast — set through
    ``POST /api/arbicore/execution/mode/{strategy}`` by an operator.
  * Reuses every subsystem — no rewrites. Missing subsystems (e.g. no
    certifier wired) degrade cleanly: the pipeline still journals the
    row and stops at the last successful stage.
  * Pure orchestration. Owns no persistent state of its own — the
    journal *is* the state.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..data.journal import ExecutionStatus, OpportunityJournal


logger = logging.getLogger("arbicore.execution.pipeline")


# ---------------------------------------------------------------------------
# Modes that authorise automatic broadcast. Anything else journals a
# SHADOW_RECORDED terminal and stops.
# ---------------------------------------------------------------------------
BROADCAST_MODES = frozenset({"LIMITED_LIVE", "FULL_LIVE"})

# Modes that authorise deep analysis + shadow recording.
ANALYSIS_MODES = frozenset({"PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE"})


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class StageOutcome:
    stage: str
    ok: bool
    detail: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class PipelineResult:
    opportunity_id: str
    strategy: str
    mode: str
    action: str                   # 'broadcast' | 'shadow' | 'deny' | 'reject' | 'observe'
    reason: str
    stages: List[Dict[str, Any]] = field(default_factory=list)
    plan_id: Optional[str] = None
    broadcast_receipt: Optional[Dict[str, Any]] = None
    generated_at: str = field(default_factory=_iso_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class OpportunityPipeline:
    """Coordinates one opportunity through the full production loop.

    Constructor accepts every dependency as ``Optional`` so tests can
    inject fakes and the runtime pod can wire the real components. When
    a dependency is missing the corresponding stage is skipped with a
    ``skipped`` outcome — never a crash.
    """

    def __init__(
        self,
        *,
        journal: OpportunityJournal,
        mode_repo=None,
        kill_switch=None,
        capital_allocator=None,
        certifier=None,
        broadcaster=None,
        plans_repo=None,
    ):
        self._journal = journal
        self._mode = mode_repo
        self._kill = kill_switch
        self._alloc = capital_allocator
        self._certifier = certifier
        self._broadcaster = broadcaster
        self._plans = plans_repo

    # =====================================================================
    # Public entry point
    # =====================================================================
    async def evaluate(
        self,
        opp: Dict[str, Any],
        *,
        strategy: Optional[str] = None,
        scanner_family: Optional[str] = None,
    ) -> PipelineResult:
        """Walk one opportunity through the canonical pipeline.

        ``opp`` is a dict — accepts either a ``DiscoveredOpportunity``
        (``.to_dict()``) or an ad-hoc dict from a test. The dict must
        carry ``opportunity_id`` at minimum.
        """
        opportunity_id = opp.get("opportunity_id") or ""
        if not opportunity_id:
            return PipelineResult(
                opportunity_id="",
                strategy=strategy or opp.get("strategy") or "unknown",
                mode="UNKNOWN",
                action="reject",
                reason="missing opportunity_id",
            )

        strategy = strategy or opp.get("strategy") or opp.get("opportunity_type") or "flash_loan_arbitrage"

        # 1. Read mode
        mode = await self._resolve_mode(strategy)

        # 2. Journal discovery
        await self._journal.record_discovery(
            {**opp, "opportunity_id": opportunity_id,
             "opportunity_type": opp.get("opportunity_type") or strategy},
            mode=mode,
            scanner_family=scanner_family,
            detail={"strategy": strategy},
        )

        result = PipelineResult(
            opportunity_id=opportunity_id,
            strategy=strategy,
            mode=mode,
            action="observe",
            reason="pipeline entered",
        )

        # OBSERVE — record and stop.
        if mode not in ANALYSIS_MODES:
            result.action = "observe"
            result.reason = "mode is OBSERVE — no analysis"
            result.stages.append(StageOutcome(
                stage="observe_only", ok=True,
                detail="OBSERVE mode records the opportunity and skips downstream stages.",
            ).to_dict())
            return result

        # 3. Quote stage — quote data may already be on the opp
        quote_outcome = self._extract_quote(opp)
        result.stages.append(quote_outcome.to_dict())
        await self._journal.record_event(
            opportunity_id, kind="quoted",
            detail=quote_outcome.payload,
            patch=self._quote_patch(opp),
            status=ExecutionStatus.QUOTED.value if quote_outcome.ok else None,
        )

        # 4. Gas stage
        gas_outcome = self._extract_gas(opp)
        result.stages.append(gas_outcome.to_dict())
        await self._journal.record_event(
            opportunity_id, kind="gas_estimated",
            detail=gas_outcome.payload,
            patch={"gas_estimate": gas_outcome.payload} if gas_outcome.ok else None,
            status=ExecutionStatus.GAS_ESTIMATED.value if gas_outcome.ok else None,
        )

        # 5. Profit stage
        profit_outcome = self._compute_profit(opp, gas_outcome.payload)
        result.stages.append(profit_outcome.to_dict())
        await self._journal.record_event(
            opportunity_id, kind="profit_evaluated",
            detail=profit_outcome.payload,
            patch=self._profit_patch(profit_outcome.payload),
            status=ExecutionStatus.PROFITED.value if profit_outcome.ok else None,
        )
        if not profit_outcome.ok:
            result.action = "reject"
            result.reason = profit_outcome.detail or "unprofitable"
            await self._journal.record_event(
                opportunity_id, kind="rejected",
                detail={"reason": result.reason},
                patch={"rejection_reason": result.reason},
                status=ExecutionStatus.REJECTED.value,
            )
            return result

        # 6. Policy gate — kill switch, mode, capital
        policy_outcome = await self._policy_check(strategy, mode, profit_outcome.payload)
        result.stages.append(policy_outcome.to_dict())
        await self._journal.record_event(
            opportunity_id, kind="policy_evaluated",
            detail=policy_outcome.payload,
            patch={"policy_decision": policy_outcome.payload},
        )
        if not policy_outcome.ok:
            result.action = "deny"
            result.reason = policy_outcome.detail
            await self._journal.record_event(
                opportunity_id, kind="policy_denied",
                detail=policy_outcome.payload,
                status=ExecutionStatus.POLICY_DENIED.value,
            )
            return result

        # 7. Certification (only for flash-loan style opps; skipped when
        #    the certifier or the required inputs are absent)
        cert_outcome = await self._certify(opp, strategy)
        result.stages.append(cert_outcome.to_dict())
        await self._journal.record_event(
            opportunity_id, kind="certified",
            detail=cert_outcome.payload,
            patch={"certification_result": cert_outcome.payload},
            status=ExecutionStatus.CERTIFIED.value if cert_outcome.ok else None,
        )
        if not cert_outcome.ok:
            result.action = "reject"
            result.reason = cert_outcome.detail
            await self._journal.record_event(
                opportunity_id, kind="rejected_at_certification",
                detail=cert_outcome.payload,
                patch={"rejection_reason": cert_outcome.detail},
                status=ExecutionStatus.REJECTED.value,
            )
            return result

        # 8. Decision — SHADOW records, LIMITED_LIVE+ would broadcast.
        if mode not in BROADCAST_MODES:
            # SHADOW / PAPER — record what WOULD have happened.
            result.action = "shadow"
            result.reason = "mode not promoted for automatic broadcast"
            expected = {
                "would_survive": True,
                "expected_net_profit_usd": profit_outcome.payload.get("net_profit_usd"),
                "expected_confidence": opp.get("confidence"),
                "certification_status": cert_outcome.payload.get("status"),
            }
            await self._journal.record_event(
                opportunity_id, kind="shadow_recorded",
                detail={"mode": mode},
                patch={"expected_result": expected},
                status=ExecutionStatus.SHADOW_RECORDED.value,
            )
            return result

        # 9. Broadcast — only reached with LIMITED_LIVE or FULL_LIVE
        broadcast_outcome = await self._broadcast(opp, strategy, result)
        result.stages.append(broadcast_outcome.to_dict())
        if broadcast_outcome.ok:
            result.action = "broadcast"
            result.reason = "broadcast dispatched"
            result.broadcast_receipt = broadcast_outcome.payload
            await self._journal.record_event(
                opportunity_id, kind="broadcast_sent",
                detail=broadcast_outcome.payload,
                patch={"actual_result": broadcast_outcome.payload},
                status=ExecutionStatus.BROADCAST_SENT.value,
            )
        else:
            result.action = "reject"
            result.reason = broadcast_outcome.detail
            await self._journal.record_event(
                opportunity_id, kind="broadcast_failed",
                detail=broadcast_outcome.payload,
                patch={"actual_result": broadcast_outcome.payload,
                       "rejection_reason": broadcast_outcome.detail},
                status=ExecutionStatus.BROADCAST_FAILED.value,
            )
        return result

    # =====================================================================
    # Stage implementations
    # =====================================================================
    async def _resolve_mode(self, strategy: str) -> str:
        if self._mode is None:
            return "SHADOW"
        try:
            row = await self._mode.get(strategy)
            return (row or {}).get("mode") or "OBSERVE"
        except Exception as exc:  # noqa: BLE001
            logger.warning("pipeline mode read failed: %s", exc)
            return "OBSERVE"

    @staticmethod
    def _extract_quote(opp: Dict[str, Any]) -> StageOutcome:
        hops = opp.get("swap_hops")
        if not hops:
            return StageOutcome(
                stage="quote", ok=False,
                detail="no swap_hops on opportunity — cannot quote",
                payload={},
            )
        return StageOutcome(
            stage="quote", ok=True,
            detail=f"{len(hops)} hop(s) resolved from discovery",
            payload={"hops": len(hops), "route": [h.get("dex") for h in hops]},
        )

    @staticmethod
    def _quote_patch(opp: Dict[str, Any]) -> Dict[str, Any]:
        patch = {}
        for k in ("buy_venue", "sell_venue", "spread_pct"):
            v = opp.get(k)
            if v is not None:
                patch[k] = v
        return patch

    @staticmethod
    def _extract_gas(opp: Dict[str, Any]) -> StageOutcome:
        # Prefer explicit gas fields; else derive a nominal estimate from the
        # discovery row's borrow amount (best-effort, non-fatal).
        gas = opp.get("gas_estimate")
        if isinstance(gas, dict) and gas:
            return StageOutcome(
                stage="gas", ok=True,
                detail="gas_estimate present on opportunity",
                payload=dict(gas),
            )
        borrow_usd = opp.get("borrow_amount_usd") or opp.get("capital_required_usd") or 0
        # Conservative nominal: 0.6% of borrow as gas equivalent in preview.
        nominal = round(float(borrow_usd) * 0.006, 4) if borrow_usd else 0.0
        return StageOutcome(
            stage="gas", ok=True,
            detail="derived nominal gas estimate",
            payload={"gwei": None, "units": None, "usd": nominal, "source": "nominal"},
        )

    @staticmethod
    def _compute_profit(opp: Dict[str, Any], gas: Dict[str, Any]) -> StageOutcome:
        net = opp.get("net_profit_usd")
        if net is None:
            net = opp.get("expected_profit_usd")
        if net is None:
            return StageOutcome(
                stage="profit", ok=False,
                detail="no profitability estimate on opportunity",
                payload={},
            )
        gas_usd = float((gas or {}).get("usd") or 0.0)
        after_gas = float(net) - gas_usd
        ok = after_gas > 0.0
        return StageOutcome(
            stage="profit",
            ok=ok,
            detail=f"net={net:.4f} gas={gas_usd:.4f} after_gas={after_gas:.4f}",
            payload={
                "gross_profit_usd": float(net),
                "gas_cost_usd": gas_usd,
                "net_profit_usd": after_gas,
                "profitable": ok,
            },
        )

    @staticmethod
    def _profit_patch(profit_payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"expected_profit_usd": profit_payload.get("net_profit_usd")}

    async def _policy_check(
        self, strategy: str, mode: str, profit_payload: Dict[str, Any],
    ) -> StageOutcome:
        reasons: List[str] = []
        # Kill switch
        if self._kill is not None:
            try:
                state = await self._kill.get()
                if state and (state.get("engaged") or state.get("state") == "engaged"):
                    return StageOutcome(
                        stage="policy", ok=False,
                        detail="kill switch engaged",
                        payload={"decision": "deny", "engine": "kill_switch",
                                 "reasons": ["kill_switch_engaged"]},
                    )
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"kill_switch_read_failed:{exc}")
        # Capital allocator (informational; profit threshold gate)
        if self._alloc is not None:
            try:
                policy = await self._alloc.evaluate(
                    strategy=strategy,
                    proposed_usd=float(profit_payload.get("gross_profit_usd") or 0.0),
                    expected_net_profit_usd=float(profit_payload.get("net_profit_usd") or 0.0),
                )
                if policy and not policy.get("approved", True):
                    return StageOutcome(
                        stage="policy", ok=False,
                        detail=f"capital policy denied: {policy.get('binding_constraint')}",
                        payload={"decision": "deny", "engine": "capital",
                                 "reasons": policy.get("reasons", []),
                                 "capital": policy},
                    )
                reasons.append(f"capital_ok:{policy.get('binding_constraint') if policy else 'no-policy'}")
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"capital_check_failed:{exc}")
        return StageOutcome(
            stage="policy", ok=True,
            detail=f"policy allows in mode {mode}",
            payload={"decision": "allow", "engine": "composite",
                     "mode": mode, "reasons": reasons},
        )

    async def _certify(
        self, opp: Dict[str, Any], strategy: str,
    ) -> StageOutcome:
        """Attempt full certification. When the certifier is not wired
        (unit tests) or the opportunity is not flash-loan shaped, return
        a benign INFO outcome so the pipeline can proceed.
        """
        if self._certifier is None:
            return StageOutcome(
                stage="certification", ok=True,
                detail="certifier not wired — skipped",
                payload={"status": "skipped"},
            )
        # Only flash-loan opportunities have the fields the certifier needs.
        needed = {"chain", "borrow_token", "borrow_amount_wei",
                  "borrow_amount_usd", "flash_loan_provider", "swap_hops"}
        if not needed.issubset(opp.keys()):
            return StageOutcome(
                stage="certification", ok=True,
                detail="opportunity not flash-loan shaped — certification skipped",
                payload={"status": "skipped"},
            )
        try:
            report = await self._certifier.certify(
                strategy=strategy,
                chain=opp["chain"],
                borrow_token=opp["borrow_token"],
                borrow_amount_wei=int(opp["borrow_amount_wei"]),
                borrow_amount_usd=float(opp["borrow_amount_usd"]),
                flash_loan_provider=opp["flash_loan_provider"],
                swap_hops=opp["swap_hops"],
                opportunity_id=opp.get("opportunity_id"),
                expected_net_profit_usd=opp.get("net_profit_usd"),
            )
            d = report.to_dict() if hasattr(report, "to_dict") else dict(report)
            certified = bool(d.get("certified") or (d.get("status") == "ok"))
            return StageOutcome(
                stage="certification", ok=certified,
                detail=d.get("summary") or ("certification passed" if certified else "certification failed"),
                payload={"status": "ok" if certified else "fail", "report": d},
            )
        except Exception as exc:  # noqa: BLE001
            return StageOutcome(
                stage="certification", ok=False,
                detail=f"certifier raised {type(exc).__name__}: {exc}",
                payload={"status": "error"},
            )

    async def _broadcast(
        self, opp: Dict[str, Any], strategy: str, result: PipelineResult,
    ) -> StageOutcome:
        if self._broadcaster is None:
            return StageOutcome(
                stage="broadcast", ok=False,
                detail="broadcaster not wired",
                payload={"status": "unwired"},
            )
        plan_id = opp.get("plan_id")
        if not plan_id or self._plans is None:
            return StageOutcome(
                stage="broadcast", ok=False,
                detail="no plan_id / plans_repo — broadcaster requires a persisted plan",
                payload={"status": "no_plan"},
            )
        try:
            plan_doc = await self._plans.get(plan_id)
            if not plan_doc:
                return StageOutcome(
                    stage="broadcast", ok=False,
                    detail=f"plan {plan_id} not found",
                    payload={"status": "plan_missing"},
                )
            receipt = await self._broadcaster.broadcast_plan(
                plan_doc,
                actor="auto_executor",
                confirm=True,
                expected_net_profit_usd=opp.get("net_profit_usd"),
            )
            r = receipt.to_dict() if hasattr(receipt, "to_dict") else dict(receipt)
            result.plan_id = plan_id
            return StageOutcome(
                stage="broadcast", ok=True,
                detail="broadcast dispatched",
                payload=r,
            )
        except Exception as exc:  # noqa: BLE001
            return StageOutcome(
                stage="broadcast", ok=False,
                detail=f"broadcaster raised {type(exc).__name__}: {exc}",
                payload={"status": "error"},
            )
