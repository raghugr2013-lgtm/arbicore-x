"""Terminal-outcome classifier.

The pipeline runs its stages, records per-stage results, then calls
:func:`classify_outcome` exactly ONCE at completion.  The classifier
maps the (action, first-failed-stage, reason) triple onto one of the
eight canonical :class:`PaperOutcome` values.

Precedence (matches the pipeline's own gate order):
    1. If any stage produced ``failure_reason``, use the *first*
       failing stage's name to select the outcome.
    2. Otherwise, dispatch on the pipeline's ``action`` verb
       (shadow / broadcast / observe / reject / deny).
"""

from __future__ import annotations

from typing import Iterable, List, Mapping, Tuple

from .outcomes import PaperOutcome, TERMINAL_REASON_TO_OUTCOME


# Map failed-stage name → canonical outcome. Kept as a lookup table so
# the ordering is data-driven and easy to review.
_STAGE_FAILURE_TO_OUTCOME: Mapping[str, PaperOutcome] = {
    "quote":              PaperOutcome.ROUTE_FAILURE,
    "route":              PaperOutcome.ROUTE_FAILURE,
    "gas":                PaperOutcome.GAS_FAILURE,
    "profit":             PaperOutcome.UNPROFITABLE,
    "policy":             PaperOutcome.RISK_FAILURE,
    "certification":      PaperOutcome.RISK_FAILURE,
    "liquidity":          PaperOutcome.LIQUIDITY_FAILURE,
    "simulate":           PaperOutcome.SIMULATION_FAILURE,
    "broadcast":          PaperOutcome.SIMULATION_FAILURE,
    "observe_only":       PaperOutcome.REJECTED,
}


def _first_failed_stage(stages: Iterable[Mapping[str, object]]
                         ) -> Tuple[str, str]:
    """Return ``(stage_name, failure_reason)`` for the FIRST failed
    stage in ``stages``, or ``("", "")`` if all stages succeeded."""
    for st in stages:
        ok = st.get("ok")
        if ok is False:
            name = str(st.get("stage") or "")
            reason = (str(st.get("failure_reason") or st.get("detail") or "")
                       .strip())
            return name, reason
    return "", ""


def classify_outcome(*,
                      action: str,
                      stages: List[Mapping[str, object]],
                      generic_reason: str = "",
                      ) -> Tuple[PaperOutcome, str]:
    """Return ``(PaperOutcome, human_reason)`` for a completed pipeline.

    ``action`` is the pipeline's terminal verb — ``"broadcast"``,
    ``"shadow"``, ``"observe"``, ``"reject"``, ``"deny"``.
    ``stages`` is the ordered list of stage-metric dicts (see
    :class:`StageMetric`) — the FIRST failing stage's name determines
    the failure outcome.
    ``generic_reason`` is the human string the pipeline attached to
    ``PipelineResult.reason``; used when no stage failed but the
    pipeline still finished with a non-``broadcast`` verdict.
    """
    action = (action or "").lower()

    # (1) Fast path — every stage succeeded: honour the action verb.
    failed_stage, failed_reason = _first_failed_stage(stages)
    if not failed_stage:
        outcome = TERMINAL_REASON_TO_OUTCOME.get(action, PaperOutcome.REJECTED)
        reason = (generic_reason
                  or (f"pipeline finished with action={action!r}"
                      if action else "pipeline finished with no action"))
        return outcome, reason

    # (2) A stage failed — classify by the FIRST failure name.
    outcome = _STAGE_FAILURE_TO_OUTCOME.get(
        failed_stage.lower(), PaperOutcome.REJECTED
    )
    reason = (failed_reason
              or generic_reason
              or f"stage {failed_stage!r} failed")
    return outcome, reason
