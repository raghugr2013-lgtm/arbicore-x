# Release-Gate Closure Report (Workstream A)

**Date:** 2026-10-10  
**Branch:** `review/release-gate-closure-20261010`  
**Base (unchanged):** `3879be1ce5ef716efd07d63a7ad54291ed66a659`  
**Worktree:** `/tmp/arbicore-release-gate-a`  
**Canonical / producer:** not modified

## Summary

| Item | Verdict |
|------|---------|
| Strategy-ladder LIVE hard-gate | **PASS** |
| GET auth inventory + protection | **PASS** |
| Route-census regression tests | **PASS** |
| Redactor tuple / ws(s) schemes | **PASS** |
| JWT runtime fail-closed (no secret leak) | **PASS** |
| 62-test regression baseline | **PASS** (included in 80) |

## Mode enum mapping (verified before coding)

| System | Enum |
|--------|------|
| Control `OPERATOR_MODES` | `SHADOW`, `PAPER`, `PROFIT_ENGINE`, `LIMITED_LIVE`, `FULL_AUTOMATION` |
| Ladder `MODES` | `OBSERVE`, `PAPER`, `SHADOW`, `LIMITED_LIVE`, `FULL_LIVE` |

**Not interchangeable.** Hard-gate correspondence this build:
- ladder `LIMITED_LIVE` ↔ control `LIMITED_LIVE`
- ladder `FULL_LIVE` ↔ control `FULL_AUTOMATION`

`POST /execution/mode/{strategy}` refuses LIVE promotions server-side without calling `ExecutionModeRepo.transition`.

## GET authorization

Inventory: `GET_ROUTE_AUTH_INVENTORY_20261010.md` (181 routes).

**Public allowlist (only):** `/`, `/status`, `/system/status`, `/arbicore/version`  
**All other GETs:** `dependencies=[Depends(_require_operator_dep)]`

## Redactor

- `_redact_network_payload` now recurses into `tuple` / `set` (was passthrough).
- `redact_credential_url` embedded/fallback regex includes `ws`/`wss`.

## JWT

Fail-closed on missing/short `JWT_SECRET` asserted; error messages contain requirement text only (no secret material).

## Tests

```bash
cd /tmp/arbicore-release-gate-a/app/backend
JWT_SECRET='release-gate-jwt-secret-32chars-min!!' \
ARBICORE_JWT_SECRET='release-gate-jwt-secret-32chars-min!!' \
MONGO_URL='mongodb://127.0.0.1:27017' DB_NAME='release_gate_closure_test' \
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wp_a_auth_unification.py \
  tests/test_wp_a_emergency_auth_finalization.py \
  tests/test_wp_a_real_handlers.py \
  tests/test_wp_b_kill_switch_auth.py \
  tests/test_wp_ab_config_history_redaction.py \
  tests/test_release_gate_closure.py \
  -q --tb=line
```

**Result:** `80 passed` · log `/tmp/release_gate_a_pytest.txt`

## Limitations

- Public allowlist is intentionally minimal; UI pages that previously hit protected GETs anonymously will require login (intended).
- No production attestation of deployed env secrets.
- Stop for human review — no merge/deploy.
