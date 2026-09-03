"""M2.4 — route a CONFIRMED flash-loan candidate into the existing paper /
SHADOW OpportunityPipeline for certification.

STRICTLY SHADOW/PAPER: the adapter never signs and never broadcasts. It relies
on the OpportunityPipeline's own guarantees — broadcast only ever happens in
``LIMITED_LIVE``/``FULL_LIVE`` mode with a wired broadcaster; the SHADOW
composition wires neither, and this adapter asserts the returned action is
never ``broadcast``.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def canonical_to_pipeline_opp(canonical: Any,
                              evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Project a CONFIRMED ``CanonicalOpportunity`` + its audit evidence bundle
    onto the dict shape the OpportunityPipeline consumes. Uses ONLY values
    already produced by verification — never fabricates a quote/profit/depth."""
    econ = evidence.get("economics") or {}
    liq = evidence.get("liquidity") or {}
    hop_legs = list((evidence.get("quotes") or {}).get("hop_legs") or [])
    swap_hops = [{"dex": h.get("dex_protocol"),
                  "fee_bps": h.get("fee_bps"),
                  "pool_liquidity_usd": h.get("depth_usd")}
                 for h in hop_legs]
    net = econ.get("atomic_profit_usd")
    if net is None:
        net = getattr(canonical, "expected_profit_usd", None)
    return {
        "opportunity_id": getattr(canonical, "opportunity_id", None),
        "opportunity_type": "FLASH_LOAN_ARBITRAGE",
        "strategy": "flash_loan_arbitrage",
        "chain": evidence.get("chain") or getattr(canonical, "chain", None),
        "borrow_token": evidence.get("borrow_token"),
        "borrow_amount_usd": evidence.get("input_amount_usd"),
        "flash_loan_provider": evidence.get("flash_loan_provider"),
        "net_profit_usd": net,
        "expected_profit_usd": getattr(canonical, "expected_profit_usd", net),
        "confidence": getattr(canonical, "confidence_score", None),
        "swap_hops": swap_hops,
        "min_route_tvl_usd": liq.get("min_pool_tvl_usd_in_route"),
        "source_data_quality": "REAL",
        "validation_id": (evidence.get("bundle_id") or None),
    }


async def route_to_shadow(pipeline: Any, canonical: Any,
                          evidence: Dict[str, Any]) -> Any:
    """Drive one CONFIRMED candidate through the SHADOW/PAPER pipeline.

    Returns the ``PipelineResult``. Raises ``AssertionError`` if the pipeline
    ever reports a broadcast action — an invariant tripwire (SHADOW must never
    broadcast)."""
    opp = canonical_to_pipeline_opp(canonical, evidence)
    result = await pipeline.evaluate(
        opp, strategy="flash_loan_arbitrage", scanner_family="flash_loan_arb")
    assert getattr(result, "action", None) != "broadcast", \
        "SHADOW invariant violated: pipeline attempted broadcast"
    return result


__all__ = ["canonical_to_pipeline_opp", "route_to_shadow"]
