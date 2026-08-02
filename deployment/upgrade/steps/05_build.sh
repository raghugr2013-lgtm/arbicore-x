#!/usr/bin/env bash
# 05_build.sh — build the new backend image WITHOUT touching the running stack.
# The image is tagged with the git sha (or date fallback) recorded by 00_detect_env.sh.
# Old backend keeps serving traffic; cutover happens only in 06_cutover.sh.
source "$(dirname "${BASH_SOURCE[0]}")/../lib/common.sh"
load_env
need_cmd docker

# Pick docker-compose CLI (v2 plugin preferred, legacy v1 acceptable)
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  die "neither 'docker compose' nor 'docker-compose' is installed"
fi

log "Building image $IMAGE_TAG from ./backend (old backend remains running) ..."
# Build via compose so labels + context match the deployed manifest exactly.
( cd "$ROOT_DIR" && $DC --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" build backend )

# Verify image is now in the local registry
docker image inspect "$IMAGE_TAG" >/dev/null 2>&1 \
  || die "image $IMAGE_TAG not found after build — check build logs"
SIZE_HUMAN="$(docker image inspect -f '{{.Size}}' "$IMAGE_TAG" | awk '{printf "%.1fMB\n",$1/1024/1024}')"
ok "image built: $IMAGE_TAG  ($SIZE_HUMAN)"

# Provenance: stamp labels for the audit trail
docker image inspect -f 'arbicore.gitsha={{index .Config.Labels "arbicore.gitsha"}}  arbicore.schema={{index .Config.Labels "arbicore.schema"}}' "$IMAGE_TAG" || true

c_green "BUILD COMPLETE — old backend is still serving. Run 06_cutover.sh when ready."
