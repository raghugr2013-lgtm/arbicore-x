"""ArbiCore X — automated certification harness (repo + capability surface).

Honest, read-only, offline. Emits human-readable + machine-readable (JSON)
results for the parts that CAN be certified inside the engineering environment:

  REPOSITORY : git SHA, branch, protected-file integrity, Python compilation
  SAFETY     : signer / broadcast / auto-execution / full-live env states
  CAPABILITY : chains × venues × strategies enumeration
  MATRIX     : CHAIN|VENUE|STRATEGY state + explicit blocker (opportunity_engine)

It NEVER boots the server, contacts a real RPC, signs, broadcasts, or fabricates
pools/liquidity/quotes/opportunities. The LIVE sections (real RPC, chain
identity, block, pool resolution, real quotes, economics, simulation, evidence,
first limited-live candidate) are the VPS's job and are reported here as
``requires_vps_runtime`` — a green repo/capability result does NOT certify P0-3
or mark any opportunity limited-live eligible.

Usage:  python -m scripts.arbicore_certify [--json]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

# arbicore.runtime.__init__ transitively imports services.db which reads
# MONGO_URL at import time. This harness never touches Mongo (motor connects
# lazily); provide a safe local default so it runs standalone offline.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_certify")

PROTECTED = [
    "app/backend/arbicore/scanners/dex_arbitrage/scanner.py",
    "deployment/compose/docker-compose.yml",
    "app/backend/scripts/p0_3_flash_discovery_proof.py",
]
KEY_MODULES = [
    "app/backend/arbicore/discovery/univ3_pool_resolver.py",
    "app/backend/arbicore/discovery/opportunity_engine.py",
    "app/backend/arbicore/runtime/multichain_readiness.py",
    "app/backend/arbicore/searcher/base_all_in_cost.py",
    "app/backend/arbicore/execution/quoter.py",
]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return ""


def _repo_section(repo_root: str) -> dict:
    head = _git("-C", repo_root, "rev-parse", "HEAD")
    branch = _git("-C", repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    porcelain = _git("-C", repo_root, "status", "--porcelain")
    dirty = [ln[3:] for ln in porcelain.splitlines()] if porcelain else []
    protected_modified = sorted(set(dirty) & set(PROTECTED))
    # compile key modules (import-free syntax check)
    import py_compile
    compile_errors = []
    for m in KEY_MODULES:
        p = os.path.join(repo_root, m)
        try:
            py_compile.compile(p, doraise=True)
        except Exception as exc:  # noqa: BLE001
            compile_errors.append(f"{m}: {type(exc).__name__}")
    return {
        "git_sha": head, "branch": branch,
        "protected_files_unmodified": protected_modified == [],
        "protected_files_modified": protected_modified,
        "python_compile_ok": compile_errors == [],
        "compile_errors": compile_errors,
    }


def _safety_section() -> dict:
    def _on(*keys):
        return any((os.environ.get(k) or "").strip().lower()
                   in ("1", "true", "yes", "on") for k in keys)
    return {
        "posture": "SHADOW / detection-only / fail-closed",
        "signing_enabled": _on("ARBICORE_ENABLE_SIGNING", "ENABLE_SIGNING"),
        "broadcast_enabled": _on("ARBICORE_ENABLE_BROADCAST", "ENABLE_BROADCAST"),
        "auto_execution_enabled": _on("ARBICORE_ENABLE_AUTOEXECUTOR",
                                      "ENABLE_AUTO_EXECUTION"),
        "full_live_enabled": _on("ARBICORE_ENABLE_FULL_LIVE", "FULL_LIVE"),
        "withdrawals_enabled": _on("ARBICORE_ENABLE_WITHDRAWALS"),
    }


def build_certification(repo_root: str) -> dict:
    from arbicore.discovery.opportunity_engine import (
        enumerate_capabilities, build_opportunity_matrix)
    safety = _safety_section()
    matrix = build_opportunity_matrix()
    report = {
        "repository": _repo_section(repo_root),
        "safety": safety,
        "capabilities": enumerate_capabilities(),
        "opportunity_matrix": matrix,
        "runtime": {
            "status": "requires_vps_runtime",
            "note": ("real RPC, chain identity, block, pool resolution, quotes, "
                     "economics, simulation, evidence and the first limited-live "
                     "candidate are certified on the VPS, not here."),
        },
        "first_limited_live_candidate": None,
        "p0_3_certified": False,
    }
    repo_ok = (report["repository"]["protected_files_unmodified"]
               and report["repository"]["python_compile_ok"])
    safety_ok = not any([safety["signing_enabled"], safety["broadcast_enabled"],
                         safety["auto_execution_enabled"],
                         safety["full_live_enabled"], safety["withdrawals_enabled"]])
    report["result"] = {
        "repo_capability_pass": bool(repo_ok and safety_ok),
        "note": ("repo+capability+safety only; NOT a P0-3 or limited-live "
                 "certification."),
    }
    return report


def _human(report: dict) -> str:
    r, s = report["repository"], report["safety"]
    m = report["opportunity_matrix"]["summary"]
    lines = [
        "=" * 60, "ARBICORE X — CERTIFICATION (repo + capability surface)",
        "=" * 60,
        f"git_sha            : {r['git_sha']}  ({r['branch']})",
        f"protected_files_ok : {r['protected_files_unmodified']}  {r['protected_files_modified'] or ''}",
        f"python_compile_ok  : {r['python_compile_ok']}  {r['compile_errors'] or ''}",
        f"safety             : signing={s['signing_enabled']} broadcast={s['broadcast_enabled']} "
        f"auto_exec={s['auto_execution_enabled']} full_live={s['full_live_enabled']}",
        f"matrix rows        : {m['row_count']}  discoverable={m['discoverable_count']}  "
        f"quote_path_connected={m['quote_path_connected_count']}  "
        f"limited_live_eligible={m['limited_live_eligible_count']}",
        f"runtime            : {report['runtime']['status']}",
        f"first_limited_live : {report['first_limited_live_candidate']}",
        f"p0_3_certified     : {report['p0_3_certified']}",
        f"RESULT repo+cap    : {report['result']['repo_capability_pass']}",
        "=" * 60,
    ]
    return "\n".join(lines)


def main() -> int:
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    report = build_certification(repo_root)
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_human(report))
    return 0 if report["result"]["repo_capability_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
