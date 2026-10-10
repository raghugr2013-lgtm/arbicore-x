# WP-C Bounded Implementation Plan

**Date:** 2026-10-10  
**Status:** PLAN ONLY — **not authorized for implementation** until WP-A/WP-B snapshot review boundary is accepted  
**Depends on:** WP-A/WP-B working tree at baseline `8ac3c67d5b28c348782ee1e218e45040d46a311f` (+ uncommitted auth/KS hardening)  
**Out of scope for this plan’s execution phase:** production access, deploy, signing, broadcast, strategy activation, DEX replay

---

## 0. Preconditions (must remain true)

1. WP-A/WP-B snapshot reviewed (or explicitly waived) without discarding the producer diff.  
2. Canonical auth remains fail-closed; legacy bearer stays disabled.  
3. Network apply/rollback and KS disengage remain admin-gated.  
4. Implementation work happens in a **disposable worktree**, not by mutating production or overwriting sibling trees.  
5. Offline tests first; no live RPC/send.

---

## 1. Objectives (bounded)

Close the remaining execution-safety gaps that WP-A/WP-B intentionally deferred:

| Track | Theme | Related IDs (from prior reconciliation) |
|---|---|---|
| **C1** | Dual kill-switch store consistency | F-AUTH-04 (store split) |
| **C2** | Kill-vs-send race | F-AUTH-04 (race), F-GW-08 |
| **C3** | Transaction-byte immutability | F-GW-01 |
| **C4** | Chain allowlists / ceilings | F-GW-02 |
| **C5** | Durable budgets | F-GW-03 |
| **C6** | Nonce coordination | F-GW-05 |
| **C7** | Technical-failure cleanup | F-GW-04, F-TV residual |

Do **not** expand into strategy logic, DEX replay, or UniV4 work under WP-C.

---

## 2. Work packages

### C1 — Dual kill-switch store consistency

**Intent:** Exactly one authoritative engage flag for status, disengage APIs, and send gates.

**Likely files:**  
`server.py` (safety `_KILL` + execution `_KILL_SWITCH_REPO`), `arbicore/execution/kill_switch.py`, `arbicore/safety/kill_switch.py`, `live_signer.py`, autoexecutor wiring.

**Design choices to lock before coding:**

1. Persistent `_KILL_SWITCH_REPO` is the sole source of truth **or** a single facade that syncs both under one write path.  
2. In-memory `_KILL` either becomes a cache of the persistent store or is retired from HTTP APIs.  
3. Status endpoints report one `engaged` boolean (no silent OR of divergent stores without documenting sync).

**Acceptance tests (offline):**

- Engage via execution API → safety status + `KillSwitchRepo.guard` + signer gate all see engaged.  
- Disengage admin-only on every public API (regression from WP-B).  
- Process restart: engaged state survives (persistent store).  
- No split-brain: after engage on API A, API B cannot report disengaged.

**Non-goals:** Changing engage privilege from operator without a separate decision.

---

### C2 — Kill-vs-send race

**Intent:** Immediately before `eth_sendRawTransaction` (or equivalent sole send entry), re-read KS under the same critical section as nonce/sign; if engaged → deny.

**Likely files:** `broadcast.py`, `live_signer.py`, signer vault call sites.

**Acceptance tests:**

- Concurrent engage during send preparation → send denied.  
- KS engaged between plan build and send → deny (no partial broadcast).  
- Unit test with fake clock/ordering; no live chain.

---

### C3 — Transaction-byte immutability

**Intent:** Bytes validated for broadcast cannot be mutated before sign/send.

**Likely files:** broadcast/planner/sign path; any “re-encode” step.

**Acceptance tests:**

- Mutate calldata/tx fields after validation → deny.  
- Hash/compare validated payload at send boundary.  
- Golden vectors offline only.

---

### C4 — Chain allowlists and ceilings

**Intent:** Broadcast rejects `chain_id` outside the frozen allowlist for the active profile; enforce per-chain ceilings already implied by network/execution policy.

**Likely files:** `broadcast.py`, network config apply path, limited-live eligibility.

**Acceptance tests:**

- Base `8453` allowed for LIVE-Base profile; foreign chain_id denied.  
- Sepolia only when explicit cert profile is set (if present).  
- Multichain discovery must not imply multichain broadcast.

---

### C5 — Durable budgets

**Intent:** Cumulative gas / top-up / loss budgets persist and block send when exceeded.

**Likely files:** `capital_policy.py`, allocator, broadcast gates.

**Acceptance tests:**

- Persist counters across process restart (Mongo-backed).  
- Exceed daily loss → send denied.  
- Partial failures do not reset budgets incorrectly.

---

### C6 — Nonce coordination

**Intent:** Concurrent senders cannot reuse or race the same nonce without a lock/lease.

**Likely files:** `broadcast.py`, any nonce helper; document single-writer assumption if multi-instance is unsupported.

**Acceptance tests:**

- Two concurrent send attempts → one obtains nonce lease; other waits or fails closed.  
- If multi-instance unsupported: boot/send fails closed when second writer detected (document).

---

### C7 — Technical-failure cleanup

**Intent:** Failed technical validation does not leave durable “allowance” or sticky permissions that widen the send surface.

**Likely files:** TV / certification / allowance stores.

**Acceptance tests:**

- Failed TV clears or expires allowances.  
- Retry requires full re-validation.  
- No path from failed TV to LIVE send.

---

## 3. Suggested implementation order

```
C1 (single KS) ──► C2 (kill-vs-send) ──► C3 (byte immutability)
                         │
                         ├──► C4 (chain allowlist)
                         ├──► C5 (budgets)
                         └──► C6 (nonce)
C7 can proceed in parallel after C1 once TV stores are identified.
```

C1 is blocking for honest send-gate tests. C2 depends on C1’s authoritative read.

---

## 4. Test matrix (minimum before claiming WP-C done)

| # | Test | Offline |
|---|---|---|
| 1 | KS engage reflects on all status + guard APIs | Yes |
| 2 | Non-admin disengage → 403 (both APIs) | Yes |
| 3 | Engage during send → deny | Yes (fake send) |
| 4 | Byte mutation after validate → deny | Yes |
| 5 | Wrong chain_id → deny | Yes |
| 6 | Budget exceeded → deny; restart preserves counter | Yes (local Mongo or fake repo) |
| 7 | Concurrent nonce → fail-closed or serialized | Yes |
| 8 | Failed TV cleanup → no sticky allow | Yes |
| 9 | Regression: WP-A network apply + WP-B disengage suites still green | Yes |

Do **not** claim full-suite success if only these ran.

---

## 5. Deliverables when WP-C is authorized

1. Code changes in a disposable worktree.  
2. Focused offline tests for C1–C7.  
3. Report: `artifacts/security_reconciliation/WP_C_PRE_SEND_ENFORCEMENT_REPORT_<date>.md`  
4. Explicit residual list (e.g. multi-instance nonce if deferred).  
5. Stop for human review — no deploy/sign/broadcast.

---

## 6. Explicit exclusions

- No production host/DB/RPC/wallet access  
- No credential rotation or secret printing  
- No strategy activation / SHADOW→LIVE enablement  
- No DEX replay datasets  
- No automatic start after WP-A/WP-B Emergent review without a new authorization message  

---

## 7. Stop

This document is the bounded WP-C plan only. **Do not implement** until the WP-A/WP-B snapshot review boundary is clear and WP-C is separately authorized.
