# WP-C2/C6 Remediation Report

**Date:** 2026-10-10  
**Branch:** `review/wp-c2-c6-remediation-20261010`  
**Base (verified parent):** `f2380f58b2e1d7c2075d1363f287b9e49ea8d381` (`review/wp-c-presend-20261010`)  
**Worktree:** `/tmp/arbicore-wp-c2-c6-remediation`  
**Scope:** C2 + C6 only. Workstream A / canonical / original WP-C branch untouched.

Handoff-4 review file was not present locally at start; remediation follows the charter’s stated defects and the CONDITIONAL findings from WP-C.

---

## 1. Root-cause analysis

### C2 — Kill vs broadcast race
**Cause:** `SendCriticalSection` used a process-local `asyncio.Lock` plus a late `guard()` read. A second process could `engage` after another process passed earlier gates and still reach `eth_sendRawTransaction`, because engagement and send authorization did not share a durable linearization point.

### C6 — Nonce / writer
**Cause:** `NonceCoordinator` kept leases and writer identity in process memory. Competing workers did not share ownership; failed sends could advance the in-memory nonce without durable recovery rules for pre-RPC vs ambiguous RPC outcomes.

---

## 2. Design note

### Module
`app/backend/arbicore/execution/durable_broadcast_coordination.py` — `BroadcastCoordinator`

### C2 synchronization & linearization
| Event | Linearization point |
|-------|---------------------|
| Kill engage | Durable `on_kill_engaged`: `kill_engaged=true` + `$inc kill_fence` **before** KS row write (via `KillSwitchRepo.bind_broadcast_coordinator`) |
| New send crossing broadcast boundary | Durable `mark_entering_rpc` requiring `kill_engaged != true` and matching `active_send` lease |
| In-flight after RPC entry | `status=rpc_submitted` — **not recalled** when engage arrives later; new authorizations denied |

**Semantics:** Once engage is acknowledged in the coordination store, no *new* transaction may enter `eth_sendRawTransaction`. An already `rpc_submitted` attempt is owned by the RPC/chain. Coord/KS unavailability → deny new sends (fail closed).

### C6 durable ownership & recovery
- Global **writer lease** (TTL + fence) in `arbicore_send_coordination`
- Per-signer **nonce lease** in `arbicore_nonce_leases` with monotonic `fence`
- Definite **pre-boundary** failure → `released_pre_rpc`, same nonce reusable (no skip)
- **Ambiguous** post-boundary (timeout/error after `mark_entering_rpc`) → block allocates until `reconcile_nonce` with chain evidence
- Stale writer after TTL → another worker may claim; stale fence cannot complete foreign leases

### Wiring
- `KillSwitchRepo.engage/disengage` ↔ coordinator
- `LimitedLiveBroadcaster` requires `broadcast_coordinator`; refuse send if missing
- `server.py` constructs shared `_BROADCAST_COORDINATOR`

---

## 3. Test commands & results

```bash
cd /tmp/arbicore-wp-c2-c6-remediation/app/backend
JWT_SECRET='wp-c2c6-jwt-secret-32chars-minimum!!' \
ARBICORE_JWT_SECRET='wp-c2c6-jwt-secret-32chars-minimum!!' \
MONGO_URL='mongodb://127.0.0.1:27017' DB_NAME='wp_c2_c6_remediation_test' \
/tmp/wp_a_auth_venv/bin/python -m pytest \
  tests/test_wp_a_auth_unification.py \
  tests/test_wp_a_emergency_auth_finalization.py \
  tests/test_wp_a_real_handlers.py \
  tests/test_wp_b_kill_switch_auth.py \
  tests/test_wp_ab_config_history_redaction.py \
  tests/test_wp_c_presend_invariants.py \
  tests/test_wp_c2_c6_durable_coordination.py \
  -q --tb=line
```

**Result:** `83 passed`  
**Logs:** `/tmp/wp_c2_c6_full_pytest.txt`, `/tmp/wp_c2_c6_focused_pytest.txt`

Adversarial coverage (two coordinator instances / shared store = process analogue): engage-between-authorize-and-RPC, foreign engage via `KillSwitchRepo`, writer exclusion, nonce exclusion, lease expiry/stale owner, pre-RPC reuse, ambiguous block + reconcile, restart fence.

---

## 4. C1–C7 verdicts after regression

| Track | Verdict | Notes |
|-------|---------|-------|
| C1 | **PASS** | Unchanged SoT + mirror; engage still writes repo |
| C2 | **PASS** | Durable shared fence; Handoff-4 race closed in tests |
| C3 | **PASS** | `TxByteBinding` retained at send |
| C4 | **PASS** | Chain allowlist/ceiling retained |
| C5 | **PASS** | Durable budgets retained |
| C6 | **PASS** | Durable writer/nonce + recovery rules |
| C7 | **PASS** | TV cleanup retained |

---

## 5. Remaining limitations / operational controls

1. Coordination store is Mongo (or compatible). Mongo outage → fail closed (no new sends); operators must restore DB before LIVE broadcast.
2. Ambiguous RPC still requires **`reconcile_nonce`** with chain evidence (`tx_found_on_chain` / `eth_getTransactionCount`); no automatic blind nonce decrement.
3. Writer lease TTL default 60s — crashed holders block until expiry unless ops force-expire the lease document.
4. Multi-region dual-primary Mongo without linearizable reads is out of scope; deploy single primary / majority write concern for LIVE.
5. No production access, signing, or broadcast in this work.

**Stop for independent review — no merge/deploy.**
