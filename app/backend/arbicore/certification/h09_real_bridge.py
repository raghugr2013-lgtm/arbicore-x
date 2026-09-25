"""Certification-only H09 bridge to the real atomic simulator.

Safety:
- exact canonical evidence provenance only
- no latest/timestamp fallback
- no signing
- no broadcasting
- no production execution
- failed/incomplete evidence fails closed
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import os

from .candidate_simulation import (
    CandidateSimulationBinding,
    evaluate_candidate_simulation,
)
from .h09_bridge import resolve_candidate_binding


async def simulate_candidate_binding(
    repo: Any,
    *,
    audit_run_id: str,
    scanner_tick_id: Any,
    candidate_id: str,
    rpc_url: str,
    signer_present: bool,
    from_address: Optional[str] = None,
    sim_factory: Any = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Resolve exact evidence and execute only an eth_call simulation."""

    bundle, binding, diagnostic = await resolve_candidate_binding(
        repo,
        audit_run_id=audit_run_id,
        scanner_tick_id=scanner_tick_id,
        candidate_id=candidate_id,
    )

    if bundle is None or binding is None or not diagnostic.get("ok"):
        return None, {
            "ok": False,
            "reason": "binding_rejected",
            "binding": diagnostic,
            "signed": False,
            "broadcast": False,
        }

    if not binding.is_complete():
        return None, {
            "ok": False,
            "reason": "incomplete_binding",
            "binding": diagnostic,
            "signed": False,
            "broadcast": False,
        }

    # Import the existing canonical simulator path. Do not duplicate
    # simulation logic here.
    from arbicore.scanners.flash_loan_arbitrage.live_readiness_probes import (
        probe_atomic_simulation,
    )

    plan = bundle.get("execution_plan")
    if not isinstance(plan, dict):
        handoff = bundle.get("b7_execution_handoff")
        plan = (
            handoff.get("execution_plan")
            if isinstance(handoff, dict)
            else {}
        )

    executor = binding.executor_address
    if not executor:
        return None, {
            "ok": False,
            "reason": "missing_executor_address",
            "signed": False,
            "broadcast": False,
        }

    # The simulator receives the exact persisted B7 calldata and exact
    # quote block. It is eth_call-only.
    sim = await probe_atomic_simulation(
        bundle=bundle,
        executor_address=executor,
        rpc_url=rpc_url,
        signer_present=signer_present,
        from_address=from_address,
        block_tag=hex(int(binding.block_number)),
        sim_factory=sim_factory,
    )

    result = dict(sim or {})
    result["signed"] = False
    result["broadcast"] = False
    result["simulation_kind"] = result.get(
        "simulation_kind", "onchain_eth_call"
    )

    # CandidateSimulation evaluator remains authoritative for certification.
    # The canonical atomic simulator returns a dict, while the evaluator
    # consumes the SimulationResult-style attribute contract. Adapt ONLY at
    # this certification boundary; do not alter the canonical simulator.
    from types import SimpleNamespace

    sim_contract = SimpleNamespace(
        method=os.environ.get("ARBICORE_SIM_METHOD", "").strip(),
        ok=bool(result.get("passed") is True),
        chain=str(binding.chain) if binding.chain is not None else None,
    )

    cert = evaluate_candidate_simulation(
        binding,
        sim_contract,
    )

    certified = bool(
        cert.get("certified") is True
        and cert.get("tier") == "SIMULATION_CERTIFIED"
    )

    return result, {
        "ok": certified,
        "certification": cert,
        "binding": diagnostic,
        "signed": False,
        "broadcast": False,
    }


__all__ = ["simulate_candidate_binding"]
