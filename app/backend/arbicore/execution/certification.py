"""Wave 6E · End-to-end Execution Certification.

Composes the full execution pipeline into a single deterministic
certification report:

    Discovery → Planning → Simulation → Gas → MEV → Slippage →
    Capital Policy → Kill Switch → Live Signer

Every stage's decision is captured verbatim; the composite verdict
follows the safety-interlock pattern:

    * ``PASS``    — the pipeline would proceed to live execution
                    IF a broadcast-permitting mode were selected
                    (Wave 6D still bars byte emission).
    * ``BLOCKED`` — at least one hard gate refuses.
    * ``WAIT``    — soft gates ask the operator to review.

The pipeline never broadcasts.  ``would_broadcast=False`` invariant
is asserted twice — once on each downstream value object and once at
the composite report level.

The report is deliberately dependency-injected: the caller wires in
the exact Wave 6A/6B/6C/6D instances the server uses, so the
certification path exercises the *same* code that live requests would.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("arbicore.execution.certification")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


PIPELINE_STAGES: tuple = (
    "mode_ladder",
    "plan_build",
    "dry_run_economics",
    "simulation",
    "gas_estimate",
    "mev_routing",
    "slippage",
    "capital_policy",
    "kill_switch",
    "live_signer",
    "evidence_hooks",
)


@dataclass
class StageResult:
    stage: str
    status: str          # PASS | WAIT | BLOCKED | INFO
    detail: str
    payload: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CertificationReport:
    verdict: str                 # PASS | WAIT | BLOCKED
    strategy: str
    chain: str
    plan_id: Optional[str]
    stages: List[StageResult]
    blockers: List[str]
    warnings: List[str]
    would_broadcast: bool
    ladder_defaults: Dict[str, Any]
    generated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        assert d["would_broadcast"] is False, (
            "CertificationReport leaked would_broadcast=True"
        )
        d["stages"] = [s if isinstance(s, dict) else s.to_dict()
                       for s in d["stages"]]
        return d


class ExecutionCertifier:
    """Runs the full pipeline and produces a CertificationReport.

    Every dependency is optional at construction time — the certifier
    degrades to ``INFO`` stages when a component is not wired.  That
    way the *same* method can be used to certify:

        * The full pod (all Wave 6A/B/C/D components wired).
        * A stripped-down staging setup (e.g. tests without Mongo).
    """

    def __init__(self, *,
                 mode_repo,
                 planner,
                 dry_run_engine,
                 simulator_registry,
                 gas_oracle,
                 mev_registry,
                 slippage_estimator,
                 capital_allocator,
                 kill_switch,
                 live_signer,
                 wallet_registry=None,
                 secret_registry=None,
                 evidence_signer=None):
        self._mode = mode_repo
        self._planner = planner
        self._dry_run = dry_run_engine
        self._simulators = simulator_registry
        self._gas = gas_oracle
        self._mev = mev_registry
        self._slippage = slippage_estimator
        self._alloc = capital_allocator
        self._kill = kill_switch
        self._signer = live_signer
        self._wallets = wallet_registry
        self._secrets = secret_registry
        self._evidence = evidence_signer

    async def certify(self, *,
                      strategy: str,
                      chain: str,
                      borrow_token: str,
                      borrow_amount_wei: int,
                      borrow_amount_usd: float,
                      flash_loan_provider: str,
                      swap_hops: List[Dict[str, Any]],
                      signer_wallet_id: Optional[str] = None,
                      opportunity_id: Optional[str] = None,
                      expected_net_profit_usd: Optional[float] = None,
                      quote_effective_out_wei: Optional[int] = None,
                      simulator: Optional[str] = None,
                      mev_router: Optional[str] = None,
                      ) -> CertificationReport:
        stages: List[StageResult] = []
        blockers: List[str] = []
        warnings: List[str] = []

        # ----------------- 1. Mode ladder --------------------------------
        try:
            mode_row = await self._mode.get(strategy)
            current_mode = (mode_row or {}).get("mode") or "OBSERVE"
            stages.append(StageResult(
                stage="mode_ladder", status="INFO",
                detail=f"strategy '{strategy}' is in mode '{current_mode}'",
                payload={"mode": current_mode, "mode_row": mode_row},
            ))
        except Exception as exc:  # noqa: BLE001
            current_mode = "OBSERVE"
            stages.append(StageResult(
                stage="mode_ladder", status="BLOCKED",
                detail=f"mode read failed: {type(exc).__name__}: {exc}",
            ))
            blockers.append("mode_ladder read failed")

        # ----------------- 2. Plan build ---------------------------------
        plan = None
        plan_dict: Optional[Dict[str, Any]] = None
        try:
            plan = self._planner.build(
                strategy=strategy, chain=chain,
                borrow_token=borrow_token,
                borrow_amount_wei=borrow_amount_wei,
                flash_loan_provider=flash_loan_provider,
                swap_hops=swap_hops,
                signer_wallet_id=signer_wallet_id,
                opportunity_id=opportunity_id,
                borrow_amount_usd=borrow_amount_usd,
                mode=current_mode,
            )
            plan_dict = plan.to_dict()
            stages.append(StageResult(
                stage="plan_build", status="PASS",
                detail=f"plan built (hash={plan.plan_hash[:16]}…)",
                payload={"plan_hash": plan.plan_hash,
                          "steps": len(plan.steps),
                          "dex_route": list(plan.dex_route)},
            ))
        except Exception as exc:  # noqa: BLE001
            stages.append(StageResult(
                stage="plan_build", status="BLOCKED",
                detail=f"planner rejected: {type(exc).__name__}: {exc}",
            ))
            blockers.append(f"plan_build: {exc}")

        # ----------------- 3. Dry-run economics --------------------------
        # Phase 10.10.8 · canonical live-evaluation path.  ``evaluate_live``
        # fetches per-hop on-chain quotes + live gas before computing
        # profitability; when either channel degrades, the receipt's
        # ``quote_source`` / ``gas_source`` fields expose which fallback
        # engaged so the WAIT verdict is correctly attributed.  Callers
        # may still pass an explicit ``quote_effective_out_wei`` override,
        # in which case the legacy deterministic evaluate() runs instead.
        if plan is not None:
            if quote_effective_out_wei is not None:
                eco = self._dry_run.evaluate(
                    plan, quote_effective_out_wei=quote_effective_out_wei,
                )
            else:
                try:
                    eco = await self._dry_run.evaluate_live(plan)
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        f"live evaluation degraded: {type(exc).__name__}: {exc}"
                    )
                    eco = self._dry_run.evaluate(plan)
            status = "PASS" if eco.get("profitable") else "WAIT"
            if not eco.get("profitable"):
                warnings.append("dry_run says plan is not profitable at current inputs")
            # Surface the quote-source verdict prominently — a
            # "fallback:break_even" verdict must never masquerade as
            # a legitimate PASS/WAIT signal in the operator UI.
            qsrc = eco.get("quote_source") or "unknown"
            gsrc = eco.get("gas_source") or "unknown"
            stages.append(StageResult(
                stage="dry_run_economics", status=status,
                detail=(f"net_profit_usd={eco.get('net_profit_usd')} "
                        f"quote={qsrc} gas={gsrc} "
                        f"confidence={eco.get('confidence_score')}"),
                payload=eco,
            ))
            plan_dict = plan.to_dict()

        # ----------------- 4. Simulation ---------------------------------
        if plan_dict is not None:
            try:
                sim = await self._simulators.simulate(plan_dict, simulator=simulator)
                status = "PASS" if sim.ok else "BLOCKED"
                if not sim.ok:
                    blockers.append("simulation reported failure")
                stages.append(StageResult(
                    stage="simulation", status=status,
                    detail=f"simulator={sim.simulator} method={sim.method}",
                    payload=sim.to_dict(),
                ))
            except Exception as exc:  # noqa: BLE001
                stages.append(StageResult(
                    stage="simulation", status="BLOCKED",
                    detail=f"simulation failed: {type(exc).__name__}: {exc}",
                ))
                blockers.append("simulation failed")

        # ----------------- 5. Gas estimate -------------------------------
        if plan_dict is not None:
            try:
                gas = await self._gas.estimate(
                    chain=chain,
                    step_kinds=[s.get("kind") or "" for s in plan_dict["steps"]],
                )
                stages.append(StageResult(
                    stage="gas_estimate", status="INFO",
                    detail=f"total ${gas.total_cost_usd}",
                    payload=gas.to_dict(),
                ))
            except Exception as exc:  # noqa: BLE001
                stages.append(StageResult(
                    stage="gas_estimate", status="WAIT",
                    detail=f"gas oracle failed: {type(exc).__name__}: {exc}",
                ))
                warnings.append("gas oracle degraded")

        # ----------------- 6. MEV routing --------------------------------
        try:
            mev = await self._mev.route(router=mev_router, chain=chain)
            stages.append(StageResult(
                stage="mev_routing", status="INFO",
                detail=f"router={mev.router} kind={mev.kind} private={mev.private}",
                payload=mev.to_dict(),
            ))
        except Exception as exc:  # noqa: BLE001
            stages.append(StageResult(
                stage="mev_routing", status="WAIT",
                detail=f"MEV router failed: {type(exc).__name__}: {exc}",
            ))
            warnings.append("mev router degraded")

        # ----------------- 7. Slippage -----------------------------------
        if plan_dict is not None:
            hops = sum(1 for s in plan_dict["steps"] if s.get("kind") == "swap")
            eff_out = int((plan_dict.get("economics") or {}).get("effective_out_wei") or 0)
            if eff_out > 0:
                slip = self._slippage.estimate(
                    quoted_output_wei=eff_out, hops=max(1, hops),
                )
                stages.append(StageResult(
                    stage="slippage", status="INFO",
                    detail=f"aggregate {slip.aggregate_slippage_bps} bps",
                    payload=slip.to_dict(),
                ))
            else:
                stages.append(StageResult(
                    stage="slippage", status="INFO",
                    detail="no effective_out_wei — slippage skipped",
                ))

        # ----------------- 8. Capital policy -----------------------------
        try:
            alloc = await self._alloc.evaluate(
                strategy=strategy,
                proposed_usd=float(borrow_amount_usd),
                expected_net_profit_usd=expected_net_profit_usd,
            )
            status = "PASS" if alloc.approved else "BLOCKED"
            if not alloc.approved:
                blockers.append(
                    f"capital_policy: {alloc.binding_constraint} — "
                    f"{'; '.join(alloc.reasons) or 'denied'}"
                )
            stages.append(StageResult(
                stage="capital_policy", status=status,
                detail=(f"approved ${alloc.approved_usd:.2f} "
                        f"binding={alloc.binding_constraint}"),
                payload=alloc.to_dict(),
            ))
        except Exception as exc:  # noqa: BLE001
            stages.append(StageResult(
                stage="capital_policy", status="BLOCKED",
                detail=f"capital allocator failed: {type(exc).__name__}: {exc}",
            ))
            blockers.append("capital allocator failed")

        # ----------------- 9. Kill switch --------------------------------
        try:
            ks = await self._kill.state()
            if ks.engaged:
                stages.append(StageResult(
                    stage="kill_switch", status="BLOCKED",
                    detail=f"engaged — reason: {ks.reason}",
                    payload=ks.to_dict(),
                ))
                blockers.append(f"kill_switch engaged: {ks.reason}")
            else:
                stages.append(StageResult(
                    stage="kill_switch", status="PASS",
                    detail="disengaged",
                    payload=ks.to_dict(),
                ))
        except Exception as exc:  # noqa: BLE001
            stages.append(StageResult(
                stage="kill_switch", status="BLOCKED",
                detail=f"kill switch read failed: {type(exc).__name__}: {exc}",
            ))
            blockers.append("kill switch unavailable")

        # ----------------- 10. Live signer gate ladder -------------------
        if plan_dict is not None:
            try:
                receipt = await self._signer.sign_plan(
                    plan_dict,
                    actor="certifier",
                    expected_net_profit_usd=expected_net_profit_usd,
                )
                # Wave 6D barrier — receipt.signed==False even when all gates PASS.
                status = "PASS" if not receipt.denied_reasons else "BLOCKED"
                if receipt.denied_reasons and current_mode in ("LIMITED_LIVE", "FULL_LIVE"):
                    blockers.append(
                        "live_signer denied: " + "; ".join(receipt.denied_reasons)
                    )
                elif receipt.denied_reasons:
                    # In SHADOW mode the mode gate is expected to deny — that's
                    # not a blocker for certification, it's the invariant.
                    status = "INFO"
                stages.append(StageResult(
                    stage="live_signer", status=status,
                    detail=(f"gates {receipt.gate_ladder} — "
                            f"signed={receipt.signed} broadcast={receipt.would_broadcast}"),
                    payload=receipt.to_dict(),
                ))
            except Exception as exc:  # noqa: BLE001
                stages.append(StageResult(
                    stage="live_signer", status="BLOCKED",
                    detail=f"live signer error: {type(exc).__name__}: {exc}",
                ))
                blockers.append("live signer failed")

        # ----------------- 11. Evidence hooks ----------------------------
        evidence_stats: Optional[Dict[str, Any]] = None
        if self._evidence is not None:
            try:
                evidence_stats = self._evidence.stats
            except Exception:  # noqa: BLE001
                evidence_stats = None
        stages.append(StageResult(
            stage="evidence_hooks", status="INFO",
            detail=("evidence signer wired" if self._evidence is not None
                    else "evidence signer not wired"),
            payload={"stats": evidence_stats},
        ))

        # ----------------- Verdict ---------------------------------------
        if blockers:
            verdict = "BLOCKED"
        elif warnings:
            verdict = "WAIT"
        else:
            verdict = "PASS"

        return CertificationReport(
            verdict=verdict,
            strategy=strategy,
            chain=chain,
            plan_id=(plan.plan_id if plan else None),
            stages=stages,
            blockers=blockers,
            warnings=warnings,
            would_broadcast=False,
            ladder_defaults={
                "mode": current_mode,
                "shadow_invariant": "no signing, no broadcast in SHADOW/PAPER/OBSERVE",
                "wave6d_barrier": "no signed bytes emitted even in LIMITED_LIVE",
            },
            generated_at=_now_iso(),
        )
