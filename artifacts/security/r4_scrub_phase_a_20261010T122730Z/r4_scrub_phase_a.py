#!/usr/bin/env python3
"""R4-SCRUB Phase A — quarantine 17 reviewed carriers. No shred. Never print secrets."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

EVID = Path(os.environ["R4_SCRUB_A_EVID"])
QDIR = Path(os.environ["R4_SCRUB_A_QDIR"])
PREFLIGHT_INV = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/security/"
    "r4_scrub_preflight_20261010T111949Z/r4_scrub_inventory_reconcile.json"
)
LIVE_ENV = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env")
CTR = "arbicore-x-backend-new"
EXPECTED_DIGEST = "sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313"
NEW_ADMIN = "112c88ac69e1"
NEW_JWT = "f98650d468b2"
OLD_ADMINS = {"6757aa3396d8", "6780d7b21193"}
OLD_JWTS = {"066b178751e1", "7013ef842946"}
HOLD_DAYS = 14

TARGETS = [
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.pre-m25-usd-numeraire-20260912T121226Z",
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.g5.27-backup-20260927-101642",
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.pre-paper-20260916T112833Z",
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.backup.20261002-081704",
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.g5.62-backup-20260927-105923",
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.bak-20260916-133913",
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.pre-executor-owner-refresh-20260912T100117Z",
    "/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env.pre-t2-wss-20260911T160217Z",
    "/tmp/arbicore_ctr_all.env",
    "/tmp/arbicore-runtime-cert-ad64a50.env",
    "/tmp/arbicore-x-backend.env",
    "/tmp/arbicore-runtime-cert.env",
    "/tmp/arbicore-x-candidate.env",
    "/tmp/arbicore-backend-p0-3.env",
    "/tmp/arbicore-backend.env",
    "/tmp/arbicore-x-runtime.env",
    "/tmp/arbicore-production-env.backup",
]

LEGACY = [
    "arbicore-x-backend-h05",
    "arbicore-x-backend-w1",
    "arbicore-x-b7-candidate",
    "arbicore-x-backend",
]


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"[{utc()}] {msg}"
    print(line, flush=True)
    with open(EVID / "phase_a.log", "a") as fh:
        fh.write(line + "\n")


def fail(stage: str, detail: str) -> None:
    (EVID / "FAILURE.json").write_text(
        json.dumps({"utc": utc(), "stage": stage, "detail": detail}, indent=2) + "\n"
    )
    log(f"FAIL {stage}: {detail}")
    sys.exit(2)


def sha12(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()[:12]


def file_sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def secret_att(p: Path) -> dict:
    vals = parse_env(p.read_text(errors="replace"))
    admin = vals.get("ARBICORE_ADMIN_PASS") or vals.get("ARBICORE_ADMIN_PASSWORD") or ""
    jwt = vals.get("JWT_SECRET") or vals.get("ARBICORE_JWT_SECRET") or ""
    return {
        "admin_sha12": sha12(admin) if admin else None,
        "admin_len": len(admin) if admin else 0,
        "jwt_sha12": sha12(jwt) if jwt else None,
        "jwt_len": len(jwt) if jwt else 0,
    }


def inspect_ctr(name: str) -> dict:
    r = subprocess.run(
        ["docker", "inspect", name, "--format", "{{json .}}"],
        text=True,
        capture_output=True,
    )
    if r.returncode != 0:
        return {"container": name, "error": (r.stderr or "")[:200]}
    j = json.loads(r.stdout)
    env = {}
    for e in j.get("Config", {}).get("Env") or []:
        if "=" in e:
            k, _, v = e.partition("=")
            env[k] = v
    return {
        "container": name,
        "status": j["State"]["Status"],
        "running": j["State"]["Running"],
        "image_id": j.get("Image"),
        "health": (j.get("State") or {}).get("Health", {}).get("Status"),
        "admin_sha12": sha12(env["ARBICORE_ADMIN_PASS"]) if env.get("ARBICORE_ADMIN_PASS") else None,
        "jwt_sha12": sha12(env["JWT_SECRET"]) if env.get("JWT_SECRET") else None,
        "bootstrap_present": bool(env.get("ARBICORE_BOOTSTRAP_TOKEN")),
        "private_key_env_present": any("PRIVATE_KEY" in k and env.get(k) for k in env),
        "controls": {
            k: env.get(k)
            for k in (
                "ARBICORE_EXECUTION_MODE",
                "ARBICORE_AUTOEXEC_AUTOSTART",
                "ARBICORE_RUNTIME_AUTOSTART",
            )
        },
        "mongo_url_user": (
            env.get("MONGO_URL", "").split("://", 1)[-1].split(":", 1)[0]
            if "://" in env.get("MONGO_URL", "")
            else None
        ),
    }


def http_code(url: str, method="GET", body=None) -> int:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status
    except Exception as e:
        return int(getattr(e, "code", 0) or 0)


def main() -> None:
    os.umask(0o077)
    EVID.mkdir(parents=True, exist_ok=True)
    log("R4-SCRUB Phase A start")

    inv = json.loads(PREFLIGHT_INV.read_text())
    reviewed = {c["path"] for c in inv["scrub_candidates"]}
    approved = {r["path"] for r in inv["approved_recovery"]}
    forbidden = {
        str(LIVE_ENV),
        *approved,
        "/home/raghu/arbicore_backups/r4_admin_jwt_20261010T110918Z/admin.password.new",
        "/home/raghu/arbicore_backups/r4_admin_jwt_20261010T110918Z/admin.password.pre-r4",
        "/home/raghu/arbicore_backups/r4_admin_jwt_20261010T110918Z/backend.env.pre-r4",
        "/home/raghu/arbicore_backups/r4_admin_jwt_20261010T110918Z/jwt.secret.new",
    }

    if len(TARGETS) != 17:
        fail("precheck", f"TARGETS count {len(TARGETS)} != 17")
    if set(TARGETS) != reviewed:
        only_t = sorted(set(TARGETS) - reviewed)
        only_r = sorted(reviewed - set(TARGETS))
        fail("precheck", f"mismatch only_targets={only_t} only_reviewed={only_r}")

    live_ctr = inspect_ctr(CTR)
    if live_ctr.get("image_id") != EXPECTED_DIGEST or live_ctr.get("health") != "healthy":
        fail("precheck_live", f"digest/health bad: {live_ctr}")
    if live_ctr.get("admin_sha12") != NEW_ADMIN or live_ctr.get("jwt_sha12") != NEW_JWT:
        fail("precheck_live", "container not on new secrets")
    live_att = secret_att(LIVE_ENV)
    if live_att["admin_sha12"] != NEW_ADMIN or live_att["jwt_sha12"] != NEW_JWT:
        fail("precheck_live", "live .env not on new secrets")

    live_resolved = LIVE_ENV.resolve()
    forbidden_resolved = set()
    for f in forbidden:
        fp = Path(f)
        if fp.exists():
            forbidden_resolved.add(fp.resolve())

    prechecks = []
    for src in TARGETS:
        p = Path(src)
        row: dict = {"path": src, "ok": True, "reasons": []}
        if src in forbidden:
            row["ok"] = False
            row["reasons"].append("forbidden_overlap")
        if not p.exists():
            row["ok"] = False
            row["reasons"].append("missing")
        elif not p.is_file():
            row["ok"] = False
            row["reasons"].append("not_regular_file")
        else:
            try:
                resolved = p.resolve()
            except Exception as e:
                row["ok"] = False
                row["reasons"].append(f"resolve_error:{type(e).__name__}")
                resolved = None
            if resolved == live_resolved:
                row["ok"] = False
                row["reasons"].append("resolves_to_live_env")
            if resolved is not None and resolved in forbidden_resolved:
                row["ok"] = False
                row["reasons"].append("resolves_to_forbidden")
            if src not in reviewed:
                row["ok"] = False
                row["reasons"].append("unreviewed")
            att = secret_att(p)
            row["pre_move"] = {
                **att,
                "mode": oct(p.stat().st_mode & 0o777),
                "size": p.stat().st_size,
                "sha256": file_sha256(p),
                "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                ),
            }
            if att["admin_sha12"] not in OLD_ADMINS and att["jwt_sha12"] not in OLD_JWTS:
                row["ok"] = False
                row["reasons"].append("no_old_admin_or_jwt_fingerprint")
            if att["admin_sha12"] != "6780d7b21193" or att["jwt_sha12"] != "7013ef842946":
                row["ok"] = False
                row["reasons"].append(
                    f"unexpected_generation admin={att['admin_sha12']} jwt={att['jwt_sha12']}"
                )
        prechecks.append(row)

    (EVID / "target_precheck.json").write_text(
        json.dumps({"utc": utc(), "rows": prechecks}, indent=2) + "\n"
    )
    bad = [r for r in prechecks if not r["ok"]]
    if bad:
        fail("precheck", f"{len(bad)} targets failed: {[r['path'] for r in bad]}")

    for ap in sorted(approved):
        if not Path(ap).exists():
            fail("precheck_recovery", f"missing approved recovery {ap}")

    log(f"STAGE0_OK precheck n={len(TARGETS)}")

    if QDIR.exists():
        fail("quarantine", f"quarantine dir already exists: {QDIR}")
    QDIR.mkdir(parents=True, exist_ok=False)
    os.chmod(QDIR, 0o700)
    local_q = QDIR / "local_upgrade_backups"
    tmp_q = QDIR / "tmp_ephemeral"
    local_q.mkdir()
    tmp_q.mkdir()
    os.chmod(local_q, 0o700)
    os.chmod(tmp_q, 0o700)

    moves = []
    for src in TARGETS:
        p = Path(src)
        pre = next(r for r in prechecks if r["path"] == src)["pre_move"]
        if src.startswith("/tmp/"):
            dest_dir = tmp_q
            cls = "redundant_temporary"
        else:
            dest_dir = local_q
            cls = "redundant_local_upgrade_backup"
        dest = dest_dir / p.name
        if dest.exists():
            fail("move", f"dest exists {dest}")
        shutil.move(str(p), str(dest))
        os.chmod(dest, 0o600)
        post_sha = file_sha256(dest)
        post_att = secret_att(dest)
        if post_sha != pre["sha256"]:
            fail("integrity", f"sha256 mismatch after mv for {src}")
        if (
            post_att["admin_sha12"] != pre["admin_sha12"]
            or post_att["jwt_sha12"] != pre["jwt_sha12"]
        ):
            fail("integrity", f"secret sha12 mismatch after mv for {src}")
        if p.exists():
            fail("move", f"source still present {src}")
        moves.append(
            {
                "source": src,
                "destination": str(dest),
                "class": cls,
                "pre_mode": pre["mode"],
                "dest_mode": oct(dest.stat().st_mode & 0o777),
                "size": pre["size"],
                "sha256": post_sha,
                "admin_sha12": post_att["admin_sha12"],
                "jwt_sha12": post_att["jwt_sha12"],
                "moved_utc": utc(),
            }
        )
        log(f"MOVED {cls} name={p.name} sha256_prefix={post_sha[:16]}")

    hold_until = (datetime.now(timezone.utc) + timedelta(days=HOLD_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    move_map = {
        "utc": utc(),
        "quarantine_dir": str(QDIR),
        "quarantine_mode": oct(QDIR.stat().st_mode & 0o777),
        "hold_days": HOLD_DAYS,
        "hold_until_utc": hold_until,
        "destroy_authorised": False,
        "moves": moves,
    }
    (EVID / "move_map.json").write_text(json.dumps(move_map, indent=2) + "\n")

    restore_sh = EVID / "restore_from_quarantine.sh"
    restore_sh.write_text(
        "#!/usr/bin/env bash\n"
        "# R4-SCRUB Phase A restore — reverse quarantine moves (before destroy only).\n"
        "set -euo pipefail\n"
        f'EVID_DIR="{EVID}"\n'
        "python3 - \"$EVID_DIR/move_map.json\" <<'PY'\n"
        "import json, shutil, sys\n"
        "from pathlib import Path\n"
        "m = json.loads(Path(sys.argv[1]).read_text())\n"
        "for row in m['moves']:\n"
        "    src = Path(row['destination'])\n"
        "    dst = Path(row['source'])\n"
        "    if not src.is_file():\n"
        "        raise SystemExit(f'missing quarantine file: {src}')\n"
        "    if dst.exists():\n"
        "        raise SystemExit(f'restore target exists: {dst}')\n"
        "    dst.parent.mkdir(parents=True, exist_ok=True)\n"
        "    shutil.move(str(src), str(dst))\n"
        "    print(f'restored {dst}')\n"
        "print('restore complete')\n"
        "PY\n"
    )
    os.chmod(restore_sh, 0o700)

    post_ctr = inspect_ctr(CTR)
    post_live = secret_att(LIVE_ENV)
    sources_absent = {src: (not Path(src).exists()) for src in TARGETS}
    dests_present = {m["destination"]: Path(m["destination"]).is_file() for m in moves}
    recovery_ok = {ap: Path(ap).exists() for ap in sorted(approved)}
    legacy = []
    for n in LEGACY:
        info = inspect_ctr(n)
        legacy.append(
            {"container": n, "status": info.get("status"), "running": info.get("running")}
        )

    g579 = inspect_ctr("arbicore-g5-79-app")
    foreman = subprocess.run(
        ["docker", "inspect", "foreman-mongo", "--format", "{{.State.Status}}"],
        text=True,
        capture_output=True,
    )
    docs = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "https://api.arbicorex.in/docs"],
        text=True,
        capture_output=True,
        timeout=30,
    )
    api = subprocess.run(
        ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", "https://api.arbicorex.in/api/"],
        text=True,
        capture_output=True,
        timeout=30,
    )
    setup = http_code(
        "http://127.0.0.1:8001/api/auth/setup",
        "POST",
        {"username": "xattacker", "password": "not-used-here1"},
    )
    api_local = http_code("http://127.0.0.1:8001/api/")

    checks = {
        "S1_live_new_secrets_healthy": (
            post_live["admin_sha12"] == NEW_ADMIN
            and post_live["jwt_sha12"] == NEW_JWT
            and post_ctr.get("admin_sha12") == NEW_ADMIN
            and post_ctr.get("jwt_sha12") == NEW_JWT
            and post_ctr.get("image_id") == EXPECTED_DIGEST
            and post_ctr.get("health") == "healthy"
            and post_live["admin_sha12"] not in OLD_ADMINS
            and post_live["jwt_sha12"] not in OLD_JWTS
            and post_ctr.get("admin_sha12") not in OLD_ADMINS
            and post_ctr.get("jwt_sha12") not in OLD_JWTS
        ),
        "S2_all_17_sources_absent": all(sources_absent.values()),
        "S2b_all_17_dests_present": all(dests_present.values()),
        "S3_approved_recovery_present": all(recovery_ok.values()),
        "S4_legacy_exited_untouched": all(
            x.get("status") == "exited" and x.get("running") is False for x in legacy
        ),
        "S5_r1_r2_api": (docs.stdout or "").strip() == "404"
        and setup == 503
        and (api.stdout or "").strip() == "200"
        and api_local == 200,
        "S6_controls": (
            post_ctr.get("controls", {}).get("ARBICORE_EXECUTION_MODE") == "SHADOW"
            and post_ctr.get("controls", {}).get("ARBICORE_AUTOEXEC_AUTOSTART") == "false"
            and post_ctr.get("controls", {}).get("ARBICORE_RUNTIME_AUTOSTART") == "false"
            and not post_ctr.get("bootstrap_present")
            and not post_ctr.get("private_key_env_present")
            and post_ctr.get("mongo_url_user") == "arbicore_app"
        ),
        "quarantine_mode_700": oct(QDIR.stat().st_mode & 0o777) == "0o700",
        "no_shred": True,
        "move_count_17": len(moves) == 17,
    }
    ver = {
        "utc": utc(),
        "checks": checks,
        "all_pass": all(checks.values()),
        "details": {
            "live_dotenv": post_live,
            "live_container": {
                k: post_ctr.get(k)
                for k in (
                    "image_id",
                    "health",
                    "status",
                    "admin_sha12",
                    "jwt_sha12",
                    "controls",
                    "mongo_url_user",
                    "bootstrap_present",
                    "private_key_env_present",
                )
            },
            "sources_absent": sources_absent,
            "dests_present_count": sum(1 for v in dests_present.values() if v),
            "recovery_ok_count": sum(1 for v in recovery_ok.values() if v),
            "legacy": legacy,
            "g5_79_app": g579.get("status"),
            "foreman_mongo": (foreman.stdout or "").strip(),
            "docs_public": (docs.stdout or "").strip(),
            "api_public": (api.stdout or "").strip(),
            "setup_status": setup,
            "api_local": api_local,
            "hold_until_utc": hold_until,
            "quarantine_dir": str(QDIR),
        },
    }
    (EVID / "post_phase_a_verification.json").write_text(json.dumps(ver, indent=2) + "\n")
    if not ver["all_pass"]:
        failed = [k for k, v in checks.items() if not v]
        fail("verification", f"failed={failed}")

    (EVID / "PHASE_A_SUMMARY.json").write_text(
        json.dumps(
            {
                "utc": utc(),
                "verdict": "PASS",
                "phase": "A_quarantine_only",
                "moved": 17,
                "quarantine_dir": str(QDIR),
                "hold_until_utc": hold_until,
                "shred_or_destroy": "NOT_DONE",
                "phase_b": "NOT_DONE",
                "r4_live_verdict": "PASS WITH LIMITATIONS",
                "overall_gate_p2": "BLOCKED",
            },
            indent=2,
        )
        + "\n"
    )
    log("R4-SCRUB Phase A PASS — quarantine hold active; no destroy")


if __name__ == "__main__":
    main()
