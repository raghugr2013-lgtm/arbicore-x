#!/usr/bin/env python3
"""VPS read-only RUNTIME certification — real on-chain evidence, fail-closed.

Composes ONLY existing read-only building blocks and, per chain × venue × pair,
records the REAL runtime state advance:

  DISCOVERABLE  -> live pool resolution (getPool / getPair / poolByPair + state)
  QUOTABLE      -> live QuoterRegistry route quote (single hop, probe notional)
  LIQ_VERIFIED  -> on-chain liquidity/reserves > 0 from the resolved pool
  GROSS_ECON    -> round-trip A->B->A pre-cost gross spread (informational only;
                   NOT net profit, NOT execution readiness)

It NEVER signs, broadcasts, quotes-for-execution, changes any mode, or fabricates
a pool/quote/liquidity/spread. A chain without an operator RPC is skipped
(fail-closed). Algebra venues are DISCOVERABLE but have no quoter adapter yet
(reported honestly). Real NET economics (gas + flash-loan + slippage), fork
simulation, and any limited-live eligibility remain SEPARATE downstream gates —
this report never asserts them.

Usage:  python3 -m scripts.vps_runtime_certify [--json] [--pairs N]
Env:    PROVIDER_RPC_URLS_<CHAIN>  (or ARBICORE_RPC_URL_<CHAIN>)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_runtime_cert")

_PROBE_PAIRS = [("WETH", "USDC"), ("WETH", "USDT"), ("USDC", "USDT"),
                ("WBNB", "USDT"), ("WMATIC", "USDC"), ("WETH", "DAI")]


def _borrow_symbol(pair):
    # borrow the non-stable side when present, else the first token
    a, b = pair
    stables = {"USDC", "USDT", "DAI", "USDC.E"}
    return a if a.upper() not in stables else b


async def _head_block(chain: str):
    """Real head block + latency for the chain's configured RPC (read-only)."""
    import httpx
    from arbicore.config.persistent import resolve_rpc_url_from_env
    url = (os.environ.get(f"PROVIDER_RPC_URLS_{chain.upper()}")
           or os.environ.get(f"ARBICORE_RPC_URL_{chain.upper()}")
           or resolve_rpc_url_from_env(chain) or "")
    url = url.split(",")[0].strip()
    if not url:
        return {"rpc": None, "block": None, "latency_ms": None, "error": "no_rpc"}
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post(url, json={"jsonrpc": "2.0", "id": 1,
                                        "method": "eth_blockNumber", "params": []})
            j = r.json()
        blk = int(j["result"], 16) if "result" in j else None
        err = None if blk is not None else str(j.get("error"))[:120]
    except Exception as exc:  # noqa: BLE001
        blk, err = None, f"{type(exc).__name__}: {exc}"
    return {"rpc": url.split("//")[-1].split("/")[0], "block": blk,
            "latency_ms": int((time.time() - t0) * 1000), "error": err}


def _probe_tasks(chain: str):
    from scripts.vps_multichain_preflight import _build_probe_tasks
    return _build_probe_tasks(chain)


async def _quote_pool(reg, chain: str, pool: dict, borrow_addr: str, borrow_wei: int):
    """Single FORWARD quote borrow_addr -> other token at the probe notional.
    Returns (quotable, amount_out_wei, out_token, err). Read-only. Algebra has no
    quoter adapter yet (reported honestly, not fabricated)."""
    dex = pool.get("dex")
    t0, t1 = pool.get("token0"), pool.get("token1")
    fee = pool.get("fee")               # present for univ3 family; None for v2
    if dex in ("camelot_v3", "quickswap_v3"):
        return False, None, None, "algebra_quoter_not_wired"
    other = t1 if (borrow_addr or "").lower() == (t0 or "").lower() else t0
    hop = {"dex": dex, "token_in": borrow_addr, "token_out": other,
           "amount_in_wei": borrow_wei}
    if fee is not None:
        hop["fee"] = fee
    try:
        rq = await reg.quote_route(chain=chain, hops=[hop])
    except Exception as exc:  # noqa: BLE001
        return False, None, None, f"{type(exc).__name__}: {exc}"
    if rq.status != "ok":
        h0 = rq.hops[0] if rq.hops else None
        return False, None, None, (h0.status if h0 else rq.status)
    return True, rq.final_amount_out_wei, other, None


async def _certify_chain(chain: str, cap: int = 10):
    from arbicore.chains.registries import probe_amount_wei
    from arbicore.discovery.opportunity_engine import discover_pools_parallel
    from arbicore.searcher.runtime import make_eth_call_for_chain_from_env
    from arbicore.execution.quoter import QuoterRegistry
    from arbicore.runtime.multichain_readiness import rpc_explicitly_configured

    head = await _head_block(chain)
    if not rpc_explicitly_configured(chain):
        return {"skipped": "no_operator_configured_rpc", "head": head, "rows": []}
    if chain in ("base", "base-sepolia"):
        return {"skipped": "base_canonical_use_m3_0_real_candidate_scan",
                "head": head, "rows": []}

    tasks = _probe_tasks(chain)[:cap]
    resolved = await discover_pools_parallel(
        tasks, eth_call_for_chain=make_eth_call_for_chain_from_env,
        max_concurrency=4, per_task_timeout_s=12.0)

    from arbicore.chains.registries import tokens_for
    toks = tokens_for(chain)
    reg = QuoterRegistry()
    rows = []
    # (pair, borrow_sym) -> {venue: out_wei} for cross-venue spread
    xven: dict = {}
    for t, r in zip(tasks, resolved):
        pool = r.get("pool") or {}
        borrow_sym = _borrow_symbol(tuple(t["pair"].split("/")))
        row = {"venue": t["dex"], "abi": t["abi"], "pair": t["pair"], "fee": t["fee"],
               "borrow_sym": borrow_sym,
               "discoverable": bool(r.get("resolved")),
               "pool_address": pool.get("pool_address"),
               "liquidity_verified": bool((pool.get("liquidity") or 0) > 0
                                          or (pool.get("reserve0") or 0) > 0),
               "quotable": False, "out_wei": None, "reason": r.get("reason")}
        if row["discoverable"]:
            borrow_addr = (toks.get(borrow_sym) or {}).get("address")
            borrow_wei = probe_amount_wei(chain, borrow_sym) or 0
            if borrow_addr and borrow_wei > 0:
                q, out_wei, _out_tok, qerr = await _quote_pool(
                    reg, chain, pool, borrow_addr, borrow_wei)
                row["quotable"] = q
                row["out_wei"] = out_wei
                if not q:
                    row["reason"] = f"quote:{qerr}"
                elif out_wei and out_wei > 0:
                    key = (t["pair"], borrow_sym)
                    xven.setdefault(key, {})[t["venue"] if False else t["dex"]] = out_wei
            else:
                row["reason"] = "no_probe_amount"
        rows.append(row)

    # cross-venue gross spread (PRE-COST): same input, same output token, ≥2 venues
    cross = []
    for (pair, bsym), outs in xven.items():
        if len(outs) < 2:
            continue
        lo, hi = min(outs.values()), max(outs.values())
        gross_pct = ((hi / lo) - 1.0) * 100.0 if lo else None
        cross.append({"pair": pair, "borrow": bsym,
                      "venues": {k: str(v) for k, v in outs.items()},
                      "gross_spread_pct": round(gross_pct, 4) if gross_pct is not None else None})
    return {"skipped": None, "head": head, "rows": rows, "cross_venue": cross}


def _anvil_available() -> bool:
    from shutil import which
    return which("anvil") is not None


async def build_runtime_certification(max_pairs=None) -> dict:
    from arbicore.runtime.multichain_readiness import supported_networks
    chains = supported_networks()
    per_chain = {}
    cap = int(max_pairs) if max_pairs else 10
    for c in chains:
        per_chain[c] = await _certify_chain(c, cap=cap)

    # aggregate the state ladder counts over ALL probe rows (real evidence only)
    agg = {"probe_rows": 0, "discoverable": 0, "liquidity_verified": 0,
           "quotable": 0, "algebra_quote_gap": 0,
           "cross_venue_pairs": 0, "cross_venue_best_pct": None}
    blockers: dict = {}
    best = None
    for c, res in per_chain.items():
        for row in res["rows"]:
            agg["probe_rows"] += 1
            if row["discoverable"]:
                agg["discoverable"] += 1
            if row["liquidity_verified"]:
                agg["liquidity_verified"] += 1
            if row["quotable"]:
                agg["quotable"] += 1
            if row.get("reason") == "quote:algebra_quoter_not_wired":
                agg["algebra_quote_gap"] += 1
            rsn = row.get("reason") or ("quotable" if row["quotable"] else "?")
            blockers[rsn] = blockers.get(rsn, 0) + 1
        for cv in res.get("cross_venue", []):
            agg["cross_venue_pairs"] += 1
            g = cv.get("gross_spread_pct")
            if g is not None and (best is None or g > best):
                best = g
    agg["cross_venue_best_pct"] = best

    return {
        "safety": {"posture": "SHADOW / detection-only / fail-closed",
                   "signing": False, "broadcast": False, "auto_execution": False,
                   "full_live": False, "withdrawals": False},
        "rpc_source": "operator/public read-only (PROVIDER_RPC_URLS_<CHAIN>)",
        "simulation": {"anvil_available": _anvil_available(),
                       "note": "fork simulation requires anvil (VPS)"},
        "per_chain": per_chain,
        "aggregate": agg,
        "blockers": blockers,
        "limited_live_proven": False,
        "execution_ready_candidate": None,
        "note": ("Cross-venue gross spread is PRE-COST (no gas/flash-loan/slippage) "
                 "and is the DEX-arb signal only — never net profit or execution "
                 "readiness. Real NET economics + fork simulation + limited-live "
                 "eligibility remain separate downstream gates (Base: "
                 "scripts.m3_0_real_candidate_scan). No cell is limited-live "
                 "eligible from this read-only report."),
    }


def _human(rep: dict) -> str:
    a = rep["aggregate"]
    L = ["=" * 78, "ARBICORE X — VPS READ-ONLY RUNTIME CERTIFICATION", "=" * 78,
         f"rpc_source        : {rep['rpc_source']}",
         f"safety            : signing={rep['safety']['signing']} broadcast={rep['safety']['broadcast']} "
         f"full_live={rep['safety']['full_live']}",
         f"anvil(sim)        : {rep['simulation']['anvil_available']}",
         "-" * 78,
         f"probe_rows        : {a['probe_rows']}",
         f"discoverable      : {a['discoverable']}",
         f"liquidity_verified: {a['liquidity_verified']}",
         f"quotable          : {a['quotable']}",
         f"algebra_quote_gap : {a['algebra_quote_gap']}",
         f"cross_venue_pairs : {a['cross_venue_pairs']}  best_gross_precost%={a['cross_venue_best_pct']}",
         f"limited_live_proven: {rep['limited_live_proven']}",
         f"execution_ready   : {rep['execution_ready_candidate']}",
         "-" * 78]
    for c, res in rep["per_chain"].items():
        head = res["head"]
        hb = f"block={head.get('block')} {head.get('latency_ms')}ms" if head else "n/a"
        if res["skipped"]:
            L.append(f"{c:<10} SKIPPED: {res['skipped']}  ({hb} err={head.get('error')})")
            continue
        d = sum(1 for r in res["rows"] if r["discoverable"])
        q = sum(1 for r in res["rows"] if r["quotable"])
        lv = sum(1 for r in res["rows"] if r["liquidity_verified"])
        L.append(f"{c:<10} {hb}  rows={len(res['rows'])} discoverable={d} liq={lv} quotable={q}")
        for r in res["rows"]:
            if r["discoverable"]:
                L.append(f"{'':<12}{r['venue']:<16} {r['pair']:<11} fee={str(r['fee']):<5} "
                         f"quotable={str(r['quotable']):<5} out_wei={r['out_wei']} "
                         f"reason={r['reason']}")
        for cv in res.get("cross_venue", []):
            L.append(f"{'':<12}CROSS-VENUE {cv['pair']} borrow={cv['borrow']} "
                     f"gross_precost%={cv['gross_spread_pct']} venues={list(cv['venues'])}")
    L += ["-" * 78, rep["note"], "=" * 78]
    return "\n".join(L)


async def _amain() -> int:
    max_pairs = None
    if "--pairs" in sys.argv:
        try:
            max_pairs = int(sys.argv[sys.argv.index("--pairs") + 1])
        except Exception:  # noqa: BLE001
            max_pairs = None
    rep = await build_runtime_certification(max_pairs=max_pairs)
    if "--json" in sys.argv:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(_human(rep))
    return 0


def main() -> None:
    sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
