#!/usr/bin/env python3
"""VPS multichain PREFLIGHT — READ-ONLY reachability + blocker report.

Run on the VPS (real per-chain RPC configured) as the first step of the
multichain runtime-certification phase. It ONLY composes existing read-only
building blocks and reports, per chain × venue × flash-loan provider:

  * operator RPC configuration + gas-model presence + the exact readiness
    blocker (arbicore.runtime.multichain_readiness)
  * structural quote-path connectivity (arbicore.discovery.opportunity_engine
    build_opportunity_matrix — quote_path_connected)
  * LIVE UniV3 pool resolution for a small deterministic probe set, using the
    canonical parallel resolver (discover_pools_parallel) over the SAME
    per-chain eth_call seam the live quote provider uses
    (searcher.runtime.make_eth_call_for_chain_from_env). Base is served by its
    canonical registry (use scripts.m3_0_real_candidate_scan for Base depth).
  * eligible flash-loan providers per chain (economics.FLASH_LOAN_PROVIDERS)

It NEVER signs, NEVER broadcasts, NEVER quotes-for-execution, NEVER enables any
mode, and NEVER fabricates a pool/TVL/quote. A chain with no operator RPC is
reported ``no_operator_configured_rpc`` and is skipped for the live probe
(fail-closed). This preflight tells the operator WHICH capability seams are
actually preventing real opportunities — the input to deciding whether any
additional venue resolvers are worth building.

Usage:
    python3 -m scripts.vps_multichain_preflight [--json]

Env: per-chain operator RPC (any recognised key), e.g.
    PROVIDER_RPC_URLS_ETHEREUM, PROVIDER_RPC_URLS_ARBITRUM,
    PROVIDER_RPC_URLS_OPTIMISM, PROVIDER_RPC_URLS_POLYGON,
    PROVIDER_RPC_URLS_BNB, PROVIDER_RPC_URLS_BASE  (or ARBICORE_RPC_URL_<CHAIN>)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_preflight")

# Deterministic major/stable pairs to probe (only those present in a chain's
# verified registry are used). No fabricated tokens.
_PROBE_PAIRS = [
    ("WETH", "USDC"), ("WETH", "USDT"), ("USDC", "USDT"),
    ("WBNB", "USDT"), ("WBNB", "USDC"), ("WMATIC", "USDC"),
]
_PROBE_FEES = (500, 3000)


def _build_probe_tasks(chain: str):
    from arbicore.chains.registries import tokens_for
    toks = tokens_for(chain)
    tasks = []
    seen = set()
    for a, b in _PROBE_PAIRS:
        if a not in toks or b not in toks:
            continue
        for fee in _PROBE_FEES:
            key = tuple(sorted([a, b])) + (fee,)
            if key in seen:
                continue
            seen.add(key)
            tasks.append({
                "chain": chain, "pair": f"{a}/{b}", "fee": fee,
                "token_a": toks[a]["address"], "token_b": toks[b]["address"],
            })
    return tasks


async def _live_pool_probe(chain: str):
    """Live UniV3 pool resolution via the canonical parallel resolver + the
    existing per-chain eth_call seam. Read-only. Returns per-task rows."""
    from arbicore.discovery.opportunity_engine import discover_pools_parallel
    from arbicore.searcher.runtime import make_eth_call_for_chain_from_env
    tasks = _build_probe_tasks(chain)
    if not tasks:
        return []
    # The seam returns a real eth_call ONLY when the chain has an operator RPC.
    results = await discover_pools_parallel(
        tasks, eth_call_for_chain=make_eth_call_for_chain_from_env,
        max_concurrency=4, per_task_timeout_s=8.0)
    rows = []
    for t, r in zip(tasks, results):
        pool = r.get("pool") or {}
        rows.append({
            "pair": t["pair"], "fee": t["fee"],
            "resolved": bool(r.get("resolved")),
            "pool_address": pool.get("pool_address"),
            "liquidity": pool.get("liquidity"),
            "reason": r.get("reason"),
        })
    return rows


def _providers_for(chain: str):
    from arbicore.scanners.flash_loan_arbitrage.economics import (
        FLASH_LOAN_PROVIDERS)
    return sorted(p for p, m in FLASH_LOAN_PROVIDERS.items()
                  if chain in (m.get("supports_chains") or ()))


async def build_preflight() -> dict:
    from arbicore.runtime.multichain_readiness import (
        build_multichain_readiness_report, rpc_explicitly_configured,
        supported_networks)
    from arbicore.discovery.opportunity_engine import build_opportunity_matrix

    readiness = build_multichain_readiness_report()
    matrix = build_opportunity_matrix()
    # index quote_path_connected venues per chain
    connected: dict = {}
    for row in matrix["rows"]:
        connected.setdefault(row["chain"], {})[row["venue"]] = (
            row["quote_path_connected"])

    networks = {}
    for chain in supported_networks():
        r = readiness["networks"][chain]
        has_rpc = rpc_explicitly_configured(chain)
        live_probe = None
        if has_rpc and chain not in ("base", "base-sepolia"):
            try:
                live_probe = await _live_pool_probe(chain)
            except Exception as exc:  # noqa: BLE001 — fail closed, never fabricate
                live_probe = [{"error": f"{type(exc).__name__}: {exc}"}]
        networks[chain] = {
            "rpc_configured": r["rpc_configured"],
            "economic_rpc_configured": r["economic_rpc_configured"],
            "gas_model": r["economic_eligibility"]["gas_model"],
            "route_universe_size": r["discovery"]["route_universe_size"],
            "readiness_blocker": r["blocker"],
            "quote_path_connected_venues": connected.get(chain, {}),
            "flash_loan_providers_eligible": _providers_for(chain),
            "live_pool_probe": live_probe,
            "live_pool_probe_note": (
                "base served by canonical registry — use "
                "scripts.m3_0_real_candidate_scan for Base depth"
                if chain in ("base", "base-sepolia")
                else ("skipped: no_operator_configured_rpc"
                      if not has_rpc else "read-only getPool + state validation")
            ),
        }
    return {
        "safety": {
            "posture": "SHADOW / detection-only / fail-closed",
            "signed": False, "broadcast": False, "quotes_for_execution": False,
            "limited_live_enabled": False,
        },
        "frozen_checkpoint": "1f1d68f841bb93ac62b3b9b857751b4bbf0ec16f",
        "networks": networks,
        "matrix_summary": matrix["summary"],
        "note": ("Preflight is reachability + blocker only. No cell is QUOTABLE, "
                 "ECONOMICALLY_VALID or LIMITED-LIVE eligible from this report; "
                 "live quote/TVL/economics/simulation/evidence remain mandatory "
                 "runtime gates (Base: scripts.m3_0_real_candidate_scan / "
                 "scripts.vps_canonical_audit)."),
    }


def _human(rep: dict) -> str:
    lines = ["=" * 72,
             "ARBICORE X — VPS MULTICHAIN PREFLIGHT (read-only reachability)",
             "=" * 72,
             f"frozen_checkpoint : {rep['frozen_checkpoint']}",
             f"matrix            : rows={rep['matrix_summary']['row_count']} "
             f"discoverable={rep['matrix_summary']['discoverable_count']} "
             f"quote_path_connected={rep['matrix_summary']['quote_path_connected_count']} "
             f"limited_live={rep['matrix_summary']['limited_live_eligible_count']}",
             "-" * 72]
    for chain, n in rep["networks"].items():
        probe = n["live_pool_probe"]
        if isinstance(probe, list) and probe and "error" not in probe[0]:
            res = sum(1 for p in probe if p.get("resolved"))
            probe_s = f"{res}/{len(probe)} pools resolved"
        elif isinstance(probe, list) and probe:
            probe_s = f"error: {probe[0].get('error')}"
        else:
            probe_s = n["live_pool_probe_note"]
        lines.append(
            f"{chain:<10} rpc={str(n['rpc_configured']):<5} "
            f"econ_rpc={str(n['economic_rpc_configured']):<5} "
            f"gas={str(n['gas_model']):<5} blocker={n['readiness_blocker']}")
        lines.append(f"{'':<10} providers={','.join(n['flash_loan_providers_eligible']) or '-'}")
        lines.append(f"{'':<10} live_probe={probe_s}")
        lines.append("-" * 72)
    lines.append(rep["note"])
    lines.append("=" * 72)
    return "\n".join(lines)


async def _amain() -> int:
    rep = await build_preflight()
    if "--json" in sys.argv:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(_human(rep))
    return 0


def main() -> None:
    sys.exit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
