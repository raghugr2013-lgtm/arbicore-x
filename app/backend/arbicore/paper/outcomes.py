"""Canonical Paper Validation outcome vocabulary (v2.11.8).

Every opportunity that transits the OpportunityPipeline finishes in
exactly ONE of these eight outcomes.  The classification happens once,
at pipeline completion — never mid-flight.  Intermediate stage results
(``ok`` / ``not ok``) feed the terminal classifier but do not by
themselves constitute the outcome.
"""

from __future__ import annotations

from enum import Enum


class PaperOutcome(str, Enum):
    """Terminal Paper-Validation outcome for one opportunity.

    Membership is a **closed set**.  New outcomes require an ADR — the
    Shadow Certification + Limited Live promotion gates key off these
    exact identifiers.
    """

    #: Every stage succeeded; the pipeline would have broadcast (or did
    #: broadcast, if in LIMITED_LIVE / FULL_LIVE).
    EXECUTABLE          = "EXECUTABLE"

    #: A generic "not attempted" verdict — for example OBSERVE-mode
    #: opportunities or missing ``opportunity_id``.  Distinct from the
    #: seven *failure* outcomes so operators can filter noise from
    #: signal.
    REJECTED            = "REJECTED"

    #: Expected net profit after gas + flash-loan premium <= 0.
    UNPROFITABLE        = "UNPROFITABLE"

    #: A liquidity-depth check found insufficient on-chain reserves for
    #: the intended borrow size or hop leg.
    LIQUIDITY_FAILURE   = "LIQUIDITY_FAILURE"

    #: Gas-estimation stage failed (RPC unreachable, malformed inputs,
    #: negative gas estimate, etc.).
    GAS_FAILURE         = "GAS_FAILURE"

    #: Route-generation / quote stage could not produce a valid hop set
    #: (no swap_hops, unknown DEX, disconnected graph).
    ROUTE_FAILURE       = "ROUTE_FAILURE"

    #: Risk / policy layer rejected the opportunity — kill-switch armed,
    #: capital policy denied, certification failed, mode gate closed.
    RISK_FAILURE        = "RISK_FAILURE"

    #: The Simulation stage's ``eth_call`` (or fallback heuristic)
    #: reverted on the executor call.  Introduced in Slice B; Slice A
    #: reserves the vocabulary but no stage produces it yet.
    SIMULATION_FAILURE  = "SIMULATION_FAILURE"

    @classmethod
    def all_values(cls) -> list[str]:
        return [m.value for m in cls]


# Mapping from the pipeline's textual "action" verdicts + stage names
# to the canonical PaperOutcome. The classifier consults this table
# alongside the failed-stage name; the table below is the *tie-breaker*
# when no failed stage is available.
TERMINAL_REASON_TO_OUTCOME: dict[str, PaperOutcome] = {
    "observe":          PaperOutcome.REJECTED,
    "shadow":           PaperOutcome.EXECUTABLE,
    "broadcast":        PaperOutcome.EXECUTABLE,
    "deny":             PaperOutcome.RISK_FAILURE,
    "reject":           PaperOutcome.REJECTED,   # generic reject; classifier overrides via failed stage
}
