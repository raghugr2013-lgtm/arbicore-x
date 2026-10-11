# WP-C Recovery Evidence-Authenticity Remediation

**Date:** 2026-10-11  
**Branch:** `review/wp-c-recovery-evidence-auth-20261011`  
**Base (preserved):** `review/wp-c-send-recovery-20261011` @ `472aac4ec56c52def48094b2861668adf24eb255`  
**Parent of base:** `a574f5a7…` (Handoff 5)  
**Worktree:** `/tmp/arbicore-wp-c-recovery-evidence-auth`  
**Closes:** Emergent Handoff 6 evidence-authenticity **FAIL**

## Design note

### Authoritative evidence source
The send path stamps at `mark_entering_rpc` (before `eth_sendRawTransaction`):

* `send_id`, `signer`, `nonce`, `chain_id`, `tx_binding_digest` (SHA-256 of validated tx fields via `TxByteBinding`)

Recovery **never** treats operator JSON as proof that an RPC observation occurred.  
`RecoveryRpcVerifier` performs read-only calls against the configured per-chain provider (`resolve_rpc_url_from_env` → `EthJsonRpcProvider`):

| Observation | RPC |
|-------------|-----|
| Chain identity | `eth_chainId` must equal stuck `chain_id` |
| Transaction | `eth_getTransactionByHash(candidate)` |
| Nonces | `eth_getTransactionCount(signer, pending\|latest)` |

Operator may supply only a **lookup hint** (`candidate_tx_hash` / legacy `tx_hash` key). Fields such as `tx_found_on_chain`, `rpc_get_transaction_result`, `chain_pending_nonce`, `observed_at`, and evidence `chain_id` are **ignored**.

### Binding (`tx_found`)
Server requires the observed RPC transaction to match the stuck send:

* `from` == stuck `signer`
* `nonce` == stuck `nonce`
* `chainId` (or provider `eth_chainId` fallback) == stuck `chain_id`
* Reconstructed `TxByteBinding` digest == stuck `tx_binding_digest`

Mismatch → remain `rpc_submitted`. Success → `completed` + `resend_forbidden=true`.

### Conservative absence (`tx_absent`)
Absence of one hash is never sufficient. Policy:

1. Trusted `eth_chainId` matches stuck chain  
2. Stuck metadata complete (digest/signer/nonce/chain)  
3. `rpc_entered_at` age ≥ `ARBICORE_RECOVERY_ABSENT_MIN_AGE_S` (default 15s)  
4. Two consistent nonce observations (`ARBICORE_RECOVERY_ABSENT_REQUERY_DELAY_S`)  
5. `pending == latest` (else mempool/delayed ambiguity → block)  
6. `pending > stuck.nonce` without digest-bound `tx_found` → block  
7. If `candidate_tx_hash` provided and still present → block (use `tx_found`)  
8. Only then → `recovered_unused`

RPC / coordination / audit failure → fail closed; nonce not released.

### Crash-safe commit
1. Audit `started` (existing audit-first)  
2. CAS recovery claim  
3. Trusted RPC verify  
4. Audit **`commit_intent`** with outcome + evidence summary (**before** status mutation)  
5. CAS durable terminal status (`completed` / `recovered_unused`)  
6. Nonce reconcile + audit finish  

Restart after terminal commit returns `idempotent_already_resolved` with `resend_forbidden` preserved. Commit-intent audit failure aborts before mutation.

### Privilege
Unchanged: admin-only routes, `_audit_actor()`, forbidden secret fields, status allowlist (no keys / signed bytes / RPC URLs).

## Handoff-6 probes — closed

| Probe | Result |
|-------|--------|
| Fabricated `tx_absent` operator JSON | **CLOSED** — ignored; trusted nonce state decides |
| Unbound / mismatched tx hash vs digest | **CLOSED** — `tx_binding_digest` checked |
| Wrong evidence/RPC `chain_id` | **CLOSED** — provider `eth_chainId` must match stuck |

## Tests

```bash
cd /tmp/arbicore-wp-c-recovery-evidence-auth/app/backend
JWT_SECRET='wp-c-send-recovery-jwt-secret-32ch!!' \
ARBICORE_JWT_SECRET='wp-c-send-recovery-jwt-secret-32ch!!' \
MONGO_URL='mongodb://127.0.0.1:27017' DB_NAME='wp_c_recovery_evidence_auth_full' \
ARBICORE_RECOVERY_ABSENT_MIN_AGE_S=0 ARBICORE_RECOVERY_ABSENT_REQUERY_DELAY_S=0 \
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

**Result:** `109 passed` · `/tmp/wp_c_recovery_evidence_auth_full.txt`  
Unit-only recovery: `/tmp/wp_c_recovery_evidence_auth_unit.txt` (`26 passed`)

## Verdict matrix (producer self-check)

| Requirement | Verdict |
|-------------|---------|
| Admin auth recover + status | PASS (preserved) |
| Audit-first / fail-closed stores | PASS |
| `tx_found` + resend forbidden | PASS + digest bind |
| `tx_absent` conservative trusted RPC | PASS |
| Inconclusive stays `rpc_submitted` | PASS |
| TTL never clears `rpc_submitted` | PASS |
| Concurrent CAS / idempotency / restart | PASS |
| Crash after mutation audited/resumable | PASS (`commit_intent`) |
| Status hygiene | PASS |
| Evidence authenticity / binding | **PASS** (remediated) |
| C1–C7 regression | PASS (full suite) |

## Residual limitations
1. `tx_found` still needs a candidate hash hint (operator or nonce-lease `tx_hash`) — standard JSON-RPC cannot enumerate by nonce alone.  
2. Binding assumes legacy `gasPrice` txs (matches current broadcast path); EIP-1559-only receipts fail closed.  
3. Trusted RPC must be correctly configured per chain; misconfiguration fails closed (no release).  
4. Default absent min-age (15s) reduces but does not eliminate extreme mempool races; pending≠latest also blocks.  
5. No merge/deploy/prod/sign/broadcast in this work.

**Stop for independent adversarial review.**
