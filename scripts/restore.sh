#!/usr/bin/env bash
# restore.sh — thin wrapper. Delegates to deployment/backups/restore.sh.
# Usage: ./restore.sh <path/to/archive.gz>
# Interactive confirm inside the delegated script.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec "${REPO_ROOT}/deployment/backups/restore.sh" "$@"
