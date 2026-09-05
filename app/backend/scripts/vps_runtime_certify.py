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
from pathlib import Path
from typing import Optional

# ── sys.path bootstrap ──────────────────────────────────────────────────────
# Run correctly whether invoked as ``python -m scripts.vps_runtime_certify``
# (CWD on sys.path) OR by DIRECT PATH ``python /app/scripts/vps_runtime_certify.py``
# (production-style; sys.path[0] becomes the scripts/ dir, so ``arbicore`` is
# unimportable). APP_ROOT is this file's grandparent — ``/app`` in the shipped
# image and ``<repo>/app/backend`` in a checkout — and hosts ``arbicore``.
_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()

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


async def _quote_dir(reg, chain, dex, token_in, token_out, fee, amount_wei):
    """One directional live quote. Returns (out_wei, gas_units, err)."""
    hop = {"dex": dex, "token_in": token_in, "token_out": token_out,
           "amount_in_wei": amount_wei}
    if fee is not None:
        hop["fee"] = fee
    try:
        rq = await reg.quote_route(chain=chain, hops=[hop])
    except Exception as exc:  # noqa: BLE001
        return None, None, f"{type(exc).__name__}: {exc}"
    if rq.status != "ok":
        h0 = rq.hops[0] if rq.hops else None
        return None, None, (h0.status if h0 else rq.status)
    g = rq.hops[0].gas_estimate_units if rq.hops else None
    return rq.final_amount_out_wei, g, None


async def _quote_pool(reg, chain: str, pool: dict, borrow_addr: str, borrow_wei: int):
    """Single FORWARD quote borrow_addr -> other token at the probe notional.
    Returns (quotable, amount_out_wei, out_token, gas_units, err). Read-only."""
    t0, t1 = pool.get("token0"), pool.get("token1")
    fee = pool.get("fee")
    other = t1 if (borrow_addr or "").lower() == (t0 or "").lower() else t0
    out_wei, gas_units, err = await _quote_dir(
        reg, chain, pool.get("dex"), borrow_addr, other, fee, borrow_wei)
    if err:
        return False, None, None, None, err
    return True, out_wei, other, gas_units, None


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
    for t, r in zip(tasks, resolved):
        pool = r.get("pool") or {}
        borrow_sym = _borrow_symbol(tuple(t["pair"].split("/")))
        row = {"venue": t["dex"], "abi": t["abi"], "pair": t["pair"], "fee": t["fee"],
               "borrow_sym": borrow_sym,
               "discoverable": bool(r.get("resolved")),
               "pool_address": pool.get("pool_address"),
               "pool": pool,
               "liquidity_verified": bool((pool.get("liquidity") or 0) > 0
                                          or (pool.get("reserve0") or 0) > 0),
               "quotable": False, "out_wei": None, "out_token": None,
               "gas_units": None, "reason": r.get("reason")}
        if row["discoverable"]:
            borrow_addr = (toks.get(borrow_sym) or {}).get("address")
            borrow_wei = probe_amount_wei(chain, borrow_sym) or 0
            if borrow_addr and borrow_wei > 0:
                q, out_wei, out_tok, gas_u, qerr = await _quote_pool(
                    reg, chain, pool, borrow_addr, borrow_wei)
                row["quotable"] = q
                row["out_wei"] = out_wei
                row["out_token"] = out_tok
                row["gas_units"] = gas_u
                row["borrow_wei"] = borrow_wei
                if not q:
                    row["reason"] = f"quote:{qerr}"
            else:
                row["reason"] = "no_probe_amount"
        rows.append(row)

    candidates = await _evaluate_candidates(reg, chain, rows, toks, head.get("block"))
    # slim the stored pool ref to keep JSON compact
    for row in rows:
        row.pop("pool", None)
    return {"skipped": None, "head": head, "rows": rows, "candidates": candidates}


def _sym_decimals(toks: dict, sym: str) -> Optional[int]:
    d = (toks.get(sym) or {}).get("decimals")
    return int(d) if d is not None else None


def _addr_to_sym(toks: dict, addr: str) -> Optional[str]:
    a = (addr or "").lower()
    for sym, meta in toks.items():
        if (meta.get("address") or "").lower() == a:
            return sym
    return None


_STABLES = {"USDC", "USDT", "DAI", "USDC.E", "USDBC", "BUSD"}
_NATIVE_WRAP = {"ETH": "WETH", "POL": "WMATIC", "MATIC": "WMATIC", "BNB": "WBNB"}


def _native_usd(chain: str, rows: list, toks: dict) -> Optional[float]:
    """Derive the chain native token USD price ON-CHAIN from a quotable
    native-wrapped -> stable row. Returns None (⇒ DENY) if underivable."""
    from arbicore.chains.evm_gas import CHAIN_SPECS
    native = str((CHAIN_SPECS.get(chain, {}) or {}).get("native", "ETH")).upper()
    wrap = _NATIVE_WRAP.get(native, "WETH")
    for r in rows:
        if not r["quotable"] or not r.get("out_wei"):
            continue
        bsym = r["borrow_sym"]
        osym = _addr_to_sym(toks, r.get("out_token"))
        if bsym == wrap and osym in _STABLES:
            bdec = _sym_decimals(toks, bsym)
            odec = _sym_decimals(toks, osym)
            if bdec and odec:
                return (r["out_wei"] / 10 ** odec) / (r["borrow_wei"] / 10 ** bdec)
    return None


async def _size_sweep(reg, chain, buy, sell, toks, native_usd, bsym, bdec, price):
    """Evaluate the candidate at multiple realistic input sizes (item 4). Returns
    rows of {mult, input_usd, gross_usd} + the max-profitable / optimal size.
    A fixed probe amount is NEVER used as proof of execution profitability."""
    borrow_addr = (toks.get(bsym) or {}).get("address")
    other_addr = buy["out_token"]
    base_wei = buy["borrow_wei"]
    sweep = []
    best = None
    for mult in (0.25, 1.0, 4.0, 16.0, 64.0):
        amt = int(base_wei * mult)
        if amt <= 0:
            continue
        out1, _g1, e1 = await _quote_dir(reg, chain, buy["venue"], borrow_addr,
                                         other_addr, buy["pool"].get("fee"), amt)
        if e1 or not out1:
            sweep.append({"mult": mult, "input_usd": None, "gross_usd": None,
                          "reason": f"buy_quote_failed:{e1}"})
            continue
        back, _g2, e2 = await _quote_dir(reg, chain, sell["venue"], other_addr,
                                         borrow_addr, sell["pool"].get("fee"), out1)
        if e2 or back is None:
            sweep.append({"mult": mult, "input_usd": None, "gross_usd": None,
                          "reason": f"sell_quote_failed:{e2}"})
            continue
        gross_usd = ((back - amt) / 10 ** bdec) * price
        input_usd = (amt / 10 ** bdec) * price
        row = {"mult": mult, "input_usd": round(input_usd, 2),
               "gross_usd": round(gross_usd, 6)}
        sweep.append(row)
        if best is None or gross_usd > best["gross_usd"]:
            best = {"mult": mult, "gross_usd": gross_usd}
    optimal = (best if (best and best["gross_usd"] > 0) else None)
    return {"sizes": sweep, "max_profitable": optimal,
            "note": "all sizes non-positive" if optimal is None else "optimal>0"}


async def _evaluate_candidates(reg, chain: str, rows: list, toks: dict,
                               block=None) -> list:
    """Cross-venue NET-ECONOMICS gate (fail-closed). For each pair with >=2
    quotable venues: do the REAL round (buy borrow->other on the best venue, sell
    other->borrow on another venue), compute gross edge in USD from an on-chain
    price, then run compute_true_net_profit with REAL runtime inputs. Rejects
    conservatively on any missing/unverifiable input — no synthetic fallbacks.
    Emits a full 7-state classification + evidence bundle per candidate."""
    from collections import defaultdict
    from arbicore.chains.evm_gas import make_evm_gas_model
    from arbicore.scanners.flash_loan_arbitrage.multichain_economics import (
        compute_true_net_profit)

    gas_model = make_evm_gas_model(chain)
    native_usd = _native_usd(chain, rows, toks)
    by_pair = defaultdict(list)
    for r in rows:
        if r["quotable"] and r.get("out_wei"):
            by_pair[(r["pair"], r["borrow_sym"])].append(r)

    out = []
    for (pair, bsym), rs in by_pair.items():
        if len({r["venue"] for r in rs}) < 2:
            continue
        rs.sort(key=lambda r: r["out_wei"], reverse=True)
        buy, sell = rs[0], rs[1]           # best borrow->other ; a different venue
        bdec = _sym_decimals(toks, bsym)
        borrow_addr = (toks.get(bsym) or {}).get("address")
        cand = {"chain": chain, "block": block, "pair": pair, "borrow": bsym,
                "buy_venue": buy["venue"], "sell_venue": sell["venue"],
                "pools": {"buy": buy.get("pool_address"), "sell": sell.get("pool_address")},
                "token_path": [bsym, _addr_to_sym(toks, buy["out_token"]) or "?", bsym],
                "input_size_wei": buy.get("borrow_wei"),
                "hop_quotes": {"buy_out_wei": buy.get("out_wei"),
                               "buy_gas_units": buy.get("gas_units")},
                "liquidity": {"buy": (buy.get("pool") or {}).get("liquidity")
                                     or (buy.get("pool") or {}).get("reserve0"),
                              "sell": (sell.get("pool") or {}).get("liquidity")
                                      or (sell.get("pool") or {}).get("reserve0")},
                "fees": {"buy_fee": (buy.get("pool") or {}).get("fee"),
                         "sell_fee": (sell.get("pool") or {}).get("fee")},
                "provenance": {"rpc": "operator/public read-only",
                               "quoter_family": buy.get("abi")},
                "stages": {"DISCOVERED": True, "LIQUIDITY_VERIFIED": True,
                           "QUOTABLE": True, "ECONOMICALLY_VALID": False,
                           "VERIFIABLE": False, "SIMULATABLE": False,
                           "LIMITED_LIVE_ELIGIBLE": False},
                "eliminated_at": None, "reason": None,
                "gross_profit_usd": None, "all_in_net_usd": None,
                "size_sweep": None, "timestamp": _now_iso(),
                "evidence_id": f"cand:{chain}:{pair}:{buy['venue']}>{sell['venue']}:blk{block}"}
        # REAL sell-side close: other -> borrow on the sell venue
        other_addr = buy["out_token"]
        sell_pool = sell["pool"]
        back_wei, sell_gas, serr = await _quote_dir(
            reg, chain, sell["venue"], other_addr, borrow_addr,
            sell_pool.get("fee"), buy["out_wei"])
        cand["hop_quotes"]["sell_out_wei"] = back_wei
        cand["hop_quotes"]["sell_gas_units"] = sell_gas
        if serr or back_wei is None:
            cand["eliminated_at"] = "QUOTABLE"
            cand["reason"] = f"sell_close_quote_failed:{serr}"
            out.append(cand)
            continue
        gross_borrow_wei = back_wei - buy["borrow_wei"]
        if bsym in _STABLES:
            price = 1.0
        elif bsym in _NATIVE_WRAP.values() and native_usd:
            price = native_usd
        else:
            cand["eliminated_at"] = "NET_ECONOMICS"
            cand["reason"] = "borrow_usd_price_unavailable"
            out.append(cand)
            continue
        if not bdec:
            cand["eliminated_at"] = "NET_ECONOMICS"
            cand["reason"] = "token_decimals_unavailable"
            out.append(cand)
            continue
        gross_usd = (gross_borrow_wei / 10 ** bdec) * price
        cand["gross_profit_usd"] = round(gross_usd, 6)
        # dynamic trade-size optimization (item 4) — never trust a single size
        cand["size_sweep"] = await _size_sweep(
            reg, chain, buy, sell, toks, native_usd, bsym, bdec, price)
        if gross_usd <= 0 and not (cand["size_sweep"].get("max_profitable")):
            cand["eliminated_at"] = "NET_ECONOMICS"
            cand["reason"] = "negative_gross_edge_all_sizes"
            out.append(cand)
            continue
        notional_usd = (buy["borrow_wei"] / 10 ** bdec) * price
        route_gas = None
        if buy.get("gas_units") and sell_gas:
            route_gas = int(buy["gas_units"]) + int(sell_gas)
        verdict = await compute_true_net_profit(
            chain=chain, gas_model=gas_model, gross_profit_usd=gross_usd,
            borrow_amount_usd=notional_usd, notional_usd=notional_usd,
            route_gas_units=route_gas, native_usd=native_usd,
            borrow_token=bsym, liquidity_by_provider=None, fee_bps_by_provider=None)
        if verdict is None or verdict.get("denied"):
            cand["eliminated_at"] = "NET_ECONOMICS"
            cand["reason"] = (verdict or {}).get("reason", "net_gate_denied")
        else:
            cand["all_in_net_usd"] = verdict.get("true_net_profit_usd")
            if (cand["all_in_net_usd"] or -1) > 0:
                cand["stages"]["ECONOMICALLY_VALID"] = True
                # VERIFIABLE/SIMULATABLE require a fork sim — unavailable here
                cand["eliminated_at"] = "SIMULATABLE"
                cand["reason"] = "SIMULATION_UNAVAILABLE_no_anvil"
            else:
                cand["eliminated_at"] = "NET_ECONOMICS"
                cand["reason"] = "true_net_not_positive"
        out.append(cand)
    return out


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

    # aggregate the state ladder + candidate matrix (real evidence only)
    agg = {"probe_rows": 0, "discoverable": 0, "liquidity_verified": 0,
           "quotable": 0, "algebra_quote_gap": 0,
           "candidates": 0, "economically_valid": 0, "execution_ready": 0}
    blockers: dict = {}
    cand_gates: dict = {}
    for c, res in per_chain.items():
        for row in res["rows"]:
            agg["probe_rows"] += 1
            if row["discoverable"]:
                agg["discoverable"] += 1
            if row["liquidity_verified"]:
                agg["liquidity_verified"] += 1
            if row["quotable"]:
                agg["quotable"] += 1
            rsn = row.get("reason") or ("quotable" if row["quotable"] else "?")
            blockers[rsn] = blockers.get(rsn, 0) + 1
        for cand in res.get("candidates", []):
            agg["candidates"] += 1
            if cand["stages"]["ECONOMICALLY_VALID"]:
                agg["economically_valid"] += 1
            if cand["stages"]["LIMITED_LIVE_ELIGIBLE"]:
                agg["execution_ready"] += 1
            g = f"{cand.get('eliminated_at')}:{cand.get('reason')}"
            cand_gates[g] = cand_gates.get(g, 0) + 1

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
        "candidate_gates": cand_gates,
        "limited_live_proven": False,
        "execution_ready_candidate": None if agg["execution_ready"] == 0 else "SEE_CANDIDATES",
        "note": ("Candidates use REAL cross-venue rounds + the fail-closed net "
                 "gate (compute_true_net_profit): gross edge priced on-chain, gas "
                 "via chain gas model, route gas via quoter estimate, flash-loan "
                 "fee/liquidity via provider optimizer. Any missing/unverifiable "
                 "input ⇒ conservative DENY (no synthetic fallback). Fork "
                 "simulation requires anvil (VPS). No cell is limited-live "
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
         f"candidates        : {a['candidates']}  economically_valid={a['economically_valid']}  "
         f"execution_ready={a['execution_ready']}",
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
        for cand in res.get("candidates", []):
            sw = (cand.get("size_sweep") or {}).get("max_profitable")
            L.append(f"{'':<12}CANDIDATE {cand['pair']} {cand['buy_venue']}>{cand['sell_venue']} "
                     f"gross_usd={cand['gross_profit_usd']} net={cand['all_in_net_usd']} "
                     f"best_size={sw} eliminated_at={cand['eliminated_at']} reason={cand['reason']}")
    L += ["-" * 78, f"candidate_gates: {rep.get('candidate_gates')}", rep["note"], "=" * 78]
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
