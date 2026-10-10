#!/usr/bin/env python3
"""R3-APPLY orchestrator — never prints secrets."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote_plus

EXPECTED = "sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313"
TS = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
EVID = Path(f"/home/raghu/projects/arbicore-x-cert/artifacts/security/r3_mongo_leastpriv_apply_{TS}")
BK = Path(f"/home/raghu/arbicore_backups/r3_mongo_leastpriv_{TS}")
ENVF = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env")
COMPOSE_DIR = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose")
OVERRIDE = Path("/tmp/arbicore-s2a-rpc-redact-override.yml")
VAL_ARCHIVE = Path(
    "/home/raghu/arbicore_backups/r3_backup_validation_20261010T101234Z/"
    "arbicore_x_20261010T101234Z.archive.gz"
)
VAL_META = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/security/"
    "r3_decision_package_20261010T095919Z/backup_validation_meta.json"
)


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    print(msg, flush=True)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2) + "\n")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def docker_exec_sh(script: str) -> subprocess.CompletedProcess:
    """Run script inside factory-mongo; INITDB env expands in container only."""
    return run(["docker", "exec", "factory-mongo", "sh", "-c", script])


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
    write_json(EVID / "paths.json", {"evid": str(EVID), "bk": str(BK), "ts": TS})

    # --- Stage 0: prechecks ---
    img = run(
        ["docker", "inspect", "arbicore-x-backend-new", "--format", "{{.Image}}"]
    ).stdout.strip()
    if img != EXPECTED:
        fail("precheck", f"digest mismatch {img}")
    meta = json.loads(VAL_META.read_text())
    if not meta.get("validation_passed"):
        fail("precheck", "validation backup not passed")
    if not VAL_ARCHIVE.is_file():
        fail("precheck", "validation archive missing")
    if subprocess.call(["gzip", "-t", str(VAL_ARCHIVE)]) != 0:
        fail("precheck", "validation archive gzip failed")
    if not OVERRIDE.is_file() or not ENVF.is_file():
        fail("precheck", "compose override or env missing")

    baseline_disc = docker_exec_sh(
        'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" '
        '-p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin '
        '--eval \'db.getSiblingDB("arbicore_x").arbicore_discovery_candidates'
        ".estimatedDocumentCount()'"
    ).stdout.strip()
    write_json(
        EVID / "pre_apply_baseline.json",
        {
            "utc": utc(),
            "image": img,
            "discovery_estimated": int(baseline_disc),
            "validation_archive": str(VAL_ARCHIVE),
            "five_vs_six": (
                "Six RPC URL keys present; Alchemy key fps ca6545ba on "
                "ETH/ARB/OP/POLY/BNB + primary/archive; BASE is public "
                "mainnet.base.org (no Alchemy key). Read-only; unchanged."
            ),
        },
    )
    log(f"STAGE0_OK discovery={baseline_disc}")

    # --- Stage 1: apply-time backup ---
    dump_script = f"""
set -e
OUT=/tmp/arbicore_x_{TS}.archive.gz
mongodump \\
  --username="$MONGO_INITDB_ROOT_USERNAME" \\
  --password="$MONGO_INITDB_ROOT_PASSWORD" \\
  --authenticationDatabase=admin \\
  --db=arbicore_x \\
  --archive="$OUT" \\
  --gzip
ls -la "$OUT"
"""
    dump = docker_exec_sh(dump_script)
    (EVID / "apply_mongodump.log").write_text(dump.stdout + dump.stderr)
    arch_host = BK / f"arbicore_x_{TS}.archive.gz"
    run(["docker", "cp", f"factory-mongo:/tmp/arbicore_x_{TS}.archive.gz", str(arch_host)])
    docker_exec_sh(f"rm -f /tmp/arbicore_x_{TS}.archive.gz")
    shutil.copy2(ENVF, BK / "backend.env.pre-r3")
    for p in BK.iterdir():
        os.chmod(p, 0o600)
    if subprocess.call(["gzip", "-t", str(arch_host)]) != 0:
        fail("backup", "apply archive gzip failed")
    st = arch_host.stat()
    if st.st_size < 100_000_000:
        fail("backup", f"archive too small {st.st_size}")
    write_json(
        EVID / "apply_backup_meta.json",
        {
            "utc": utc(),
            "archive": str(arch_host),
            "size_bytes": st.st_size,
            "mode": oct(st.st_mode & 0o777),
            "env_backup": str(BK / "backend.env.pre-r3"),
            "validation_archive_ref": str(VAL_ARCHIVE),
        },
    )
    log(f"STAGE1_OK backup_size={st.st_size}")

    # --- Stage 2: create user ---
    existing = docker_exec_sh(
        'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" '
        '-p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin '
        '--eval \'JSON.stringify(db.getSiblingDB("admin").getUser("arbicore_app"))\''
    ).stdout.strip()
    if existing not in ("null", "undefined", ""):
        fail("createUser", "arbicore_app already exists")

    pwd = run(["openssl", "rand", "-base64", "32"]).stdout.strip()
    pass_path = BK / "arbicore_app.password"
    pass_path.write_text(pwd)
    os.chmod(pass_path, 0o600)
    js = """const fs = require('fs');
const pwd = fs.readFileSync('/tmp/arbicore_app.password', 'utf8').replace(/\\r?\\n$/, '');
if (!pwd || pwd.length < 16) { throw new Error('password file empty/short'); }
const admin = db.getSiblingDB('admin');
if (admin.getUser('arbicore_app')) { throw new Error('arbicore_app already exists'); }
admin.createUser({
  user: 'arbicore_app',
  pwd: pwd,
  roles: [ { role: 'readWrite', db: 'arbicore_x' } ]
});
const info = admin.getUser('arbicore_app');
print(JSON.stringify({ user: info.user, roles: info.roles, db: info.db }));
"""
    js_host = BK / "create_arbicore_app.js"
    js_host.write_text(js)
    os.chmod(js_host, 0o600)
    run(["docker", "cp", str(pass_path), "factory-mongo:/tmp/arbicore_app.password"])
    run(["docker", "cp", str(js_host), "factory-mongo:/tmp/create_arbicore_app.js"])
    create = docker_exec_sh(
        """
set -e
chmod 600 /tmp/arbicore_app.password /tmp/create_arbicore_app.js
mongosh --quiet \
  --username="$MONGO_INITDB_ROOT_USERNAME" \
  --password="$MONGO_INITDB_ROOT_PASSWORD" \
  --authenticationDatabase=admin \
  /tmp/create_arbicore_app.js
rm -f /tmp/arbicore_app.password /tmp/create_arbicore_app.js
"""
    )
    (EVID / "create_user_result.json").write_text(create.stdout.strip() + "\n")
    if create.stderr:
        (EVID / "create_user.stderr").write_text(create.stderr)
    try:
        js_host.unlink()
    except OSError:
        pass
    created = json.loads(create.stdout.strip())
    if created.get("user") != "arbicore_app":
        fail("createUser", "unexpected create result")
    roles = created.get("roles") or []
    if roles != [{"role": "readWrite", "db": "arbicore_x"}]:
        fail("createUser", f"unexpected roles {roles}")
    write_json(
        EVID / "credential_attestation.json",
        {
            "user": "arbicore_app",
            "password_sha12": hashlib.sha256(pwd.encode()).hexdigest()[:12],
            "roles": roles,
        },
    )
    log(f"STAGE2_OK user=arbicore_app roles={roles}")

    # --- Stage 3: offline verify as app user ---
    run(["docker", "cp", str(pass_path), "factory-mongo:/tmp/arbicore_app.password"])
    verify_script = r"""
set -e
U=arbicore_app
P=$(cat /tmp/arbicore_app.password)
mongosh --quiet --username "$U" --password "$P" --authenticationDatabase admin --eval '
  const out = {};
  out.ping = db.adminCommand({ping:1}).ok;
  const ax = db.getSiblingDB("arbicore_x");
  out.arbicore_cols = ax.getCollectionNames().length;
  out.discovery = ax.arbicore_discovery_candidates.estimatedDocumentCount();
  try { db.getSiblingDB("strategy_factory_v1").getCollectionNames(); out.factory_denied = false; }
  catch (e) { out.factory_denied = true; out.factory_err = String(e.message||e).slice(0,160); }
  try { db.adminCommand({listDatabases:1}); out.listDBs_denied = false; }
  catch (e) { out.listDBs_denied = true; }
  try { db.getSiblingDB("admin").createUser({user:"x",pwd:"y",roles:[]}); out.admin_denied = false; }
  catch (e) { out.admin_denied = true; }
  const c = ax.r3_apply_probe;
  const id = new ObjectId();
  c.insertOne({_id:id, purpose:"r3-apply-probe", ts: new Date()});
  out.crud_read = c.findOne({_id:id}) != null;
  c.deleteOne({_id:id});
  out.crud_delete = c.findOne({_id:id}) == null;
  out.ttl_indexes_login_attempts = ax.login_attempts.getIndexes().filter(i=>i.expireAfterSeconds!=null).length;
  print(JSON.stringify(out));
'
rm -f /tmp/arbicore_app.password
"""
    vrun = docker_exec_sh(verify_script)
    (EVID / "app_user_offline_verify.json").write_text(vrun.stdout.strip() + "\n")
    if vrun.stderr:
        (EVID / "app_user_offline_verify.stderr").write_text(vrun.stderr)
    v = json.loads(vrun.stdout.strip())
    for key in ("ping", "factory_denied", "listDBs_denied", "admin_denied", "crud_read", "crud_delete"):
        if key == "ping":
            if v.get("ping") != 1:
                fail("offline_verify", f"ping={v.get('ping')}")
        elif not v.get(key):
            fail("offline_verify", f"{key}={v.get(key)} full={v}")
    if v.get("arbicore_cols", 0) < 50:
        fail("offline_verify", f"cols={v.get('arbicore_cols')}")
    log(f"STAGE3_OK offline_verify={v}")

    # --- Stage 4: env switch ---
    text = ENVF.read_text()
    new_lines = []
    old_user = None
    changed = False
    for line in text.splitlines(keepends=True):
        if line.startswith("MONGO_URL="):
            old = line[len("MONGO_URL=") :].rstrip("\n")
            m = re.match(r"mongodb://([^:]+):([^@]+)@([^/?]+)(\?.*)?$", old)
            if not m:
                fail("env_switch", "unrecognized MONGO_URL shape")
            old_user = m.group(1)
            host = m.group(3)
            qs = m.group(4) or "?authSource=admin"
            if "authSource=" not in qs:
                qs = ("?" if not qs.startswith("?") else qs)
                qs = qs + ("&" if len(qs) > 1 else "") + "authSource=admin"
            new_uri = f"mongodb://arbicore_app:{quote_plus(pwd)}@{host}{qs}"
            new_lines.append("MONGO_URL=" + new_uri + "\n")
            changed = True
        else:
            new_lines.append(line)
    if not changed:
        fail("env_switch", "MONGO_URL not found")
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
    keys1 = {
        l.split("=", 1)[0]
        for l in (BK / "backend.env.pre-r3").read_text().splitlines()
        if "=" in l and not l.startswith("#")
    }
    keys2 = {
        l.split("=", 1)[0]
        for l in ENVF.read_text().splitlines()
        if "=" in l and not l.startswith("#")
    }
    write_json(
        EVID / "env_switch_attestation.json",
        {
            "utc": utc(),
            "old_username": old_user,
            "new_username": user,
            "password_sha12": hashlib.sha256(pwd.encode()).hexdigest()[:12],
            "keys_equal": keys1 == keys2,
            "env_mode": oct(ENVF.stat().st_mode & 0o777),
        },
    )
    log(f"STAGE4_OK env_user={user}")

    # --- Stage 5: recreate ---
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
        fail("recreate", "backend not healthy within timeout — rollback required")

    img2 = run(
        ["docker", "inspect", "arbicore-x-backend-new", "--format", "{{.Image}}"]
    ).stdout.strip()
    if img2 != EXPECTED:
        fail("recreate", f"digest changed {img2}")

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
    for line in env_live.splitlines():
        if line.startswith("MONGO_URL="):
            live_user = re.match(r"mongodb://([^:]+):", line.split("=", 1)[1]).group(1)
    write_json(
        EVID / "post_recreate_identity.json",
        {"username": live_user, "image": img2, "health": "healthy", "utc": utc()},
    )
    if live_user != "arbicore_app":
        fail("recreate", f"live username={live_user}")
    log("STAGE5_OK recreate healthy digest unchanged user=arbicore_app")
    write_json(
        EVID / "APPLY_STAGES_COMPLETE.json",
        {"utc": utc(), "evid": str(EVID), "bk": str(BK), "ts": TS},
    )
    # keep password escrow in BK; do not shred until post-verify succeeds (separate step)
    log(f"APPLY_COMPLETE EVID={EVID} BK={BK}")


if __name__ == "__main__":
    main()
