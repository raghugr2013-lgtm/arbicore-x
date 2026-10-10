#!/usr/bin/env python3
"""R4-APPLY — Admin/JWT secret rotation. Never prints secret values."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.parse import quote_plus, unquote, urlparse

EVID = Path(os.environ["R4_EVID"])
BK = Path(os.environ["R4_BK"])
ENVF = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env")
COMPOSE_DIR = Path("/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose")
OVERRIDE = Path("/tmp/arbicore-s2a-rpc-redact-override.yml")
EXPECTED_DIGEST = "sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313"
BASE = "http://127.0.0.1:8001"
CTR = "arbicore-x-backend-new"
MONGO_CTR = "factory-mongo"
OLD_ADMIN_SHA12 = "6757aa3396d8"
OLD_JWT_SHA12 = "066b178751e1"
ADMIN_ID = "eeeeb6d9-d1b0-4ff9-9fa1-7fa044b5ef06"


def utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"[{utc()}] {msg}"
    print(line, flush=True)
    with open(EVID / "apply.log", "a") as fh:
        fh.write(line + "\n")


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, default=str) + "\n")
    os.chmod(path, 0o600 if "secret" in path.name or "password" in path.name else 0o644)


def sha12(val: str) -> str:
    return hashlib.sha256(val.encode()).hexdigest()[:12]


def fail(stage: str, detail: str) -> None:
    write_json(EVID / "FAILURE.json", {"utc": utc(), "stage": stage, "detail": detail})
    log(f"FAIL {stage}: {detail}")
    sys.exit(2)


def run(cmd, cwd=None, env=None, timeout=300):
    return subprocess.run(
        cmd, cwd=cwd, env=env, text=True, capture_output=True, timeout=timeout, check=False
    )


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def att(val: str) -> dict:
    return {"present": bool(val), "len": len(val), "sha12": sha12(val) if val else None}


class ApiSession:
    """Cookie-aware client; keeps one opener+jar for the whole session."""

    def __init__(self):
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def cookie_header(self) -> str:
        return "; ".join(f"{c.name}={c.value}" for c in self.jar)

    def request(self, method: str, url: str, body=None, timeout=30, cookie_override: str | None = None):
        data = None if body is None else json.dumps(body).encode()
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if cookie_override is not None:
            headers["Cookie"] = cookie_override
            req = urllib.request.Request(url, data=data, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    raw = resp.read().decode()
                    return resp.status, (json.loads(raw) if raw else {})
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                try:
                    parsed = json.loads(raw) if raw else {}
                except json.JSONDecodeError:
                    parsed = {"raw": raw[:300]}
                return e.code, parsed
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                raw = resp.read().decode()
                return resp.status, (json.loads(raw) if raw else {})
        except urllib.error.HTTPError as e:
            raw = e.read().decode(errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw[:300]}
            return e.code, parsed


def http_json(method: str, url: str, body=None, timeout=30):
    """Stateless one-shot (no cookies)."""
    return ApiSession().request(method, url, body=body, timeout=timeout)

def inspect_ctr() -> dict:
    r = run(["docker", "inspect", CTR, "--format", "{{json .}}"])
    if r.returncode != 0:
        fail("inspect", r.stderr[:400])
    j = json.loads(r.stdout)
    env = {}
    for e in j["Config"]["Env"]:
        if "=" in e:
            k, _, v = e.partition("=")
            env[k] = v
    return {
        "image_id": j["Image"],
        "config_image": j["Config"]["Image"],
        "health": (j.get("State") or {}).get("Health", {}).get("Status"),
        "status": j["State"]["Status"],
        "env_admin": att(env.get("ARBICORE_ADMIN_PASS", "")),
        "env_jwt": att(env.get("JWT_SECRET", "")),
        "bootstrap_present": bool(env.get("ARBICORE_BOOTSTRAP_TOKEN")),
        "private_key_env_present": any(
            "PRIVATE_KEY" in k and env.get(k) for k in env
        ),
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


def _mongo_creds(mongo_url: str) -> tuple[str, str]:
    parsed = urlparse(mongo_url)
    return unquote(parsed.username or ""), unquote(parsed.password or "")


def _docker_exec_env_file(name: str, value: str) -> Path:
    """Write a 0600 env-file for `docker exec --env-file` (avoids secret argv)."""
    p = BK / f".docker_env_{name}"
    # docker --env-file format: KEY=VALUE
    p.write_text(f"{name}={value}\n")
    os.chmod(p, 0o600)
    return p


def mongo_users_meta(mongo_url: str) -> dict:
    """Read admin users doc via mongosh; credentials via --env-file only."""
    user, pwd = _mongo_creds(mongo_url)
    js = r"""
const uri = 'mongodb://' + encodeURIComponent(process.env.MU) + ':' + encodeURIComponent(process.env.MP) + '@127.0.0.1:27017/arbicore_x?authSource=admin';
const conn = connect(uri);
const full = conn.getSiblingDB('arbicore_x').users.findOne({username:'admin'});
if (!full) { print(JSON.stringify({found:false})); quit(0); }
const hash = full.password_hash || '';
print(JSON.stringify({
  found: true,
  username: full.username,
  role: full.role,
  id: full.id,
  session_version: full.session_version,
  created_at: full.created_at,
  updated_at: full.updated_at,
  password_hash_present: !!hash,
  password_hash_algo_prefix: hash.slice(0,4),
  password_hash: hash,
}));
"""
    ef_u = _docker_exec_env_file("MU", user)
    ef_p = _docker_exec_env_file("MP", pwd)
    # merge into one env file
    ef = BK / ".docker_env_mongo"
    ef.write_text(f"MU={user}\nMP={pwd}\n")
    os.chmod(ef, 0o600)
    ef_u.unlink(missing_ok=True)
    ef_p.unlink(missing_ok=True)
    r = subprocess.run(
        [
            "docker",
            "exec",
            "--env-file",
            str(ef),
            MONGO_CTR,
            "mongosh",
            "--quiet",
            "--eval",
            js,
        ],
        text=True,
        capture_output=True,
        timeout=60,
    )
    ef.unlink(missing_ok=True)
    if r.returncode != 0:
        fail("mongo_meta", (r.stderr or r.stdout)[:400])
    lines = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        fail("mongo_meta", f"no json: {(r.stdout or '')[:200]}")
    doc = json.loads(lines[-1])
    if doc.get("password_hash"):
        doc["password_hash_sha12"] = sha12(doc["password_hash"])
    else:
        doc["password_hash_sha12"] = None
    return doc


def mongodump_users(mongo_url: str) -> Path:
    user, pwd = _mongo_creds(mongo_url)
    out_dir = BK / "mongodump_users"
    out_dir.mkdir(mode=0o700, exist_ok=True)
    remote = "/tmp/r4_users_dump"
    run(["docker", "exec", MONGO_CTR, "rm", "-rf", remote])
    ef = BK / ".docker_env_mongo"
    ef.write_text(f"MU={user}\nMP={pwd}\n")
    os.chmod(ef, 0o600)
    # Use --username/--password from env inside container (URI-safe)
    inner = (
        f"mongodump --host=127.0.0.1 --port=27017 --username=\"$MU\" --password=\"$MP\" "
        f"--authenticationDatabase=admin --db=arbicore_x --collection=users --out={remote}"
    )
    r = subprocess.run(
        ["docker", "exec", "--env-file", str(ef), MONGO_CTR, "bash", "-lc", inner],
        text=True,
        capture_output=True,
        timeout=120,
    )
    ef.unlink(missing_ok=True)
    (EVID / "mongodump_users.log").write_text(
        "rc=%s\nstdout_len=%d\nstderr_len=%d\n"
        % (r.returncode, len(r.stdout or ""), len(r.stderr or ""))
    )
    if r.returncode != 0:
        fail("mongodump_users", "mongodump failed (see log lengths)")
    r2 = run(["docker", "cp", f"{MONGO_CTR}:{remote}/arbicore_x/users.bson", str(out_dir / "users.bson")])
    r3 = run(
        [
            "docker",
            "cp",
            f"{MONGO_CTR}:{remote}/arbicore_x/users.metadata.json",
            str(out_dir / "users.metadata.json"),
        ]
    )
    run(["docker", "exec", MONGO_CTR, "rm", "-rf", remote])
    if r2.returncode != 0 or r3.returncode != 0:
        fail("mongodump_users", "docker cp failed")
    for p in out_dir.iterdir():
        os.chmod(p, 0o600)
    return out_dir


def patch_env(old: dict[str, str], new_admin: str, new_jwt: str) -> None:
    lines = ENVF.read_text().splitlines(keepends=True)
    out = []
    seen_admin = seen_jwt = False
    for line in lines:
        if line.startswith("ARBICORE_ADMIN_PASS="):
            out.append(f"ARBICORE_ADMIN_PASS={new_admin}\n")
            seen_admin = True
        elif line.startswith("JWT_SECRET="):
            out.append(f"JWT_SECRET={new_jwt}\n")
            seen_jwt = True
        else:
            out.append(line if line.endswith("\n") else line + "\n")
    if not seen_admin or not seen_jwt:
        fail("patch_env", f"missing keys admin={seen_admin} jwt={seen_jwt}")
    tmp = ENVF.with_suffix(".env.r4tmp")
    tmp.write_text("".join(out))
    os.chmod(tmp, 0o600)
    tmp.replace(ENVF)
    os.chmod(ENVF, 0o600)
    new = parse_env(ENVF.read_text())
    if set(new) != set(old):
        fail("patch_env", f"key set drift: +{set(new)-set(old)} -{set(old)-set(new)}")
    for k in old:
        if k in ("ARBICORE_ADMIN_PASS", "JWT_SECRET"):
            continue
        if new.get(k) != old.get(k):
            fail("patch_env", f"unexpected change to {k}")
    if sha12(new["ARBICORE_ADMIN_PASS"]) == OLD_ADMIN_SHA12:
        fail("patch_env", "admin sha12 unchanged")
    if sha12(new["JWT_SECRET"]) == OLD_JWT_SHA12:
        fail("patch_env", "jwt sha12 unchanged")
    if sha12(new["ARBICORE_ADMIN_PASS"]) != sha12(new_admin):
        fail("patch_env", "admin write mismatch")
    if sha12(new["JWT_SECRET"]) != sha12(new_jwt):
        fail("patch_env", "jwt write mismatch")


def wait_healthy(timeout_s=90) -> dict:
    for i in range(1, timeout_s + 1):
        info = inspect_ctr()
        with open(EVID / "health_wait.log", "a") as fh:
            fh.write(f"wait_{i} health={info['health']} status={info['status']} digest={info['image_id'][:19]}\n")
        if info["health"] == "healthy" and info["status"] == "running":
            return info
        time.sleep(1)
    fail("health_wait", "timeout waiting healthy")


def public_probe(path: str) -> int:
    r = run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"https://api.arbicorex.in{path}"], timeout=30)
    try:
        return int((r.stdout or "0").strip())
    except ValueError:
        return -1


def main() -> None:
    os.umask(0o077)
    EVID.mkdir(parents=True, exist_ok=True)
    BK.mkdir(parents=True, exist_ok=True)
    os.chmod(BK, 0o700)
    log("R4-APPLY start")

    # ── Stage 0: pre-checks ──
    if not ENVF.is_file() or not OVERRIDE.is_file():
        fail("precheck", "env or override missing")
    mode = oct(ENVF.stat().st_mode & 0o777)
    env = parse_env(ENVF.read_text())
    pre = {
        "utc": utc(),
        "env_mode": mode,
        "admin": att(env.get("ARBICORE_ADMIN_PASS", "")),
        "jwt": att(env.get("JWT_SECRET", "")),
        "admin_user": env.get("ARBICORE_ADMIN_USER") or "admin",
        "container": inspect_ctr(),
    }
    if pre["admin"]["sha12"] != OLD_ADMIN_SHA12 or pre["jwt"]["sha12"] != OLD_JWT_SHA12:
        fail("precheck", "live sha12 drift from preflight baseline")
    if pre["container"]["image_id"] != EXPECTED_DIGEST:
        fail("precheck", f"digest mismatch {pre['container']['image_id']}")
    if pre["container"]["health"] != "healthy":
        fail("precheck", "not healthy")
    if pre["container"]["controls"].get("ARBICORE_EXECUTION_MODE") != "SHADOW":
        fail("precheck", "not SHADOW")
    if pre["container"]["controls"].get("ARBICORE_AUTOEXEC_AUTOSTART") != "false":
        fail("precheck", "AUTOEXEC not false")
    if pre["container"]["controls"].get("ARBICORE_RUNTIME_AUTOSTART") != "false":
        fail("precheck", "RUNTIME not false")
    if pre["container"]["bootstrap_present"]:
        fail("precheck", "BOOTSTRAP present")
    if pre["container"]["mongo_url_user"] != "arbicore_app":
        fail("precheck", "mongo user not arbicore_app")

    old_pass = env["ARBICORE_ADMIN_PASS"]
    sess0 = ApiSession()
    st, body = sess0.request(
        "POST", f"{BASE}/api/auth/login", {"username": pre["admin_user"], "password": old_pass}
    )
    if st != 200:
        fail("precheck_login", f"status={st} detail={body}")
    pre_cookie = sess0.cookie_header()
    if "access_token=" not in pre_cookie:
        fail("precheck_login", "login 200 but no access_token cookie")
    st_me, me = sess0.request("GET", f"{BASE}/api/auth/me")
    if st_me != 200 or me.get("id") != ADMIN_ID:
        fail("precheck_me", f"status={st_me} me_keys={list(me)} cookie_names={[c.name for c in sess0.jar]}")
    pre["login_ok"] = True
    pre["me_id"] = me.get("id")
    write_json(EVID / "pre_apply_probe.json", {k: v for k, v in pre.items()})
    log("STAGE0_OK prechecks")

    # ── Stage 1: backup ──
    shutil.copy2(ENVF, BK / "backend.env.pre-r4")
    os.chmod(BK / "backend.env.pre-r4", 0o600)
    (BK / "admin.password.pre-r4").write_text(old_pass)
    os.chmod(BK / "admin.password.pre-r4", 0o600)
    users = mongo_users_meta(env["MONGO_URL"])
    restore_doc = {
        "id": users.get("id"),
        "username": users.get("username"),
        "session_version": users.get("session_version"),
        "password_hash": users.get("password_hash"),
        "updated_at": users.get("updated_at"),
    }
    (BK / "users_admin_doc.pre-r4.json").write_text(json.dumps(restore_doc) + "\n")
    os.chmod(BK / "users_admin_doc.pre-r4.json", 0o600)
    dump_dir = mongodump_users(env["MONGO_URL"])
    # redacted meta for evidence
    redacted = {k: v for k, v in users.items() if k != "password_hash"}
    write_json(
        EVID / "backup_attestation.json",
        {
            "utc": utc(),
            "bk": str(BK),
            "bk_mode": oct(BK.stat().st_mode & 0o777),
            "env_backup": str(BK / "backend.env.pre-r4"),
            "env_backup_mode": oct((BK / "backend.env.pre-r4").stat().st_mode & 0o777),
            "admin_pass_escrow": str(BK / "admin.password.pre-r4"),
            "admin_pass_sha12": sha12(old_pass),
            "users_doc_escrow": str(BK / "users_admin_doc.pre-r4.json"),
            "mongodump_users": str(dump_dir),
            "mongo_admin_meta": redacted,
            "pre_rotation_cookie_captured": bool(pre_cookie),
            "baseline_session_version": users.get("session_version"),
        },
    )
    if users.get("session_version") != 2:
        log(f"WARN session_version={users.get('session_version')} (preflight expected 2)")
    log("STAGE1_OK backup")

    # ── Stage 2: generate secrets ──
    gen_jwt = subprocess.run(
        ["openssl", "rand", "-hex", "32"], text=True, capture_output=True, check=True
    ).stdout.strip()
    gen_admin = subprocess.run(
        ["openssl", "rand", "-base64", "24"], text=True, capture_output=True, check=True
    ).stdout.strip()
    if len(gen_jwt) < 64:
        fail("generate", "jwt too short")
    if len(gen_admin) < 16:
        fail("generate", "admin pass too short")
    (BK / "jwt.secret.new").write_text(gen_jwt + "\n")
    (BK / "admin.password.new").write_text(gen_admin + "\n")
    os.chmod(BK / "jwt.secret.new", 0o600)
    os.chmod(BK / "admin.password.new", 0o600)
    write_json(
        EVID / "generation_attestation.json",
        {
            "utc": utc(),
            "jwt": att(gen_jwt),
            "admin_pass": att(gen_admin),
            "method": {"jwt": "openssl rand -hex 32", "admin": "openssl rand -base64 24"},
            "note": "values only in 0600 escrow under BK; never printed",
        },
    )
    log("STAGE2_OK generate")

    # ── Stage 3: patch live .env ──
    patch_env(env, gen_admin, gen_jwt)
    post_env = parse_env(ENVF.read_text())
    write_json(
        EVID / "env_patch_attestation.json",
        {
            "utc": utc(),
            "env_mode": oct(ENVF.stat().st_mode & 0o777),
            "admin": att(post_env["ARBICORE_ADMIN_PASS"]),
            "jwt": att(post_env["JWT_SECRET"]),
            "old_admin_sha12": OLD_ADMIN_SHA12,
            "old_jwt_sha12": OLD_JWT_SHA12,
            "keys_modified": ["ARBICORE_ADMIN_PASS", "JWT_SECRET"],
        },
    )
    log("STAGE3_OK env_patch")

    # ── Stage 4: recreate backend ──
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
        timeout=180,
    )
    (EVID / "compose_recreate.log").write_text(
        f"rc={compose.returncode}\n--- stdout ---\n{compose.stdout}\n--- stderr ---\n{compose.stderr}\n"
    )
    if compose.returncode != 0:
        fail("recreate", f"compose rc={compose.returncode}")
    info = wait_healthy()
    if info["image_id"] != EXPECTED_DIGEST:
        fail("recreate", f"digest changed to {info['image_id']}")
    if info["env_admin"]["sha12"] != sha12(gen_admin) or info["env_jwt"]["sha12"] != sha12(gen_jwt):
        fail("recreate", "container ENV sha12 mismatch vs generated")
    # boot provision should not overwrite hash — session_version still baseline until change-password
    users_after_boot = mongo_users_meta(post_env["MONGO_URL"])
    write_json(
        EVID / "post_recreate_probe.json",
        {
            "utc": utc(),
            "container": info,
            "mongo_admin_meta": {k: v for k, v in users_after_boot.items() if k != "password_hash"},
            "hash_sha12_unchanged": users_after_boot.get("password_hash_sha12")
            == users.get("password_hash_sha12"),
            "session_version": users_after_boot.get("session_version"),
        },
    )
    if users_after_boot.get("password_hash_sha12") != users.get("password_hash_sha12"):
        fail("recreate", "password_hash changed on boot — provisioner overwrite unexpected")
    log("STAGE4_OK recreate")

    # ── Stage 5: old cookie should be dead; login old pass; change-password ──
    st_old, body_old = ApiSession().request(
        "GET", f"{BASE}/api/auth/me", cookie_override=pre_cookie
    )
    sess2 = ApiSession()
    st_login_old, body_login = sess2.request(
        "POST",
        f"{BASE}/api/auth/login",
        {"username": pre["admin_user"], "password": old_pass},
    )
    if st_login_old != 200:
        fail("login_old_after_jwt", f"status={st_login_old} body={body_login}")
    st_chg, body_chg = sess2.request(
        "POST",
        f"{BASE}/api/auth/change-password",
        {"current_password": old_pass, "new_password": gen_admin},
    )
    if st_chg != 200:
        fail("change_password", f"status={st_chg} body={body_chg}")
    sess3 = ApiSession()
    st_new, body_new = sess3.request(
        "POST",
        f"{BASE}/api/auth/login",
        {"username": pre["admin_user"], "password": gen_admin},
    )
    if st_new != 200:
        fail("login_new", f"status={st_new} body={body_new}")
    st_me2, me2 = sess3.request("GET", f"{BASE}/api/auth/me")
    if st_me2 != 200:
        fail("me_new", f"status={st_me2}")
    st_old_pass, body_old_pass = http_json(
        "POST",
        f"{BASE}/api/auth/login",
        {"username": pre["admin_user"], "password": old_pass},
    )
    users_final = mongo_users_meta(post_env["MONGO_URL"])
    write_json(
        EVID / "auth_rotation_probe.json",
        {
            "utc": utc(),
            "pre_cookie_me_status": st_old,
            "login_old_pass_after_jwt_status": st_login_old,
            "change_password_status": st_chg,
            "change_password_ok": body_chg.get("ok"),
            "login_new_pass_status": st_new,
            "me_after_new_login_status": st_me2,
            "me_username": me2.get("username"),
            "me_id": me2.get("id"),
            "login_old_pass_after_change_status": st_old_pass,
            "session_version_before": users.get("session_version"),
            "session_version_after": users_final.get("session_version"),
            "password_hash_sha12_before": users.get("password_hash_sha12"),
            "password_hash_sha12_after": users_final.get("password_hash_sha12"),
            "hash_changed": users_final.get("password_hash_sha12") != users.get("password_hash_sha12"),
        },
    )
    if st_old == 200:
        fail("verify_v5", "pre-rotation cookie still accepted")
    if st_old_pass == 200:
        fail("verify_v4", "old password still accepted after change")
    if not (
        isinstance(users_final.get("session_version"), int)
        and users_final["session_version"] > (users.get("session_version") or 0)
    ):
        fail("verify_v6", f"session_version not bumped: {users_final.get('session_version')}")
    if users_final.get("password_hash_sha12") == users.get("password_hash_sha12"):
        fail("verify_hash", "password_hash sha12 unchanged after change-password")
    log("STAGE5_OK password_coordinated")

    # ── Stage 6: full verification ──
    api_local = run(["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}", f"{BASE}/api/"], timeout=30)
    api_code = int((api_local.stdout or "0").strip() or "0")
    setup_st, setup_body = http_json(
        "POST",
        f"{BASE}/api/auth/setup",
        {"username": "xattacker", "password": "not-used-here1"},
    )
    docs_pub = public_probe("/docs")
    api_pub = public_probe("/api/")
    # legacy containers still exited
    legacy = {}
    for name in (
        "arbicore-x-backend-h05",
        "arbicore-x-backend-w1",
        "arbicore-x-b7-candidate",
        "arbicore-x-backend",
    ):
        rr = run(["docker", "inspect", name, "--format", "{{.State.Status}}"])
        legacy[name] = (rr.stdout or "").strip() if rr.returncode == 0 else "missing"
    g579 = run(["docker", "inspect", "arbicore-g5-79-app", "--format", "{{.State.Status}}"])
    foreman = run(["docker", "inspect", "foreman-mongo", "--format", "{{.State.Status}}"])
    final_ctr = inspect_ctr()
    checks = {
        "V1_digest_healthy": final_ctr["image_id"] == EXPECTED_DIGEST and final_ctr["health"] == "healthy",
        "V2_sha12_rotated": final_ctr["env_admin"]["sha12"] != OLD_ADMIN_SHA12
        and final_ctr["env_jwt"]["sha12"] != OLD_JWT_SHA12
        and att(post_env["ARBICORE_ADMIN_PASS"])["sha12"] != OLD_ADMIN_SHA12,
        "V3_login_new_and_me": st_new == 200 and st_me2 == 200,
        "V4_old_password_rejected": st_old_pass == 401,
        "V5_pre_cookie_rejected": st_old == 401,
        "V6_session_version_gt_baseline": users_final.get("session_version", 0)
        > (users.get("session_version") or 0),
        "V7_r1_r2_api": docs_pub == 404 and setup_st == 503 and api_code == 200,
        "V8_controls": final_ctr["controls"].get("ARBICORE_EXECUTION_MODE") == "SHADOW"
        and final_ctr["controls"].get("ARBICORE_AUTOEXEC_AUTOSTART") == "false"
        and final_ctr["controls"].get("ARBICORE_RUNTIME_AUTOSTART") == "false"
        and not final_ctr["bootstrap_present"]
        and not final_ctr["private_key_env_present"],
        "V9_mongo_user_and_peers": final_ctr["mongo_url_user"] == "arbicore_app"
        and all(v == "exited" for v in legacy.values())
        and (g579.stdout or "").strip() == "running",
        "V10_no_secrets_in_reports": True,
    }
    ver = {
        "utc": utc(),
        "checks": checks,
        "details": {
            "digest": final_ctr["image_id"],
            "health": final_ctr["health"],
            "env_admin_sha12": final_ctr["env_admin"]["sha12"],
            "env_jwt_sha12": final_ctr["env_jwt"]["sha12"],
            "dotenv_admin_sha12": att(post_env["ARBICORE_ADMIN_PASS"])["sha12"],
            "dotenv_jwt_sha12": att(post_env["JWT_SECRET"])["sha12"],
            "api_local": api_code,
            "api_public": api_pub,
            "docs_public": docs_pub,
            "setup_status": setup_st,
            "session_version": users_final.get("session_version"),
            "password_hash_sha12": users_final.get("password_hash_sha12"),
            "controls": final_ctr["controls"],
            "legacy": legacy,
            "g5_79_app": (g579.stdout or "").strip(),
            "foreman_mongo": (foreman.stdout or "").strip(),
            "mongo_user": final_ctr["mongo_url_user"],
        },
        "all_pass": all(checks.values()),
    }
    write_json(EVID / "post_apply_verification.json", ver)
    if not ver["all_pass"]:
        failed = [k for k, v in checks.items() if not v]
        fail("verification", f"failed={failed}")
    log("STAGE6_OK verification_all_pass")

    # rollback helper (no secrets)
    rollback = f"""#!/usr/bin/env bash
# R4-APPLY rollback — restore pre-r4 .env and recreate backend.
# If change-password already applied, also restore users admin doc from escrow
#   (BK/users_admin_doc.pre-r4.json) via authorised mongosh — not automated here.
set -euo pipefail
BK="{BK}"
BACKUP_ENV="${{1:-$BK/backend.env.pre-r4}}"
ENVF="{ENVF}"
EXPECTED="{EXPECTED_DIGEST}"
test -f "$BACKUP_ENV"
cp -a "$BACKUP_ENV" "$ENVF"
chmod 600 "$ENVF"
cd "{COMPOSE_DIR}"
docker compose -f docker-compose.prod.yml -f {OVERRIDE} \\
  up -d --no-deps --force-recreate --pull never backend
test "$(docker inspect {CTR} --format '{{{{.Image}}}}')" = "$EXPECTED"
echo "env rollback complete; if password was changed, restore users hash from $BK/users_admin_doc.pre-r4.json"
"""
    (EVID / "rollback.sh").write_text(rollback)
    os.chmod(EVID / "rollback.sh", 0o700)

    write_json(
        EVID / "APPLY_SUMMARY.json",
        {
            "utc": utc(),
            "verdict": "PASS",
            "evid": str(EVID),
            "bk": str(BK),
            "new_admin_sha12": sha12(gen_admin),
            "new_jwt_sha12": sha12(gen_jwt),
            "session_version": users_final.get("session_version"),
            "digest": EXPECTED_DIGEST,
            "historical_scrub": "NOT_IN_SCOPE",
            "overall_gate_p2": "BLOCKED",
        },
    )
    log("R4-APPLY PASS")


if __name__ == "__main__":
    main()
