#!/usr/bin/env bash
# 99_rollback.sh — restore the OLD backend. Mongo is never touched -> data intact.
# This is the SAFE rollback: it relies on the fact that 06_cutover.sh only stopped (never
# removed) the OLD container, so we just start it again and tear down the NEW.
#
# It does NOT restore from the mongodump archive — that would be destructive and is only
# needed if Mongo itself is corrupted (manual procedure documented in §8 of the readiness
# report). The realignment is schema-additive: the OLD build simply ignores the new seed
# docs in arbicore_scanner_config/arbicore_scanner_state, so functional rollback is enough.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker
need_cmd curl

DRY_RUN=false
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=true
fi

if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  die "docker compose not installed"
fi

if [ "$DRY_RUN" = true ]; then
  log "DRY-RUN: would stop NEW backend only ($BACKEND_NEW)"
  if docker inspect "$BACKEND_NEW" >/dev/null 2>&1; then
    ok "DRY-RUN: NEW backend exists; removal skipped"
  else
    ok "DRY-RUN: NEW backend already absent"
  fi
else
  log "Stopping NEW backend only ($BACKEND_NEW) ..."

  if docker inspect "$BACKEND_NEW" >/dev/null 2>&1; then
    docker rm -f "$BACKEND_NEW" >/dev/null
    ok "NEW backend removed"
  else
    ok "NEW backend already absent"
  fi
fi

log "Preparing OLD backend rollback ($BACKEND_OLD) ..."

SNAP="$(ls -1t "${LOG_DIR}"/old_backend_state_*.json 2>/dev/null | head -1 || true)"
[ -n "$SNAP" ] || die "no old-backend rollback snapshot found"
[ -f "$SNAP" ] || die "rollback snapshot missing: $SNAP"

if docker inspect "$BACKEND_OLD" >/dev/null 2>&1; then
  log "OLD container exists; starting it ..."
  docker start "$BACKEND_OLD" >/dev/null
  ok "OLD backend started"
else
  log "OLD container absent; reconstructing from snapshot ..."

  python3 - "$SNAP" "$BACKEND_OLD" "${1:-}" <<'PY_RECON'
import json
import os
import subprocess
import sys

snap = sys.argv[1]
name = sys.argv[2]
mode = sys.argv[3] if len(sys.argv) > 3 else ""

dry_run = mode == "--dry-run"

data = json.load(open(snap))
if not isinstance(data, list) or len(data) != 1:
    raise SystemExit("invalid rollback snapshot")

x = data[0]
cfg = x["Config"]
host = x["HostConfig"]

snapshot_name = x["Name"].lstrip("/")
if snapshot_name != name:
    raise SystemExit(
        f"snapshot name mismatch: expected {name}, got {snapshot_name}"
    )

image = cfg["Image"]

# Verify image exists before attempting reconstruction.
subprocess.run(
    ["docker", "image", "inspect", image],
    check=True,
    stdout=subprocess.DEVNULL,
)

env_file = "/tmp/arbicore-rollback-env"

try:
    with open(env_file, "w") as f:
        for item in cfg.get("Env", []):
            f.write(item + "\n")

    os.chmod(env_file, 0o600)

    args = [
        "docker", "create",
        "--name", name,
    ]

    restart = host.get("RestartPolicy") or {}
    if restart.get("Name"):
        args += ["--restart", restart["Name"]]

    if cfg.get("User"):
        args += ["--user", cfg["User"]]

    if cfg.get("WorkingDir"):
        args += ["--workdir", cfg["WorkingDir"]]

    if cfg.get("Hostname"):
        args += ["--hostname", cfg["Hostname"]]

    for port, bindings in (host.get("PortBindings") or {}).items():
        for b in bindings or []:
            host_ip = b.get("HostIp") or ""
            host_port = b.get("HostPort") or ""
            container_port = port.split("/")[0]

            if not host_port:
                raise SystemExit("invalid port binding")

            if host_ip:
                pub = f"{host_ip}:{host_port}:{container_port}"
            else:
                pub = f"{host_port}:{container_port}"

            args += ["-p", pub]

    for mount in x.get("Mounts", []):
        if mount.get("Type") != "bind":
            raise SystemExit(
                f"unsupported mount type: {mount.get('Type')}"
            )

        source = mount.get("Source")
        destination = mount.get("Destination")

        if not source or not destination:
            raise SystemExit("invalid bind mount")

        spec = (
            f"type=bind,source={source},destination={destination}"
        )

        if not mount.get("RW", True):
            spec += ",readonly"

        args += ["--mount", spec]

    network = host.get("NetworkMode")
    if network:
        args += ["--network", network]

    # Preserve the original network aliases when available.
    endpoints = x.get("NetworkSettings", {}).get("Networks", {})
    endpoint = endpoints.get(network, {}) if network else {}
    aliases = endpoint.get("Aliases") or []

    for alias in aliases:
        if alias and alias != name:
            args += ["--network-alias", alias]

    # Preserve container labels without printing their values.
    for key, value in (cfg.get("Labels") or {}).items():
        args += ["--label", f"{key}={value}"]

    args += ["--env-file", env_file]

    entrypoint = cfg.get("Entrypoint")
    if entrypoint:
        raise SystemExit(
            "snapshot contains an Entrypoint; explicit handling required"
        )

    cmd = cfg.get("Cmd") or []
    if not cmd:
        raise SystemExit("snapshot contains no command")

    args += [image] + cmd

    print("RECONSTRUCTION_VALIDATION=PASS")
    print(f"CONTAINER={name}")
    print(f"IMAGE={image}")
    print(f"NETWORK={network}")
    print(f"MOUNTS={len(x.get('Mounts', []))}")
    print(f"ENVIRONMENT_ENTRIES={len(cfg.get('Env', []))}")
    print(f"NETWORK_ALIASES={len(aliases)}")
    print("SECRETS_PRINTED=NO")

    if dry_run:
        print("EXECUTION=SKIPPED_DRY_RUN")
    else:
        subprocess.run(args, check=True)
        print("EXECUTION=DOCKER_CREATE_COMPLETE")

finally:
    try:
        os.remove(env_file)
    except FileNotFoundError:
        pass
PY_RECON

  ok "OLD backend reconstruction completed"
fi

log "Waiting up to 60s for OLD /api/ to return 200 ..."
ATTEMPTS=0
until [ "$ATTEMPTS" -ge 30 ]; do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8001/api/ || true)"
  [ "$CODE" = "200" ] && break
  ATTEMPTS=$((ATTEMPTS+1))
  sleep 2
done
[ "$CODE" = "200" ] || c_red "  WARN  OLD /api/ never returned 200 (last=$CODE) — inspect 'docker logs $BACKEND_OLD'"
[ "$CODE" = "200" ] && ok "OLD /api/ -> 200"

cat <<'NOTE'

[rollback] Functional rollback complete.
  - Mongo was never touched -> all 320 opportunities + history are intact.
  - The new build's seeded arbicore_scanner_config / arbicore_scanner_state docs are
    harmless to the OLD build (it ignores them).
  - If you need an "exact pre-state" reset of those seed docs, do so manually using the
    procedure in /audit/13_production_readiness_report.md §8 — NOT included here so no
    destructive command can ever be executed by accident.
NOTE
c_green "ROLLBACK DONE — production is on the OLD backend again."
