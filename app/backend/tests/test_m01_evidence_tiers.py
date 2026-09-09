"""P1/M01+M06 regression — canonical evidence tiers and the anti-fabrication
rule that heuristic/mocked simulation can never read as certification.
Offline / deterministic.
"""
from __future__ import annotations

import asyncio

from arbicore.certification.evidence_tiers import (
    EvidenceTier, NON_CERTIFYING_SIM_METHODS, is_certifying_sim_method,
    sim_evidence_tier,
)
from arbicore.execution.simulation import NoopSimulator


def test_tier_ordering_strict():
    order = [EvidenceTier.UNKNOWN, EvidenceTier.SYMBOLIC, EvidenceTier.CONNECTED,
             EvidenceTier.DISCOVERED, EvidenceTier.QUOTED,
             EvidenceTier.ROUTE_CONSTRUCTABLE, EvidenceTier.EXECUTION_CAPABLE,
             EvidenceTier.CANDIDATE_CERTIFIED, EvidenceTier.SIMULATION_CERTIFIED,
             EvidenceTier.RUNTIME_CERTIFIED, EvidenceTier.LIMITED_LIVE_ELIGIBLE]
    assert [int(x) for x in order] == list(range(len(order)))


def test_lower_tiers_never_reach_certified():
    # M01 invariant: none of the pre-execution tiers equal/exceed simulation cert.
    for t in (EvidenceTier.SYMBOLIC, EvidenceTier.CONNECTED,
              EvidenceTier.DISCOVERED, EvidenceTier.QUOTED,
              EvidenceTier.ROUTE_CONSTRUCTABLE, EvidenceTier.EXECUTION_CAPABLE):
        assert t < EvidenceTier.SIMULATION_CERTIFIED
        assert t < EvidenceTier.RUNTIME_CERTIFIED
        assert t < EvidenceTier.LIMITED_LIVE_ELIGIBLE


def test_noop_symbolic_paper_are_non_certifying():
    for m in ("noop", "symbolic", "estimate_symbolic", "paper", "heuristic",
              "capability", "availability", "", None):
        assert is_certifying_sim_method(m) is False
    assert "noop" in NON_CERTIFYING_SIM_METHODS


def test_only_exact_candidate_bound_methods_certify():
    for m in ("atomic_exact", "atomic_state_override", "fork_exact", "exact_call"):
        assert is_certifying_sim_method(m) is True


def test_sim_evidence_tier_never_certifies_heuristic_even_if_ok():
    # ok=True + noop must NOT be SIMULATION_CERTIFIED (the exact H09/M01 defect).
    assert sim_evidence_tier("noop", True) == EvidenceTier.EXECUTION_CAPABLE
    assert sim_evidence_tier("noop", True) < EvidenceTier.SIMULATION_CERTIFIED
    # exact + ok certifies; exact + not-ok does not.
    assert sim_evidence_tier("atomic_exact", True) == EvidenceTier.SIMULATION_CERTIFIED
    assert sim_evidence_tier("atomic_exact", False) == EvidenceTier.UNKNOWN


def test_noop_simulator_result_method_is_non_certifying():
    sim = asyncio.new_event_loop().run_until_complete(
        NoopSimulator().simulate({"chain": "base", "steps": [
            {"step_index": 0, "kind": "swap", "provider": "uniswap_v3"}]}))
    assert sim.ok is True                     # heuristic result IS ok…
    assert is_certifying_sim_method(sim.method) is False  # …but NEVER certifying
    assert sim_evidence_tier(sim.method, sim.ok) < EvidenceTier.SIMULATION_CERTIFIED
