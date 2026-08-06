"""Slice A · pipeline.py rewrite — add per-stage timing + evidence persistence.

Idempotent: safe to re-run.  Rewrites only the specific patterns we
target; leaves everything else untouched.
"""
import re

PATH = "/app/app/backend/arbicore/execution/pipeline.py"
with open(PATH, "r") as f:
    src = f.read()

# ---------------------------------------------------------------------
# 1. Insert helper methods just above `# ============  Stage implementations`
# ---------------------------------------------------------------------
HELPER_BLOCK = '''    # =====================================================================
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
                # Simulation backend is populated by Slice B stages; Slice A
                # leaves it None.
                simulation_backend = None,
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
'''

# Replace the "Stage implementations" section header exactly once.
old_header = '    # =====================================================================\n    # Stage implementations\n    # =====================================================================\n'
assert src.count(old_header) == 1, "expected exactly one Stage implementations header"
src = src.replace(old_header, HELPER_BLOCK, 1)

# ---------------------------------------------------------------------
# 2. Wrap each `result.stages.append(<x>.to_dict())` with timing capture.
#    We insert the perf capture two lines above the append, then rewrite
#    the append line itself.  The pattern per stage is:
#
#        <indent>_t_perf = time.perf_counter(); _t_iso = _iso_now()
#        <existing stage call — untouched>
#        <indent>result.stages.append(self._stamp(<var>, _t_perf, _t_iso))
#
# The seven sites we target are:
#     observe_only, quote, gas, profit, policy, certification, broadcast
# ---------------------------------------------------------------------

# 2a. observe_only literal
_before = '''        # OBSERVE — record and stop.
        if mode not in ANALYSIS_MODES:
            result.action = "observe"
            result.reason = "mode is OBSERVE — no analysis"
            result.stages.append(StageOutcome(
                stage="observe_only", ok=True,
                detail="OBSERVE mode records the opportunity and skips downstream stages.",
            ).to_dict())
            return result'''
_after = '''        # OBSERVE — record and stop.
        if mode not in ANALYSIS_MODES:
            result.action = "observe"
            result.reason = "mode is OBSERVE — no analysis"
            _t_perf = time.perf_counter(); _t_iso = _iso_now()
            _obs = StageOutcome(
                stage="observe_only", ok=True,
                detail="OBSERVE mode records the opportunity and skips downstream stages.",
            )
            result.stages.append(self._stamp(_obs, _t_perf, _t_iso))
            return result'''
assert _before in src, "observe_only pattern not found"
src = src.replace(_before, _after, 1)

# 2b. quote / gas / profit / policy / certification stage-append pattern.
# Each has the form:
#     <var>_outcome = <expr>
#     result.stages.append(<var>_outcome.to_dict())
# and we prefix with a perf/iso capture, replace the append.
_pairs = [
    ("quote_outcome = self._extract_quote(opp)",
     "result.stages.append(quote_outcome.to_dict())"),
    ("gas_outcome = self._extract_gas(opp)",
     "result.stages.append(gas_outcome.to_dict())"),
    ("profit_outcome = self._compute_profit(opp, gas_outcome.payload)",
     "result.stages.append(profit_outcome.to_dict())"),
    ("policy_outcome = await self._policy_check(strategy, mode, profit_outcome.payload)",
     "result.stages.append(policy_outcome.to_dict())"),
    ("cert_outcome = await self._certify(opp, strategy)",
     "result.stages.append(cert_outcome.to_dict())"),
    ("broadcast_outcome = await self._broadcast(opp, strategy, result)",
     "result.stages.append(broadcast_outcome.to_dict())"),
]
for call_line, append_line in _pairs:
    old = f"        {call_line}\n        {append_line}\n"
    var = call_line.split(' ', 1)[0]
    new = (
        f"        _t_perf = time.perf_counter(); _t_iso = _iso_now()\n"
        f"        {call_line}\n"
        f"        result.stages.append(self._stamp({var}, _t_perf, _t_iso))\n"
    )
    assert old in src, f"pattern for {var!r} not found"
    src = src.replace(old, new, 1)

with open(PATH, "w") as f:
    f.write(src)
print("pipeline.py rewrite OK")
