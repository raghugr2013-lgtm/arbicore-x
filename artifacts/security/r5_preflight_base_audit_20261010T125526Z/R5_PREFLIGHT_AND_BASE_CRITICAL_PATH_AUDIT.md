# ArbiCore X — R5-PREFLIGHT + Base Critical-Path Audit

**Authorisation:** Read-only only · **R5-APPLY / P2 / live execution NOT executed**  
**UTC:** `2026-10-10T12:55:26Z`  
**Evidence:** `artifacts/security/r5_preflight_base_audit_20261010T125526Z/` · probe [`r5_preflight_probe.json`](r5_preflight_probe.json)  
**Overall security gate / P2:** **BLOCKED**

**Preserved (rechecked):** digest `69fe2459…` healthy · SHADOW · AUTOEXEC=false · RUNTIME=false · no BOOTSTRAP · no deployer key in backend ENV · six-network RPC left intact · R1/R2 held · R3/R4 results unchanged · legacy exited · g5.79/Foreman untouched

**Secret policy this report:** no private-key values, no key material hashes for disclosure, no copies created.

---

## Part A — R5 deployer-key exposure

### Assessment

| Item | Finding |
|---|---|
| **Verdict** | **FAIL / READY FOR EXPLICIT R5-APPLY AUTHORISATION** (containment proposal only) |
| Plaintext location | `/home/raghu/projects/arbicore-x-v2/contracts/.env` · mode `0600` · `DEPLOYER_PRIVATE_KEY` **present** · len **64** · hex-shaped |
| Cert tree | `arbicore-x-cert/contracts/.env` **absent** |
| Foundry keystore | `~/.foundry/keystores/arbicore-base-mainnet-deployer` · mode `0600` · encrypted JSON (no cleartext address field) |
| Address inventory file | `arbicore-x-v2/contracts/.deployer_address.txt` → `0x65afB0a65Fd22F88022915F53eD48DA34fb02003` (git-tracked) |
| Key-derived address (local reconcile) | `0x3b37a5E124b177fEE30365deb295A5CCF76841Cd` |
| Address file vs key | **MISMATCH** (file ≠ key) |
| On-chain executor owner | `FlashLoanReceiver` `0x0e3fdb0f…5927f` · `owner()` = `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89` |
| Broadcast deployer (8453 run-latest) | same `0x0a43…` (third identity) |
| Active use | **No** forge/cast deploy processes · **not** in backend ENV · deploy docs/scripts reference `$DEPLOYER_PRIVATE_KEY` for **manual** `forge script --broadcast` only |
| Git exposure | `.env` gitignored · **0** `contracts/.env` objects in `git rev-list` · address file tracked (public only) |
| Balances (Base, public RPC) | `0x3b37…` **0 ETH** · `0x65af…` **0 ETH** (confirms prior `gate_deployer_balances.json`; Alchemy keyed URL 429 this session) |

**Compromised?** **Treat as compromised for policy purposes.** Plaintext 32-byte key on a multi-purpose workstation is exposure even at **0 ETH**. Zero balance is **not** safety. Inventory inconsistency (three addresses: key / file / on-chain owner) means recovery and ownership paths are ambiguous until reconciled under R5-APPLY.

### Prior evidence paths

- [`SECURITY_GATE_RECONCILIATION.md`](../SECURITY_GATE_RECONCILIATION.md) §I  
- [`S1B_POST_ROTATION_VERIFICATION.md`](../s1b_vault_rotation_preflight_20261009/S1B_POST_ROTATION_VERIFICATION.md) §4  
- [`gate_deployer_balances.json`](../s2a_alchemy_containment_20261009/gate_deployer_balances.json)  
- This probe: [`r5_preflight_probe.json`](r5_preflight_probe.json)

### Bounded remediation proposal (NOT executed)

1. **Compromise posture:** Assume plaintext key material may have been readable by other local principals/backups; do not rely on “dust = safe.”  
2. **Replacement:** Generate new deployer via `cast wallet new` or Foundry keystore **only**; store in `~/.foundry/keystores/…` (`0600`); escrow offline; **never** rewrite plaintext into `contracts/.env`.  
3. **Remove plaintext without destroying evidence:**  
   - Copy current `contracts/.env` → approved backup dir `0700` / file `0600` (R5 escrow)  
   - Replace live file with `.env.example`-style template **without** `DEPLOYER_PRIVATE_KEY` (keep `BASE_RPC_URL` / Basescan as needed under separate secret hygiene)  
   - Retain Foundry keystore; document unlock procedure for future authorised deploys  
4. **Address inventory:** Rewrite `.deployer_address.txt` to the **authoritative** address after operator chooses: (a) keystore-derived new key, or (b) migrate ownership from `0x0a43…` if that remains production owner.  
5. **Contract ownership / migration:** Live executor owner is **`0x0a43…`**, not the plaintext-key address nor the address file. Any `transferOwnership` / redeploy needs **separate on-chain transaction authorisation**, funded wallet, and verification (`owner()`). **Out of R5 file-containment alone.**  
6. **Backup / rollback:** Escrow pre-change `.env` + keystore backup; rollback = restore escrowed `.env` (re-exposes plaintext — last resort). Cannot “un-compromise” a key once exposed.  
7. **Post-change verification:** no `DEPLOYER_PRIVATE_KEY` in tree; backend ENV still clean; balances recheck (read-only); controls/digest unchanged; git status clean of secrets.  
8. **Approvals required before:** R5-APPLY (file containment); any broadcast/ownership tx; funding; R6 revoke; P2 deploy.

---

## Part B — R4-SCRUB Phase A closeout

| Check | Result |
|---|---|
| Manifest `move_map.json` vs quarantine | **17/17** dest present · sha256 match · mode `0600` |
| Sources absent | **17/17** |
| Quarantine dir mode | `0700` · `/home/raghu/arbicore_backups/r4_scrub_quarantine_20261010T122730Z/` |
| Live `.env` / runtime | Unchanged by scrub · admin/JWT sha12 still `112c88ac69e1` / `f98650d468b2` · digest healthy |
| Shred / Phase B | **Not done** (correct) |
| Broad `/home/raghu` find | **Not run** this audit |

| Hold clock | UTC |
|---|---|
| **Hold start** (first move) | `2026-10-10T12:29:00Z` |
| **Hold days** | 14 |
| **Earliest destroy-review** | `2026-10-24T12:29:00Z` |

Restore (pre-destroy only): `artifacts/security/r4_scrub_phase_a_20261010T122730Z/restore_from_quarantine.sh`  
Closeout probe fields: [`r5_preflight_probe.json`](r5_preflight_probe.json) → `r4_closeout`.

---

## Part C — Base strategy critical path (research only)

### DEX 266 + 15 hold-out

| Item | Status |
|---|---|
| Primary 266-candidate replay | **PENDING / BLOCKED** — no on-disk criteria/cohort/pass-fail package (reconciled with [`CRITICAL_PATH_BOARD_BASE_FULL_LIVE_20261010.md`](../../CRITICAL_PATH_BOARD_BASE_FULL_LIVE_20261010.md) B-DEX-266) |
| 15-tx hold-out | **PENDING / BLOCKED** — same; keep **separate** when package exists |
| Do not invent criteria | **Held** |

Related completed research (not a substitute for 266/15): G1.5 offline coverage (`artifacts/g15/audit_offline_base_replay_20261009/`) · UniV4 inventory **DO NOT IMPLEMENT** · G1.6 false-arb offline.

### ~379 s discovery→decision latency

| Evidence | Value |
|---|---|
| Source | [`PERFORMANCE_BASELINE.md`](../../performance/p1_readonly_baseline/PERFORMANCE_BASELINE.md) |
| observe→verify p50 | **379.2 s** (n=672) |
| observe→claim p50 | **375.1 s** (n=383) — **queue wait** |
| Active verify median | **1.64 s** |
| Claim→stamp p50 | **6.54 s** |
| Coverage | ~95% candidates expire unverified |

**Cause:** Queue wait dominates (~99% of wall-clock). Not RPC-verify hot-path; admission/volume ≫ 6-worker drain.

**Smallest fix (measurement first, then admission):**  
1. **Minimum deployable instrumentation (already packaged):** P2 durable `claimed_at` + stage timing — `artifacts/performance/p2_release/` (**not** authorised to deploy; security gate blocks; live image is now `69fe2459…` so re-apply-check required before any future deploy auth).  
2. **Latency reduction (separate design auth):** discovery admission / TTL / priority so insert rate matches verify capacity (P1 rank #2). Do **not** raise worker count first.

**SHADOW validation metrics (when authorised):** p50/p95/p99 observe→claim and observe→verify; stale/expired rate; fresh_eligible_depth; verify_rate; failure classes (venue unreadable, gate-7 deny); keep AUTOEXEC/RUNTIME false; no threshold relaxation.

**Families:** Triangular = second validation family (pending independent package). Morpho liquidations = bounded offline only (census exists; no build).

---

## Gate board (this audit)

| Gate | Status |
|---|---|
| R1–R3 | **PASS** / R3 **PASS WITH LIMITATIONS** |
| R4 live + Phase A quarantine | **PASS WITH LIMITATIONS** · hold to `2026-10-24T12:29:00Z` |
| R4 destroy / Phase B | **PENDING** (not authorised) |
| R5 | **FAIL exposure** · preflight **READY FOR R5-APPLY AUTH** · apply **not** done |
| R6 | **BLOCKED** / UNKNOWN revoke |
| P2 timing patch deploy | Packaged · **BLOCKED** by security gate + no deploy auth |
| DEX 266 / 15 hold-out | **BLOCKED** (missing package) |
| Triangular / Morpho family decisions | **PENDING** / deferrable |
| Overall / P2 / live execution | **BLOCKED** |

---

## Single recommended next action

**Explicit R5-APPLY (file containment only):** escrow then remove plaintext `DEPLOYER_PRIVATE_KEY` from `arbicore-x-v2/contracts/.env`; keep Foundry keystore; reconcile address inventory; **no** on-chain txs in that auth.

Do **not** start quarantine destroy before `2026-10-24T12:29:00Z`, Phase B, R6 revoke, P2 deploy, or invent a 266/15 package.

**Stopped for review. No mutation executed.**
