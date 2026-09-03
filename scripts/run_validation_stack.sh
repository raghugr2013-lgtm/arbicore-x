#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ArbiCore X — repeatable disposable validation stack runner.
#
# Wraps `docker compose -f deployment/compose/docker-compose.validation.yml
# run --rm --build validator` with a deterministic, self-cleaning lifecycle so
# repeated authoritative validation runs NEVER collide with a stale validator
# container/network and NEVER touch production.
#
# READ-ONLY / SAFE: the audited worktree is bind-mounted read-only; the
# validator Mongo is ephemeral (tmpfs); production Mongo/containers/compose are
# untouched. NEVER signs, broadcasts, enables Live/Limited-Live, or mutates
# production. Stamps the EXACT checked-out SHA/branch under validation.
#
# Usage (from the detached worktree at the SHA you want to validate):
#   bash scripts/run_validation_stack.sh
#   ARBICORE_RUN_LIVE_AUDIT=1 bash scripts/run_validation_stack.sh   # + live phase
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/deployment/compose/docker-compose.validation.yml"
# Unique project name per invocation guarantees full isolation from any prior
# (possibly stale) validator project, so nothing can block this run.
PROJECT="arbicore_val_$(date -u +%Y%m%d%H%M%S)_$(head -c3 /dev/urandom | od -An -tx1 | tr -d ' \n')"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found on host — cannot run the disposable validation stack." >&2
  echo "Install Docker (or run scripts/run_vps_validator_audit.sh directly with pytest)." >&2
  exit 127
fi

# Prefer `docker compose` (v2); fall back to `docker-compose` (v1).
if docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
else
  echo "ERROR: neither 'docker compose' nor 'docker-compose' is available." >&2
  exit 127
fi

export VALIDATION_GIT_SHA="${VALIDATION_GIT_SHA:-$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)}"
export VALIDATION_GIT_BRANCH="${VALIDATION_GIT_BRANCH:-$(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)}"

DC_BASE=("${DC[@]}" -p "${PROJECT}" -f "${COMPOSE_FILE}")

cleanup() {
  # Remove THIS run's containers, networks and ephemeral volumes. Scoped to the
  # unique project so it can never affect production or another validation run.
  "${DC_BASE[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "=============================================================="
echo "ArbiCore X — disposable validation stack"
echo "project      : ${PROJECT}"
echo "compose_file : ${COMPOSE_FILE}"
echo "git_sha      : ${VALIDATION_GIT_SHA}"
echo "git_branch   : ${VALIDATION_GIT_BRANCH}"
echo "=============================================================="

# Pre-clean (defensive): a prior crash under THIS unique project would be rare,
# but keep the invariant that we start from nothing.
cleanup

STATUS=0
"${DC_BASE[@]}" run --rm --build validator || STATUS=$?

echo "=============================================================="
if [ "${STATUS}" -eq 0 ]; then
  echo "VALIDATION STACK RESULT: PASS (exit 0)"
else
  echo "VALIDATION STACK RESULT: FAIL (exit ${STATUS})"
fi
echo "=============================================================="
exit "${STATUS}"
