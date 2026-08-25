#!/usr/bin/env python3
"""M3.0 VPS validation harness — READ-ONLY, NEVER signs/broadcasts.

Run INSIDE the M3.0 validator container on the VPS (real Base RPC/WSS/env):

    python -m scripts.m3_0_vps_validate            # uses latest CONFIRMED bundle
    python -m scripts.m3_0_vps_validate '<plan-json>'   # explicit plan

It proves the controlled-live safety layer is really constructed and runs one
opportunity through detection→verification→M3.0 final validation, STOPPING
before signing (confirm=False, no key). Emits a single audit record of the
final M3 gates with PASS/DENY reasons.

Safety: broadcast_plan is called with confirm=False, so the sign +
eth_sendRawTransaction branch is unreachable. No signing key is provisioned,
LIMITED_LIVE is never set, production is never touched.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys


def _mask(v):
    if not v:
        return None
    return f"{v[:10]}…<REDACTED> (len={len(v)})"


async def main() -> None:
    from arbicore.runtime.composition import build_controlled_live_safety
    from arbicore.execution.pre_broadcast import PreBroadcastValidator, CircuitBreaker
    from arbicore.searcher.runtime import (make_base_eth_call_from_env,
                                           build_base_tvl_provider)
    from arbicore.searcher.price_feed import build_base_price_feed_from_env
    from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
        make_live_quote_provider)
    from arbicore.scanners.flash_loan_arbitrage.economics import FlashLoanEconomicsAssessor
    from arbicore.execution.quoter import QuoterRegistry

    audit: dict = {"env": {}, "constructions": {}, "opportunity": {},
                   "m3_final_gates": {}, "broadcast_ladder": {}, "verdict": {}}

    # 1) env presence (masked)
    for k in ("ARBICORE_RPC_URL", "ARBICORE_RPC_URL_BASE", "ARBICORE_WSS_URL_BASE",
              "ARBICORE_NATIVE_PRICE_USD", "ARBICORE_USD_NUMERAIRE",
              "ARBICORE_AERO_CL_FACTORY_BASE", "ARBICORE_AERO_POOL_FACTORY_BASE",
              "BASE_BALANCER_V2_VAULT"):
        audit["env"][k] = _mask(os.environ.get(k)) if "URL" in k else os.environ.get(k)

    quoter = QuoterRegistry()

    # 2) prove each real dependency is constructed (mirrors build_controlled_live_safety)
    eth_call = make_base_eth_call_from_env()
    price_feed = build_base_price_feed_from_env(quoter)
    tvl_provider = (build_base_tvl_provider(eth_call, price_feed.price_source)
                    if (eth_call and price_feed) else None)
    quote_prov = make_live_quote_provider(quoter, tvl_provider=tvl_provider)
    econ = FlashLoanEconomicsAssessor.__name__
    audit["constructions"] = {
        "QuoterRegistry_M2_1": type(quoter).__name__,
        "eth_call": bool(eth_call),
        "price_feed_M2_5": type(price_feed).__name__ if price_feed else None,
        "tvl_provider_M2_6": type(tvl_provider).__name__ if tvl_provider else None,
        "live_quote_provider": bool(quote_prov),
        "economics_assessor": econ,
    }

    validator, breaker = build_controlled_live_safety(quoter)
    audit["constructions"]["PreBroadcastValidator"] = (
        isinstance(validator, PreBroadcastValidator))
    audit["constructions"]["CircuitBreaker"] = isinstance(breaker, CircuitBreaker)

    # 3) pick an opportunity (latest CONFIRMED evidence bundle → plan), else arg/template
    plan = None
    if len(sys.argv) > 1:
        plan = json.loads(sys.argv[1])
    else:
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
            doc = await db.evidence_bundles.find_one(
                {"verification_status": "CONFIRMED"}, sort=[("created_at", -1)])
            doc = doc or await db.evidence_bundles.find_one({}, sort=[("created_at", -1)])
            if doc:
                r = doc.get("route", {})
                plan = {"strategy": "flash_loan_arbitrage", "chain": "base",
                        "opportunity_id": doc.get("opportunity_id") or doc.get("bundle_id"),
                        "borrow_token": doc.get("borrow_token"),
                        "borrow_amount_usd": doc.get("input_amount_usd"),
                        "flash_loan_provider": doc.get("flash_loan_provider") or "balancer_v2",
                        "route_pools": r.get("route_pools"),
                        "cycle_token_path": r.get("cycle_token_path"),
                        "quoted_block": (doc.get("block_context") or {}).get("verified_at_ts"),
                        "deadline_ts": None}
        except Exception as exc:  # noqa: BLE001
            audit["opportunity"]["load_error"] = f"{type(exc).__name__}: {exc}"
    audit["opportunity"]["plan"] = plan

    # 4) M3.0 FINAL validation (fresh M2.1 quote + M2.5 price + M2.6 TVL + economics + flashloan)
    if validator is not None and plan is not None:
        decision = await validator.validate(plan)
        audit["m3_final_gates"] = {"ok": decision.ok, "gates": decision.gate,
                                   "reasons": decision.reasons}
    else:
        audit["m3_final_gates"] = {
            "ok": False,
            "reason": ("validator is None (no Base RPC / price feed) — FAIL-CLOSED"
                       if validator is None else "no opportunity/plan available")}

    # 5) full broadcaster ladder, confirm=False → HELD (never signs)
    try:
        from arbicore.execution.broadcast import LimitedLiveBroadcaster
        from arbicore.execution.mode import ExecutionModeRepo
        from arbicore.execution.kill_switch import KillSwitchRepo
        from arbicore.execution.capital_policy import CapitalPolicyRepo, CapitalAllocator
        from motor.motor_asyncio import AsyncIOMotorClient
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        b = LimitedLiveBroadcaster(
            kill_switch=KillSwitchRepo(db), mode_repo=ExecutionModeRepo(db),
            wallet_registry=None, secret_registry=None,
            capital_allocator=CapitalAllocator(CapitalPolicyRepo(db)),
            pre_broadcast_validator=validator, circuit_breaker=breaker,
            require_revalidation=True)
        rc = await b.broadcast_plan(plan or {"strategy": "flash_loan_arbitrage",
                                             "chain": "base"}, confirm=False)
        audit["broadcast_ladder"] = {"gate_ladder": rc.gate_ladder,
                                     "broadcast_sent": rc.broadcast_sent,
                                     "denied_reasons": rc.denied_reasons}
    except Exception as exc:  # noqa: BLE001
        audit["broadcast_ladder"] = {"error": f"{type(exc).__name__}: {exc}"}

    audit["verdict"] = {
        "controlled_live_layer_constructed": bool(validator and breaker),
        "require_revalidation": True,
        "signed_or_broadcast": audit["broadcast_ladder"].get("broadcast_sent", False),
        "safe": audit["broadcast_ladder"].get("broadcast_sent", True) is False,
    }
    print(json.dumps(audit, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
