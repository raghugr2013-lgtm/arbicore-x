#!/usr/bin/env bash
# upgrade.sh — delegate the BACKEND-ONLY upgrade to the audited upgrade toolkit.
# This is a thin wrapper. All logic lives in deployment/upgrade/ (SHA-locked
# audit heritage from the legacy realignment toolkit — never modify that
# subtree without an accompanying audit).
#
# Usage:
#   ./upgrade.sh            # runs: 00 detect -> 01 preflight -> 02 backup -> 03 index_audit
#                           #        (then stops, prints continuation instructions)
#   ./upgrade.sh full       # runs the full chain up to 11_snapshot (build + cutover + canary + validate)
#   ./upgrade.sh rollback   # runs 99_rollback.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UPGRADE_DIR="${REPO_ROOT}/deployment/upgrade"

[ -d "$UPGRADE_DIR" ] || {
  echo "upgrade toolkit missing at $UPGRADE_DIR" >&2
  exit 1
}

ACTION="${1:-safe}"

case "$ACTION" in
  safe)
    cd "$UPGRADE_DIR"
    make detect
    make preflight
    make backup
    make index-audit
    echo ""
    echo "  Stopped before build/cutover on purpose. Continue manually:"
    echo "    cd $UPGRADE_DIR"
    echo "    make build      # safe — builds image, old keeps serving"
    echo "    make cutover    # THE ONLY DOWNTIME WINDOW (seconds)"
    echo "    make canary     # 60s post-cutover probe with auto-rollback on threshold"
    echo "    make validate   # acceptance"
    echo "    make snapshot   # observability"
    echo "    make rollback   # ONLY if a step above fails"
    ;;
  full)
    cd "$UPGRADE_DIR"
    make detect
    make preflight
    make backup
    make index-audit
    make build
    make cutover
    make canary
    make validate
    make snapshot
    ;;
  rollback)
    cd "$UPGRADE_DIR"
    make rollback
    ;;
  *)
    echo "unknown action: $ACTION" >&2
    echo "usage: $0 [safe|full|rollback]" >&2
    exit 2
    ;;
esac
