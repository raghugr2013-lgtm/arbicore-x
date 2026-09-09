"""Canonical evidence-tier model (P1/M01).

ONE ordered, non-ambiguous ladder of what has actually been established for a
chain / venue / candidate. Every readiness or certification surface must map its
result onto exactly one of these tiers and MUST NOT report a higher tier than
the strongest *positive, candidate-bound* evidence it actually holds.

Hard invariants (M01):
  * CONFIGURED / CONNECTED / DISCOVERED / QUOTED / ROUTE_CONSTRUCTABLE /
    EXECUTION_CAPABLE must NEVER be represented as SIMULATION_CERTIFIED,
    RUNTIME_CERTIFIED or LIMITED_LIVE_ELIGIBLE.
  * A NoopSimulator / symbolic / paper-calldata / heuristic result, an
    environment "GREEN", mere Anvil availability, or any infrastructure-only
    check MUST NOT produce SIMULATION_CERTIFIED or higher. Only an EXACT,
    candidate-bound simulation method may.

This module is pure/deterministic and holds no runtime state.
"""
from __future__ import annotations

from enum import IntEnum


class EvidenceTier(IntEnum):
    """Strictly increasing strength of evidence. Compare with >= / <."""
    UNKNOWN = 0
    SYMBOLIC = 1              # configured / declared only (no live contact)
    CONNECTED = 2            # RPC capability proven (chain-verified endpoint)
    DISCOVERED = 3           # resolver found the pool/route on the target chain
    QUOTED = 4               # every ordered hop has a live quote at the size
    ROUTE_CONSTRUCTABLE = 5  # exact calldata targets a verified deployment
    EXECUTION_CAPABLE = 6    # provider/receiver/router/caller/chain compatible
    CANDIDATE_CERTIFIED = 7  # a specific candidate's evidence is coherently bound
    SIMULATION_CERTIFIED = 8  # exact candidate-bound simulation passed
    RUNTIME_CERTIFIED = 9    # all evidence fresh, persisted, replayable
    LIMITED_LIVE_ELIGIBLE = 10  # + operator approval / mode / caps / final reval


# Simulation "methods" that are HEURISTIC / MOCKED / infra-only. A result whose
# method is in this set can NEVER be SIMULATION_CERTIFIED — it is at most
# informational telemetry.
NON_CERTIFYING_SIM_METHODS = frozenset({
    "noop", "symbolic", "estimate_symbolic", "paper", "heuristic",
    "capability", "capability_self_test", "infra", "availability", "",
})

# Simulation methods that CAN certify — an exact, candidate-bound execution of
# the real route (fork/state-override atomic call against real chain state).
CERTIFYING_SIM_METHODS = frozenset({
    "atomic_exact", "atomic_state_override", "fork_exact", "exact_call",
})


def is_certifying_sim_method(method: object) -> bool:
    """True only for an EXACT candidate-bound simulation method (M01/H09).
    Unknown / heuristic / infra-only methods fail closed (False)."""
    m = str(method or "").strip().lower()
    if not m or m in NON_CERTIFYING_SIM_METHODS:
        return False
    return m in CERTIFYING_SIM_METHODS


def sim_evidence_tier(method: object, ok: object) -> EvidenceTier:
    """Map a simulation result to its honest tier. A non-certifying method (or a
    failed exact sim) never reaches SIMULATION_CERTIFIED."""
    if is_certifying_sim_method(method) and bool(ok):
        return EvidenceTier.SIMULATION_CERTIFIED
    return EvidenceTier.EXECUTION_CAPABLE if bool(ok) else EvidenceTier.UNKNOWN
