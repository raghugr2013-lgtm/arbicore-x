"""H09 (P1 Batch 2) — candidate-bound simulation contract, fail-closed.

A genuine candidate simulation must bind ALL of the evidence that makes a result
specific to one candidate on one chain at one block. Infrastructure availability
(an Anvil node up, a simulator object present, a boolean "ok") is NOT a PASS.

This module defines the binding contract + a fail-closed evaluator. It performs
NO RPC, NO fork, NO signing — it only decides whether a supplied simulation
RESULT may be treated as a candidate-bound SIMULATION_CERTIFIED signal. The exact
fork/state-override simulator that produces a certifying result runs on the VPS;
until such a result exists, this evaluator denies (which is correct).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from arbicore.certification.evidence_tiers import (
    EvidenceTier, is_certifying_sim_method,
)

# Every field that MUST be bound for a candidate simulation to mean anything.
REQUIRED_BINDING_FIELDS = (
    "chain", "block_number", "token", "token_decimals", "exact_input_wei",
    "route", "calldata", "liquidity_state", "economics",
    "executor_address", "receiver_version",
)


@dataclass(frozen=True)
class CandidateSimulationBinding:
    chain: Optional[str] = None
    block_number: Optional[int] = None
    token: Optional[str] = None
    token_decimals: Optional[int] = None
    exact_input_wei: Optional[int] = None
    route: Optional[List[Any]] = None
    calldata: Optional[str] = None
    liquidity_state: Optional[Dict[str, Any]] = None
    economics: Optional[Dict[str, Any]] = None
    executor_address: Optional[str] = None
    receiver_version: Optional[str] = None

    def missing_fields(self) -> List[str]:
        """Bound fields that are absent / empty (fail-closed check)."""
        missing: List[str] = []
        for name in REQUIRED_BINDING_FIELDS:
            v = getattr(self, name, None)
            if v is None:
                missing.append(name)
            elif isinstance(v, (str, list, dict)) and len(v) == 0:
                missing.append(name)
            elif name == "exact_input_wei" and isinstance(v, int) and v <= 0:
                missing.append(name)
            elif name == "receiver_version" and str(v).strip().lower() in (
                    "", "unversioned"):
                missing.append(name)
        return missing

    def is_complete(self) -> bool:
        return not self.missing_fields()


def evaluate_candidate_simulation(
    binding: CandidateSimulationBinding,
    sim_result: Any,
) -> Dict[str, Any]:
    """Decide whether ``sim_result`` certifies ``binding``. FAIL CLOSED.

    Certified (tier=SIMULATION_CERTIFIED) ONLY when ALL hold:
      1. the binding is complete (every REQUIRED_BINDING_FIELDS present);
      2. the simulation method is an EXACT candidate-bound method (M01);
      3. sim_result.ok is True;
      4. the simulated chain equals the bound chain.
    Otherwise: not certified, tier<=EXECUTION_CAPABLE, with explicit reasons.
    """
    reasons: List[str] = []

    missing = binding.missing_fields()
    if missing:
        reasons.append(f"incomplete_binding:{','.join(missing)}")

    method = getattr(sim_result, "method", None)
    ok = bool(getattr(sim_result, "ok", False))
    sim_chain = getattr(sim_result, "chain", None)

    if not is_certifying_sim_method(method):
        reasons.append(
            f"non_certifying_sim_method:{method!r} "
            "(noop/symbolic/paper/heuristic/infra never certifies)")
    if not ok:
        reasons.append("simulation_not_ok")
    if binding.chain is not None and sim_chain is not None and \
            str(sim_chain).lower() != str(binding.chain).lower():
        reasons.append(
            f"chain_mismatch:sim={sim_chain!r}!=bound={binding.chain!r}")

    certified = not reasons
    tier = (EvidenceTier.SIMULATION_CERTIFIED if certified
            else (EvidenceTier.EXECUTION_CAPABLE if ok else EvidenceTier.UNKNOWN))
    return {
        "certified": certified,
        "tier": tier.name,
        "denied_reasons": reasons,
        "binding_complete": not missing,
        "sim_method": method,
        "note": ("candidate-bound simulation certified"
                 if certified else
                 "NOT simulation-certified — fail closed (see denied_reasons)"),
    }


__all__ = [
    "REQUIRED_BINDING_FIELDS", "CandidateSimulationBinding",
    "evaluate_candidate_simulation",
]
