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


def _quote_block_from_evidence(doc):
    """Return only a genuine block-number field from an evidence bundle.

    Mongo may deserialize numeric values as an integer-like/string value;
    accept decimal representations only when they come from an explicit
    ``block_number``/``quote_block`` field. Wall-clock timestamps are never
    considered.
    """
    def _coerce(value):
        if isinstance(value, int) and not isinstance(value, bool):
            return value if value > 0 else None
        if isinstance(value, str) and value.strip().isdigit():
            n = int(value.strip())
            return n if n > 0 else None
        return None

    bc = doc.get("block_context") or {}
    qblock = _coerce(bc.get("block_number"))
    if qblock is not None:
        return qblock
    qblock = _coerce(bc.get("quote_block"))
    if qblock is not None:
        return qblock
    quotes = doc.get("quotes") or {}
    qblock = _coerce(quotes.get("quote_block"))
    if qblock is not None:
        return qblock
    route = doc.get("route") or {}
    candidates = []
    for leg in (quotes.get("hop_legs") or route.get("hop_legs") or
                route.get("legs") or []):
        if isinstance(leg, dict):
            qblock = _coerce(leg.get("block_number"))
            if qblock is not None:
                candidates.append(qblock)
    return max(candidates) if candidates else None


def _plan_from_evidence(doc):
    """Build the validator plan from one Mongo evidence document."""
    route = doc.get("route") or {}
    return {
        "strategy": "flash_loan_arbitrage", "chain": "base",
        "opportunity_id": doc.get("opportunity_id") or doc.get("bundle_id"),
        "borrow_token": doc.get("borrow_token"),
        "borrow_amount_usd": doc.get("input_amount_usd"),
        "flash_loan_provider": doc.get("flash_loan_provider") or "balancer_v2",
        "route_pools": route.get("route_pools"),
        "cycle_token_path": route.get("cycle_token_path"),
        "quoted_block": _quote_block_from_evidence(doc),
        "deadline_ts": None,
    }


def _flash_loan_evidence_filter(verification_status=None):
    """Restrict M3's source to the flash-loan verifier evidence schema.

    ``evidence_bundles`` is shared by multiple scanners. Selecting the newest
    CONFIRMED document globally can feed M3 a bundle without
    ``quotes.hop_legs`` while the flash-loan verifier has genuine provenance.
    """
    query = {"source_component": "flash_loan_arb_verifier"}
    if verification_status is not None:
        query["verification_status"] = verification_status
    return query


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
        FLASH_LOAN_PROVIDERS)
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

    # M2.6 PROPAGATION — resolve the Aerodrome/Slipstream route pools on-chain
    # and write REAL addresses into the canonical registry BEFORE reading
    # addresses/TVL below, so stage_2 mirrors the working quote path (single
    # source of truth). Fail-closed: unresolved pools stay address=None.
    try:
        from arbicore.searcher.aero_resolver import resolve_and_propagate
        if eth_call is not None:
            n_prop = await resolve_and_propagate(
                eth_call, route_pools,
                get_block=(price_feed._head_block if price_feed else None))
            out["stage_2_aero_propagated"] = n_prop
    except Exception as exc:  # noqa: BLE001
        out["stage_2_aero_propagated"] = f"ERROR {type(exc).__name__}: {exc}"

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
        from arbicore.discovery.base_venues import probe_amount
        hops = []
        for i, pid in enumerate(route_pools):
            spec = dict(specs.get(pid) or {})
            tin, tout = token_path[i], token_path[i + 1]
            # token_address is case-insensitive (Base has mixed-case symbols
            # such as cbETH/USDbC); None ⇒ keep the raw symbol so the culprit
            # is visible rather than raising KeyError.
            h = {"dex": spec.get("dex") or "uniswap_v3",
                 "token_in": token_address(tin) or tin,
                 "token_out": token_address(tout) or tout}
            if "fee" in spec:
                h["fee"] = spec["fee"]
            if "tick_spacing" in spec:
                h["tick_spacing"] = spec["tick_spacing"]
            if "stable" in spec:
                h["stable"] = spec["stable"]
            if i == 0:
                h["amount_in_wei"] = int(probe_amount(borrow_token))
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
            "gas_cost_usd": facts.get("gas_cost_usd"),
            "tx_gas_units": facts.get("tx_gas_units"),
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

    # Stage 8 — MEV classification from REAL Base congestion (eth_feeHistory
    # gasUsedRatio). Mirrors composition.fresh_fn stage=mev exactly: no source /
    # any read failure ⇒ fresh_fn DENIES here (fail-closed).
    from arbicore.searcher.runtime import make_base_congestion_source_from_env
    from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
        MevRiskScorer)
    congestion_source = make_base_congestion_source_from_env()
    try:
        congestion = (await congestion_source()
                      if congestion_source is not None else None)
        mev_out = {
            "congestion_pct": congestion,
            "congestion_source": ("eth_feeHistory.gasUsedRatio"
                                  if congestion_source is not None
                                  else "no_base_rpc"),
        }
        if congestion is None:
            mev_out["mev_ok"] = None
            mev_out["note"] = "fresh_fn DENIES at stage=mev (fail-closed)"
        else:
            mv = MevRiskScorer().classify(
                source_chain_congestion=congestion,
                destination_chain_congestion=congestion,
                asset=borrow_token, notional_usd=borrow_usd, is_atomic=True)
            mev_out.update({
                "level": str(mv["level"]), "label": mv["label"],
                "score": mv["score"],
                # LOW/MEDIUM pass, HIGH denies (matches fresh_fn policy).
                "mev_ok": mv["label"] != "HIGH"})
    except Exception as exc:  # noqa: BLE001
        mev_out = f"ERROR {type(exc).__name__}: {exc}"
    out["stage_8_mev"] = mev_out

    # Stages 9-14 intentionally expose the remaining fresh_fn and execution
    # gates as structured, read-only diagnostics.  They never sign, submit,
    # or mutate state.  Values are derived only from the real facts collected
    # above; unavailable inputs remain unavailable (fail-closed).
    facts = out.get("stage_6_facts")
    if isinstance(facts, dict):
        gross = facts.get("gross_profit_pct")
        gas = facts.get("gas_cost_usd")
        out["stage_9_economics"] = {
            "gross_profit_pct": gross,
            "gas_cost_usd": gas,
            "tx_gas_units": facts.get("tx_gas_units"),
            "economics_inputs_present": (gross is not None),
        }
        # Invoke the same chain gas model used by fresh_fn. This performs real
        # gas-price and Base GasPriceOracle reads; unavailable inputs remain a
        # structured denial rather than a placeholder cost.
        all_in = None
        try:
            from arbicore.chains.gas_model import get_chain_gas_model
            gm = get_chain_gas_model("base")
            px = out.get("stage_4_borrow_price_usd")
            gross_usd = borrow_usd * float(gross or 0.0) / 100.0
            if gm is not None:
                all_in = await gm.all_in_cost(
                    gross_profit_usd=gross_usd,
                    borrow_amount_usd=borrow_usd,
                    notional_usd=borrow_usd,
                    gas_units=facts.get("tx_gas_units"),
                    eth_usd=px,
                )
        except Exception as exc:  # noqa: BLE001
            out["stage_10_all_in_cost_error"] = f"{type(exc).__name__}: {exc}"
        out["stage_10_all_in_cost"] = (
            {"available": True, **all_in} if all_in is not None else {
                "available": False,
                "gas_units_present": facts.get("tx_gas_units") is not None,
                "reason": "gas/all-in inputs unavailable (fail-closed)",
            })
    else:
        out["stage_9_economics"] = {"economics_inputs_present": False}
        out["stage_10_all_in_cost"] = {"available": False,
                                        "reason": "facts unavailable"}

    hb = out.get("stage_3_head_block")
    quoted = plan.get("quoted_block")
    deadline = plan.get("deadline_ts")
    now_ts = __import__("time").time()
    out["stage_11_prebroadcast_gates"] = {
        "block_freshness": isinstance(hb, int) and (
            quoted is None or (isinstance(quoted, int) and hb >= quoted and hb - quoted <= 5)),
        "reorg_protection": isinstance(hb, int) and (
            quoted is None or (isinstance(quoted, int) and hb >= quoted)),
        "deadline": deadline is None or now_ts <= float(deadline),
        "price_ok": isinstance(out.get("stage_4_borrow_price_usd"), (int, float)),
        "tvl_ok": bool(isinstance(facts, dict) and
                        (facts.get("min_pool_tvl_usd_in_route") or 0) > 0 and
                        facts.get("tvl_provenance") == "onchain_reserves"),
        "profit_buffer": None,
        "duplicate_opportunity": "not_claimed (probe is read-only)",
    }
    # Calldata/simulation are represented explicitly so a VPS operator can
    # distinguish missing execution prerequisites from fresh-market failures.
    hops = plan.get("hops") or []
    out["stage_12_calldata"] = {
        "shape_ok": bool(route_pools and len(token_path) == len(route_pools) + 1),
        "swap_hops_present": bool(hops) or bool(route_pools),
        "slippage_bounds_present": all(
            isinstance(h, dict) and int(h.get("amount_out_min_wei") or 0) > 0
            for h in hops) if hops else None,
    }
    out["stage_13_atomic_simulation"] = {
        "read_only": True,
        "available": bool(os.environ.get("ARBICORE_EXECUTOR_ADDRESS_BASE") and
                           os.environ.get("ARBICORE_EXECUTOR_BYTECODE")),
        "passed": False,
        "reason": "requires deployed executor, signer-backed simulation inputs, and a real candidate",
    }
    out["stage_14_confirmation"] = {
        "confirm": False,
        "broadcast_permitted": False,
        "reason": "VPS harness is permanently confirm=false",
    }

    # Culprit summary
    culprit = _first_blocking_stage(out)
    out["FIRST_BLOCKING_STAGE"] = culprit
    return out


def _first_blocking_stage(o: dict) -> str:
    """Ordered EXACTLY as composition.fresh_fn evaluates dependencies:
    plan-shape → resolve_pools → live_quote(facts) → hop_legs → mev →
    head_block → borrow_price → flashloan_available. The reported stage is the
    first one that would make fresh_fn return None (DENY)."""
    # 1. plan shape (extract_plan / token_path_shape)
    if not o.get("stage_1_plan_shape", {}).get("shape_ok"):
        return "stage_1_plan_shape (cycle_token_path length != route_pools+1)"
    # 2. live_quote facts (stage_6) — None ⇒ route unpriceable
    facts = o.get("stage_6_facts")
    if isinstance(facts, str):
        # An exception string here means live_quote raised BEFORE mev is ever
        # reached in fresh_fn — report it as the (earlier) blocking stage.
        return (f"stage_6_facts errored ({facts}) -> fresh_fn DENY at "
                "stage=live_quote (before mev)")
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
    # 3. hop_legs
    if isinstance(facts, dict) and not facts.get("n_hop_legs"):
        return ("stage_6 facts present but n_hop_legs=0 -> fresh_fn DENY at "
                "stage=hop_legs")
    # 4. MEV — real congestion + classification (stage_8)
    mev = o.get("stage_8_mev")
    if isinstance(mev, str):
        return f"stage_8_mev {mev} -> fresh_fn DENY at stage=mev"
    if isinstance(mev, dict):
        if mev.get("congestion_pct") is None:
            return ("stage_8_mev real Base congestion unavailable "
                    "(eth_feeHistory gasUsedRatio) -> fresh_fn DENY at "
                    "stage=mev (fail-closed)")
        if mev.get("mev_ok") is not True:
            return (f"stage_8_mev risk={mev.get('label')} "
                    f"(score={mev.get('score')}) -> mev_ok gate will DENY")
    # 5. economics (fresh_fn evaluates this before head/flash-loan reads)
    econ = o.get("stage_9_economics", {})
    if isinstance(econ, dict) and econ and not econ.get("economics_inputs_present", True):
        return "stage_9_economics unavailable -> fresh_fn DENY at economics"
    # 6. head block
    hb = o.get("stage_3_head_block")
    if not isinstance(hb, int):
        return (f"stage_3_head_block unavailable ({hb}) -> block_freshness "
                "gate will DENY")
    # 7. borrow-token price
    px = o.get("stage_4_borrow_price_usd")
    if not isinstance(px, (int, float)):
        return (f"stage_4_borrow_price_usd unavailable ({px}) -> flashloan/"
                "price gate will DENY")
    # 8. flash-loan availability
    fl = o.get("stage_7_flashloan_availability", {})
    if fl.get("available") is not True:
        return f"stage_7_flashloan_availability not True ({fl.get('available')})"
    # 9. all-in gas/economics (after head + flash-loan availability)
    all_in = o.get("stage_10_all_in_cost", {})
    if isinstance(all_in, dict) and all_in and all_in.get("available") is False:
        return "stage_10_all_in_cost unavailable -> fresh_fn DENY (fail-closed)"
    gates = o.get("stage_11_prebroadcast_gates", {})
    if isinstance(gates, dict):
        for key in ("block_freshness", "reorg_protection", "deadline", "price_ok", "tvl_ok"):
            if gates.get(key) is False:
                return f"stage_11_prebroadcast_gates.{key}=false -> PreBroadcastValidator DENY"
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
            # M3 consumes the flash-loan verifier's evidence bundle, not the
            # newest bundle across every scanner. The latter was the runtime
            # boundary that discarded genuine flash-loan hop block provenance.
            doc = await db.evidence_bundles.find_one(
                _flash_loan_evidence_filter("CONFIRMED"),
                sort=[("created_at", -1)])
            doc = doc or await db.evidence_bundles.find_one(
                _flash_loan_evidence_filter(), sort=[("created_at", -1)])
            if doc:
                plan = _plan_from_evidence(doc)
                audit["opportunity"]["evidence_bundle"] = {
                    "bundle_id": doc.get("bundle_id"),
                    "source_component": doc.get("source_component"),
                    "quote_hop_blocks": [
                        h.get("block_number") for h in
                        ((doc.get("quotes") or {}).get("hop_legs") or [])
                        if isinstance(h, dict) and h.get("block_number") is not None
                    ],
                    "selected_quote_block": plan.get("quoted_block"),
                }
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
    # Machine-readable audit: pure JSON only. Runtime logs go to STDERR (see
    # basicConfig above); the audit JSON goes to STDOUT and, when
    # ARBICORE_M3_AUDIT_FILE is set, to that file — so `python -m json.tool`
    # never sees interleaved log lines ("Extra data").
    payload = json.dumps(audit, indent=2, default=str)
    audit_file = os.environ.get("ARBICORE_M3_AUDIT_FILE")
    if audit_file:
        with open(audit_file, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
        logging.getLogger("scripts.m3_0_vps_validate").info(
            "audit JSON written to %s", audit_file)
    print(payload)


if __name__ == "__main__":
    asyncio.run(main())
