"""Multichain canonical execution-document generator (flash-loan DEX arb).

MINIMUM targeted bridge so the EXISTING six-chain opportunity candidates
produce the SAME canonical execution document that
``OpportunityEngine → OpportunityPipeline → AutoExecutor`` already consume for
Base (``{chain, borrow_token, borrow_amount_wei, borrow_amount_usd,
flash_loan_provider, swap_hops}``).

It is a PURE, deterministic function — no second scanner, no second executor,
no network. All execution gating is delegated to the single source of truth
``settlement_dispatcher.evaluate_settlement`` (venue/flash/schema/executor),
so a document is emitted ONLY when the route is genuinely executable through a
verified deployed executor on that chain. Every other case is fail-closed with
an explicit reason and NO ``execution_document``.

This module NEVER signs, broadcasts, sizes for profit, or promotes modes.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from .settlement_dispatcher import evaluate_settlement, Verdict


def _classify(route: List[Dict[str, Any]]) -> str:
    n = len(route)
    venues = {(h.get("dex") or "").lower() for h in route}
    if n == 2:
        return "cross_venue_dex_dex" if len(venues) > 1 else "dex_dex"
    if n == 3:
        return "triangular"
    return "multi_hop"


def _fee_tier_bps(fee_ppm: Any) -> int:
    # Uniswap V3 fee is expressed in ppm (500/3000/10000); bps = ppm/100.
    return int(fee_ppm or 0) // 100


def build_execution_document(
    candidate: Dict[str, Any],
    *,
    executor_deployed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Convert a validated six-chain flash-loan-arb candidate into the canonical
    execution document, or return a fail-closed result.

    ``candidate`` contract::

        {
          "chain": "arbitrum",
          "opportunity_id": "...",
          "flash_loan_provider": "balancer_v2",
          "borrow": {"symbol","address","decimals","amount_wei","amount_usd"},
          "route": [ {"dex","token_in","token_in_addr","token_out",
                      "token_out_addr","fee"(ppm)} , ... ],   # ordered cycle
          "economics": {...}   # from the ACTUAL route; net_profit_usd passed thru
        }

    ``executor_deployed`` forwards the operator/env-resolved deployment truth to
    the settlement dispatcher (None ⇒ authoritative executor_registry lookup).
    """
    chain = candidate.get("chain")
    provider = candidate.get("flash_loan_provider")
    route = candidate.get("route") or []
    borrow = candidate.get("borrow") or {}
    econ = candidate.get("economics") or {}

    def _fail(verdict: str, reason: str, settlement: Optional[Dict[str, Any]] = None):
        return {"ok": False, "verdict": verdict, "reason": reason,
                "execution_document": None, "settlement": settlement,
                "signed": False, "broadcast": False}

    # ── Structural validation (fail-closed) ────────────────────────────────
    if not chain or not provider or not route:
        return _fail("REJECTED", "invalid_candidate:missing_chain_provider_or_route")
    try:
        amount_wei = int(borrow.get("amount_wei"))
    except (TypeError, ValueError):
        return _fail("REJECTED", "invalid_candidate:borrow_amount_wei_not_int")
    if amount_wei <= 0:
        return _fail("REJECTED", "invalid_candidate:borrow_amount_wei_must_be_positive")
    borrow_symbol = borrow.get("symbol")
    if not borrow_symbol or not borrow.get("address"):
        return _fail("REJECTED", "invalid_candidate:borrow_token_incomplete")

    # Route must be a closed cycle starting/ending at the borrow token.
    if route[0].get("token_in") != borrow_symbol or route[-1].get("token_out") != borrow_symbol:
        return _fail("REJECTED", "invalid_candidate:route_not_a_cycle_on_borrow_token")
    for i in range(len(route) - 1):
        if route[i].get("token_out") != route[i + 1].get("token_in"):
            return _fail("REJECTED", f"invalid_candidate:token_path_broken_at_hop_{i}")
    for i, h in enumerate(route):
        if not h.get("token_in_addr") or not h.get("token_out_addr"):
            return _fail("REJECTED", f"invalid_candidate:hop_{i}_missing_token_address")

    # ── Execution gating — SINGLE SOURCE OF TRUTH (fail-closed) ────────────
    venues = [h.get("dex") for h in route]
    decision = evaluate_settlement(
        flash_provider=provider, swap_venues=venues, chain=chain,
        executor_deployed=executor_deployed)
    settlement = decision.to_dict()
    if decision.verdict is not Verdict.EXECUTABLE:
        # Unsupported venue → REQUIRES_NEW_RECEIVER; missing executor →
        # REJECTED/executor_deployed; unsupported provider → REJECTED; etc.
        return _fail(decision.verdict.value,
                     f"not_executable:{decision.first_blocker}:{decision.reason}",
                     settlement)

    # ── Build canonical swap_hops (all Uniswap V3 by construction here) ────
    swap_hops: List[Dict[str, Any]] = []
    for i, h in enumerate(route):
        swap_hops.append({
            "token_in": h["token_in_addr"],
            "token_out": h["token_out_addr"],
            "fee_tier_bps": _fee_tier_bps(h.get("fee")),
            "amount_in_wei": amount_wei if i == 0 else 0,   # forward output after hop 0
            "amount_out_min_wei": 0,                         # real sizing sets this later
        })

    document = {
        "chain": chain,
        "opportunity_id": candidate.get("opportunity_id"),
        "strategy": "flash_loan_arbitrage",
        "opportunity_type": _classify(route),
        "borrow_token": borrow_symbol,
        "borrow_amount_wei": amount_wei,
        "borrow_amount_usd": borrow.get("amount_usd"),
        "flash_loan_provider": provider,
        "swap_hops": swap_hops,
        "token_path": [route[0]["token_in"]] + [h["token_out"] for h in route],
        "dex_path": [h.get("dex") for h in route],
        "net_profit_usd": econ.get("net_profit_usd"),
        "executor_address": decision.executor_address,
    }
    return {"ok": True, "verdict": "EXECUTABLE", "reason": None,
            "execution_document": document, "settlement": settlement,
            "signed": False, "broadcast": False}


__all__ = ["build_execution_document"]
