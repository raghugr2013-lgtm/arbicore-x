# WP-C Pre-Send Enforcement Report (Workstream B)

**Date:** 2026-10-10  
**Branch:** `review/wp-c-presend-20261010`  
**Base (unchanged):** `3879be1ce5ef716efd07d63a7ad54291ed66a659`  
**Worktree:** `/tmp/arbicore-wp-c-presend-b`  
**Canonical / producer:** not modified  
**Plan:** `WP_C_BOUNDED_IMPLEMENTATION_PLAN_20261010.md`

## Verdict by track

| Track | Theme | Verdict | Notes |
|-------|--------|---------|-------|
| **C1** | Dual KS → one authoritative store | **PASS** | Persistent `KillSwitchRepo` is SoT; in-memory `_KILL` is mirror via `bind_memory_mirror`; safety engage/disengage write repo; unavailable → engaged |
| **C2** | Kill-vs-send race | **CONDITIONAL** | `SendCriticalSection` re-reads KS under process lock immediately before send — closes TOCTOU in-process. **Not** a distributed lock across hosts |
| **C3** | Tx-byte immutability | **PASS** | `TxByteBinding` digest bound and re-checked at send |
| **C4** | Chain allowlist + ceilings | **PASS** | Base `8453` only; per-chain USD ceiling enforced |
| **C5** | Durable budgets | **PASS** | `DurableBudgetStore` atomic `$inc` + wired into `LimitedLiveBroadcaster` |
| **C6** | Nonce coordination | **CONDITIONAL** | Process-local lease + `ARBICORE_BROADCAST_INSTANCE_ID` single-writer. Multi-instance without shared lease → **not guaranteed** |
| **C7** | TV failure cleanup | **PASS** | Failed/non-ready TV clears `arbicore_tv_allowances` and marks records expired / not live-eligible |

Overall workstream: **CONDITIONAL PASS** (C2/C6 multi-instance residual).

## Key files

- `arbicore/execution/presend_invariants.py` (new)
- `arbicore/execution/kill_switch.py` (mirror bind, fail-closed guard)
- `arbicore/execution/broadcast.py` (critical section, binding, chain, budget, nonce)
- `server.py` (authoritative safety KS paths, TV cleanup, budget store wiring)
- `tests/test_wp_c_presend_invariants.py`
- `tests/test_wp_b_kill_switch_auth.py` (safety tests updated for repo SoT)

## Tests

```bash
cd /tmp/arbicore-wp-c-presend-b/app/backend
JWT_SECRET='wp-c-presend-jwt-secret-32chars-min!!' \
ARBICORE_JWT_SECRET='wp-c-presend-jwt-secret-32chars-min!!' \
MONGO_URL='mongodb://127.0.0.1:27017' DB_NAME='wp_c_presend_test' \
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wp_a_auth_unification.py \
  tests/test_wp_a_emergency_auth_finalization.py \
  tests/test_wp_a_real_handlers.py \
  tests/test_wp_b_kill_switch_auth.py \
  tests/test_wp_ab_config_history_redaction.py \
  tests/test_wp_c_presend_invariants.py \
  -q --tb=short
```

**Result:** `70 passed` · log `/tmp/wp_c_presend_b_pytest.txt`  
(62 regression baseline + 8 WP-C adversarial)

## Limitations (do not weaken)

1. **Multi-instance kill-vs-send / nonce:** process-local only → report **CONDITIONAL**, not PASS, until a distributed lock/lease exists.
2. No live RPC/sign/broadcast exercised (by design).
3. Ladder LIVE hard-gate is Workstream A (separate branch).
4. Stop for human review — no merge/deploy.
