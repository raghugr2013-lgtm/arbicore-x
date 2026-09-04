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
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..data.journal import ExecutionStatus, OpportunityJournal
from ..paper import (
    EvidenceBundle,
    PaperOutcome,
    SimulationRouter,
    check_liquidity,
    classify_outcome,
    new_validation_id,
)


logger = logging.getLogger("arbicore.execution.pipeline")


# ---------------------------------------------------------------------------
# Modes that authorise automatic broadcast. Anything else journals a
# SHADOW_RECORDED terminal and stops.
# ---------------------------------------------------------------------------
BROADCAST_MODES = frozenset({"LIMITED_LIVE", "FULL_LIVE"})

# Modes that authorise deep analysis + shadow recording.
ANALYSIS_MODES = frozenset({"PAPER", "SHADOW", "LIMITED_LIVE", "FULL_LIVE"})

# T0-3 · explicit readiness/infra sentinels returned by ``_resolve_mode``.
# These are NOT valid ladder modes — they force an operator-visible fault
# instead of silently degrading to legitimate OBSERVE.
MODE_UNRESOLVED = "__MODE_UNRESOLVED__"
MODE_ERROR = "__MODE_ERROR__"


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

    # v2.11.8 Paper Validation Framework additions — additive, safe for
    # existing callers.  ``validation_id`` is assigned at pipeline entry;
    # ``outcome`` is classified exactly once at pipeline completion.
    validation_id: str = ""
    outcome: str = ""
    outcome_reason: str = ""

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
        evidence_repo=None,
        simulator=None,
        capital_balance_provider=None,
        auto_confirm: bool = False,
    ):
        self._journal = journal
        self._mode = mode_repo
        self._kill = kill_switch
        self._alloc = capital_allocator
        # Optional async callable → current operating capital (USD) from the
        # LIVE wallet balance. No fixed-capital fallback; when absent the capital
        # gate is informational-only (execution stays gated elsewhere).
        self._capital_balance_provider = capital_balance_provider
        self._certifier = certifier
        self._broadcaster = broadcaster
        self._plans = plans_repo
        # S3 · autonomous per-transaction confirmation is DEFAULT-OFF.
        # Even when a strategy is promoted to LIMITED_LIVE/FULL_LIVE, the
        # auto-executor path will run the full gate ladder + preflight but
        # HOLD at the operator-confirm gate unless an operator explicitly
        # enables auto_confirm. SHADOW/PAPER never reach broadcast.
        self._auto_confirm = bool(auto_confirm)
        # v2.11.8 Paper Validation Framework — optional. When None, the
        # pipeline still classifies + returns the outcome on PipelineResult
        # but nothing is persisted.
        self._evidence = evidence_repo
        # v2.11.8 Slice B — SimulationRouter. Lazily built from env when
        # no explicit backend is passed. Contract: the router selects
        # ``eth_call`` when an RPC is wired for the opportunity's chain
        # and falls back to the ``heuristic`` backend otherwise. Both
        # backends implement the SimulationBackend Protocol.
        self._simulator = simulator or SimulationRouter.from_env()
        # Per-evaluate() slot for the simulation backend name — read by
        # ``_persist_evidence`` when building the EvidenceBundle.
        self._last_simulation_backend: Optional[str] = None

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
        # v2.11.8 — assign / reuse the canonical Paper Validation ID as
        # the very first act.  Reuses upstream-assigned IDs (retries,
        # replays) so evidence bundles are stable across attempts.
        validation_id = str(opp.get("validation_id") or "").strip() or new_validation_id()
        # Reset per-evaluate scratchpads so state does not leak between
        # opps on a long-lived pipeline instance.
        self._last_simulation_backend = None
        try:
            result = await self._evaluate_inner(
                opp, strategy=strategy, scanner_family=scanner_family,
                validation_id=validation_id,
            )
        finally:
            # No matter how the pipeline exits, we do not want to lose
            # a validation_id.  The classifier + evidence-bundle write
            # happens on the success path below; unexpected exceptions
            # bubble up (the pipeline is a subordinate — the caller
            # decides whether to swallow them).
            pass

        # -----------------------------------------------------------------
        # Terminal classification — happens exactly once, right here.
        # -----------------------------------------------------------------
        outcome, outcome_reason = classify_outcome(
            action=result.action,
            stages=result.stages,
            generic_reason=result.reason,
        )
        result.validation_id  = validation_id
        result.outcome        = outcome.value
        result.outcome_reason = outcome_reason

        # Persist the immutable EvidenceBundle if a repo is wired.
        await self._persist_evidence(
            result=result,
            opp=opp,
            outcome=outcome,
            outcome_reason=outcome_reason,
            scanner_family=scanner_family,
        )
        return result

    async def _evaluate_inner(
        self,
        opp: Dict[str, Any],
        *,
        strategy: Optional[str] = None,
        scanner_family: Optional[str] = None,
        validation_id: str,
    ) -> PipelineResult:
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

        # T0-3: a missing execution_mode row (MODE_UNRESOLVED) or a mode-read
        # failure (MODE_ERROR) is an explicit, operator-visible readiness/infra
        # fault — NOT a silent, legitimate OBSERVE.
        if mode in (MODE_UNRESOLVED, MODE_ERROR):
            return self._readiness_fault_result(mode, strategy, opportunity_id)

        # 2. Journal discovery
        await self._journal.record_discovery(
            {**opp, "opportunity_id": opportunity_id,
             "opportunity_type": opp.get("opportunity_type") or strategy},
            mode=mode,
            scanner_family=scanner_family,
            detail={"strategy": strategy, "validation_id": validation_id},
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
            _t_perf = time.perf_counter(); _t_iso = _iso_now()
            _obs = StageOutcome(
                stage="observe_only", ok=True,
                detail="OBSERVE mode records the opportunity and skips downstream stages.",
            )
            result.stages.append(self._stamp(_obs, _t_perf, _t_iso))
            return result

        # 3. Quote stage — quote data may already be on the opp
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        quote_outcome = self._extract_quote(opp)
        result.stages.append(self._stamp(quote_outcome, _t_perf, _t_iso))
        await self._journal.record_event(
            opportunity_id, kind="quoted",
            detail=quote_outcome.payload,
            patch=self._quote_patch(opp),
            status=ExecutionStatus.QUOTED.value if quote_outcome.ok else None,
        )

        # 3b. Liquidity stage (v2.11.8 Slice B). Runs immediately after
        #     the quote so scanners that couldn't populate reserves
        #     don't trigger it; when hops DO carry ``pool_liquidity_usd``
        #     we fail-fast on under-liquid hops.  Uses only fields the
        #     scanner emits — never fabricates a value.
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        liq = check_liquidity(opp)
        _liq_stage = StageOutcome(
            stage="liquidity", ok=liq.ok,
            detail=liq.detail,
            payload=liq.to_stage_payload(),
        )
        result.stages.append(self._stamp(_liq_stage, _t_perf, _t_iso))
        await self._journal.record_event(
            opportunity_id, kind="liquidity_checked",
            detail=liq.to_stage_payload(),
        )
        if not liq.ok:
            result.action = "reject"
            result.reason = liq.detail
            await self._journal.record_event(
                opportunity_id, kind="rejected_at_liquidity",
                detail=liq.to_stage_payload(),
                patch={"rejection_reason": liq.detail},
                status=ExecutionStatus.REJECTED.value,
            )
            return result

        # 4. Gas stage
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        gas_outcome = self._extract_gas(opp)
        result.stages.append(self._stamp(gas_outcome, _t_perf, _t_iso))
        await self._journal.record_event(
            opportunity_id, kind="gas_estimated",
            detail=gas_outcome.payload,
            patch={"gas_estimate": gas_outcome.payload} if gas_outcome.ok else None,
            status=ExecutionStatus.GAS_ESTIMATED.value if gas_outcome.ok else None,
        )

        # 5. Profit stage
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        profit_outcome = self._compute_profit(opp, gas_outcome.payload)
        result.stages.append(self._stamp(profit_outcome, _t_perf, _t_iso))
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
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        policy_outcome = await self._policy_check(strategy, mode, profit_outcome.payload)
        result.stages.append(self._stamp(policy_outcome, _t_perf, _t_iso))
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
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        cert_outcome = await self._certify(opp, strategy)
        result.stages.append(self._stamp(cert_outcome, _t_perf, _t_iso))
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

        # 7b. Simulate stage (v2.11.8 Slice B). Runs immediately after
        #     certification for every ANALYSIS-mode opp — including
        #     SHADOW/PAPER — so Paper Validation captures the same
        #     execution-viability check LIMITED_LIVE would apply.
        #     Uses the SimulationRouter to select eth_call when an RPC
        #     is wired, otherwise the documented HeuristicSimulator.
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        sim_res = await self._run_simulate_stage(opp, strategy)
        self._last_simulation_backend = sim_res.backend
        _sim_stage = StageOutcome(
            stage="simulate", ok=sim_res.ok,
            detail=sim_res.detail,
            payload=sim_res.to_stage_payload(),
        )
        result.stages.append(self._stamp(_sim_stage, _t_perf, _t_iso))
        await self._journal.record_event(
            opportunity_id, kind="simulated",
            detail=sim_res.to_stage_payload(),
        )
        if not sim_res.ok:
            result.action = "reject"
            result.reason = sim_res.detail or "simulation reverted"
            await self._journal.record_event(
                opportunity_id, kind="rejected_at_simulation",
                detail=sim_res.to_stage_payload(),
                patch={"rejection_reason": result.reason},
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
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        broadcast_outcome = await self._broadcast(opp, strategy, result)
        result.stages.append(self._stamp(broadcast_outcome, _t_perf, _t_iso))
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
    # v2.11.8 Paper Validation Framework helpers
    # =====================================================================
    def _stamp(self, outcome, start_perf, started_iso):
        """Enrich a ``StageOutcome`` dict with per-stage timing + normalise
        the failure_reason field.  Called from every stage-append site."""
        ended_iso = _iso_now()
        duration_ms = round((time.perf_counter() - start_perf) * 1000.0, 3)
        d = outcome.to_dict()
        d["started_at"]     = started_iso
        d["ended_at"]       = ended_iso
        d["duration_ms"]    = duration_ms
        d["failure_reason"] = None if outcome.ok else (outcome.detail or "").strip() or None
        return d

    async def _run_simulate_stage(self, opp: Dict[str, Any], strategy: str):
        """Run the SimulationRouter for one opportunity.

        The router picks ``eth_call`` when an RPC is wired for the opp's
        chain and falls back to the ``HeuristicSimulator`` otherwise.
        Both backends implement :class:`~arbicore.paper.SimulationBackend`.

        The pipeline extracts the executor call target + calldata from
        the plan_head when the opp carries one; otherwise it hands a
        synthetic payload to the heuristic backend (which validates
        selector shape only, not on-chain semantics).
        """
        # Pull plan head from the opp when the caller populated one
        # (typical for planner-produced opps).
        plan = opp.get("plan_head") or {}
        chain = opp.get("chain") or "base"
        to    = plan.get("contract_address") or opp.get("executor_address") or ""
        data  = plan.get("calldata_hex")     or opp.get("calldata_hex")     or ""
        from_ = opp.get("signer_address") or opp.get("recipient") or opp.get("owner") or "0x0000000000000000000000000000000000000001"
        # When the opp doesn't carry a plan head (very common for
        # scanner-emitted candidates), fall through to the heuristic
        # backend with a placeholder selector so it can still assert
        # basic shape and record `backend=heuristic` on the evidence.
        if not to:
            to   = "0x0000000000000000000000000000000000000001"
        if not data:
            data = "0x00000000"
        return await self._simulator.simulate(
            chain=chain, to=to, data=data, from_=from_,
        )

    async def _persist_evidence(self, *,
                                 result: "PipelineResult",
                                 opp: Dict[str, Any],
                                 outcome: "PaperOutcome",
                                 outcome_reason: str,
                                 scanner_family: Optional[str]) -> None:
        """Write the immutable EvidenceBundle exactly once.

        No-ops (with a warning log) when no evidence repo was wired.  Any
        write failure is logged but never propagated — the pipeline's
        primary contract is orchestration, not persistence, and every
        journal event is already written independently.
        """
        if self._evidence is None:
            return
        try:
            bundle = EvidenceBundle(
                validation_id      = result.validation_id,
                opportunity_id     = result.opportunity_id,
                strategy           = result.strategy,
                mode               = result.mode,
                outcome            = outcome,
                outcome_reason     = outcome_reason,
                stages             = list(result.stages),
                scanner_family     = scanner_family,
                plan_id            = result.plan_id,
                simulation_backend = self._last_simulation_backend,
                inputs             = {
                    "strategy":          result.strategy,
                    "chain":             opp.get("chain"),
                    "opportunity_type":  opp.get("opportunity_type"),
                    "borrow_token":      opp.get("borrow_token"),
                    "borrow_amount_usd": opp.get("borrow_amount_usd"),
                    "flash_loan_provider": opp.get("flash_loan_provider"),
                },
                pipeline_action    = result.action,
            )
            await self._evidence.insert(bundle)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PaperEvidence insert failed for validation_id=%s: %s",
                result.validation_id, exc,
            )

    # =====================================================================
    # Stage implementations
    # =====================================================================
    async def _resolve_mode(self, strategy: str) -> str:
        """Look up the analysis mode for a strategy.

        Scanner emissions historically use SCREAMING_SNAKE_CASE strategy
        names (``CEX_ARBITRAGE``), while ``execution_mode_state`` stores
        them lower-case (``cex_arbitrage``).  v2.11.10 · normalise both
        directions so the strategies actually reach analysis stages
        instead of short-circuiting at OBSERVE — this was the root
        cause of the 0.00% executable_rate on the first live Shadow
        Certification run.
        """
        if self._mode is None:
            return "SHADOW"
        candidates: List[str] = []
        if strategy:
            candidates.append(strategy)
            candidates.append(strategy.lower())
            candidates.append(strategy.upper())
        seen = set()
        try:
            for cand in candidates:
                if not cand or cand in seen:
                    continue
                seen.add(cand)
                row = await self._mode.get(cand)
                if row and row.get("mode"):
                    return row["mode"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("pipeline mode read failed: %s", exc)
            return MODE_ERROR
        return MODE_UNRESOLVED

    def _readiness_fault_result(self, mode: str, strategy: str,
                                opportunity_id: str) -> "PipelineResult":
        """T0-3: build an explicit readiness/infra fault result.

        Missing mode ⇒ ``readiness_error`` (config_missing); mode-read error
        ⇒ ``infra_error``. Never mislabeled as legitimate OBSERVE.
        """
        is_missing = mode == MODE_UNRESOLVED
        reason = (
            f"config_missing: no execution_mode_state row for strategy "
            f"'{strategy}' — seed execution modes (NOT a valid OBSERVE)"
            if is_missing else
            f"infra_error: execution_mode read failed for strategy '{strategy}'"
        )
        result = PipelineResult(
            opportunity_id=opportunity_id,
            strategy=strategy,
            mode=("UNRESOLVED" if is_missing else "ERROR"),
            action=("readiness_error" if is_missing else "infra_error"),
            reason=reason,
        )
        result.outcome = "READINESS_ERROR" if is_missing else "INFRA_ERROR"
        result.outcome_reason = reason
        _t_perf = time.perf_counter(); _t_iso = _iso_now()
        _obs = StageOutcome(stage="readiness_check", ok=False, detail=reason)
        result.stages.append(self._stamp(_obs, _t_perf, _t_iso))
        return result

    @staticmethod
    def _extract_quote(opp: Dict[str, Any]) -> StageOutcome:
        """Resolve a route for the pipeline.

        Accepts three canonical shapes emitted by different scanner
        families:

        1. ``swap_hops`` — explicit hop list (DEX aggregator / flash loan
           style).  Preferred.
        2. ``buy_venue`` + ``sell_venue`` + ``asset`` — CEX / DEX
           spread scanners emit this pair form.  v2.11.10 synthesises
           a 2-hop route so the downstream stages have something to
           reason about instead of the pipeline blanket-rejecting
           every venue-pair opportunity as ``no swap_hops``.
        3. Neither — hard ``no route`` failure.
        """
        hops = opp.get("swap_hops")
        if hops:
            return StageOutcome(
                stage="quote", ok=True,
                detail=f"{len(hops)} hop(s) resolved from discovery",
                payload={"hops": len(hops), "route": [h.get("dex") for h in hops]},
            )

        # Fallback — synthesise a 2-hop route from the venue-pair form
        # scanners like CEX_ARBITRAGE / DEX_ARBITRAGE emit.
        buy_venue  = opp.get("buy_venue")
        sell_venue = opp.get("sell_venue")
        asset      = opp.get("asset") or opp.get("symbol")
        if buy_venue and sell_venue and asset:
            synth_hops = [
                {
                    "dex":       str(buy_venue),
                    "direction": "buy",
                    "asset":     str(asset),
                    "price":     opp.get("buy_price"),
                },
                {
                    "dex":       str(sell_venue),
                    "direction": "sell",
                    "asset":     str(asset),
                    "price":     opp.get("sell_price"),
                },
            ]
            return StageOutcome(
                stage="quote", ok=True,
                detail=(
                    f"synthesised 2-hop route from venue pair "
                    f"({buy_venue} → {sell_venue})"
                ),
                payload={
                    "hops":       2,
                    "route":      [str(buy_venue), str(sell_venue)],
                    "synthetic":  True,
                    "asset":      str(asset),
                },
            )

        return StageOutcome(
            stage="quote", ok=False,
            detail="no swap_hops on opportunity — cannot quote",
            payload={},
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
        """Estimate execution cost as a stand-in for gas.

        Returns cost in USD.  Applied by the ``profit`` stage as a
        deduction from gross profit.  Venue-family aware:

        * CEX↔CEX (``opportunity_type=CEX_ARBITRAGE``, both venues are
          off-chain exchanges) — cost is aggregate exchange trading
          fees (~0.20% round-trip nominal).
        * Cross-chain (``opportunity_type=CROSS_CHAIN_ARBITRAGE``) —
          bridge fees dominate; use 1.0% nominal.
        * DEX / Flash-loan (on-chain) — 0.60% nominal gas budget.

        Explicit ``gas_estimate`` on the opportunity always wins.
        """
        gas = opp.get("gas_estimate")
        if isinstance(gas, dict) and gas:
            return StageOutcome(
                stage="gas", ok=True,
                detail="gas_estimate present on opportunity",
                payload=dict(gas),
            )
        borrow_usd = (opp.get("borrow_amount_usd")
                      or opp.get("capital_required_usd")
                      or 0)
        borrow_usd = float(borrow_usd or 0.0)
        # Enum values (Pydantic model_dump) stringify as "OpportunityType.CEX_ARBITRAGE"
        # so normalise via ``.value`` / ``.name`` when available.
        def _norm(v):
            if v is None:
                return ""
            if hasattr(v, "value"):
                v = v.value
            return str(v).upper()
        opp_type = _norm(opp.get("opportunity_type"))
        strategy = _norm(opp.get("strategy"))
        family = opp_type or strategy
        # Nominal fee rate per family — conservative but honest.
        if family == "CEX_ARBITRAGE":
            rate = 0.002   # 0.20% round-trip fee (taker × 2)
            source = "cex_taker_fee_nominal"
        elif family == "CROSS_CHAIN_ARBITRAGE":
            rate = 0.010   # 1.00% bridge + gas
            source = "cross_chain_bridge_nominal"
        elif family in ("DEX_ARBITRAGE", "DEX_CAPITAL_ARBITRAGE",
                        "FLASH_LOAN_ARBITRAGE", "LAUNCH_ARBITRAGE",
                        "FUNDING_ARBITRAGE"):
            rate = 0.006   # 0.60% on-chain gas
            source = "onchain_gas_nominal"
        else:
            rate = 0.006
            source = "nominal_default"
        nominal = round(borrow_usd * rate, 4) if borrow_usd else 0.0
        return StageOutcome(
            stage="gas", ok=True,
            detail=f"derived nominal cost ({source} at {rate:.3%})",
            payload={
                "gwei":   None,
                "units":  None,
                "usd":    nominal,
                "source": source,
                "rate":   rate,
            },
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
        # Kill switch — use the authoritative KillSwitchRepo.state() API.
        # (S2: the previous ``.get()`` call did not exist on the repo, so
        # the exception was swallowed and the gate never actually denied.)
        if self._kill is not None:
            try:
                engaged = False
                if hasattr(self._kill, "state"):
                    st = await self._kill.state()
                    engaged = bool(getattr(st, "engaged", False))
                elif hasattr(self._kill, "get"):
                    st = await self._kill.get()
                    engaged = bool(st and (st.get("engaged")
                                           or st.get("state") == "engaged"))
                if engaged:
                    return StageOutcome(
                        stage="policy", ok=False,
                        detail="kill switch engaged",
                        payload={"decision": "deny", "engine": "kill_switch",
                                 "reasons": ["kill_switch_engaged"]},
                    )
            except Exception as exc:  # noqa: BLE001
                reasons.append(f"kill_switch_read_failed:{exc}")
        # Capital allocator (informational; profit threshold gate). DYNAMIC:
        # reference capital comes from the LIVE wallet balance provider, never a
        # fixed default. When no provider is wired, sizing capital is unavailable
        # → allocator fails closed; treated as informational here (no execution
        # occurs in non-broadcast modes), while real caps still hard-deny.
        if self._alloc is not None:
            try:
                ref_capital = None
                if self._capital_balance_provider is not None:
                    ref_capital = await self._capital_balance_provider()
                _eval_kwargs = dict(
                    strategy=strategy,
                    proposed_usd=float(profit_payload.get("gross_profit_usd") or 0.0),
                    expected_net_profit_usd=float(profit_payload.get("net_profit_usd") or 0.0),
                )
                # Only pass live-derived reference capital when a provider is
                # wired (keeps fakes/other callers unaffected; real allocator
                # already fails closed when it is absent/None).
                if self._capital_balance_provider is not None:
                    _eval_kwargs["reference_capital_usd"] = ref_capital
                policy = await self._alloc.evaluate(**_eval_kwargs)
                _pol = (policy if isinstance(policy, dict)
                        else policy.to_dict() if hasattr(policy, "to_dict")
                        else {})
                binding = _pol.get("binding_constraint")
                if _pol and not _pol.get("approved", True):
                    if binding == "wallet_balance_unavailable":
                        # No live balance wired → cannot size; informational only
                        # (execution stays gated elsewhere; real caps still deny).
                        reasons.append("capital_info:wallet_balance_unavailable")
                    else:
                        return StageOutcome(
                            stage="policy", ok=False,
                            detail=f"capital policy denied: {binding}",
                            payload={"decision": "deny", "engine": "capital",
                                     "reasons": _pol.get("reasons", []),
                                     "capital": _pol},
                        )
                else:
                    reasons.append(f"capital_ok:{binding if _pol else 'no-policy'}")
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
                confirm=self._auto_confirm,
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
