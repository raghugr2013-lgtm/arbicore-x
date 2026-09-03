#!/usr/bin/env python3
"""ArbiCore X · Spread Widener Watch — READ-ONLY market-edge monitor.

Continuously (or once) evaluates the REAL gross/net edge of every canonical Base
route cycle against live RPC and FLAGS the moment any route's edge turns positive
enough to be worth a full M3.0 validation. It NEVER signs, NEVER broadcasts, and
NEVER lowers an economics threshold — it only tells you WHICH route to run through
``scripts.m3_0_vps_validate`` / ``scripts.m3_0_real_candidate_scan`` next.

Route universe:
  * fee-tier / cross-DEX 2-hop cycles auto-enumerated from the canonical registry
    (every token pair that has >= 2 pools), token borrowed must be flash-loanable.
  * plus any explicit cycles from CONFIRMED evidence bundles in Mongo (freshest first).

Edge per route (all from genuine on-chain reads, nothing fabricated):
  * gross_profit_pct  — from the live quote provider (M2.1 + M2.6 TVL)
  * est_net_usd       — from FlashLoanEconomicsAssessor (gas/fees/MEV applied),
                        MEV level from REAL eth_feeHistory congestion.
A route is flagged ``worth_m3_validation`` when:
  est_net_usd >= ARBICORE_SPREAD_WATCH_MIN_NET_USD (default = M3 floor 25 + buffer 10 = 35)
  OR gross_profit_pct >= ARBICORE_SPREAD_WATCH_MIN_GROSS_PCT (default 0.0).

Requires: ARBICORE_RPC_URL(+_BASE) and ARBICORE_USD_NUMERAIRE=USDC.
Env: ARBICORE_SPREAD_WATCH_INTERVAL_S (>0 → loop), ARBICORE_SPREAD_WATCH_BORROW_USD
     (default 10000), ARBICORE_M3_AUDIT_FILE (write clean JSON snapshot).
Safety: read-only. No broadcaster is constructed here at all.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional


def _worth_m3(net: Optional[float], min_net: float) -> bool:
    """A route is worth a full M3 validation ONLY when it was fully priced
    (net computed) AND its estimated net clears the M3 floor+buffer. A positive
    gross with a still-negative net is surfaced separately as ``edge_positive``
    (an early spread signal) but does NOT trigger M3 — M3 would only deny it at
    the profit buffer."""
    return bool(net is not None and net >= min_net)


def _near_threshold(rows, min_net: float, band: float, top: int):
    """Priced routes still BELOW min_net but within ``band``, nearest first."""
    for r in rows:
        r["net_gap_usd"] = _net_gap(r.get("est_net_usd"), min_net)
    near = sorted(
        [r for r in rows if r.get("net_gap_usd") is not None
         and 0.0 < r["net_gap_usd"] <= band],
        key=lambda r: r["net_gap_usd"])[:top]
    for r in near:
        r["near_threshold"] = True
    return near


def _net_gap(net: Optional[float], min_net: float) -> Optional[float]:
    """Distance below the min-net threshold: ``min_net - net``. >0 ⇒ still below
    threshold by this much (smaller = nearer); <=0 ⇒ already at/above threshold.
    None when the route was not fully priced."""
    return None if net is None else (min_net - net)


def _cfg_f(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, "") or default)
    except (TypeError, ValueError):
        return default


def _enumerate_cycles() -> List[Dict[str, Any]]:
    """Auto-build 2-hop fee-tier / cross-DEX cycles from the canonical registry."""
    from arbicore.discovery.base_pool_registry import get_canonical_pools
    from arbicore.discovery.base_venues import canonical_symbol, BORROW_TOKENS

    borrowable = {canonical_symbol(s) for s in BORROW_TOKENS}
    by_pair: Dict[frozenset, List[Any]] = {}
    for p in get_canonical_pools():
        key = frozenset((p.token0_symbol, p.token1_symbol))
        by_pair.setdefault(key, []).append(p)

    cycles: List[Dict[str, Any]] = []
    for pair, pools in by_pair.items():
        if len(pools) < 2:
            continue
        syms = list(pair)
        # borrow token = a flash-loanable member of the pair
        borrow = next((s for s in syms if s in borrowable), None)
        if borrow is None:
            continue
        other = syms[0] if syms[1] == borrow else syms[1]
        for i in range(len(pools)):
            for j in range(len(pools)):
                if i == j:
                    continue
                cycles.append({
                    "name": f"{borrow}/{other} {pools[i].canonical_id} -> {pools[j].canonical_id}",
                    "borrow_token": borrow,
                    "route_pools": [pools[i].canonical_id, pools[j].canonical_id],
                    "cycle_token_path": [borrow, other, borrow]})
    return cycles


async def _load_confirmed_cycles(limit: int = 20) -> List[Dict[str, Any]]:
    """Freshest CONFIRMED evidence bundles from Mongo → cycle plans (best-effort)."""
    out: List[Dict[str, Any]] = []
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
        cur = db.evidence_bundles.find(
            {"verification_status": "CONFIRMED"}).sort("created_at", -1).limit(limit)
        async for doc in cur:
            r = doc.get("route", {})
            if r.get("route_pools") and r.get("cycle_token_path"):
                out.append({
                    "name": f"CONFIRMED:{doc.get('opportunity_id') or doc.get('bundle_id')}",
                    "borrow_token": doc.get("borrow_token"),
                    "route_pools": r["route_pools"],
                    "cycle_token_path": r["cycle_token_path"]})
    except Exception:  # noqa: BLE001 — no Mongo / no bundles ⇒ skip
        pass
    return out


async def _evaluate(cycles, quote_provider, econ, congestion_pct, mev, borrow_usd):
    from arbicore.models.enums import MevRiskLevel
    rows: List[Dict[str, Any]] = []
    for c in cycles:
        borrow = (c.get("borrow_token") or "").upper()
        hm = {"chain": "base", "provider": "balancer_v2",
              "borrow_token": borrow, "route_pools": c["route_pools"],
              "cycle_token_path": c["cycle_token_path"]}
        try:
            facts = await quote_provider(hm, borrow_usd)
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": c["name"], "error": f"{type(exc).__name__}: {exc}"})
            continue
        if not facts or not (facts.get("hop_legs")):
            rows.append({"name": c["name"], "route_quote_status":
                         (facts or {}).get("route_quote_status"),
                         "gross_profit_pct": None, "est_net_usd": None,
                         "worth_m3_validation": False})
            continue
        status = facts.get("route_quote_status")
        gross = facts.get("gross_profit_pct")
        # Only trust FULLY-priced routes (mirrors M3 fresh_quote gate). A
        # non-"ok" status means >=1 hop was unpriceable/degraded (often just
        # public-RPC rate-limiting) and its gross_profit_pct is meaningless —
        # never flag those. Also refuse implausible spreads (quote anomaly).
        max_gross = _cfg_f("ARBICORE_SPREAD_WATCH_MAX_GROSS_PCT", 50.0)
        if status != "ok" or gross is None or abs(float(gross)) > max_gross:
            rows.append({"name": c["name"], "route_pools": c["route_pools"],
                         "route_quote_status": status,
                         "gross_profit_pct": gross, "est_net_usd": None,
                         "min_pool_tvl_usd_in_route": facts.get("min_pool_tvl_usd_in_route"),
                         "note": "not fully priceable / anomaly — not flagged",
                         "worth_m3_validation": False})
            continue
        # real MEV level from real congestion (never fabricated)
        if congestion_pct is None:
            level, label = MevRiskLevel.MEDIUM, "MEDIUM"
        else:
            mv = mev.classify(source_chain_congestion=congestion_pct,
                              destination_chain_congestion=congestion_pct,
                              asset=borrow, notional_usd=borrow_usd, is_atomic=True)
            level, label = mv["level"], mv["label"]
        try:
            e = econ.assess(
                provider="balancer_v2", chain="base", borrow_token=borrow,
                borrow_amount_usd=borrow_usd, hop_legs=list(facts.get("hop_legs") or []),
                signal_categories=["balancer_v2", "base"], real_outcomes=[],
                synthetic_outcomes=[], gross_profit_pct=float(gross or 0.0),
                mev_risk_level=level, gas_cost_usd_override=facts.get("gas_cost_usd"),
                tx_gas_units=facts.get("tx_gas_units"))
            net = e.atomic_profit_usd
        except Exception as exc:  # noqa: BLE001
            net = None
            rows.append({"name": c["name"], "gross_profit_pct": gross,
                         "est_net_usd": None, "econ_error":
                         f"{type(exc).__name__}: {exc}", "worth_m3_validation": False})
            continue
        rows.append({
            "name": c["name"], "route_pools": c["route_pools"],
            "borrow_token": borrow,
            "route_quote_status": facts.get("route_quote_status"),
            "gross_profit_pct": gross, "est_net_usd": net,
            "min_pool_tvl_usd_in_route": facts.get("min_pool_tvl_usd_in_route"),
            "mev_label": label, "congestion_pct": congestion_pct,
        })
    return rows


async def _scan_once(focus_route_pools=None) -> Dict[str, Any]:
    from arbicore.execution.quoter import QuoterRegistry
    from arbicore.searcher.runtime import (make_base_eth_call_from_env,
                                            build_base_tvl_provider,
                                            make_base_congestion_source_from_env)
    from arbicore.searcher.price_feed import build_base_price_feed_from_env
    from arbicore.scanners.flash_loan_arbitrage.live_quote_provider import (
        make_live_quote_provider)
    from arbicore.scanners.flash_loan_arbitrage.economics import (
        FlashLoanEconomicsAssessor)
    from arbicore.scanners.cross_chain_arbitrage.bridge_intelligence import (
        MevRiskScorer)
    from arbicore.intelligence.roi_probability import ROIProbabilityEngine
    from arbicore.searcher.aero_resolver import resolve_and_propagate

    min_net = _cfg_f("ARBICORE_SPREAD_WATCH_MIN_NET_USD",
                     _cfg_f("ARBICORE_MIN_NET_PROFIT_USD", 25.0)
                     + _cfg_f("ARBICORE_SAFETY_BUFFER_USD", 10.0))
    min_gross = _cfg_f("ARBICORE_SPREAD_WATCH_MIN_GROSS_PCT", 0.0)
    borrow_usd = _cfg_f("ARBICORE_SPREAD_WATCH_BORROW_USD", 10000.0)

    eth_call = make_base_eth_call_from_env()
    if eth_call is None:
        return {"error": "no Base RPC configured (fail-closed)",
                "ts": time.time()}
    quoter = QuoterRegistry()
    price_feed = build_base_price_feed_from_env(quoter)
    tvl_provider = (build_base_tvl_provider(eth_call, price_feed.price_source)
                    if price_feed else None)
    quote_provider = make_live_quote_provider(quoter, tvl_provider=tvl_provider)
    econ = FlashLoanEconomicsAssessor(
        roi_engine=ROIProbabilityEngine(min_sample=8, winsorize_pct=0.05))
    mev = MevRiskScorer()
    cong_src = make_base_congestion_source_from_env()
    congestion = await cong_src() if cong_src else None

    cycles = await _load_confirmed_cycles() + _enumerate_cycles()
    # Focused re-sampling: restrict to a caller-supplied set of near/flagged routes.
    if focus_route_pools:
        focus_set = {tuple(x) for x in focus_route_pools}
        cycles = [c for c in cycles if tuple(c["route_pools"]) in focus_set]
    max_routes = int(_cfg_f("ARBICORE_SPREAD_WATCH_MAX_ROUTES", 0.0))
    if max_routes > 0:
        cycles = cycles[:max_routes]
    # propagate Aerodrome/Slipstream addresses for all routes (TVL alignment)
    all_pools = [p for c in cycles for p in c["route_pools"]]
    try:
        await resolve_and_propagate(eth_call, all_pools,
                                    get_block=price_feed._head_block if price_feed else None)
    except Exception:  # noqa: BLE001
        pass

    rows = await _evaluate(cycles, quote_provider, econ, congestion, mev, borrow_usd)
    for r in rows:
        net = r.get("est_net_usd")
        gross = r.get("gross_profit_pct")
        # net computed ⇒ route was fully priced + plausible
        r["edge_positive"] = bool(net is not None and gross is not None
                                  and gross >= min_gross)
        r["worth_m3_validation"] = _worth_m3(net, min_net)
    ranked = sorted(rows, key=lambda x: (x.get("est_net_usd") is None,
                                         -(x.get("est_net_usd") or -1e9)))
    flagged = [r for r in ranked if r.get("worth_m3_validation")]

    # READ-ONLY near-threshold signal: priced routes still BELOW min_net but
    # within a small band — the "almost there" set to watch/sample more often.
    # This never lowers min_net and never triggers signing/broadcast.
    near_band = _cfg_f("ARBICORE_SPREAD_WATCH_NEAR_BAND_USD", 25.0)
    near_top = int(_cfg_f("ARBICORE_SPREAD_WATCH_NEAR_TOP", 10.0))
    near = _near_threshold(rows, min_net, near_band, near_top)
    # union of qualifying + almost-there routes → candidates for focused sampling
    focus_pools = ([r["route_pools"] for r in flagged]
                   + [r["route_pools"] for r in near])

    return {
        "ts": time.time(), "congestion_pct": congestion,
        "focus": bool(focus_route_pools),
        "thresholds": {"min_net_usd": min_net, "min_gross_pct": min_gross,
                       "borrow_usd": borrow_usd, "near_band_usd": near_band},
        "routes_scanned": len(rows), "flagged_count": len(flagged),
        "edge_positive_count": sum(1 for r in rows if r.get("edge_positive")),
        "near_threshold_count": len(near),
        "flagged": flagged,
        "near_threshold": near,
        "focus_route_pools": focus_pools,
        "top5_by_net": ranked[:5],
        "safe": True, "signed_or_broadcast": False,
    }


def _emit(snap: Dict[str, Any], audit_file: Optional[str]) -> None:
    payload = json.dumps(snap, indent=2, default=str)
    if audit_file:
        with open(audit_file, "w", encoding="utf-8") as fh:
            fh.write(payload + "\n")
    print(payload, flush=True)
    log = logging.getLogger("arbicore.spread_watch")
    if snap.get("flagged"):
        log.warning("SPREAD WIDENER: %d route(s) now worth M3 validation — run "
                    "scripts.m3_0_vps_validate with the flagged route_pools",
                    snap["flagged_count"])
    elif snap.get("near_threshold_count"):
        nearest = snap["near_threshold"][0]
        log.warning("NEAR THRESHOLD: %d route(s) within $%.2f of min_net; "
                    "closest gap=$%.2f (%s) — read-only, no action taken",
                    snap["near_threshold_count"],
                    snap["thresholds"]["near_band_usd"],
                    nearest.get("net_gap_usd"), nearest.get("name"))


async def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    interval = _cfg_f("ARBICORE_SPREAD_WATCH_INTERVAL_S", 0.0)
    focus_interval = _cfg_f("ARBICORE_SPREAD_WATCH_FOCUS_INTERVAL_S", 0.0)
    audit_file = os.environ.get("ARBICORE_M3_AUDIT_FILE")

    while True:
        snap = await _scan_once()
        _emit(snap, audit_file)
        if interval <= 0:
            break
        focus = snap.get("focus_route_pools") or []
        # Optionally sample the near-threshold / flagged routes more often
        # (read-only) BETWEEN full passes, without lowering any threshold.
        if focus_interval > 0 and focus:
            elapsed = 0.0
            while elapsed + focus_interval < interval:
                await asyncio.sleep(focus_interval)
                elapsed += focus_interval
                _emit(await _scan_once(focus_route_pools=focus), audit_file)
            await asyncio.sleep(max(0.0, interval - elapsed))
        else:
            await asyncio.sleep(interval)


if __name__ == "__main__":
    asyncio.run(main())
