# WP-C Send Recovery Follow-up

**Date:** 2026-10-11  
**Branch:** `review/wp-c-send-recovery-20261011`  
**Base (H5, preserved):** `a574f5a7ab5d5c54531045086b727fa843fe3796`  
**Worktree:** `/tmp/arbicore-wp-c-send-recovery`  
**Handoff-5 file:** not present locally; implemented from charter requirements.

## Design note

### Problem
A process crash after `mark_entering_rpc` leaves `active_send.status=rpc_submitted`. TTL must **not** clear this state (that would assume non-submission). Operators need an evidence-based recovery path.

### Solution
1. **Stamp recovery metadata** at RPC entry: `signer`, `nonce`, `chain_id`, `tx_binding_digest` (never signed bytes / keys / RPC URLs).
2. **Admin API**
   - `GET /api/arbicore/execution/broadcast/coordination-status` — `_require_admin_dep`
   - `POST /api/arbicore/execution/broadcast/recover-stuck-send` — `_require_admin_dep`
3. **`BroadcastCoordinator.recover_stuck_send`**
   - Audit-first insert to `arbicore_send_recovery_audit` (fail closed)
   - CAS recovery claim on `rpc_submitted` (concurrent-safe)
   - Decisions:
     - `tx_found` — requires `tx_found_on_chain=true`, `rpc_get_transaction_result=found`, `tx_hash` → status `completed`, `resend_forbidden=true`, nonce reconcile advance; **no resend**
     - `tx_absent` — requires `tx_found_on_chain=false`, `rpc_get_transaction_result=not_found`, pending≤nonce → `recovered_unused`, nonce reusable for a **new** send_id
     - `investigate` — audit only; remain `rpc_submitted`
   - Inconclusive / contradictory evidence → remain blocked
   - Idempotent if already `completed` / `recovered_unused`
4. **TTL policy:** `authorize_send` may reclaim expired `authorized` only; **never** `rpc_submitted`.

### Privilege & audit
Server-derived `_audit_actor()`; admin-only; durable audit with operator, decision, evidence summary (hash prefix only).

## Tests

```bash
cd /tmp/arbicore-wp-c-send-recovery/app/backend
JWT_SECRET='wp-c-send-recovery-jwt-secret-32ch!!' \
ARBICORE_JWT_SECRET='wp-c-send-recovery-jwt-secret-32ch!!' \
MONGO_URL='mongodb://127.0.0.1:27017' DB_NAME='wp_c_send_recovery_test' \
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wp_a_auth_unification.py \
  tests/test_wp_a_emergency_auth_finalization.py \
  tests/test_wp_a_real_handlers.py \
  tests/test_wp_b_kill_switch_auth.py \
  tests/test_wp_ab_config_history_redaction.py \
  tests/test_wp_c_presend_invariants.py \
  tests/test_wp_c2_c6_durable_coordination.py \
  tests/test_wp_c_send_recovery.py \
  -q --tb=line
```

**Result:** `97 passed` · `/tmp/wp_c_send_recovery_full.txt`

Adversarial coverage: tx found / never submitted / ambiguous timeout / contradictory evidence / concurrent recovery / restart idempotency / audit failure / TTL non-clear / investigate / forbidden fields / anon+operator HTTP / malformed / no-resend proof.

## C1–C7

| C1 | C2 | C3 | C4 | C5 | C6 | C7 |
|----|----|----|----|----|----|-----|
| PASS | PASS | PASS | PASS | PASS | PASS | PASS |

## Residual limitations
1. Operators must supply chain/RPC evidence; the endpoint does not itself call live RPC (by design in this offline recovery surface).
2. Recovery claim TTL (120s) only releases a *stale claim lock*, not `rpc_submitted` itself.
3. No merge/deploy/prod/sign/broadcast in this work.

**Stop for independent review.**
