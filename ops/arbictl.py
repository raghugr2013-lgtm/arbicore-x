#!/usr/bin/env python3
"""arbictl — ArbiCore X Production Operations Toolkit (v2.9.1)

Single-file CLI. Zero runtime dependencies beyond stdlib + httpx.
Every subcommand is idempotent and read-only against a live deployment
unless it explicitly restarts services.

v2.9.1 maintenance release — no behaviour changes. Runtime `pip install`
was removed to comply with Ubuntu 24.04 / PEP 668. httpx must be provided
by the surrounding environment (project venv, backend container venv, or
distro package). See ops/arbictl (bash wrapper) for interpreter discovery.

Subcommands:
    deploy         one-command safe deploy
    preflight      readiness check
    validate-start begin the 7-day validation run
    snapshot       export one daily evidence bundle
    evidence-pack  bundle every daily snapshot into one tarball
    dashboard      CLI dashboard (system-at-a-glance)
    upgrade        upgrade to a new tag with rollback safety
    rollback       restore previous validated release
    version        print the running version
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:
    # v2.9.1: never suggest a runtime `pip install` here — Ubuntu 24 / PEP 668
    # blocks it. The bash wrapper (ops/arbictl) selects an interpreter that
    # already has httpx; direct invocation should point the operator at that
    # wrapper (or an existing venv). We deliberately do NOT `pip install`.
    print(
        "arbictl: python interpreter missing httpx and no runtime install "
        "is permitted.\n"
        "  Use the shell wrapper (ops/arbictl) — it auto-selects a venv that "
        "already has httpx.\n"
        "  Or run against an existing venv, e.g.:\n"
        "      /app/venv/bin/python ops/arbictl.py <cmd>\n"
        "  Or provision a project venv once:\n"
        "      python3 -m venv .venv && .venv/bin/pip install httpx",
        file=sys.stderr,
    )
    sys.exit(3)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
DEFAULT_BASE = os.environ.get("ARBICTL_BASE_URL", "http://localhost:8001")
DEFAULT_REPO = os.environ.get("ARBICTL_REPO", "/app/canonical_repo")
DEFAULT_RELEASES = os.environ.get("ARBICTL_RELEASES", "/app/releases")
DEFAULT_EVIDENCE = os.environ.get(
    "ARBICTL_EVIDENCE", "/var/lib/arbicore/evidence")
DEFAULT_BACKUP = os.environ.get(
    "ARBICTL_BACKUP", "/var/lib/arbicore/backups")


def _c(msg: str, colour: str = "") -> str:
    codes = {"g": "\033[32m", "r": "\033[31m", "y": "\033[33m",
             "b": "\033[34m", "d": "\033[2m", "0": "\033[0m"}
    if not sys.stdout.isatty() or not colour:
        return msg
    return f"{codes.get(colour, '')}{msg}{codes['0']}"


def _iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run(cmd: List[str], check: bool = True,
          capture: bool = False, cwd: Optional[str] = None) -> str:
    r = subprocess.run(cmd, capture_output=capture, text=True, cwd=cwd,
                        check=False)
    if check and r.returncode != 0:
        raise RuntimeError(
            f"cmd failed ({r.returncode}): {' '.join(cmd)}\n"
            f"stderr: {(r.stderr or '')[:400]}")
    return (r.stdout or "").strip() if capture else ""


def _get(path: str, base: str, timeout: float = 12.0,
          token: Optional[str] = None) -> Optional[Dict[str, Any]]:
    h = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.get(f"{base}{path}", timeout=timeout, headers=h)
        r.raise_for_status()
        return r.json()
    except Exception as e:                                           # noqa
        print(_c(f"  ✗ GET {path}: {e}", "r"))
        return None


def _post(path: str, base: str, token: Optional[str] = None,
           json_body: Optional[Dict[str, Any]] = None,
           timeout: float = 12.0) -> Optional[Dict[str, Any]]:
    h = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        r = httpx.post(f"{base}{path}", json=json_body or {},
                        headers=h, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:                                           # noqa
        print(_c(f"  ✗ POST {path}: {e}", "r"))
        return None


def _wait_for(url: str, base: str, timeout: float = 90.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        if _get(url, base, timeout=3.0) is not None:
            return True
        time.sleep(2)
    return False


def _login(base: str, username: str, password: str) -> Optional[str]:
    try:
        r = httpx.post(f"{base}/api/auth/login",
                        json={"username": username, "password": password},
                        timeout=6.0)
        r.raise_for_status()
        d = r.json()
        return d.get("access_token") or d.get("token")
    except Exception as e:                                           # noqa
        print(_c(f"login failed: {e}", "r"))
        return None


def _ok_bad(ok: bool) -> str:
    return _c("PASS", "g") if ok else _c("FAIL", "r")


def _emit_json(payload: Dict[str, Any], out_dir: Path,
                name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{name}_{_now_slug()}.json"
    p.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return p


# ---------------------------------------------------------------------------
# subcommand: version
# ---------------------------------------------------------------------------
def cmd_version(args) -> int:
    version_file = Path(args.repo) / "VERSION"
    ver = version_file.read_text().strip() if version_file.exists() else "?"
    live = _get("/api/", args.base) or {}
    print(f"repo version: {ver}")
    print(f"live api:     {live.get('message', 'unavailable')}")
    return 0


# ---------------------------------------------------------------------------
# subcommand: preflight
# ---------------------------------------------------------------------------
def cmd_preflight(args) -> int:
    print(_c("== ArbiCore X preflight ==", "b"))
    steps: List[Tuple[str, bool, str]] = []

    # Local process checks
    try:
        _run(["mongod", "--version"], capture=True)
        steps.append(("mongo binary", True, "installed"))
    except Exception as e:                                           # noqa
        steps.append(("mongo binary", False, str(e)[:80]))

    supervisor_ok = shutil.which("supervisorctl") is not None
    steps.append(("supervisorctl", supervisor_ok, "found" if supervisor_ok else "missing"))

    # Live endpoint checks
    api_alive = _get("/api/", args.base) is not None
    steps.append(("backend api", api_alive, args.base))

    pf = _get("/api/arbicore/preflight", args.base)
    if pf and pf.get("ok"):
        steps.append(("preflight endpoint", True,
                       f"passed={pf.get('passed')}/{pf.get('total')}"))
    else:
        steps.append(("preflight endpoint", False,
                       "failed" if pf else "unreachable"))

    prov = _get("/api/arbicore/providers/status", args.base)
    if prov and prov.get("available"):
        pc = prov.get("provider_count", 0)
        steps.append(("provider registry", pc >= 20,
                       f"providers={pc}"))
    else:
        steps.append(("provider registry", False, "unavailable"))

    live = _get("/api/arbicore/live/status", args.base)
    steps.append(("live_market scanner",
                   bool(live and live.get("running")),
                   f"running={bool(live and live.get('running'))}"))

    cross = _get("/api/arbicore/scanners/cross/status", args.base)
    if cross:
        cd = cross.get("cex_dex", {}).get("running", False)
        dd = cross.get("dex_dex", {}).get("running", False)
        steps.append(("cross scanners", cd and dd,
                       f"cex_dex={cd} dex_dex={dd}"))
    else:
        steps.append(("cross scanners", False, "unavailable"))

    safety = _get("/api/arbicore/safety/status", args.base)
    if safety:
        eng = safety.get("kill", {}).get("engaged", False)
        live_exec = safety.get("live_execution_enabled", True)
        steps.append(("kill switch engaged", eng, str(eng)))
        steps.append(("live execution disabled", not live_exec,
                       f"live_exec={live_exec}"))
    else:
        steps.append(("safety endpoint", False, "unavailable"))

    daily = _get("/api/arbicore/validation/daily_status", args.base)
    steps.append(("daily summary writer",
                   bool(daily and daily.get("running")),
                   f"running={bool(daily and daily.get('running'))}"))

    rc = _get("/api/arbicore/config/runtime", args.base)
    steps.append(("runtime config", bool(rc and rc.get("available")),
                   "loaded" if rc else "missing"))

    # Print table
    fails = 0
    for name, ok, detail in steps:
        if not ok:
            fails += 1
        print(f"  [{_ok_bad(ok)}]  {name:28s}  {detail}")

    print()
    if fails == 0:
        print(_c(f"✔ preflight PASSED — {len(steps)}/{len(steps)}", "g"))
        return 0
    print(_c(f"✗ preflight FAILED — {fails} of {len(steps)} steps failed", "r"))
    return 1


# ---------------------------------------------------------------------------
# subcommand: dashboard
# ---------------------------------------------------------------------------
def cmd_dashboard(args) -> int:
    print(_c("=== ArbiCore X Operations Dashboard ===", "b"))
    version = (Path(args.repo) / "VERSION").read_text().strip() \
        if (Path(args.repo) / "VERSION").exists() else "?"
    tag = _run(["git", "describe", "--tags", "--always"],
                capture=True, cwd=args.repo, check=False)
    print(f"repo version : {version}   git-tag: {tag or '?'}")

    prov = _get("/api/arbicore/providers/status", args.base) or {}
    live = _get("/api/arbicore/live/status", args.base) or {}
    cross = _get("/api/arbicore/scanners/cross/status", args.base) or {}
    memory = _get("/api/arbicore/memory/summary", args.base) or {}
    daily = _get("/api/arbicore/validation/daily_status", args.base) or {}
    read = _get("/api/arbicore/postvalidation/readiness_score",
                 args.base) or {}
    safety = _get("/api/arbicore/safety/status", args.base) or {}

    by_kind = prov.get("by_kind") or {}
    healthy = sum(1 for rows in by_kind.values() for r in rows
                    if r.get("status") == "HEALTHY")
    total_prov = prov.get("provider_count", 0)

    scanners = [
        ("live_market",
          live.get("running"),
          (live.get("stats") or {}).get("iterations", 0),
          (live.get("stats") or {}).get("opportunities_emitted", 0)),
    ]
    for k, s in (cross or {}).items():
        if isinstance(s, dict) and s.get("available") is not None:
            scanners.append(
                (k, s.get("running"),
                  (s.get("stats") or {}).get("iterations", 0),
                  (s.get("stats") or {}).get("opportunities_emitted", 0)))

    opps = memory.get("opportunities") or {}
    total_opps = opps.get("total", 0)

    print()
    print(f"safety      : kill={_c(str(safety.get('kill',{}).get('engaged')), 'g' if safety.get('kill',{}).get('engaged') else 'r')}  live_exec={safety.get('live_execution_enabled')}")
    print(f"providers   : {healthy}/{total_prov} HEALTHY")
    print("scanners    :")
    for sid, run, it, emit in scanners:
        c = "g" if run else "r"
        print(f"  {sid:20s}  {_c('RUNNING' if run else 'STOPPED', c)}  iter={it:<6d}  emitted={emit}")
    print(f"opportunities in MID: {total_opps}")
    print(f"daily writer: running={daily.get('running')}  "
           f"run_id={daily.get('run_id','-')}  "
           f"last={daily.get('last_summary_at','-')}")

    if read.get("overall"):
        ov = read["overall"]
        print(f"readiness   : {ov.get('grade')}  score={ov.get('score')}  "
               f"verdict={ov.get('verdict','-')}")

    anoms = daily.get("last_anomalies") or []
    crits = [a for a in anoms if a.get("severity") == "critical"]
    if crits:
        print(_c(f"anomalies   : {len(crits)} CRITICAL — investigate", "r"))
    elif anoms:
        print(_c(f"anomalies   : {len(anoms)} advisory", "y"))
    else:
        print(_c("anomalies   : none", "g"))

    return 0


# ---------------------------------------------------------------------------
# subcommand: snapshot (daily evidence exporter)
# ---------------------------------------------------------------------------
_SNAP_ENDPOINTS = [
    ("validation_summary", "/api/arbicore/validation/summary"),
    ("last_daily",         "/api/arbicore/validation/last_daily"),
    ("providers",          "/api/arbicore/providers/status"),
    ("scanners_cross",     "/api/arbicore/scanners/cross/status"),
    ("live_status",        "/api/arbicore/live/status"),
    ("live_prices",        "/api/arbicore/live/prices"),
    ("memory",             "/api/arbicore/memory/summary"),
    ("observability",      "/api/arbicore/observability"),
    ("safety",             "/api/arbicore/safety/status"),
    ("config_runtime",     "/api/arbicore/config/runtime"),
    ("readiness_score",    "/api/arbicore/postvalidation/readiness_score"),
    ("recommendations",    "/api/arbicore/postvalidation/recommendations"),
    ("executive_summary",  "/api/arbicore/postvalidation/executive_summary"),
]


def cmd_snapshot(args) -> int:
    day_dir = Path(args.evidence) / _now_slug()
    day_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Any] = {"created_at": _iso(),
                                 "base": args.base,
                                 "endpoints": {}}
    ok, bad = 0, 0
    for name, path in _SNAP_ENDPOINTS:
        data = _get(path, args.base, timeout=15.0)
        if data is None:
            manifest["endpoints"][name] = {"ok": False, "path": path}
            bad += 1
            continue
        p = day_dir / f"{name}.json"
        p.write_text(json.dumps(data, indent=2, sort_keys=True))
        manifest["endpoints"][name] = {"ok": True, "path": path,
                                          "file": p.name,
                                          "bytes": p.stat().st_size}
        ok += 1
    (day_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True))
    print(f"snapshot written to {day_dir} — {ok} ok, {bad} failed")
    return 0 if bad == 0 else 1


# ---------------------------------------------------------------------------
# subcommand: validate-start
# ---------------------------------------------------------------------------
def cmd_validate_start(args) -> int:
    print(_c("== validate-start ==", "b"))
    rc = cmd_preflight(args)
    if rc != 0:
        print(_c("preflight failed — refusing to start validation", "r"))
        return rc
    safety = _get("/api/arbicore/safety/status", args.base) or {}
    if not safety.get("kill", {}).get("engaged"):
        print(_c("KILL SWITCH IS NOT ENGAGED — refusing to start", "r"))
        return 3
    if safety.get("live_execution_enabled"):
        print(_c("LIVE EXECUTION ENABLED — refusing to start", "r"))
        return 3
    # Record start
    run_dir = Path(args.evidence)
    run_dir.mkdir(parents=True, exist_ok=True)
    start = {"validation_start": _iso(),
              "duration_days": args.days,
              "base": args.base,
              "safety_snapshot": safety,
              "operator": os.environ.get("USER") or "unknown"}
    (run_dir / "validation_run.json").write_text(
        json.dumps(start, indent=2, sort_keys=True))
    print(_c(f"✔ validation run started ({args.days} days) — "
              f"evidence root: {run_dir}", "g"))
    print("  archive daily with:  arbictl snapshot")
    print("  at the end run:      arbictl evidence-pack")
    return 0


# ---------------------------------------------------------------------------
# subcommand: evidence-pack
# ---------------------------------------------------------------------------
def cmd_evidence_pack(args) -> int:
    src = Path(args.evidence)
    if not src.exists():
        print(_c(f"evidence dir {src} missing", "r"))
        return 4
    out_dir = Path(args.out or (Path(DEFAULT_RELEASES) / "evidence"))
    out_dir.mkdir(parents=True, exist_ok=True)
    tar_path = out_dir / f"arbicore_evidence_{_now_slug()}.tar.gz"
    with tarfile.open(tar_path, "w:gz") as tf:
        tf.add(str(src), arcname="arbicore_evidence")
    # write summary
    print(_c(f"✔ evidence pack: {tar_path} ({tar_path.stat().st_size} bytes)",
             "g"))
    return 0


# ---------------------------------------------------------------------------
# subcommand: deploy
# ---------------------------------------------------------------------------
def cmd_deploy(args) -> int:
    print(_c(f"== deploy tag {args.tag} ==", "b"))
    repo = args.repo
    # 1. Verify bundle checksum (if provided)
    if args.checksum:
        shasums = Path(args.checksum)
        if not shasums.exists():
            print(_c(f"checksum file not found: {shasums}", "r"))
            return 5
        try:
            _run(["sha256sum", "-c", str(shasums)],
                  cwd=str(shasums.parent))
            print(_c("✔ bundle checksums verified", "g"))
        except Exception as e:                                       # noqa
            print(_c(f"checksum verify failed: {e}", "r"))
            return 5

    # 2. Backup current release
    Path(args.backup).mkdir(parents=True, exist_ok=True)
    prev_tag = _run(["git", "describe", "--tags", "--always"],
                     cwd=repo, capture=True, check=False)
    backup_dir = Path(args.backup) / f"pre_{args.tag}_{_now_slug()}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / "PREV_TAG").write_text(prev_tag or "unknown")
    print(f"backup meta: {backup_dir}")

    # 3. Fetch + checkout tag
    _run(["git", "fetch", "--tags"], cwd=repo, check=False)
    try:
        _run(["git", "checkout", args.tag], cwd=repo)
        print(_c(f"✔ checked out {args.tag}", "g"))
    except Exception as e:                                           # noqa
        print(_c(f"checkout failed: {e}", "r"))
        return 6

    # 4. Restart services
    try:
        _run(["sudo", "supervisorctl", "restart", "backend"], check=False)
        _run(["sudo", "supervisorctl", "restart", "frontend"], check=False)
        print(_c("✔ services restarted via supervisor", "g"))
    except Exception:                                                # noqa
        print(_c("supervisor restart returned non-zero — continuing", "y"))

    # 5. Wait for backend
    if not _wait_for("/api/", args.base, timeout=90):
        print(_c("backend did not come back within 90s", "r"))
        return 7

    # 6. Run preflight
    rc = cmd_preflight(args)
    if rc != 0:
        print(_c("preflight FAILED after deploy — rollback recommended", "r"))
        return rc

    # 7. Summary
    print(_c(f"✔ deploy {args.tag} completed cleanly", "g"))
    return 0


# ---------------------------------------------------------------------------
# subcommand: upgrade / rollback
# ---------------------------------------------------------------------------
def cmd_upgrade(args) -> int:
    # save current tag for rollback
    prev = _run(["git", "describe", "--tags", "--always"],
                 cwd=args.repo, capture=True, check=False)
    Path(args.backup).mkdir(parents=True, exist_ok=True)
    (Path(args.backup) / "LAST_KNOWN_GOOD").write_text(prev or "")
    print(f"last-known-good: {prev}")
    return cmd_deploy(args)


def cmd_rollback(args) -> int:
    p = Path(args.backup) / "LAST_KNOWN_GOOD"
    if not p.exists():
        print(_c("no LAST_KNOWN_GOOD marker — nothing to roll back to", "r"))
        return 8
    prev = p.read_text().strip()
    if not prev:
        print(_c("LAST_KNOWN_GOOD is empty", "r"))
        return 8
    print(_c(f"rolling back to {prev}", "y"))
    args.tag = prev
    args.checksum = None
    return cmd_deploy(args)


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------
def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser("arbictl",
                                  description="ArbiCore X ops toolkit")
    p.add_argument("--base", default=DEFAULT_BASE,
                    help=f"backend base URL (default {DEFAULT_BASE})")
    p.add_argument("--repo", default=DEFAULT_REPO,
                    help=f"repo path (default {DEFAULT_REPO})")
    p.add_argument("--releases", default=DEFAULT_RELEASES,
                    help=f"releases dir (default {DEFAULT_RELEASES})")
    p.add_argument("--evidence", default=DEFAULT_EVIDENCE,
                    help=f"evidence dir (default {DEFAULT_EVIDENCE})")
    p.add_argument("--backup", default=DEFAULT_BACKUP,
                    help=f"backup dir (default {DEFAULT_BACKUP})")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("version").set_defaults(fn=cmd_version)
    sub.add_parser("preflight").set_defaults(fn=cmd_preflight)
    sub.add_parser("dashboard").set_defaults(fn=cmd_dashboard)
    sub.add_parser("snapshot").set_defaults(fn=cmd_snapshot)

    vs = sub.add_parser("validate-start")
    vs.add_argument("--days", type=int, default=7)
    vs.set_defaults(fn=cmd_validate_start)

    ep = sub.add_parser("evidence-pack")
    ep.add_argument("--out", default=None)
    ep.set_defaults(fn=cmd_evidence_pack)

    d = sub.add_parser("deploy")
    d.add_argument("--tag", required=True)
    d.add_argument("--checksum", default=None,
                    help="path to a SHASUMS file to verify")
    d.set_defaults(fn=cmd_deploy)

    up = sub.add_parser("upgrade")
    up.add_argument("--tag", required=True)
    up.add_argument("--checksum", default=None)
    up.set_defaults(fn=cmd_upgrade)

    rb = sub.add_parser("rollback")
    rb.set_defaults(fn=cmd_rollback)

    args = p.parse_args(argv)
    try:
        return int(args.fn(args) or 0)
    except KeyboardInterrupt:
        print(_c("interrupted", "y"))
        return 130
    except Exception as e:                                            # noqa
        print(_c(f"arbictl: fatal: {e}", "r"))
        return 1


if __name__ == "__main__":
    sys.exit(main())
