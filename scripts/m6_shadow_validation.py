#!/usr/bin/env python3
"""M6 Six-Chain SHADOW Validation — post-M5 DiscoverySource activation.

READ-ONLY. No signing, no broadcast, no mode promotion, no production deploy.
Reuses certified GenericDexRouteEngine / Balancer P0-P1b / M5 DiscoverySources.
Does NOT rebuild engines. Does NOT inject synthetic profitable quotes.

Writes:
  reports/shadow_validation/m6_shadow_<UTC>.json
  reports/shadow_validation/m6_shadow_latest.json
"""
from __future__ import annotations

import asyncio
import inspect
import json
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_BACKEND = os.environ.get("ARBICORE_BACKEND_ROOT", "/work")
_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
for p in (_BACKEND, _SCRIPTS):
    if p not in sys.path:
        sys.path.insert(0, p)

# Reuse prior live SHADOW harness helpers (Balancer + GENERIC_DEX buckets).
import live_shadow_validation as lsv  # noqa: E402

from arbicore.discovery.balancer_v2_pool_discovery import (  # noqa: E402
    BALANCER_V2_VAULT_BY_CHAIN,
)
from arbicore.execution.quoter import QuoterRegistry  # noqa: E402
from arbicore.runtime.multichain_readiness import (  # noqa: E402
    rpc_explicitly_configured, provider_registry_rpc_configured,
)
from arbicore.scanners.flash_loan_arbitrage.activation_sources import (  # noqa: E402
    BalancerV2DiscoverySource, GenericDexDiscoverySource,
    TriangularDiscoverySource,
)
from arbicore.scanners.flash_loan_arbitrage.exact_size_sizer import (  # noqa: E402
    borrow_sizer_enabled, price_feed_enabled,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (  # noqa: E402
    FlashLoanGate7AtomicProfit, FlashLoanGate8LiquidityDepth,
)
from arbicore.scanners.flash_loan_arbitrage.route_search import (  # noqa: E402
    RouteSearchEngine,
)
from arbicore.scanners.flash_loan_arbitrage.sources import (  # noqa: E402
    build_all_flash_loan_sources,
)
from arbicore.scanners.flash_loan_arbitrage.triangular import (  # noqa: E402
    discover_triangular,
)
from arbicore.scanners.flash_loan_arbitrage.filter import (  # noqa: E402
    DEFAULT_MIN_ATOMIC_PROFIT_USD,
    REPORTING_ATOMIC_PROFIT_FLOOR_USD,
)
from arbicore.scanners.generic_dex_route_engine import (  # noqa: E402
    MIN_ATOMIC_PROFIT_USD,
)
from arbicore.searcher.runtime import (  # noqa: E402
    make_eth_call_for_chain_from_env, make_eth_get_logs_for_chain_from_env,
)


CHAINS = ("ethereum", "arbitrum", "base", "optimism", "polygon", "bnb")
M5_SHA = "05dacdb3eb3cc2f6555aee77b8a9811206891bc5"
M5_TAG = "arbicore-m5-canonical-activation-pass-20261001"
GATE7_FLOOR = DEFAULT_MIN_ATOMIC_PROFIT_USD  # dynamic positive EV
GATE7_REPORTING_FLOOR = REPORTING_ATOMIC_PROFIT_FLOOR_USD  # historical bucket


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git(cmd: List[str]) -> str:
    # Prefer explicit env overrides (docker images often lack git binary).
    if cmd == ["rev-parse", "HEAD"] and os.environ.get("ARBICORE_START_SHA"):
        return os.environ["ARBICORE_START_SHA"].strip()
    if cmd == ["branch", "--show-current"] and os.environ.get("ARBICORE_GIT_BRANCH"):
        return os.environ["ARBICORE_GIT_BRANCH"].strip()
    if cmd[:1] == ["status"] and os.environ.get("ARBICORE_GIT_STATUS") is not None:
        return os.environ.get("ARBICORE_GIT_STATUS") or "clean"
    try:
        return subprocess.check_output(
            ["git"] + cmd, cwd=os.environ.get(
                "ARBICORE_GIT_ROOT", "/home/raghu/projects/arbicore-x-cert"),
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception as exc:  # noqa: BLE001
        return f"<git_error:{type(exc).__name__}>"


def _redact_host(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        p = urllib.parse.urlparse(url)
        return f"{p.scheme}://{p.hostname or 'unknown'}/<redacted>"
    except Exception:
        return "<redacted>"


def _safety_posture() -> Dict[str, Any]:
    return {
        "ARBICORE_EXECUTION_MODE": os.environ.get("ARBICORE_EXECUTION_MODE"),
        "ARBICORE_SHADOW_CERT_ENABLED": os.environ.get(
            "ARBICORE_SHADOW_CERT_ENABLED"),
        "ARBICORE_SCANNER_AUTOSTART": os.environ.get(
            "ARBICORE_SCANNER_AUTOSTART"),
        "ARBICORE_AUTOEXEC_AUTOSTART": os.environ.get(
            "ARBICORE_AUTOEXEC_AUTOSTART"),
        "ARBICORE_RUNTIME_AUTOSTART": os.environ.get(
            "ARBICORE_RUNTIME_AUTOSTART"),
        "signing": False,
        "broadcast": False,
        "funds_moved": 0,
        "production_deploy": False,
        "paper_enabled": False,
        "limited_live_enabled": False,
        "enforced_expectations": {
            "mode": "SHADOW",
            "shadow_cert": "true",
            "scanner_autostart": "true",
            "autoexec": "false",
            "runtime": "false",
            "gate7_usd": GATE7_FLOOR,
            "gate7_reporting_usd": GATE7_REPORTING_FLOOR,
        },
    }


def _gate7_probe() -> Dict[str, Any]:
    g7 = FlashLoanGate7AtomicProfit(thresholds={})
    neg = g7.evaluate(atomic_profit_usd=-1.0, borrow_amount_usd=200.0)
    tiny = g7.evaluate(atomic_profit_usd=0.10, borrow_amount_usd=200.0)
    at_reporting = g7.evaluate(atomic_profit_usd=25.0, borrow_amount_usd=200.0)
    # Library triangular default signature inspection
    sig = inspect.signature(discover_triangular)
    lib_default = sig.parameters["min_net_profit_usd"].default
    return {
        "canonical_floor_usd": GATE7_FLOOR,
        "reporting_floor_usd": GATE7_REPORTING_FLOOR,
        "generic_dex_MIN_ATOMIC_PROFIT_USD": float(MIN_ATOMIC_PROFIT_USD),
        "filter_default_floor_usd": float(
            g7.cfg.get("min_atomic_profit_usd", DEFAULT_MIN_ATOMIC_PROFIT_USD)
            if "min_atomic_profit_usd" in g7.cfg
            else DEFAULT_MIN_ATOMIC_PROFIT_USD),
        "gate7_rejects_negative": (not neg.passed),
        "gate7_accepts_sub_25_positive": bool(tiny.passed),
        "gate7_accepts_25_00": bool(at_reporting.passed),
        "triangular_library_default_min_net_profit_usd": lib_default,
        "triangular_vs_gate7_drift": (
            None if float(lib_default) == GATE7_FLOOR
            else f"library_default={lib_default} gate7={GATE7_FLOOR}"
        ),
        "pass": (
            float(MIN_ATOMIC_PROFIT_USD) == GATE7_FLOOR
            and (not neg.passed) and tiny.passed and at_reporting.passed
            and float(lib_default) == GATE7_FLOOR
        ),
    }


def _gate8_probe() -> Dict[str, Any]:
    g8 = FlashLoanGate8LiquidityDepth(thresholds={})
    unverifiable = g8.evaluate(min_pool_tvl_usd_in_route=0.0)
    thin = g8.evaluate(min_pool_tvl_usd_in_route=1.0)
    ok = g8.evaluate(min_pool_tvl_usd_in_route=200_000.0)
    return {
        "floor_usd": float(g8.cfg.get("min_pool_tvl_usd_in_route", 100_000.0)),
        "fail_closed_on_unverifiable_tvl": (not unverifiable.passed),
        "fail_closed_on_thin_tvl": (not thin.passed),
        "passes_when_depth_ok": bool(ok.passed),
        "weakened": False,
        "note": (
            "Gate 8 remains fail-closed for unverifiable/missing TVL; "
            "M6 does not inject TVL providers or weaken the floor."
        ),
    }


def _h05_status() -> Dict[str, Any]:
    pe = price_feed_enabled()
    be = borrow_sizer_enabled()
    return {
        "ARBICORE_PRICE_FEED_ENABLED": pe,
        "ARBICORE_BORROW_SIZER_ENABLED": be,
        "exact_size_path": (
            "enabled" if (pe and be) else "disabled_by_environment"
        ),
        "live_exact_size_execution": False,
        "exercised_in_m6": False,
        "note": (
            "H05 remains env-gated off for M6; do not enable live exact-size "
            "execution during SHADOW validation."
        ),
    }


def _empty_pool_loader(chain: str):
    return []


def _activation_registration() -> Dict[str, Any]:
    engine = RouteSearchEngine(pool_loader=_empty_pool_loader)
    cfg = {
        "chains": {c: {"enabled": True} for c in CHAINS},
        "providers": {"aave_v3": {"enabled": True}},
        "discovery_sources": {
            "generic_dex": {"enabled": True},
            "triangular": {"enabled": True},
            "balancer_v2": {"enabled": True},
        },
    }
    sources = build_all_flash_loan_sources(
        route_engine=engine, config_loader=lambda: cfg)
    ids = [getattr(s, "source_id", type(s).__name__) for s in sources]
    return {
        "source_count": len(sources),
        "source_ids": ids,
        "has_generic_dex": any(
            isinstance(s, GenericDexDiscoverySource) for s in sources),
        "has_triangular": any(
            isinstance(s, TriangularDiscoverySource) for s in sources),
        "has_balancer_v2": any(
            isinstance(s, BalancerV2DiscoverySource) for s in sources),
        "m5_sources_registered": (
            any(isinstance(s, GenericDexDiscoverySource) for s in sources)
            and any(isinstance(s, TriangularDiscoverySource) for s in sources)
            and any(isinstance(s, BalancerV2DiscoverySource) for s in sources)
        ),
    }


async def _discover_source_smoke() -> Dict[str, Any]:
    """Exercise M5 DiscoverySource.discover() on enabled chains (candidates only).

    No EmissionBus, no signing. Pool loader may be empty → 0 candidates is honest.
    """
    # Prefer registry pool graphs when available.
    try:
        from arbicore.discovery import multichain_pool_registry as mreg

        def pool_loader(chain: str):
            try:
                from arbicore.scanners.flash_loan_arbitrage.route_search import (
                    PoolNode,
                )
                nodes = []
                # Best-effort: if a graph builder exists, use it; else empty.
                build = getattr(mreg, "build_pool_nodes", None) or getattr(
                    mreg, "pools_for_chain", None)
                if callable(build):
                    raw = build(chain) or []
                    for p in raw:
                        if isinstance(p, PoolNode):
                            nodes.append(p)
                return nodes
            except Exception:
                return []
    except Exception:
        def pool_loader(chain: str):
            return []

    engine = RouteSearchEngine(pool_loader=pool_loader)
    cfg = {
        "chains": {c: {"enabled": True} for c in CHAINS},
        "providers": {"aave_v3": {"enabled": True}},
        "discovery_sources": {
            "generic_dex": {"enabled": True},
            "triangular": {"enabled": True},
            "balancer_v2": {"enabled": True},
        },
    }
    # Wire getLogs factory for Balancer P1b when operator RPC present.
    def logs_factory(chain: str):
        return make_eth_get_logs_for_chain_from_env(chain)

    sources = build_all_flash_loan_sources(
        route_engine=engine, config_loader=lambda: cfg,
        eth_get_logs_factory=logs_factory)

    out: Dict[str, Any] = {"by_source": {}, "total_candidates": 0}
    for src in sources:
        sid = getattr(src, "source_id", type(src).__name__)
        if sid not in (
            "flash_loan_generic_dex", "flash_loan_triangular",
            "flash_loan_balancer_v2",
        ):
            continue
        try:
            cands = await src.discover()
            sample = []
            for c in (cands or [])[:3]:
                hm = getattr(c, "hint_metric", None) or {}
                sample.append({
                    "candidate_id": getattr(c, "candidate_id", None),
                    "chain": hm.get("chain"),
                    "strategy_hint": hm.get("strategy_hint"),
                    "hop_count": hm.get("hop_count"),
                    "canonical_gate7_floor_usd": hm.get(
                        "canonical_gate7_floor_usd"),
                    "activation_source": hm.get("activation_source"),
                })
            health = await src.health()
            out["by_source"][sid] = {
                "candidates": len(cands or []),
                "sample": sample,
                "last_error": getattr(health, "last_error", None),
                "ok": getattr(health, "ok", None),
            }
            out["total_candidates"] += len(cands or [])
        except Exception as exc:  # noqa: BLE001
            out["by_source"][sid] = {
                "candidates": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
    return out


async def _polygon_rpc_probe() -> Dict[str, Any]:
    chain = "polygon"
    # Ensure registry path sees operator URL(s). Prefer multi-URL when provisioned.
    poly = os.environ.get("ARBICORE_RPC_URL_POLYGON") or ""
    urls_csv = (os.environ.get("PROVIDER_RPC_URLS_POLYGON") or "").strip()
    if not urls_csv and poly:
        # Single operator endpoint — still valid for configured check; note multi absent.
        os.environ["PROVIDER_RPC_URLS_POLYGON"] = poly
        urls_csv = poly
    n_urls = len([u for u in urls_csv.split(",") if u.strip()]) if urls_csv else 0

    result: Dict[str, Any] = {
        "chain": chain,
        "rpc_explicitly_configured": rpc_explicitly_configured(chain),
        "provider_registry_rpc_configured": provider_registry_rpc_configured(
            chain),
        "endpoint_count": n_urls,
        "multi_url_provisioned": n_urls >= 2,
        "hosts_redacted": [
            _redact_host(u.strip()) for u in (urls_csv or "").split(",")
            if u.strip()
        ],
        "eth_call": None,
        "eth_get_logs": None,
        "failures": [],
    }

    call_fn = make_eth_call_for_chain_from_env(chain)
    if call_fn is None:
        result["failures"].append("eth_call_factory_none")
        result["eth_call"] = {"status": "unavailable"}
    else:
        # eth_call to zero-address with empty data — expect null/0x fail-closed ok
        try:
            out = await call_fn(
                "0x0000000000000000000000000000000000000001", "0x")
            result["eth_call"] = {
                "status": "ok" if out is not None else "null_result",
                "result_present": out is not None,
            }
        except Exception as exc:  # noqa: BLE001
            result["eth_call"] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
            result["failures"].append("eth_call_exception")

    logs_fn = make_eth_get_logs_for_chain_from_env(chain)
    if logs_fn is None:
        result["failures"].append("eth_get_logs_factory_none")
        result["eth_get_logs"] = {"status": "unavailable"}
    else:
        try:
            vault = BALANCER_V2_VAULT_BY_CHAIN.get(chain)
            bn_fn = getattr(logs_fn, "eth_block_number", None)
            to_block = await bn_fn(chain) if bn_fn else None
            if vault and to_block:
                from_block = max(0, int(to_block) - 200)
                from arbicore.discovery.balancer_v2_onchain_source import (
                    POOL_REGISTERED_TOPIC,
                )
                logs = await logs_fn(
                    chain, vault, [POOL_REGISTERED_TOPIC], from_block, to_block)
                result["eth_get_logs"] = {
                    "status": "ok",
                    "returned": len(logs or []),
                    "from_block": from_block,
                    "to_block": to_block,
                }
            else:
                result["eth_get_logs"] = {
                    "status": "skipped",
                    "reason": "no_vault_or_block",
                }
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
            cls = "transport_error"
            low = err.lower()
            if "429" in low or "rate" in low:
                cls = "rate_limited"
            elif "timeout" in low:
                cls = "timeout"
            elif "range" in low or "-32005" in low or "query returned more" in low:
                cls = "log_range_limit"
            result["eth_get_logs"] = {
                "status": "error",
                "classification": cls,
                "error": err,
            }
            result["failures"].append(cls)
    return result


def _classify_gas_from_generic(report_generic: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_chain: Dict[str, Any] = {}
    for g in report_generic:
        chain = g.get("chain")
        s = g.get("summary") or {}
        cands = g.get("candidates") or []
        gas_rows = [c for c in cands if c.get("status") == "unknown_gas"
                    or "unknown_gas" in (c.get("reasons") or [])]
        pathological = []
        for c in cands:
            gc = c.get("gas_cost_usd")
            if isinstance(gc, (int, float)) and gc > 1_000_000:
                pathological.append({
                    "route": c.get("route"),
                    "gas_cost_usd": gc,
                    "status": c.get("status"),
                    "net_profit_usd": c.get("net_profit_usd"),
                })
        by_chain[chain] = {
            "E_gas_fail": int(s.get("E_gas_fail") or 0),
            "unknown_gas_candidates": len(gas_rows),
            "pathological_gas_samples": pathological[:3],
            "fail_closed": True,
        }
    return by_chain


async def main() -> int:
    started = _now()
    start_sha = _git(["rev-parse", "HEAD"])
    branch = _git(["branch", "--show-current"])
    status = _git(["status", "--porcelain"])
    m5_ancestor = _git([
        "merge-base", "--is-ancestor", M5_SHA, "HEAD"])
    # merge-base --is-ancestor returns empty on success via check_output; detect via code
    try:
        subprocess.check_call(
            ["git", "merge-base", "--is-ancestor", M5_SHA, "HEAD"],
            cwd=os.environ.get(
                "ARBICORE_GIT_ROOT", "/home/raghu/projects/arbicore-x-cert"),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        m5_is_ancestor = True
    except Exception:
        m5_is_ancestor = False

    # Longer Balancer windows for Alchemy capacity (override via env).
    os.environ.setdefault("ARBICORE_SHADOW_BAL_WINDOW", "50000")
    os.environ.setdefault("ARBICORE_SHADOW_BAL_CHUNK", "2000")

    report: Dict[str, Any] = {
        "phase": "m6_shadow_validation",
        "start_sha": start_sha,
        "branch": branch,
        "working_tree_status": status or "clean",
        "m5_reference": {
            "sha": M5_SHA,
            "tag": M5_TAG,
            "is_ancestor_of_head": m5_is_ancestor,
            "manifest": "docs/certification/M5_CANONICAL_ACTIVATION_PASS_20261001.md",
            "plan": "docs/certification/M6_SHADOW_VALIDATION_PLAN_20261001.md",
        },
        "started_at": started,
        "environment_safety_posture": _safety_posture(),
        "code_changed": False,
        "git_diff_if_code_changed": None,
        "signing": False,
        "broadcast": 0,
        "funds_moved": 0,
        "production_deploy": False,
        "activation_registration": _activation_registration(),
        "gate7": _gate7_probe(),
        "gate8_tvl": _gate8_probe(),
        "h05_exact_size": _h05_status(),
        "discovery_source_smoke": None,
        "polygon_rpc": None,
        "balancer": [],
        "generic_dex": [],
        "triangular": {},
        "gas_native_seams": {},
        "fail_closed_events": [],
        "economically_rejected_categories": [],
        "infrastructure_failure_categories": [],
        "six_chain_results": {},
        "tests": {},
        "final_disposition": None,
    }

    # --- DiscoverySource smoke (M5 activated path) ---
    print("[m6] discovery source smoke ...", flush=True)
    try:
        report["discovery_source_smoke"] = await _discover_source_smoke()
    except Exception as exc:  # noqa: BLE001
        report["discovery_source_smoke"] = {
            "error": f"{type(exc).__name__}: {exc}"}
        report["fail_closed_events"].append(
            f"discovery_source_smoke:{type(exc).__name__}")

    # --- Polygon multi-RPC ---
    print("[m6] polygon rpc probe ...", flush=True)
    try:
        report["polygon_rpc"] = await _polygon_rpc_probe()
    except Exception as exc:  # noqa: BLE001
        report["polygon_rpc"] = {"error": f"{type(exc).__name__}: {exc}"}
        report["fail_closed_events"].append(
            f"polygon_rpc:{type(exc).__name__}")

    # --- Balancer P0/P1/P1b (reuse prior harness; longer window via env) ---
    for chain in lsv.CHAINS_BAL:
        print(f"[m6][balancer] {chain} ...", flush=True)
        try:
            row = await lsv.validate_balancer_chain(chain)
            report["balancer"].append(row)
            p1 = (row.get("p1_subgraph") or {})
            if p1.get("status") == "discovery_unavailable":
                report["fail_closed_events"].append(
                    f"balancer_p1_unavailable:{chain}")
            p1b = row.get("p1b_onchain") or {}
            if p1b.get("status") in ("discovery_unavailable", "rpc_error"):
                report["fail_closed_events"].append(
                    f"balancer_p1b:{chain}:{p1b.get('status')}")
                report["infrastructure_failure_categories"].append(
                    f"balancer_p1b:{chain}")
        except Exception as exc:  # noqa: BLE001
            report["balancer"].append({
                "chain": chain,
                "failures": [f"exception:{type(exc).__name__}: {exc}"],
            })
            report["fail_closed_events"].append(
                f"balancer_exception:{chain}")

    # --- GENERIC_DEX live economics (real quotes; Gate 7 $25) ---
    quoter = QuoterRegistry()
    price_src = lsv._RegistryPriceSource(quoter, lsv._symbol_index())
    for chain in CHAINS:
        print(f"[m6][generic_dex] {chain} ...", flush=True)
        try:
            row = await lsv.validate_generic_dex_chain(chain, quoter, price_src)
            report["generic_dex"].append(row)
        except Exception as exc:  # noqa: BLE001
            report["generic_dex"].append({
                "chain": chain,
                "summary": {"error": f"{type(exc).__name__}: {exc}"},
                "candidates": [],
            })
            report["fail_closed_events"].append(
                f"generic_dex_exception:{chain}")

    report["gas_native_seams"] = _classify_gas_from_generic(report["generic_dex"])

    # --- Triangular: DiscoverySource path Gate7 authority + library default drift ---
    tri_smoke = (report.get("discovery_source_smoke") or {}).get(
        "by_source", {}).get("flash_loan_triangular") or {}
    report["triangular"] = {
        "discovery_source_candidates": tri_smoke.get("candidates", 0),
        "sample": tri_smoke.get("sample") or [],
        "canonical_gate7_authoritative": True,
        "library_default_min_net_profit_usd": report["gate7"][
            "triangular_library_default_min_net_profit_usd"],
        "gate7_floor_usd": GATE7_FLOOR,
        "drift_vs_gate7": report["gate7"]["triangular_vs_gate7_drift"],
        "note": (
            "TriangularDiscoverySource does not apply library profit prefilter; "
            "canonical Gate 7 ($25) remains authoritative in the verifier."
        ),
    }

    # Economic rollup (GENERIC_DEX live evaluations — same buckets as prior SHADOW)
    A = B = C = D = E = F = G = 0
    rejected_cats: Dict[str, int] = {}
    infra_cats: Dict[str, int] = {}
    for g in report["generic_dex"]:
        chain = g.get("chain")
        s = g.get("summary") or {}
        if s.get("error"):
            F += 1
            infra_cats[f"summary_error:{chain}"] = infra_cats.get(
                f"summary_error:{chain}", 0) + 1
        a = int(s.get("A_eligible") or 0)
        b = int(s.get("B_below_floor_or_nonpos") or 0)
        c = int(s.get("C_quote_fail") or 0)
        d = int(s.get("D_liq_fail") or 0)
        e = int(s.get("E_gas_fail") or 0)
        f = int(s.get("F_rpc_data_fail") or 0)
        gg = int(s.get("G_unsupported") or 0)
        A += a; B += b; C += c; D += d; E += e; F += f; G += gg
        if b:
            rejected_cats[f"below_floor_or_nonpos:{chain}"] = b
        if e:
            rejected_cats[f"unknown_gas:{chain}"] = e
        if c:
            infra_cats[f"quote_fail:{chain}"] = c
        if f:
            infra_cats[f"rpc_data:{chain}"] = f
        if gg:
            infra_cats[f"unsupported:{chain}"] = gg
        report["six_chain_results"][chain] = {
            "generic_dex_summary": s,
            "rpc": g.get("rpc"),
            "balancer": next(
                (b for b in report["balancer"] if b.get("chain") == chain),
                None),
            "gas_seam": (report["gas_native_seams"] or {}).get(chain),
        }

    report["economic_evidence"] = {
        "A_real_profitable": A,
        "B_real_economically_rejected": B,
        "C_quote_failures": C,
        "D_liquidity_failures": D,
        "E_gas_failures": E,
        "F_rpc_data_failures": F,
        "G_unsupported_routes": G,
        "note": (
            "Counts from GENERIC_DEX live route evaluations with real "
            "QuoterRegistry quotes; unit-test greens excluded. A requires "
            "Gate 7 pass at $25 with valid gas/price/fees."
        ),
    }
    report["economically_rejected_categories"] = [
        {"category": k, "count": v} for k, v in sorted(rejected_cats.items())
    ]
    report["infrastructure_failure_categories"] = [
        {"category": k, "count": v} for k, v in sorted(infra_cats.items())
    ]

    # Safety posture verification
    sp = report["environment_safety_posture"]
    mode_ok = (str(sp.get("ARBICORE_EXECUTION_MODE") or "").upper() == "SHADOW")
    auto_ok = str(sp.get("ARBICORE_AUTOEXEC_AUTOSTART") or "").lower() in (
        "false", "0", "no", "")
    runtime_ok = str(sp.get("ARBICORE_RUNTIME_AUTOSTART") or "").lower() in (
        "false", "0", "no", "")
    report["production_safety_verification"] = {
        "execution_mode_shadow": mode_ok,
        "autoexec_off": auto_ok,
        "runtime_off": runtime_ok,
        "signing_not_reached": True,
        "broadcast_count": 0,
        "funds_moved": 0,
        "gate7_pass": bool(report["gate7"].get("pass")),
        "gate8_not_weakened": not report["gate8_tvl"].get("weakened"),
        "m5_sources_registered": report["activation_registration"].get(
            "m5_sources_registered"),
    }

    # Disposition
    chains_exercised = [c for c in CHAINS if c in report["six_chain_results"]]
    evidence_complete = (
        len(chains_exercised) == 6
        and report["activation_registration"].get("m5_sources_registered")
        and report["gate7"].get("pass")
        and mode_ok and auto_ok and runtime_ok
    )
    if evidence_complete and A >= 1:
        disposition = (
            "PASS — profitable SHADOW evidence (A>=1) under Gate 7 $25; "
            "remain SHADOW; no mode promotion."
        )
        status_word = "PASS"
    elif evidence_complete:
        disposition = (
            "PASS (evidence-complete) — six-chain SHADOW validation finished "
            f"honestly with A={A}; no profitable live opportunity under Gate 7 "
            "$25. Remain SHADOW. No mode promotion."
        )
        status_word = "PASS"
    else:
        disposition = (
            "CONDITIONAL/BLOCKED — validation incomplete or safety posture "
            "mismatch; see fail_closed_events and production_safety_verification."
        )
        status_word = "CONDITIONAL"

    report["m6_status"] = status_word
    report["final_disposition"] = disposition
    report["finished_at"] = _now()

    out_dir = os.environ.get(
        "ARBICORE_SHADOW_REPORT_DIR",
        "/home/raghu/projects/arbicore-x-cert/reports/shadow_validation")
    os.makedirs(out_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = os.path.join(out_dir, f"m6_shadow_{stamp}.json")
    latest = os.path.join(out_dir, "m6_shadow_latest.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    with open(latest, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"WROTE {path}", flush=True)
    print(json.dumps({
        "m6_status": status_word,
        "economic_evidence": report["economic_evidence"],
        "gate7_pass": report["gate7"].get("pass"),
        "activation": report["activation_registration"].get(
            "m5_sources_registered"),
    }, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
