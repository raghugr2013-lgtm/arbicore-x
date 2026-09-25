"""H09 isolated bridge: canonical flash-loan evidence -> candidate binding.

Certification-only adapter.

Safety invariants:
- exact audit_run_id + scanner_tick_id + candidate_id provenance
- no timestamp/latest fallback
- no fabricated binding fields
- no signing
- no broadcasting
- no production execution
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from .candidate_simulation import CandidateSimulationBinding


def _execution_plan(bundle: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the persisted B7 execution plan without inventing data."""
    plan = bundle.get("execution_plan")
    if isinstance(plan, dict):
        return plan

    handoff = bundle.get("b7_execution_handoff")
    if isinstance(handoff, dict):
        plan = handoff.get("execution_plan")
        if isinstance(plan, dict):
            return plan

    return {}


def _quotes(bundle: Dict[str, Any]) -> Dict[str, Any]:
    value = bundle.get("quotes")
    return value if isinstance(value, dict) else {}


def _liquidity(bundle: Dict[str, Any]) -> Dict[str, Any]:
    value = bundle.get("liquidity")
    return value if isinstance(value, dict) else {}


def _economics(bundle: Dict[str, Any]) -> Dict[str, Any]:
    value = bundle.get("economics")
    return value if isinstance(value, dict) else {}


def _quote_block(bundle: Dict[str, Any], quotes: Dict[str, Any],
                 plan: Dict[str, Any]) -> Optional[int]:
    for obj in (quotes, plan, bundle):
        for key in ("quote_block", "quoted_block", "block_number"):
            value = obj.get(key)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None
    return None


def build_candidate_simulation_binding(
    bundle: Dict[str, Any],
) -> Tuple[Optional[CandidateSimulationBinding], Dict[str, Any]]:
    """Build a complete H09 binding from ONE persisted canonical evidence bundle.

    Missing or ambiguous evidence is returned as a fail-closed diagnostic.
    """
    if not isinstance(bundle, dict):
        return None, {"ok": False, "reason": "bundle_not_dict"}

    plan = _execution_plan(bundle)
    quotes = _quotes(bundle)
    liquidity = _liquidity(bundle)
    economics = _economics(bundle)

    chain = bundle.get("chain")
    token = plan.get("token") or bundle.get("borrow_token")
    decimals = (
        quotes.get("token_decimals")
        or bundle.get("token_decimals")
        or plan.get("token_decimals")
    )
    exact_input = (
        plan.get("exact_input_wei")
        or quotes.get("quoted_amount_in_wei")
        or bundle.get("exact_input_wei")
    )
    route = plan.get("route") or bundle.get("route")
    calldata = (
        plan.get("executor_entry_calldata")
        or plan.get("calldata")
        or bundle.get("executor_entry_calldata")
    )
    executor = plan.get("executor_address") or bundle.get("executor_address")
    receiver_version = (
        plan.get("receiver_version") or bundle.get("receiver_version")
    )
    block_number = _quote_block(bundle, quotes, plan)

    binding = CandidateSimulationBinding(
        chain=str(chain).lower() if chain is not None else None,
        block_number=block_number,
        token=str(token) if token is not None else None,
        token_decimals=int(decimals) if decimals is not None else None,
        exact_input_wei=int(exact_input) if exact_input is not None else None,
        route=route if isinstance(route, list) else None,
        calldata=str(calldata) if calldata is not None else None,
        liquidity_state=liquidity or None,
        economics=economics or None,
        executor_address=str(executor) if executor is not None else None,
        receiver_version=(
            str(receiver_version) if receiver_version is not None else None
        ),
    )

    missing = binding.missing_fields()
    if missing:
        return binding, {
            "ok": False,
            "reason": "incomplete_binding",
            "missing_fields": missing,
        }

    return binding, {
        "ok": True,
        "reason": "complete_candidate_binding",
        "candidate_id": bundle.get("candidate_id"),
        "opportunity_id": bundle.get("opportunity_id"),
        "chain": binding.chain,
        "block_number": binding.block_number,
    }


async def resolve_candidate_binding(
    repo: Any,
    *,
    audit_run_id: str,
    scanner_tick_id: Any,
    candidate_id: str,
    worker_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[CandidateSimulationBinding], Dict[str, Any]]:
    """Resolve exactly one canonical bundle and construct its H09 binding."""
    if not audit_run_id or scanner_tick_id is None or not candidate_id:
        return None, None, {
            "ok": False,
            "reason": "missing_exact_provenance",
        }

    rows = await repo.find_for_audit(
        audit_run_id=audit_run_id,
        scanner_tick_id=scanner_tick_id,
        candidate_id=candidate_id,
        worker_id=worker_id,
        source_component="flash_loan_arb_verifier",
    )

    if len(rows) != 1:
        return None, None, {
            "ok": False,
            "reason": "expected_exactly_one_bundle",
            "bundle_count": len(rows),
        }

    bundle = rows[0]

    if bundle.get("candidate_id") != candidate_id:
        return None, None, {
            "ok": False,
            "reason": "candidate_identity_mismatch",
        }

    if bundle.get("verification_status") != "CONFIRMED":
        return None, None, {
            "ok": False,
            "reason": "bundle_not_confirmed",
            "verification_status": bundle.get("verification_status"),
        }

    # Never allow audit evidence to certify a broadcast/executed action.
    if bundle.get("broadcast") is True:
        return None, None, {
            "ok": False,
            "reason": "broadcast_evidence_forbidden",
        }

    binding, diagnostic = build_candidate_simulation_binding(bundle)
    return bundle, binding, diagnostic


__all__ = [
    "build_candidate_simulation_binding",
    "resolve_candidate_binding",
]
