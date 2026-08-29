#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# ArbiCore X — flash-loan limited-live readiness audit runner (repo tooling).
#
# READ-ONLY / SAFE: this runner ONLY executes the deterministic, offline
# regression suite that guards the flash-loan verification pipeline. It NEVER
# signs, NEVER broadcasts, NEVER enables Live/Limited-Live, and NEVER mutates
# any deployment. It emits an audit_run_id so a run can be correlated with the
# diagnostic provenance stamped onto persisted evidence bundles.
#
# Usage:
#   scripts/run_vps_validator_audit.sh
#
# On the VPS, Codex may additionally run the live validators
# (python -m scripts.m3_0_vps_validate) which require real Base RPC / Mongo;
# those are intentionally NOT invoked here to keep this runner hermetic.
# ---------------------------------------------------------------------------
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/app/backend"
AUDIT_RUN_ID="flarb_audit:$(date -u +%Y%m%dT%H%M%SZ):$(head -c4 /dev/urandom | od -An -tx1 | tr -d ' \n')"

echo "=============================================================="
echo "ArbiCore X flash-loan readiness audit"
echo "audit_run_id : ${AUDIT_RUN_ID}"
echo "repo_root    : ${REPO_ROOT}"
echo "git_sha      : $(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo unknown)"
echo "git_branch   : $(git -C "${REPO_ROOT}" rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
echo "=============================================================="

# Deterministic guards for the safety-critical flash-loan pipeline. These are
# the invariants that MUST hold before any VPS live validation is attempted.
TESTS=(
  "tests/test_flashloan_partial_quote_economics.py"
  "tests/test_flashloan_diagnostic_provenance.py"
  "tests/test_m2_1_live_quote_provider.py"
  "tests/test_m2_2_real_tvl_gate8.py"
  "tests/test_m2_3_evidence_bundle.py"
  "tests/test_d6_1_economics_and_gates.py"
  "tests/test_economics_swap_fee_double_count.py"
  "tests/test_m3_0_pre_broadcast.py"
  "tests/test_m3_0_diagnostic_ordering.py"
)

cd "${BACKEND_DIR}"
echo "Running ${#TESTS[@]} deterministic regression modules..."
export ARBICORE_AUDIT_RUN_ID="${AUDIT_RUN_ID}"
python -m pytest "${TESTS[@]}" -q -p no:cacheprovider
STATUS=$?

echo "=============================================================="
if [ "${STATUS}" -eq 0 ]; then
  echo "AUDIT RESULT: PASS (code-level flash-loan guards green)"
  echo "NOTE: code-ready only. Real VPS live validation (RPC/Mongo) is separate."
else
  echo "AUDIT RESULT: FAIL (see failures above) — NOT ready for VPS validation"
fi
echo "audit_run_id : ${AUDIT_RUN_ID}"
echo "=============================================================="
exit "${STATUS}"
