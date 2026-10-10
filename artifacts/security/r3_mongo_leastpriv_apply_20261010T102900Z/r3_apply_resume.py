#!/usr/bin/env python3
"""Resume R3-APPLY after successful createUser (102900Z). Env still root."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

EXPECTED = "sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313"
PRIOR = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/security/"
    "r3_mongo_leastpriv_apply_20261010T102900Z"
)
PRIOR_BK = Path("/home/raghu/arbicore_backups/r3_mongo_leastpriv_20261010T102900Z")
PASS = PRIOR_BK / "arbicore_app.password"
ENVF = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env")
COMPOSE_DIR = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose")
OVERRIDE = Path("/tmp/arbicore-s2a-rpc-redact-override.yml")

TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVID = Path(
    f"/home/raghu/projects/arbicore-x-cert/artifacts/security/"
    f"r3_mongo_leastpriv_apply_{TS}"
)
BK = Path(f"/home/raghu/arbicore_backups/r3_mongo_leastpriv_{TS}")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(msg, flush=True)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def fail(stage: str, detail: str) -> None:
    write_json(
        EVID / "FAILURE.json",
        {"utc": utc(), "stage": stage, "detail": detail, "r3_applied": False},
    )
    log(f"FAIL stage={stage} detail={detail}")
    sys.exit(1)


def main() -> None:
    EVID.mkdir(parents=True, exist_ok=True)
    BK.mkdir(parents=True, exist_ok=True)
    os.chmod(EVID, 0o700)
    os.chmod(BK, 0o700)
    (EVID / "timestamp.txt").write_text(TS + "\n")

    if not PASS.is_file():
        fail("resume", "password escrow missing")
    pwd = PASS.read_text().strip()
    if len(pwd) < 16:
        fail("resume", "password escrow short")

    # Document resume rationale
    prior_fail = json.loads((PRIOR / "FAILURE.json").read_text())
    prior_verify = json.loads((PRIOR / "app_user_offline_verify.json").read_text())
    write_json(
        EVID / "resume_context.json",
        {
            "utc": utc(),
            "prior_evid": str(PRIOR),
            "prior_bk": str(PRIOR_BK),
            "prior_failure": prior_fail,
            "prior_verify": prior_verify,
            "rationale": (
                "createUser succeeded with exact readWrite@arbicore_x. "
                "Offline verify incorrectly treated listDatabases success as "
                "failure; MongoDB returns only authorized DBs for scoped users. "
                "factory_denied and admin_denied already true. Resuming env "
                "switch + recreate. No dropUser; reuse escrowed password."
            ),
            "password_sha12": hashlib.sha256(pwd.encode()).hexdigest()[:12],
        },
    )

    # Re-confirm user + auth with escrow
    run(["docker", "cp", str(PASS), "factory-mongo:/tmp/arbicore_app.password"])
    auth = run(
        [
            "docker",
            "exec",
            "factory-mongo",
            "sh",
            "-c",
            """
P=$(cat /tmp/arbicore_app.password)
mongosh --quiet --username arbicore_app --password "$P" --authenticationDatabase admin --eval '
  const out={};
  out.ping=db.adminCommand({ping:1}).ok;
  const ax=db.getSiblingDB("arbicore_x");
  out.cols=ax.getCollectionNames().length;
  out.discovery=ax.arbicore_discovery_candidates.estimatedDocumentCount();
  try { db.getSiblingDB("strategy_factory_v1").stats(); out.factory_denied=false; }
  catch(e){ out.factory_denied=true; }
  try { db.getSiblingDB("admin").createUser({user:"x",pwd:"y",roles:[]}); out.admin_denied=false; }
  catch(e){ out.admin_denied=true; }
  // listDatabases may succeed but only show authorized DBs
  try {
    const dbs=db.adminCommand({listDatabases:1, nameOnly:true}).databases.map(d=>d.name).sort();
    out.listDatabases_names=dbs;
    out.listDatabases_contains_factory=("strategy_factory_v1" in dbs) || dbs.includes("strategy_factory_v1");
  } catch(e){ out.listDatabases_error=String(e.message||e).slice(0,120); }
  print(JSON.stringify(out));
'
rm -f /tmp/arbicore_app.password
""",
        ]
    )
    (EVID / "resume_auth_verify.json").write_text(auth.stdout.strip() + "\n")
    v = json.loads(auth.stdout.strip())
    if v.get("ping") != 1 or not v.get("factory_denied") or not v.get("admin_denied"):
        fail("resume_auth", str(v))
    if v.get("listDatabases_contains_factory"):
        fail("resume_auth", "app user can see factory DB in listDatabases")
    log(f"RESUME_AUTH_OK {v}")

    # Ensure env still root (pre-switch)
    env_user = None
    for line in ENVF.read_text().splitlines():
        if line.startswith("MONGO_URL="):
            env_user = re.match(r"mongodb://([^:]+):", line.split("=", 1)[1]).group(1)
    if env_user != "root":
        fail("env_switch", f"unexpected pre-switch user={env_user}")

    # Fresh env backup in this BK + copy prior archive ref
    import shutil

    shutil.copy2(ENVF, BK / "backend.env.pre-r3")
    os.chmod(BK / "backend.env.pre-r3", 0o600)
    # keep password escrow also in this BK
    shutil.copy2(PASS, BK / "arbicore_app.password")
    os.chmod(BK / "arbicore_app.password", 0o600)
    # pointer to prior dump
    write_json(
        EVID / "backup_refs.json",
        {
            "apply_backup_102900Z": json.loads(
                (PRIOR / "apply_backup_meta.json").read_text()
            ),
            "validation_backup": (
                "/home/raghu/arbicore_backups/r3_backup_validation_20261010T101234Z/"
                "arbicore_x_20261010T101234Z.archive.gz"
            ),
            "env_backup_this_resume": str(BK / "backend.env.pre-r3"),
        },
    )

    # Stage 4: env switch
    text = ENVF.read_text()
    new_lines = []
    changed = False
    for line in text.splitlines(keepends=True):
        if line.startswith("MONGO_URL="):
            old = line[len("MONGO_URL=") :].rstrip("\n")
            m = re.match(r"mongodb://([^:]+):([^@]+)@([^/?]+)(\?.*)?$", old)
            if not m:
                fail("env_switch", "bad MONGO_URL shape")
            host = m.group(3)
            qs = m.group(4) or "?authSource=admin"
            if "authSource=" not in qs:
                qs = qs + ("&" if len(qs) > 1 else "") + "authSource=admin"
                if not qs.startswith("?"):
                    qs = "?" + qs.lstrip("&")
            new_uri = f"mongodb://arbicore_app:{quote_plus(pwd)}@{host}{qs}"
            new_lines.append("MONGO_URL=" + new_uri + "\n")
            changed = True
        else:
            new_lines.append(line)
    if not changed:
        fail("env_switch", "MONGO_URL missing")
    tmp = ENVF.with_suffix(".env.r3tmp")
    tmp.write_text("".join(new_lines))
    os.chmod(tmp, 0o600)
    tmp.replace(ENVF)
    os.chmod(ENVF, 0o600)
    user = None
    for line in ENVF.read_text().splitlines():
        if line.startswith("MONGO_URL="):
            user = re.match(r"mongodb://([^:]+):", line.split("=", 1)[1]).group(1)
    if user != "arbicore_app":
        fail("env_switch", f"post-write user={user}")
    write_json(
        EVID / "env_switch_attestation.json",
        {
            "utc": utc(),
            "old_username": "root",
            "new_username": user,
            "password_sha12": hashlib.sha256(pwd.encode()).hexdigest()[:12],
            "env_mode": oct(ENVF.stat().st_mode & 0o777),
            "keys_note": "MONGO_URL value only; key set unchanged",
        },
    )
    log("STAGE4_OK env_user=arbicore_app")

    # Stage 5: recreate
    compose = run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.prod.yml",
            "-f",
            str(OVERRIDE),
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "--pull",
            "never",
            "backend",
        ],
        cwd=str(COMPOSE_DIR),
    )
    (EVID / "compose_recreate.log").write_text(compose.stdout + compose.stderr)
    healthy = False
    for i in range(1, 61):
        try:
            h = run(
                [
                    "docker",
                    "inspect",
                    "arbicore-x-backend-new",
                    "--format",
                    "{{.State.Health.Status}}",
                ]
            ).stdout.strip()
            s = run(
                [
                    "docker",
                    "inspect",
                    "arbicore-x-backend-new",
                    "--format",
                    "{{.State.Status}}",
                ]
            ).stdout.strip()
        except subprocess.CalledProcessError:
            h, s = "missing", "missing"
        with open(EVID / "health_wait.log", "a") as fh:
            fh.write(f"wait_{i} health={h} status={s}\n")
        if h == "healthy" and s == "running":
            healthy = True
            break
        time.sleep(5)
    if not healthy:
        fail("recreate", "not healthy — execute rollback")

    img = run(
        ["docker", "inspect", "arbicore-x-backend-new", "--format", "{{.Image}}"]
    ).stdout.strip()
    if img != EXPECTED:
        fail("recreate", f"digest {img}")
    env_live = run(
        [
            "docker",
            "inspect",
            "arbicore-x-backend-new",
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
        ]
    ).stdout
    live_user = None
    vals = {}
    for line in env_live.splitlines():
        if "=" in line:
            k, val = line.split("=", 1)
            vals[k] = val
        if line.startswith("MONGO_URL="):
            live_user = re.match(r"mongodb://([^:]+):", line.split("=", 1)[1]).group(1)
    write_json(
        EVID / "post_recreate_identity.json",
        {
            "utc": utc(),
            "username": live_user,
            "image": img,
            "health": "healthy",
            "ARBICORE_EXECUTION_MODE": vals.get("ARBICORE_EXECUTION_MODE"),
            "ARBICORE_AUTOEXEC_AUTOSTART": vals.get("ARBICORE_AUTOEXEC_AUTOSTART"),
            "ARBICORE_RUNTIME_AUTOSTART": vals.get("ARBICORE_RUNTIME_AUTOSTART"),
        },
    )
    if live_user != "arbicore_app":
        fail("recreate", f"live_user={live_user}")
    log("STAGE5_OK")
    write_json(
        EVID / "APPLY_STAGES_COMPLETE.json",
        {
            "utc": utc(),
            "evid": str(EVID),
            "bk": str(BK),
            "prior_create_evid": str(PRIOR),
            "user_create_ts": "20261010T102900Z",
        },
    )
    log(f"RESUME_COMPLETE EVID={EVID}")


if __name__ == "__main__":
    main()
