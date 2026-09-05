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
from pathlib import Path

# arbicore.runtime.__init__ transitively imports services.db which reads
# MONGO_URL at import time. This harness never touches Mongo (motor connects
# lazily); provide a safe local default so it runs standalone offline.
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "arbicore_x_certify")

# ── Environment-agnostic roots (never hardcoded to one layout) ──────────────
# This harness always lives at ``<APP_ROOT>/scripts/arbicore_certify.py`` in
# BOTH layouts, so APP_ROOT is derived from THIS file:
#   * repo / CI checkout : APP_ROOT = <repo>/app/backend  (git root = <repo>)
#   * prod-style container: APP_ROOT = /app  (Dockerfile `COPY app/backend/
#                           /app/`; .git stripped; identity via BUILD_INFO.json)
APP_ROOT = Path(__file__).resolve().parent.parent


def _find_git_root(start: Path):
    for d in (start, *start.parents):
        if (d / ".git").exists():
            return d
    return None


GIT_ROOT = _find_git_root(APP_ROOT)

# Protected files: ``repo`` = repository-relative path used by the git-dirty
# modification guard; ``app`` = the path (relative to APP_ROOT) where the file
# is actually SHIPPED inside the backend image, or None when the file is
# deployment-only and intentionally NOT copied into the backend image (e.g. the
# compose file). Existence of shippable protected files is checked in BOTH
# layouts; a deployment-only file absent from the image is reported (not a
# failure), never silently marked present.
PROTECTED = [
    {"repo": "app/backend/arbicore/scanners/dex_arbitrage/scanner.py",
     "app": "arbicore/scanners/dex_arbitrage/scanner.py"},
    {"repo": "deployment/compose/docker-compose.yml", "app": None},
    {"repo": "app/backend/scripts/p0_3_flash_discovery_proof.py",
     "app": "scripts/p0_3_flash_discovery_proof.py"},
]
# APP_ROOT-relative so py_compile resolves in BOTH layouts. A missing file
# surfaces as a compile error (never silently skipped / marked passing).
KEY_MODULES = [
    "arbicore/discovery/univ3_pool_resolver.py",
    "arbicore/discovery/opportunity_engine.py",
    "arbicore/runtime/multichain_readiness.py",
    "arbicore/searcher/base_all_in_cost.py",
    "arbicore/execution/quoter.py",
]


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args],
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return ""


def _build_identity() -> dict:
    """Real deployment identity in BOTH layouts. Precedence mirrors the app's
    /api/arbicore/version exactly: ARBICORE_GIT_* env > BUILD_INFO.json (written
    at image build before .git is stripped) > live git (dev/CI). Never
    fabricated — an unresolvable field is reported as ``unknown``/``unset``."""
    stamp: dict = {}
    p = APP_ROOT / "BUILD_INFO.json"
    try:
        if p.exists():
            stamp = json.loads(p.read_text()) or {}
    except Exception:  # noqa: BLE001
        stamp = {}

    def live(*args: str):
        if GIT_ROOT is None:
            return ""
        return _git("-C", str(GIT_ROOT), *args)

    # Precedence for a CERTIFICATION result: an explicit operator override wins,
    # then LIVE GIT when a real checkout is present (it certifies the EXACT
    # working tree), then the build-time stamp (the honest source inside a
    # .git-stripped image), else unknown. This differs deliberately from the
    # app's version endpoint (stamp-first) so certify never reports a stale
    # baked SHA over the actually-checked-out code.
    live_sha = live("rev-parse", "HEAD")
    git_sha = (os.environ.get("ARBICORE_GIT_SHA") or live_sha
               or stamp.get("git_sha") or "unknown")
    git_tag = (os.environ.get("ARBICORE_GIT_TAG")
               or live("describe", "--tags", "--always", "--dirty")
               or stamp.get("git_tag") or "unknown")
    branch = live("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    source = ("env" if os.environ.get("ARBICORE_GIT_SHA")
              else "git" if live_sha
              else "build_info" if stamp.get("git_sha") else "unknown")
    return {
        "git_sha": git_sha, "git_tag": git_tag, "branch": branch,
        "git_source": source, "git_available": GIT_ROOT is not None,
        "image_ref": (os.environ.get("ARBICORE_IMAGE_REF")
                      or stamp.get("image_ref") or "unset"),
        "image_digest": (os.environ.get("ARBICORE_IMAGE_DIGEST")
                         or stamp.get("image_digest") or "unset"),
    }


def _repo_section() -> dict:
    ident = _build_identity()

    # (a) protected-file MODIFICATION guard (git-dirty). Only meaningful with a
    # git checkout; in a .git-stripped image it is reported as unavailable
    # (None) — never a false "unmodified". Dev/CI strength is unchanged.
    protected_modified = None
    if GIT_ROOT is not None:
        porcelain = _git("-C", str(GIT_ROOT), "status", "--porcelain")
        dirty = [ln[3:] for ln in porcelain.splitlines()] if porcelain else []
        protected_modified = sorted(set(dirty) & {x["repo"] for x in PROTECTED})

    # (b) protected-file INTEGRITY (existence) — checked in BOTH layouts. A file
    # that SHOULD ship in the backend image but is missing FAILS integrity. A
    # deployment-only file (app=None) absent from the image is reported honestly
    # (present=None, not_in_image) and is not counted as a failure.
    protected_status = []
    integrity_ok = True
    for x in PROTECTED:
        if GIT_ROOT is not None:
            fp = GIT_ROOT / x["repo"]
            present = fp.exists()
            location = str(fp)
            if not present:
                integrity_ok = False
        elif x["app"] is not None:
            fp = APP_ROOT / x["app"]
            present = fp.exists()
            location = str(fp)
            if not present:
                integrity_ok = False
        else:
            present = None            # deployment-only, correctly not in image
            location = "not_in_image"
        protected_status.append({
            "path": x["repo"], "present": present, "location": location,
            "in_image": x["app"] is not None})

    # (c) compilation of key modules — resolved against APP_ROOT (works in both
    # layouts). Missing file ⇒ explicit compile error (never skipped).
    import py_compile
    compile_errors = []
    for m in KEY_MODULES:
        fp = APP_ROOT / m
        if not fp.exists():
            compile_errors.append(f"{m}: FileNotFound at {fp}")
            continue
        try:
            py_compile.compile(str(fp), doraise=True)
        except Exception as exc:  # noqa: BLE001
            compile_errors.append(f"{m}: {type(exc).__name__}")

    return {
        "app_root": str(APP_ROOT),
        "git_root": str(GIT_ROOT) if GIT_ROOT else None,
        "git_available": ident["git_available"],
        "git_source": ident["git_source"],
        "git_sha": ident["git_sha"],
        "git_sha_short": (ident["git_sha"][:12]
                          if ident["git_sha"] != "unknown" else "unknown"),
        "git_tag": ident["git_tag"],
        "branch": ident["branch"],
        "image_ref": ident["image_ref"],
        "image_digest": ident["image_digest"],
        "protected_files_unmodified": (protected_modified == []
                                       if protected_modified is not None
                                       else None),
        "protected_files_modified": protected_modified,
        "protected_files_status": protected_status,
        "protected_files_integrity_ok": integrity_ok,
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


def build_certification() -> dict:
    # Repository section (git identity + protected integrity + KEY_MODULES
    # compilation) FIRST — it never imports the app, so a syntactically broken
    # module is reported as a compile error rather than crashing the harness.
    repo = _repo_section()
    safety = _safety_section()

    # Capability + matrix require importing the real modules. Guard the import
    # so a broken/removed module surfaces as an explicit error (never fabricated
    # capability data) and the overall result fails closed.
    capabilities = None
    matrix = None
    matrix_error = None
    try:
        from arbicore.discovery.opportunity_engine import (
            enumerate_capabilities, build_opportunity_matrix)
        capabilities = enumerate_capabilities()
        matrix = build_opportunity_matrix()
    except Exception as exc:  # noqa: BLE001 — never fabricate a matrix
        matrix_error = f"{type(exc).__name__}: {exc}"
        matrix = {"summary": {"row_count": 0, "discoverable_count": 0,
                              "quote_path_connected_count": 0,
                              "limited_live_eligible_count": 0},
                  "rows": [], "error": matrix_error}

    report = {
        "repository": repo,
        "safety": safety,
        "capabilities": capabilities,
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
    r = report["repository"]
    # Protected posture: PASS when integrity holds AND the git-dirty guard is
    # either clean (git checkout) or not applicable (.git-stripped image) — a
    # DIRTY protected file (git available) fails; a MISSING shippable protected
    # file fails; a False is never coerced to pass.
    protected_ok = (r["protected_files_integrity_ok"]
                    and r["protected_files_unmodified"] is not False)
    repo_ok = (protected_ok and r["python_compile_ok"]
               and matrix_error is None)
    safety_ok = not any([safety["signing_enabled"], safety["broadcast_enabled"],
                         safety["auto_execution_enabled"],
                         safety["full_live_enabled"], safety["withdrawals_enabled"]])
    report["result"] = {
        "repo_capability_pass": bool(repo_ok and safety_ok),
        "protected_ok": bool(protected_ok),
        "matrix_error": matrix_error,
        "note": ("repo+capability+safety only; NOT a P0-3 or limited-live "
                 "certification."),
    }
    return report


def _human(report: dict) -> str:
    r, s = report["repository"], report["safety"]
    m = report["opportunity_matrix"]["summary"]
    pf = "unmodified" if r["protected_files_unmodified"] is True else (
        "MODIFIED" if r["protected_files_unmodified"] is False
        else "n/a (no .git — integrity-checked)")
    lines = [
        "=" * 64, "ARBICORE X — CERTIFICATION (repo + capability surface)",
        "=" * 64,
        f"app_root           : {r['app_root']}",
        f"git_root           : {r['git_root']}  (available={r['git_available']})",
        f"git_sha            : {r['git_sha']}  ({r['branch']})  [src={r['git_source']}]",
        f"git_tag            : {r['git_tag']}",
        f"image_ref          : {r['image_ref']}",
        f"image_digest       : {r['image_digest']}",
        f"protected_files    : {pf}  modified={r['protected_files_modified'] or ''}  "
        f"integrity_ok={r['protected_files_integrity_ok']}",
        f"python_compile_ok  : {r['python_compile_ok']}  {r['compile_errors'] or ''}",
        f"safety             : signing={s['signing_enabled']} broadcast={s['broadcast_enabled']} "
        f"auto_exec={s['auto_execution_enabled']} full_live={s['full_live_enabled']}",
        f"matrix rows        : {m['row_count']}  discoverable={m['discoverable_count']}  "
        f"quote_path_connected={m['quote_path_connected_count']}  "
        f"limited_live_eligible={m['limited_live_eligible_count']}",
        f"runtime            : {report['runtime']['status']}",
        f"matrix_error       : {report['result'].get('matrix_error')}",
        f"first_limited_live : {report['first_limited_live_candidate']}",
        f"p0_3_certified     : {report['p0_3_certified']}",
        f"RESULT repo+cap    : {report['result']['repo_capability_pass']}  "
        f"(protected_ok={report['result']['protected_ok']})",
        "=" * 64,
    ]
    return "\n".join(lines)


def main() -> int:
    report = build_certification()
    if "--json" in sys.argv:
        print(json.dumps(report, indent=2, default=str))
    else:
        print(_human(report))
    return 0 if report["result"]["repo_capability_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
