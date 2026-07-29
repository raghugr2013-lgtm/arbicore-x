#!/usr/bin/env bash
# backup.sh — thin wrapper. Delegates to deployment/backups/backup.sh.
# Cron-friendly. Non-interactive.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${REPO_ROOT}/deployment/backups/backup.sh" "$@"
