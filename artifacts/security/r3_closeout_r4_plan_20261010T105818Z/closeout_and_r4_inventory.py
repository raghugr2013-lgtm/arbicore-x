#!/usr/bin/env python3
"""Read-only R3 closeout probe + R4 secret-location inventory (no secret values printed)."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

EVID = Path(__file__).resolve().parent
EXPECTED = "sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313"
APPLY = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/security/"
    "r3_mongo_leastpriv_apply_20261010T105128Z"
)
PRIOR = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/security/"
    "r3_mongo_leastpriv_apply_20261010T102900Z"
)
VAL_META = Path(
    "/home/raghu/projects/arbicore-x-cert/artifacts/security/"
    "r3_decision_package_20261010T095919Z/backup_validation_meta.json"
)
ENVF = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env")
V2 = Path("/home/raghu/projects/arbicore-x-v2")


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, text=True, capture_output=True, **kw)


def http(url, method="GET", data=None):
    cmd = ["curl", "-sS", "-o", "/tmp/r3co_body", "-w", "%{http_code}", "--max-time", "15"]
    if method == "POST":
        cmd += ["-X", "POST", "-H", "Content-Type: application/json", "-d", data or "{}"]
    cmd.append(url)
    try:
        return int(run(cmd).stdout.strip())
    except Exception as e:
        return str(e)


def sha12(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()[:12]


def key_fps(url: str | None):
    m = re.search(r"/v2/([^/?]+)", url or "")
    return hashlib.sha256(m.group(1).encode()).hexdigest()[:8] if m else None


def mongo_user_of(cname: str):
    e = run(
        ["docker", "inspect", cname, "--format", "{{range .Config.Env}}{{println .}}{{end}}"]
    ).stdout
    for line in e.splitlines():
        if line.startswith("MONGO_URL="):
            m = re.match(r"mongodb://([^:]+):", line.split("=", 1)[1])
            return m.group(1) if m else None
    return None


def scan_env_file(path: Path, keys=("ARBICORE_ADMIN_PASS", "JWT_SECRET", "ARBICORE_ADMIN_USER")):
    if not path.is_file():
        return None
    st = path.stat()
    out = {
        "path": str(path),
        "mode": oct(st.st_mode & 0o777),
        "size": st.st_size,
        "mtime_utc": datetime.fromtimestamp(st.st_mtime, timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        ),
        "keys": {},
    }
    try:
        text = path.read_text(errors="replace")
    except PermissionError:
        out["error"] = "permission_denied"
        return out
    for line in text.splitlines():
        if "=" not in line or line.strip().startswith("#"):
            continue
        k, v = line.split("=", 1)
        if k in keys or k in ("ARBICORE_ADMIN_PASS", "JWT_SECRET", "ARBICORE_ADMIN_USER", "ARBICORE_BOOTSTRAP_TOKEN"):
            if k in ("ARBICORE_ADMIN_PASS", "JWT_SECRET", "ARBICORE_BOOTSTRAP_TOKEN"):
                out["keys"][k] = {"present": bool(v), "len": len(v), "sha12": sha12(v) if v else None}
            elif k == "ARBICORE_ADMIN_USER":
                out["keys"][k] = {"value": v}  # username not secret
    return out


def main():
    img = run(
        ["docker", "inspect", "arbicore-x-backend-new", "--format", "{{.Image}}"]
    ).stdout.strip()
    health = run(
        [
            "docker",
            "inspect",
            "arbicore-x-backend-new",
            "--format",
            "{{.State.Health.Status}}",
        ]
    ).stdout.strip()
    env_txt = run(
        [
            "docker",
            "inspect",
            "arbicore-x-backend-new",
            "--format",
            "{{range .Config.Env}}{{println .}}{{end}}",
        ]
    ).stdout
    vals = {}
    for line in env_txt.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            vals[k] = v
    mongo_user = re.match(r"mongodb://([^:]+):", vals.get("MONGO_URL", "")).group(1)
    fps = {
        c: key_fps(vals.get(f"ARBICORE_RPC_URL_{c}", ""))
        for c in ["ETHEREUM", "ARBITRUM", "OPTIMISM", "POLYGON", "BNB", "BASE"]
    }

    users = run(
        [
            "docker",
            "exec",
            "factory-mongo",
            "sh",
            "-c",
            (
                'mongosh --quiet -u "$MONGO_INITDB_ROOT_USERNAME" '
                '-p "$MONGO_INITDB_ROOT_PASSWORD" --authenticationDatabase admin '
                "--eval 'JSON.stringify({user:db.getSiblingDB(\"admin\").getUser(\"arbicore_app\").user,"
                "roles:db.getSiblingDB(\"admin\").getUser(\"arbicore_app\").roles,"
                "discovery:db.getSiblingDB(\"arbicore_x\").arbicore_discovery_candidates.estimatedDocumentCount(),"
                "ttl:db.getSiblingDB(\"arbicore_x\").getCollectionNames().reduce((n,c)=>{try{return n+db.getSiblingDB(\"arbicore_x\").getCollection(c).getIndexes().filter(i=>i.expireAfterSeconds!=null).length}catch(e){return n}},0),"
                "probe_exists:db.getSiblingDB(\"arbicore_x\").getCollectionNames().includes(\"r3_apply_probe\")})'"
            ),
        ]
    ).stdout.strip()
    users_j = json.loads(users)

    pass_path = Path(
        "/home/raghu/arbicore_backups/r3_mongo_leastpriv_20261010T102900Z/arbicore_app.password"
    )
    app_ok = None
    if pass_path.is_file():
        run(["docker", "cp", str(pass_path), "factory-mongo:/tmp/arbicore_app.password"])
        app = run(
            [
                "docker",
                "exec",
                "factory-mongo",
                "sh",
                "-c",
                (
                    'P=$(cat /tmp/arbicore_app.password); '
                    'mongosh --quiet --username arbicore_app --password "$P" '
                    "--authenticationDatabase admin --eval '"
                    "JSON.stringify({ping:db.adminCommand({ping:1}).ok,"
                    "factory_denied:(()=>{try{db.getSiblingDB(\"strategy_factory_v1\").getCollectionNames();return false}"
                    "catch(e){return true}})(),"
                    "dbs:db.adminCommand({listDatabases:1,nameOnly:true}).databases.map(d=>d.name)})'; "
                    "rm -f /tmp/arbicore_app.password"
                ),
            ]
        ).stdout.strip()
        app_ok = json.loads(app)

    r1 = {
        u: http(u)
        for u in [
            "https://144-91-78-175.sslip.io/docs",
            "https://arbicorex.in/docs",
            "https://api.arbicorex.in/docs",
        ]
    }
    r2 = http(
        "http://127.0.0.1:8001/api/auth/setup",
        "POST",
        '{"username":"r3co","password":"x1234567","confirm_password":"x1234567"}',
    )
    api = http("http://127.0.0.1:8001/api/")

    legacy = run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "name=arbicore-x-backend",
            "--format",
            "{{.Names}}\t{{.Status}}",
        ]
    ).stdout.strip().splitlines()
    g579 = run(
        [
            "docker",
            "ps",
            "--filter",
            "name=arbicore-g5-79",
            "--format",
            "{{.Names}}\t{{.Status}}\t{{.Image}}",
        ]
    ).stdout.strip().splitlines()
    foreman = run(
        [
            "docker",
            "ps",
            "--filter",
            "name=foreman",
            "--format",
            "{{.Names}}\t{{.Status}}",
        ]
    ).stdout.strip().splitlines()

    # admin/JWT attestation from live container (sha12 only)
    admin_jwt_live = {
        "ARBICORE_ADMIN_USER": vals.get("ARBICORE_ADMIN_USER"),
        "ARBICORE_ADMIN_PASS": {
            "present": bool(vals.get("ARBICORE_ADMIN_PASS")),
            "len": len(vals.get("ARBICORE_ADMIN_PASS") or ""),
            "sha12": sha12(vals["ARBICORE_ADMIN_PASS"]) if vals.get("ARBICORE_ADMIN_PASS") else None,
        },
        "JWT_SECRET": {
            "present": bool(vals.get("JWT_SECRET")),
            "len": len(vals.get("JWT_SECRET") or ""),
            "sha12": sha12(vals["JWT_SECRET"]) if vals.get("JWT_SECRET") else None,
        },
        "BOOTSTRAP_PRESENT": any("BOOTSTRAP" in k for k in vals),
        "PRIVATE_KEY_ENV_PRESENT": any("PRIVATE_KEY" in k or "MNEMONIC" in k for k in vals),
        "SIGNER_ADDRESS": vals.get("ARBICORE_EXECUTOR_SIGNER_ADDRESS"),
    }

    val_meta = json.loads(VAL_META.read_text())
    val_arch = Path(val_meta["archive"])
    apply_bk = Path("/home/raghu/arbicore_backups/r3_mongo_leastpriv_20261010T102900Z")
    apply_arch = next(apply_bk.glob("arbicore_x_*.archive.gz"), None)
    post = json.loads((APPLY / "post_apply_verification.json").read_text())
    create = json.loads((PRIOR / "create_user_result.json").read_text())

    # evidence reconciliation table
    claimed = {
        "digest": post["checks"]["digest"],
        "mongo_user": post["raw"]["mongo_user"] == "arbicore_app",
        "roles": post["raw"]["root_usersInfo"]["roles"]
        == [{"role": "readWrite", "db": "arbicore_x"}],
        "crud_index": post["checks"]["app_crud"] and post["checks"]["app_index_ops"],
        "persistence": post["checks"]["persistence_discovery"],
        "factory_non_impact": post["checks"]["factory_still_root"]
        and post["checks"]["factory_healthy"],
        "r1_r2": post["checks"]["r1_ok"]
        and post["checks"]["r2_local_503"]
        and post["checks"]["r2_public_503"],
        "controls": post["checks"]["shadow"]
        and post["checks"]["autoexec_false"]
        and post["checks"]["runtime_false"],
        "auth_me": post["checks"]["auth_me_200"],
    }
    evidence_files = {
        "execution_report": str(APPLY / "R3_APPLY_EXECUTION_REPORT.md"),
        "post_apply_verification": str(APPLY / "post_apply_verification.json"),
        "create_user_result": str(PRIOR / "create_user_result.json"),
        "credential_attestation": str(PRIOR / "credential_attestation.json"),
        "apply_backup_meta": str(PRIOR / "apply_backup_meta.json"),
        "backup_validation_meta": str(VAL_META),
        "env_switch": str(APPLY / "env_switch_attestation.json")
        if (APPLY / "env_switch_attestation.json").exists()
        else None,
        "post_recreate_identity": str(APPLY / "post_recreate_identity.json")
        if (APPLY / "post_recreate_identity.json").exists()
        else None,
    }

    checks = {
        "digest": img == EXPECTED,
        "health_healthy": health == "healthy",
        "mongo_arbicore_app": mongo_user == "arbicore_app",
        "roles_exact": users_j.get("roles")
        == [{"role": "readWrite", "db": "arbicore_x"}],
        "discovery_persisted": users_j.get("discovery", 0) >= 3921188,
        "ttl_17": users_j.get("ttl") == 17,
        "app_ping": (app_ok or {}).get("ping") == 1,
        "app_factory_denied": (app_ok or {}).get("factory_denied") is True,
        "factory_root": mongo_user_of("factory-backend") == "root"
        and mongo_user_of("factory-runner") == "root",
        "factory_healthy": run(
            ["docker", "inspect", "factory-backend", "--format", "{{.State.Health.Status}}"]
        ).stdout.strip()
        == "healthy"
        and run(
            ["docker", "inspect", "factory-runner", "--format", "{{.State.Health.Status}}"]
        ).stdout.strip()
        == "healthy",
        "shadow": vals.get("ARBICORE_EXECUTION_MODE") == "SHADOW",
        "autoexec_false": vals.get("ARBICORE_AUTOEXEC_AUTOSTART") == "false",
        "runtime_false": vals.get("ARBICORE_RUNTIME_AUTOSTART") == "false",
        "bootstrap_absent": not any("BOOTSTRAP" in k for k in vals),
        "r1_404": all(v == 404 for v in r1.values()),
        "r2_503": r2 == 503,
        "api_200": api == 200,
        "alchemy_five": all(
            fps[c] == "ca6545ba"
            for c in ["ETHEREUM", "ARBITRUM", "OPTIMISM", "POLYGON", "BNB"]
        )
        and key_fps(vals.get("ARBICORE_RPC_URL")) == "ca6545ba",
        "six_rpc_keys": all(bool(vals.get(f"ARBICORE_RPC_URL_{c}")) for c in fps),
        "no_private_key_env": not any(
            "PRIVATE_KEY" in k or "MNEMONIC" in k for k in vals
        ),
        "g579_untouched": any("g5.79-green" in x and "Up" in x for x in g579),
        "legacy_ok": all(
            ("Exited" in x or x.startswith("arbicore-x-backend-new\tUp")) for x in legacy
        ),
        "backups_present": val_arch.is_file()
        and val_meta.get("validation_passed") is True
        and bool(apply_arch and apply_arch.is_file()),
        "create_roles_match_live": create.get("roles") == users_j.get("roles"),
    }
    failures = [k for k, v in checks.items() if v is not True]

    missing_or_gaps = []
    if post.get("all_pass") is False and not post.get("failed"):
        missing_or_gaps.append(
            "post_apply_verification.json has all_pass=false while failed=[] "
            "(stale boolean after auth/me fix); checks object is authoritative"
        )
    if not (APPLY / "env_switch_attestation.json").exists():
        missing_or_gaps.append("env_switch_attestation.json missing in final evid dir")
    if users_j.get("probe_exists"):
        missing_or_gaps.append(
            "empty r3_apply_probe collection still present (documented residual; non-blocking)"
        )
    # CRUD/index not re-executed this closeout (avoid mutation); rely on recorded evidence
    missing_or_gaps.append(
        "Closeout did not re-run mutating CRUD/index probes; attested from "
        "post_apply_verification.json app_live (write_ok/index_create_ok) only"
    )

    live = {
        "utc": utc(),
        "image": img,
        "health": health,
        "mongo_user": mongo_user,
        "controls": {
            "ARBICORE_EXECUTION_MODE": vals.get("ARBICORE_EXECUTION_MODE"),
            "ARBICORE_AUTOEXEC_AUTOSTART": vals.get("ARBICORE_AUTOEXEC_AUTOSTART"),
            "ARBICORE_RUNTIME_AUTOSTART": vals.get("ARBICORE_RUNTIME_AUTOSTART"),
        },
        "alchemy_fps": fps,
        "primary_fps": key_fps(vals.get("ARBICORE_RPC_URL")),
        "usersInfo": users_j,
        "app_user_probe": app_ok,
        "factory": {
            "backend_user": mongo_user_of("factory-backend"),
            "runner_user": mongo_user_of("factory-runner"),
        },
        "r1": r1,
        "r2_setup": r2,
        "api_local": api,
        "legacy": legacy,
        "g579": g579,
        "foreman_names": [x.split("\t")[0] for x in foreman],
        "admin_jwt_live_attestation": admin_jwt_live,
        "claimed_vs_recorded": claimed,
        "evidence_files": evidence_files,
        "closeout_checks": checks,
        "closeout_failures": failures,
        "missing_or_gaps": missing_or_gaps,
        "r3_closeout_verdict": "PASS WITH LIMITATIONS"
        if not failures
        else "FOLLOW-UP REQUIRED",
        "limitations_unchanged": [
            "Factory still root (out of R3 scope)",
            "BASE RPC public mainnet.base.org (pre-existing)",
            "Historical ransom-note / pre-2026-09-07 log gap",
            "r3_apply_probe collection residual",
            "Overall gate / P2 BLOCKED pending R4–R6",
        ],
    }
    (EVID / "r3_live_closeout_probe.json").write_text(json.dumps(live, indent=2) + "\n")

    # --- R4 inventory ---
    inventory = {
        "utc": utc(),
        "scope": "plaintext ARBICORE_ADMIN_PASS + JWT_SECRET (and related admin user)",
        "live": {
            "container_env": admin_jwt_live,
            "dotenv": scan_env_file(ENVF),
        },
        "historical_candidates": [],
        "approved_archives_note": (
            "Approved recovery backups under /home/raghu/arbicore_backups/* may contain "
            "pre-rotation .env copies; retain under policy — do not auto-delete in R4 apply"
        ),
    }

    # glob historical .env-like paths (metadata + sha12 if readable; no values)
    patterns = [
        V2 / "deployment/upgrade/backend/.env*",
        Path("/tmp") / "arbicore*.env*",
        Path("/home/raghu/arbicore_backups") / "*/backend.env*",
        Path("/home/raghu/arbicore_backups") / "*/*.env*",
    ]
    seen = set()
    for pattern in patterns:
        for p in Path(pattern.parent).glob(pattern.name):
            if str(p) in seen:
                continue
            seen.add(str(p))
            meta = scan_env_file(p)
            if meta and (
                "ARBICORE_ADMIN_PASS" in meta.get("keys", {})
                or "JWT_SECRET" in meta.get("keys", {})
            ):
                inventory["historical_candidates"].append(meta)

    # stopped legacy container env sha12s
    legacy_env = []
    for name in [
        "arbicore-x-backend-h05",
        "arbicore-x-backend-w1",
        "arbicore-x-b7-candidate",
        "arbicore-x-backend",
    ]:
        try:
            e = run(
                [
                    "docker",
                    "inspect",
                    name,
                    "--format",
                    "{{range .Config.Env}}{{println .}}{{end}}",
                ]
            ).stdout
        except subprocess.CalledProcessError:
            continue
        item = {"container": name, "keys": {}}
        for line in e.splitlines():
            if line.startswith("ARBICORE_ADMIN_PASS="):
                v = line.split("=", 1)[1]
                item["keys"]["ARBICORE_ADMIN_PASS"] = {
                    "len": len(v),
                    "sha12": sha12(v),
                }
            if line.startswith("JWT_SECRET="):
                v = line.split("=", 1)[1]
                item["keys"]["JWT_SECRET"] = {"len": len(v), "sha12": sha12(v)}
            if line.startswith("ARBICORE_ADMIN_USER="):
                item["keys"]["ARBICORE_ADMIN_USER"] = {
                    "value": line.split("=", 1)[1]
                }
        if item["keys"]:
            legacy_env.append(item)
    inventory["stopped_legacy_container_env"] = legacy_env

    # compose/.env files (usually no admin secrets — note if present)
    compose_env = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose/.env")
    inventory["compose_dotenv_has_admin_jwt"] = False
    if compose_env.is_file():
        t = compose_env.read_text(errors="replace")
        inventory["compose_dotenv_has_admin_jwt"] = (
            "ARBICORE_ADMIN_PASS=" in t or "JWT_SECRET=" in t
        )

    (EVID / "r4_secret_location_inventory.json").write_text(
        json.dumps(inventory, indent=2) + "\n"
    )
    print(
        json.dumps(
            {
                "evid": str(EVID),
                "verdict": live["r3_closeout_verdict"],
                "failures": failures,
                "gaps": missing_or_gaps,
                "mongo_user": mongo_user,
                "roles": users_j.get("roles"),
                "discovery": users_j.get("discovery"),
                "admin_pass_sha12": admin_jwt_live["ARBICORE_ADMIN_PASS"]["sha12"],
                "jwt_sha12": admin_jwt_live["JWT_SECRET"]["sha12"],
                "hist_count": len(inventory["historical_candidates"]),
                "legacy_env_count": len(legacy_env),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
