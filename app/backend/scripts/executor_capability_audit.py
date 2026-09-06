#!/usr/bin/env python3
"""Executor-capability AUDIT — read-only, fail-closed, no fabrication.

Classifies the COMPLETE opportunity surface across the real execution gates and
reports, per chain × venue and per flash-loan provider, exactly how far a
candidate can currently advance:

    DISCOVERABLE          live pool resolver seam exists (opportunity_engine)
    QUOTABLE              live QuoterRegistry route adapter exists
    ROUTE_CONSTRUCTABLE   a DEX calldata adapter exists (execution.adapters)
    EXECUTION_CAPABLE     the DEPLOYED on-chain FlashLoanReceiver can actually
                          encode/execute this venue — TODAY that is Uniswap V3
                          swap hops ONLY, borrowable via Balancer V2 OR Aave V3
                          flash (both flash heads exist in the deployed receiver
                          ABI; executor_capability.SUPPORTED_DEXES)

SIMULATION and real EXECUTION are runtime gates that require the VPS (anvil fork
+ operator RPC + funded signer + Limited-Live approval) and are reported as
``requires_vps_runtime`` — never asserted here. This audit NEVER changes
SUPPORTED_DEXES, NEVER adds a synthetic adapter, and NEVER claims a capability
it cannot evidence from the real registries.

Usage:  python3 -m scripts.executor_capability_audit [--json]
        python /app/scripts/executor_capability_audit.py [--json]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_exec_audit")

# The deployed executor's authoritative flash-loan support, reconciled to the
# deployed FlashLoanReceiver ABI: Balancer V2 (`execute`/`receiveFlashLoan`)
# AND Aave V3 (`executeAave`/`executeOperation`) flash heads both exist.
EXECUTOR_SUPPORTED_FLASH = frozenset({"balancer_v2", "aave_v3"})


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v


# Explicit certification state model (never collapsed). Offline evidence can
# only advance IMPLEMENTED / STATE_VERIFIED(discovery seam) / QUOTABLE /
# ROUTE_CONSTRUCTABLE / EXECUTION_CAPABLE(construction level). The runtime
# states below require the VPS (operator RPC probe, on-chain state, anvil fork,
# funded signer) and are reported requires_runtime — NEVER asserted here.
CERTIFICATION_STATES = [
    "IMPLEMENTED", "CONFIGURED", "RPC_VERIFIED", "STATE_VERIFIED", "QUOTABLE",
    "ECONOMICALLY_VALID", "ROUTE_CONSTRUCTABLE", "SIMULATABLE",
    "EXECUTION_CAPABLE", "RUNTIME_CERTIFIED", "LIMITED_LIVE_ELIGIBLE",
]
_RUNTIME_ONLY_STATES = frozenset({
    "CONFIGURED", "RPC_VERIFIED", "STATE_VERIFIED", "ECONOMICALLY_VALID",
    "SIMULATABLE", "RUNTIME_CERTIFIED", "LIMITED_LIVE_ELIGIBLE"})


def _cell_states(discoverable, quotable, route_ok, exec_ok) -> dict:
    """Per-cell state evidence. Offline-provable states carry a bool; runtime
    states carry ``"requires_runtime"`` (never fabricated to True)."""
    offline = {
        "IMPLEMENTED": True,
        "QUOTABLE": bool(quotable),
        "ROUTE_CONSTRUCTABLE": bool(route_ok),
        "EXECUTION_CAPABLE": bool(exec_ok),     # on-chain receiver supports venue
    }
    out = {}
    for s in CERTIFICATION_STATES:
        out[s] = "requires_runtime" if s in _RUNTIME_ONLY_STATES else offline[s]
    return out


def audit_execution_capability() -> dict:
    from arbicore.discovery.opportunity_engine import build_opportunity_matrix
    from arbicore.execution.adapters import AdapterRegistry
    from arbicore.scanners.flash_loan_arbitrage.executor_capability import (
        SUPPORTED_DEXES)
    from arbicore.scanners.flash_loan_arbitrage.economics import (
        FLASH_LOAN_PROVIDERS)

    reg = AdapterRegistry()
    catalog = reg.catalog()
    dex_adapter_keys = {_norm(d["dex"]) for d in catalog["dex_providers"]}
    flash_adapter_keys = {_norm(f["provider"]) for f in catalog["flash_loan_providers"]}
    exec_dexes = {_norm(d) for d in SUPPORTED_DEXES}

    matrix = build_opportunity_matrix()
    venues = []
    seen = set()
    for r in matrix.get("rows", []):
        key = (r.get("chain"), r.get("venue"))
        if key in seen:
            continue
        seen.add(key)
        venue = _norm(r.get("venue"))
        discoverable = bool(r.get("discoverable"))
        quotable = bool(r.get("quote_path_connected"))
        route_ok = venue in dex_adapter_keys
        exec_ok = route_ok and venue in exec_dexes

        if not discoverable:
            blocker = f"discovery: {r.get('blocker') or 'resolver_not_implemented'}"
        elif not quotable:
            blocker = "quote: quoter_adapter_not_connected"
        elif not route_ok:
            blocker = ("route_construction: no DEX calldata adapter in "
                       "execution.adapters (implement DexAdapter)")
        elif not exec_ok:
            blocker = ("execution: deployed FlashLoanReceiver encodes uniswap_v3 "
                       "swap hops only — this venue requires an upgraded/redeployed "
                       "on-chain receiver before it is execution-capable")
        else:
            blocker = ("execution_capable at construction level; runtime "
                       "SIMULATION + EXECUTION require VPS (anvil + operator RPC "
                       "+ funded signer + Limited-Live approval)")

        venues.append({
            "chain": r.get("chain"), "venue": r.get("venue"),
            "abi": r.get("abi"),
            "discoverable": discoverable, "quotable": quotable,
            "route_constructable": route_ok, "execution_capable": exec_ok,
            "states": _cell_states(discoverable, quotable, route_ok, exec_ok),
            "blocker": blocker,
        })

    flash = []
    for provider, meta in sorted(FLASH_LOAN_PROVIDERS.items()):
        pn = _norm(provider)
        adapter_ok = pn in flash_adapter_keys
        exec_ok = pn in EXECUTOR_SUPPORTED_FLASH
        if not adapter_ok:
            blocker = ("no FlashLoanAdapter in execution.adapters "
                       "(borrow/repay calldata not implemented)")
        elif not exec_ok:
            blocker = ("adapter exists but deployed FlashLoanReceiver flash heads "
                       "are balancer_v2 + aave_v3 only — this provider requires "
                       "an upgraded receiver")
        else:
            blocker = ("execution-capable borrow provider; runtime availability "
                       "(vault liquidity, RPC) proven on VPS")
        flash.append({
            "provider": provider,
            "supports_chains": list(meta.get("supports_chains") or ()),
            "adapter_available": adapter_ok,
            "execution_capable": exec_ok,
            "blocker": blocker,
        })

    summary = {
        "venue_cells": len(venues),
        "discoverable": sum(1 for v in venues if v["discoverable"]),
        "quotable": sum(1 for v in venues if v["quotable"]),
        "route_constructable": sum(1 for v in venues if v["route_constructable"]),
        "execution_capable": sum(1 for v in venues if v["execution_capable"]),
        "executor_supported_dexes": sorted(exec_dexes),
        "executor_supported_flash": sorted(EXECUTOR_SUPPORTED_FLASH),
        "dex_adapters_available": sorted(dex_adapter_keys),
        "flash_adapters_available": sorted(flash_adapter_keys),
    }
    return {
        "safety": {"posture": "SHADOW / detection-only / fail-closed",
                   "signing": False, "broadcast": False, "execution": False},
        "note": ("Static execution-capability classification from the REAL "
                 "registries. SIMULATION and EXECUTION are VPS runtime gates "
                 "(requires_vps_runtime); never asserted here. No SUPPORTED_DEXES "
                 "change, no synthetic adapter, no fabricated capability."),
        "certification_state_model": {
            "states": CERTIFICATION_STATES,
            "offline_provable": [s for s in CERTIFICATION_STATES
                                 if s not in _RUNTIME_ONLY_STATES],
            "runtime_only": sorted(_RUNTIME_ONLY_STATES),
        },
        "summary": summary, "venues": venues, "flash_providers": flash,
    }


def _human(rep: dict) -> str:
    s = rep["summary"]
    lines = ["=" * 78, "ARBICORE X — EXECUTOR CAPABILITY AUDIT (read-only)", "=" * 78,
             f"executor DEX (on-chain)   : {s['executor_supported_dexes']}",
             f"executor FLASH (on-chain) : {s['executor_supported_flash']}",
             f"DEX adapters (calldata)   : {s['dex_adapters_available']}",
             f"FLASH adapters (calldata) : {s['flash_adapters_available']}",
             f"venue cells               : {s['venue_cells']}  "
             f"discoverable={s['discoverable']} quotable={s['quotable']} "
             f"route_constructable={s['route_constructable']} "
             f"execution_capable={s['execution_capable']}",
             "-" * 78, "VENUES (chain · venue · abi):"]
    for v in rep["venues"]:
        flags = (f"D={int(v['discoverable'])} Q={int(v['quotable'])} "
                 f"R={int(v['route_constructable'])} X={int(v['execution_capable'])}")
        lines.append(f"  {v['chain']:<9} {v['venue']:<22} {v['abi'] or '-':<8} {flags}")
        lines.append(f"      → {v['blocker']}")
    lines.append("-" * 78)
    lines.append("FLASH-LOAN PROVIDERS:")
    for f in rep["flash_providers"]:
        lines.append(f"  {f['provider']:<14} adapter={int(f['adapter_available'])} "
                     f"exec_capable={int(f['execution_capable'])}  chains={f['supports_chains']}")
        lines.append(f"      → {f['blocker']}")
    lines.append("=" * 78)
    lines.append(rep["note"])
    return "\n".join(lines)


def main() -> int:
    rep = audit_execution_capability()
    if "--json" in sys.argv:
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(_human(rep))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
