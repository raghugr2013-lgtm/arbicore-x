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
import logging
import os
import sys


def _mask(v):
    if not v:
        return None
    return f"{v[:10]}…<REDACTED> (len={len(v)})"


async def _probe_fresh_stages(plan, quoter):
    """READ-ONLY step-by-step probe of every fresh_fn dependency for ``plan``.

    Runs each stage in isolation and records the exact value/exception so the
    operator sees the SINGLE culprit stage. NEVER signs, NEVER broadcasts —
    only eth_call reads. Mirrors composition.fresh_fn exactly."""
    from arbicore.searcher.runtime import (make_base_eth_call_from_env,
                                            build_base_tvl_provider)
    from arbicore.searcher.price_feed import build_base_price_feed_from_env
    from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
        make_live_quote_provider)
    from arbicore.scanners.flash_loan_arbitrage.economics import (
        FlashLoanEconomicsAssessor, FLASH_LOAN_PROVIDERS)
    from arbicore.intelligence.roi_probability import ROIProbabilityEngine
    from arbicore.discovery.base_venues import build_pool_graph, token_address
    from arbicore.discovery.base_pool_registry import (canonical_pool_by_id,
                                                       get_canonical_pools)

    out: dict = {}
    if plan is None:
        return {"error": "no plan/opportunity available to probe"}

    eth_call = make_base_eth_call_from_env()
    price_feed = build_base_price_feed_from_env(quoter)
    tvl_provider = (build_base_tvl_provider(eth_call, price_feed.price_source)
                    if (eth_call and price_feed) else None)
    quote_prov = make_live_quote_provider(quoter, tvl_provider=tvl_provider)
    _, specs = build_pool_graph()

    route_pools = list(plan.get("route_pools") or [])
    token_path = [str(t).upper() for t in (plan.get("cycle_token_path") or [])]
    borrow_token = (plan.get("borrow_token") or "").upper()
    borrow_usd = float(plan.get("borrow_amount_usd") or 0.0)
    provider = (plan.get("flash_loan_provider") or plan.get("provider")
                or "balancer_v2")

    # Stage 1 — plan shape (fresh_fn returns None here on any mismatch)
    out["stage_1_plan_shape"] = {
        "route_pools": route_pools, "n_route_pools": len(route_pools),
        "cycle_token_path": token_path, "n_token_path": len(token_path),
        "expected_token_path_len": len(route_pools) + 1,
        "shape_ok": len(route_pools) >= 2
        and len(token_path) == len(route_pools) + 1,
        "borrow_token": borrow_token, "borrow_amount_usd": borrow_usd,
    }

    # Stage 2 — per-pool spec resolution + REAL address + on-chain TVL
    pool_probe = []
    for pid in route_pools:
        spec = specs.get(pid)
        cp = canonical_pool_by_id(pid)
        addr = getattr(cp, "address", None) if cp else None
        tvl = None
        tvl_err = None
        if tvl_provider is not None and addr:
            try:
                tvl = await tvl_provider.get_pool_tvl_usd("base", addr)
            except Exception as exc:  # noqa: BLE001
                tvl_err = f"{type(exc).__name__}: {exc}"
        pool_probe.append({
            "pool_id": pid, "spec_found_in_graph": spec is not None,
            "spec": spec, "canonical_resolved": cp is not None,
            "real_address": addr, "onchain_tvl_usd": tvl, "tvl_error": tvl_err,
        })
    out["stage_2_pools"] = pool_probe

    # Stage 3 — head block
    try:
        out["stage_3_head_block"] = await price_feed._head_block()
    except Exception as exc:  # noqa: BLE001
        out["stage_3_head_block"] = f"ERROR {type(exc).__name__}: {exc}"

    # Stage 4 — borrow-token USD price
    try:
        px = await price_feed.price_source(borrow_token)
        out["stage_4_borrow_price_usd"] = px
    except Exception as exc:  # noqa: BLE001
        px = None
        out["stage_4_borrow_price_usd"] = f"ERROR {type(exc).__name__}: {exc}"

    # Stage 5 — raw per-hop route quote (shows WHICH hop degrades + why)
    if out["stage_1_plan_shape"]["shape_ok"]:
        hops = []
        for i, pid in enumerate(route_pools):
            spec = dict(specs.get(pid) or {})
            tin, tout = token_path[i], token_path[i + 1]
            h = {"dex": spec.get("dex") or "uniswap_v3",
                 "token_in": token_address(tin) if tin in _known(tin) else tin,
                 "token_out": token_address(tout) if tout in _known(tout) else tout}
            if "fee" in spec:
                h["fee"] = spec["fee"]
            if "tick_spacing" in spec:
                h["tick_spacing"] = spec["tick_spacing"]
            if "stable" in spec:
                h["stable"] = spec["stable"]
            if i == 0:
                from arbicore.discovery.base_venues import PROBE_AMOUNT
                h["amount_in_wei"] = int(PROBE_AMOUNT.get(borrow_token, 10 ** 16))
            hops.append(h)
        try:
            rq = await quoter.quote_route(chain="base", hops=hops)
            out["stage_5_route_quote"] = {
                "status": rq.status,
                "final_amount_out_wei": rq.final_amount_out_wei,
                "hops": [{"idx": q.hop_index, "dex": q.dex, "status": q.status,
                          "error": q.error, "amount_out_wei": q.amount_out_wei}
                         for q in rq.hops],
            }
        except Exception as exc:  # noqa: BLE001
            out["stage_5_route_quote"] = f"ERROR {type(exc).__name__}: {exc}"
    else:
        out["stage_5_route_quote"] = "SKIPPED (plan shape invalid)"

    # Stage 6 — live_quote_provider facts (what fresh_fn actually consumes)
    try:
        hm = {"chain": "base", "provider": provider, "borrow_token": borrow_token,
              "route_pools": route_pools, "cycle_token_path": token_path}
        facts = await quote_prov(hm, borrow_usd)
        out["stage_6_facts"] = (None if facts is None else {
            "route_quote_status": facts.get("route_quote_status"),
            "gross_profit_pct": facts.get("gross_profit_pct"),
            "n_hop_legs": len(facts.get("hop_legs") or []),
            "min_pool_tvl_usd_in_route": facts.get("min_pool_tvl_usd_in_route"),
            "tvl_provenance": facts.get("tvl_provenance"),
        })
    except Exception as exc:  # noqa: BLE001
        out["stage_6_facts"] = f"ERROR {type(exc).__name__}: {exc}"

    # Stage 7 — Balancer V2 Vault balanceOf (real flash-loan availability)
    vault = (os.environ.get("BASE_BALANCER_V2_VAULT")
             or "0xBA12222222228d8Ba445958a75a0704d566BF2C8")
    meta = FLASH_LOAN_PROVIDERS.get((provider or "").lower())
    fl = {"vault": vault, "vault_from_env": bool(os.environ.get("BASE_BALANCER_V2_VAULT")),
          "provider_supported_on_base": bool(
              meta and "base" in meta.get("supports_chains", ()))}
    cp = next((p for p in get_canonical_pools()
               if borrow_token in (p.token0_symbol.upper(), p.token1_symbol.upper())),
              None)
    if cp is None:
        fl["result"] = "None (no canonical pool exposes borrow token)"
    else:
        if cp.token0_symbol.upper() == borrow_token:
            taddr, tdec = cp.token0_address, cp.token0_decimals
        else:
            taddr, tdec = cp.token1_address, cp.token1_decimals
        fl["borrow_token_address"] = taddr
        data = "0x70a08231" + vault.lower().replace("0x", "").rjust(64, "0")
        try:
            raw = await eth_call(taddr, data)
            bal = int(raw, 16) / (10 ** int(tdec)) if raw else None
            fl["vault_balance"] = bal
            if bal is not None and isinstance(px, (int, float)) and px and px > 0:
                fl["needed_tokens"] = borrow_usd / px
                fl["available"] = bal >= (borrow_usd / px)
            else:
                fl["available"] = "None (missing balance or borrow price)"
        except Exception as exc:  # noqa: BLE001
            fl["result"] = f"ERROR balanceOf {type(exc).__name__}: {exc}"
    out["stage_7_flashloan_availability"] = fl

    # Culprit summary
    culprit = _first_blocking_stage(out)
    out["FIRST_BLOCKING_STAGE"] = culprit
    return out


def _known(sym):
    try:
        from arbicore.discovery.base_venues import TOKENS
        return TOKENS
    except Exception:  # noqa: BLE001
        return {}


def _first_blocking_stage(o: dict) -> str:
    if not o.get("stage_1_plan_shape", {}).get("shape_ok"):
        return "stage_1_plan_shape (cycle_token_path length != route_pools+1)"
    facts = o.get("stage_6_facts")
    if facts is None:
        rq = o.get("stage_5_route_quote")
        if isinstance(rq, dict):
            bad = [h for h in rq.get("hops", []) if h.get("status") != "ok"]
            if bad:
                return ("stage_6_facts=None because route not fully priceable; "
                        f"degraded hops: {bad}")
        return "stage_6_facts=None (route unpriceable / break_even)"
    if isinstance(facts, dict) and facts.get("route_quote_status") != "ok":
        return ("stage_6 quote status != ok -> fresh_quote gate will DENY "
                f"(status={facts.get('route_quote_status')})")
    hb = o.get("stage_3_head_block")
    if not isinstance(hb, int):
        return (f"stage_3_head_block unavailable ({hb}) -> block_freshness "
                "gate will DENY")
    px = o.get("stage_4_borrow_price_usd")
    if not isinstance(px, (int, float)):
        return (f"stage_4_borrow_price_usd unavailable ({px}) -> flashloan/"
                "price gate will DENY")
    fl = o.get("stage_7_flashloan_availability", {})
    if fl.get("available") is not True:
        return f"stage_7_flashloan_availability not True ({fl.get('available')})"
    return "none - all fresh stages resolved (validation should be GREEN)"


async def main() -> None:
    # Surface the M3.0 fresh_fn per-stage diagnostics to stderr so a live
    # validate() call also prints the exact blocking stage.
    logging.basicConfig(
        level=logging.INFO, stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    logging.getLogger("arbicore.m3_0.fresh_fn").setLevel(logging.INFO)

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

    # 3b) READ-ONLY step-by-step probe — pinpoint the exact failing stage.
    try:
        audit["fresh_stage_probe"] = await _probe_fresh_stages(plan, quoter)
    except Exception as exc:  # noqa: BLE001
        audit["fresh_stage_probe"] = {"error": f"{type(exc).__name__}: {exc}"}

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

    _sent = bool(audit["broadcast_ladder"].get("broadcast_sent") or False)
    audit["verdict"] = {
        "controlled_live_layer_constructed": bool(validator and breaker),
        "require_revalidation": True,
        "signed_or_broadcast": _sent,
        "safe": _sent is False,
    }
    print(json.dumps(audit, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
