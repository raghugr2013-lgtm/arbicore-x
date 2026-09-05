#!/usr/bin/env python3
"""M3.0 · REAL-Base candidate scan — READ-ONLY, NEVER signs/broadcasts.

Runs a set of genuine canonical Base cycles through the REAL M3.0 controlled-live
safety layer (real eth_call quotes, real M2.5 on-chain USD price, real M2.6 TVL,
real economics, real MEV from eth_feeHistory, real Balancer flash-loan liquidity)
and reports, per candidate, EVERY M3 gate result plus the actual economics/TVL/
MEV numbers and the first blocking stage.

Objective: surface whether ANY canonical Base cycle is genuinely eligible right
now (m3_final_gates.ok=true) WITHOUT lowering thresholds or fabricating anything.
If none is profitable, the correct result is DENY (fail-closed) with real numbers.

Safety: no signing key is provisioned, broadcast_plan is only ever exercised with
confirm=False (a single ladder check), production/proxy are untouched.

Requires (isolated validator env only):
    ARBICORE_RPC_URL_BASE=<real Base RPC>   ARBICORE_USD_NUMERAIRE=USDC
Optional audit file: ARBICORE_M3_AUDIT_FILE=/path/audit.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time


# Genuine canonical Base cycles (fee-tier, cross-DEX, stable, triangular).
CANDIDATES = [
    {"name": "WETH/USDC univ3 fee-tier (500->3000)",
     "borrow_token": "WETH", "borrow_amount_usd": 10000.0,
     "route_pools": ["uniswap_v3:USDC:WETH:500", "uniswap_v3:USDC:WETH:3000"],
     "cycle_token_path": ["WETH", "USDC", "WETH"]},
    {"name": "WETH/USDC cross-DEX (univ3 500 -> aerodrome slipstream)",
     "borrow_token": "WETH", "borrow_amount_usd": 10000.0,
     "route_pools": ["uniswap_v3:USDC:WETH:500", "aerodrome_slipstream:USDC:WETH:100"],
     "cycle_token_path": ["WETH", "USDC", "WETH"]},
    {"name": "USDC/USDT stable cross-DEX (univ3 100 -> aerodrome classic)",
     "borrow_token": "USDC", "borrow_amount_usd": 10000.0,
     "route_pools": ["uniswap_v3:USDC:USDT:100", "aerodrome:USDC:USDT:stable"],
     "cycle_token_path": ["USDC", "USDT", "USDC"]},
    {"name": "WETH->USDC->cbETH->WETH triangular (univ3)",
     "borrow_token": "WETH", "borrow_amount_usd": 10000.0,
     "route_pools": ["uniswap_v3:USDC:WETH:500", "uniswap_v3:USDC:cbETH:500",
                     "uniswap_v3:WETH:cbETH:500"],
     "cycle_token_path": ["WETH", "USDC", "cbETH", "WETH"]},
    {"name": "WETH/wstETH cross-DEX (univ3 100 -> aerodrome slipstream 1)",
     "borrow_token": "WETH", "borrow_amount_usd": 10000.0,
     "route_pools": ["uniswap_v3:WETH:wstETH:100", "aerodrome_slipstream:WETH:wstETH:1"],
     "cycle_token_path": ["WETH", "wstETH", "WETH"]},
]


def _controlled_live_unavailable_reason(quoter) -> str:
    """READ-ONLY diagnosis of WHY build_controlled_live_safety returned None so
    the operator sees the exact missing controlled-live dependency. Never builds
    a fake validator — only re-probes the same real constructors (fail-closed).
    """
    from arbicore.searcher.runtime import make_base_eth_call_from_env
    from arbicore.searcher.price_feed import build_base_price_feed_from_env
    try:
        if make_base_eth_call_from_env() is None:
            return ("controlled_live_unavailable: no Base RPC provider "
                    "(make_base_eth_call_from_env is None) — FAIL-CLOSED")
        if build_base_price_feed_from_env(quoter) is None:
            return ("controlled_live_unavailable: no on-chain USD price feed "
                    "(build_base_price_feed_from_env is None; set "
                    "ARBICORE_USD_NUMERAIRE) — FAIL-CLOSED")
    except Exception as exc:  # noqa: BLE001 — diagnosis never raises
        return f"controlled_live_unavailable: probe_error {type(exc).__name__}: {exc}"
    return "controlled_live_unavailable: PreBroadcastValidator not constructed — FAIL-CLOSED"


async def validate_candidate(validator, plan, unavailable_reason: str) -> dict:
    """Run the REAL PreBroadcastValidator when it is constructed; otherwise
    return a fail-closed DENY carrying the exact reason. NEVER fabricates a
    PASS, NEVER stubs/bypasses the validator, NEVER accepts a fallback. This is
    the same fail-closed contract m3_0_vps_validate uses and it removes the
    AttributeError when controlled-live deps (Base RPC / USD price feed) are
    unavailable."""
    if validator is None:
        return {"ok": False, "gates": {}, "reasons": [unavailable_reason]}
    decision = await validator.validate(plan)
    return {"ok": decision.ok, "gates": decision.gate,
            "reasons": decision.reasons}


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")

    from arbicore.execution.quoter import QuoterRegistry
    from arbicore.runtime.composition import build_controlled_live_safety
    from arbicore.execution.pre_broadcast import PreBroadcastValidator, CircuitBreaker
    from arbicore.providers.rpc import EthJsonRpcProvider
    from arbicore.config.persistent import resolve_rpc_url_from_env
    from scripts.m3_0_vps_validate import _probe_fresh_stages

    audit: dict = {"env": {}, "head_block": None, "candidates": [], "summary": {}}
    for k in ("ARBICORE_RPC_URL_BASE", "ARBICORE_RPC_URL", "ARBICORE_USD_NUMERAIRE",
              "ARBICORE_AERO_CL_FACTORY_BASE", "BASE_BALANCER_V2_VAULT"):
        v = os.environ.get(k)
        audit["env"][k] = (f"{v[:16]}…" if v and "URL" in k else v)

    url = resolve_rpc_url_from_env("base")
    if not url:
        print(json.dumps({"error": "no Base RPC configured (fail-closed)"}, indent=2))
        return
    head = await EthJsonRpcProvider(chain="base", url=url).eth_get_block_number()
    audit["head_block"] = head

    quoter = QuoterRegistry()
    validator, breaker = build_controlled_live_safety(quoter)
    audit["validator_constructed"] = isinstance(validator, PreBroadcastValidator)
    audit["breaker_constructed"] = isinstance(breaker, CircuitBreaker)
    # Fail-closed (no crash) when controlled-live deps are unavailable: record
    # the exact missing dependency once, and DENY every candidate with it.
    unavailable_reason = (None if validator is not None
                          else _controlled_live_unavailable_reason(quoter))
    if unavailable_reason is not None:
        audit["validator_unavailable_reason"] = unavailable_reason

    best = None
    for c in CANDIDATES:
        plan = {"strategy": "flash_loan_arbitrage", "chain": "base",
                "opportunity_id": f"scan:{c['name']}",
                "borrow_token": c["borrow_token"],
                "borrow_amount_usd": c["borrow_amount_usd"],
                "flash_loan_provider": "balancer_v2",
                "route_pools": c["route_pools"],
                "cycle_token_path": c["cycle_token_path"],
                "quoted_block": head,                 # within lag of fresh head
                "deadline_ts": time.time() + 120.0}

        probe = await _probe_fresh_stages(plan, quoter)
        m3_gates = await validate_candidate(validator, plan, unavailable_reason)

        facts = probe.get("stage_6_facts")
        mev = probe.get("stage_8_mev")
        fl = probe.get("stage_7_flashloan_availability", {})
        entry = {
            "name": c["name"], "plan": plan,
            "real_numbers": {
                "route_quote_status": (facts or {}).get("route_quote_status")
                if isinstance(facts, dict) else facts,
                "gross_profit_pct": (facts or {}).get("gross_profit_pct")
                if isinstance(facts, dict) else None,
                "min_pool_tvl_usd_in_route": (facts or {}).get("min_pool_tvl_usd_in_route")
                if isinstance(facts, dict) else None,
                "tvl_provenance": (facts or {}).get("tvl_provenance")
                if isinstance(facts, dict) else None,
                "mev": mev,
                "flashloan_available": fl.get("available"),
                "flashloan_vault_balance": fl.get("vault_balance"),
            },
            "aero_propagated": probe.get("stage_2_aero_propagated"),
            "pools": probe.get("stage_2_pools"),
            "first_blocking_stage": probe.get("FIRST_BLOCKING_STAGE"),
            "m3_final_gates": m3_gates,
        }
        audit["candidates"].append(entry)
        if m3_gates["ok"] and best is None:
            best = c["name"]

    # single confirm=False ladder check → proves no broadcast path is taken
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
        rc = await b.broadcast_plan(audit["candidates"][0]["plan"], confirm=False)
        audit["broadcast_ladder"] = {"broadcast_sent": rc.broadcast_sent,
                                     "denied_reasons": rc.denied_reasons}
    except Exception as exc:  # noqa: BLE001
        audit["broadcast_ladder"] = {"error": f"{type(exc).__name__}: {exc}"}

    n_green = sum(1 for e in audit["candidates"] if e["m3_final_gates"]["ok"])
    audit["summary"] = {
        "candidates_scanned": len(audit["candidates"]),
        "green": n_green, "best_green_candidate": best,
        "broadcast_sent": bool(audit.get("broadcast_ladder", {}).get("broadcast_sent")),
        "safe": not bool(audit.get("broadcast_ladder", {}).get("broadcast_sent")),
    }

    payload = json.dumps(audit, indent=2, default=str)
    af = os.environ.get("ARBICORE_M3_AUDIT_FILE")
    if af:
        with open(af, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    print(payload)


if __name__ == "__main__":
    asyncio.run(main())
