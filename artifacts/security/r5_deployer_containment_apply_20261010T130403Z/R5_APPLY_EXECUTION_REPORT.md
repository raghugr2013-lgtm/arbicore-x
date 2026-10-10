# R5-APPLY — Local deployer private-key containment (execution report)

**Verdict: PASS WITH LIMITATIONS**  
**Authorisation:** Local file containment only · **no on-chain actions**  
**Evidence:** `artifacts/security/r5_deployer_containment_apply_20261010T130403Z/`  
**Escrow:** `/home/raghu/arbicore_backups/r5_deployer_containment_20261010T130403Z/` (`0700`)  
**Preflight used:** [`../r5_preflight_base_audit_20261010T125526Z/R5_PREFLIGHT_AND_BASE_CRITICAL_PATH_AUDIT.md`](../r5_preflight_base_audit_20261010T125526Z/R5_PREFLIGHT_AND_BASE_CRITICAL_PATH_AUDIT.md)  
**Overall security gate / P2:** **BLOCKED** (unchanged — R6 open; address identity unresolved; no on-chain auth)

**Secret policy:** no private-key values printed or written into reports.

---

## Precheck (before mutation)

| Check | Result |
|---|---|
| Target | `/home/raghu/projects/arbicore-x-v2/contracts/.env` · mode `0600` · size 285 · file sha256 `ad88e734…e758` |
| `DEPLOYER_PRIVATE_KEY` | present · len 64 |
| Other keys | `BASE_RPC_URL`, `BASESCAN_API_KEY` |
| Escrow root | `/home/raghu/arbicore_backups` present |
| Rollback | restore escrow → live `.env` (`rollback.sh`) — unambiguous |
| Active forge/deploy consumers | **none** |
| Backend | digest `69fe2459…` · healthy · SHADOW · AUTOEXEC/RUNTIME false · no deployer/private key in ENV |
| Git | `.env` gitignored · untracked |
| Foundry keystore | present · `0600` · **not modified** |

---

## Actions performed

1. Created restricted escrow dir `…/r5_deployer_containment_20261010T130403Z/` (`0700`).  
2. Copied exact live `contracts/.env` → `contracts.env.pre-r5` (`0600`); verified file sha256 match to precheck.  
3. Removed **only** the `DEPLOYER_PRIVATE_KEY=` line (1 line); left `BASE_RPC_URL` and `BASESCAN_API_KEY`; wrote via temp replace; `chmod 600`.  
4. **Did not** alter Foundry keystore, `.deployer_address.txt`, R4 quarantine, legacy containers, g5.79/Foreman, backend, RPC, or Git history.  
5. **Did not** generate/replace keys, fund, sign, broadcast, or change ownership.

---

## Verification (executed)

| ID | Check | Result |
|---|---|---|
| V1 | `DEPLOYER_PRIVATE_KEY` absent from live `.env` | **PASS** |
| V2 | Live `.env` mode `0600` | **PASS** |
| V3–V4 | Escrow present `0600`; sha256 = pre-edit file | **PASS** |
| V5 | Remaining keys = `BASE_RPC_URL`, `BASESCAN_API_KEY` only | **PASS** |
| V6 | Address file unchanged (`0x65af…2003`) | **PASS** (mismatch retained as blocker) |
| V7 | Keystore size/mode unchanged | **PASS** |
| V8 | Digest/health/controls; no deployer key in backend ENV | **PASS** |
| V9 | R1 docs 404 · R2 setup 503 · `/api/` 200 | **PASS** |
| V10 | Legacy containers still exited | **PASS** |
| V11 | R4 quarantine still `0700` | **PASS** |
| V12–V13 | No forge consumers · `.env` still untracked | **PASS** |

Evidence: [`post_apply_verification.json`](post_apply_verification.json) · [`escrow_attestation.json`](escrow_attestation.json) · [`env_edit_attestation.json`](env_edit_attestation.json)

---

## Address mismatch — separate blocker (unchanged)

| Identity | Address | Role |
|---|---|---|
| Address file (untouched) | `0x65afB0a65Fd22F88022915F53eD48DA34fb02003` | Documented inventory |
| Preflight key-derived | `0x3b37a5E124b177fEE30365deb295A5CCF76841Cd` | Former plaintext key (now only in escrow) |
| Executor owner / broadcast `from` | `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89` | On-chain production identity |

**Correction proposal (NOT done — needs separate auth after operator confirms intended identity):**  
1) Decide authoritative deploy identity (likely **C** `0x0a43…` if it remains `owner()`).  
2) Update `.deployer_address.txt` to that address only.  
3) Confirm Foundry keystore unlocks to the intended address (password-gated; out of this apply).  
4) Any ownership migration or key replacement remains **on-chain / keygen auth** — out of R5-APPLY.

---

## Rollback limitations

| Path | Notes |
|---|---|
| Restore escrow | `rollback.sh` restores plaintext key into live `.env` — **re-exposes** material; last resort only |
| Escrow retention | Escrow **must** remain `0700`/`0600` until operator risk-accepts destroy; it is recovery evidence |
| Cannot un-compromise | Prior plaintext exposure is not undone by file edit |

---

## Limitations (do not clear overall gate)

- Address inventory mismatch **open**.  
- Escrow still holds plaintext key under restricted backup.  
- R6 provider revoke **not** addressed.  
- No on-chain verification of keystore↔owner binding.  
- P2 / live execution still **BLOCKED**.

---

## Safety state

- SHADOW · AUTOEXEC=false · RUNTIME=false · signing/broadcast off  
- Digest `69fe2459…` · R1/R2 held · R4 quarantine hold untouched  

**Stopped for review. No on-chain operation authorised or performed.**
