"""Adapter: accepted Strategy IR candidate → an UNPROVEN opportunity hypothesis
for the EXISTING ArbiCore discovery/economics/simulation pipeline.

The adapter deliberately emits a hypothesis that CANNOT pass the existing
simulation gate on its own: no real quote, no calldata, no modelled repayment,
no gas — so it fails closed until the real downstream pipeline independently
fetches live data and re-validates. The adapter creates NO execution authority.
"""
from typing import Any, Dict

from .schema import StrategyIR, StrategyIRValidationError


def candidate_to_opportunity_hypothesis(ir: StrategyIR) -> Dict[str, Any]:
    """Map a validated IR to an opportunity-shaped dict tagged as a candidate.

    Fields are chosen so the existing `decide_opportunity` sim gate rejects it
    (quote UNAVAILABLE, no calldata, repayment not modelled, gas unknown). Any
    route_hints are passed as *hints only* — the pipeline must re-derive real
    routes/quotes. No signer/calldata/mode/kill/broadcast field is ever set.

    Restricted/proprietary material is NOT eligible for this path (F1): it is
    quarantined until an admin explicitly clears it.
    """
    if ir.is_restricted():
        raise StrategyIRValidationError(
            "restricted/proprietary strategy is quarantined and not eligible for "
            "the adapter/preview path until cleared by an admin")
    constraints = ir.constraints or {}
    return {
        "opportunity_id": f"stratcand:{ir.strategy_fingerprint}:{ir.strategy_version}",
        "source": "STRATEGY_IR_CANDIDATE",
        "strategy_id": ir.strategy_id,
        "strategy_fingerprint": ir.strategy_fingerprint,
        "strategy_version": ir.strategy_version,
        "strategy_type": ir.strategy_type,
        # F2: identity-tagged, alpha-bearing output is confidential.
        "confidential": True,
        # --- provenance: NOT real; a hypothesis awaiting live validation ---
        "quote_status": "UNAVAILABLE",
        "provenance": "STRATEGY_IR_CANDIDATE",
        # --- hints only (data), never authoritative routes ---
        "route_hints": ir.route_hints or [],
        "hops": [],                       # pipeline must derive real hops
        "max_hops": int(constraints.get("max_hops", 3)),
        # --- economics unknown until measured (fail-closed) ---
        "gross_spread_bps": None,
        "pool_liquidity_usd": None,
        "gas_cost_usd": 0.0,              # unknown ⇒ gas_ok False downstream
        "flash_loan_fee_bps": None,
        # --- simulation cannot pass on a hypothesis ---
        "repayment_ok": False,
        # no calldata_hex on purpose ⇒ calldata_present False downstream
        "executable": False,
        "requires_downstream_validation": True,
        # advisory research metadata (never a gate)
        "research_meta": {
            "trust": ir.provenance.trust,
            "confidence": ir.provenance.confidence,
            "source": ir.provenance.source,
            "source_class": ir.source_class.value,
        },
    }
