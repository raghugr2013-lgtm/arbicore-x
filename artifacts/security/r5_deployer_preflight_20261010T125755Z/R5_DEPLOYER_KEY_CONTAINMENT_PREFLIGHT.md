# R5 — Deployer-key containment PREFLIGHT

**Verdict: READY FOR EXPLICIT R5-APPLY AUTHORISATION**  
**Authorisation used:** READ-ONLY PREFLIGHT ONLY · **R5-APPLY NOT EXECUTED**  
**UTC:** `2026-10-10T12:57:55Z` – `2026-10-10T13:01:06Z`  
**Evidence dir:** `artifacts/security/r5_deployer_preflight_20261010T125755Z/`  
**Prior partial probe:** `artifacts/security/r5_preflight_base_audit_20261010T125526Z/r5_preflight_probe.json`

**Secret policy:** Private-key **values are never printed**. References use presence/length/`sha12`/`fp` and derived addresses only.

**Overall security gate / P2:** remains **BLOCKED** until R5-APPLY (and R6) close or are risk-accepted.

---

## 0. Controls preserved (verified this preflight)

| Control | Result |
|---|---|
| Backend digest `sha256:69fe2459…` | **PASS** · healthy |
| `ARBICORE_EXECUTION_MODE=SHADOW` | **PASS** |
| `AUTOEXEC=false` / `RUNTIME=false` | **PASS** |
| Signing/broadcast / `DEPLOYER_PRIVATE_KEY` in backend ENV | **ABSENT** |
| R1 public `/docs` | **404** |
| R2 setup | **503** |
| Six-network RPC env SET | **PASS** (eth/arb/base/op/poly/bnb) |
| R4 quarantine 17/17 · hold → `2026-10-24T12:29:00Z` | **PASS** (untouched) |
| Legacy b7/h05/w1/backend | **exited** (not started) |
| g5.79 / Foreman | status-only · **untouched** |
| P2 deploy / strategy activation | **not performed** |

---

## 1. Exposure findings and confidence

### 1.1 Confirmed plaintext carrier (HIGH confidence)

| Field | Value |
|---|---|
| Path | `/home/raghu/projects/arbicore-x-v2/contracts/.env` |
| Mode | `0600` · regular file · not symlink |
| mtime | `2026-09-01T11:39:24Z` (long-lived on disk) |
| Keys present (names only) | `DEPLOYER_PRIVATE_KEY`, `BASE_RPC_URL`, `BASESCAN_API_KEY` |
| `DEPLOYER_PRIVATE_KEY` | present · len **64** · no `0x` prefix · looks like hex |
| Key identity `sha12` | `7e792fd2e48f` |
| Derived address (local) | `0x3b37a5E124b177fEE30365deb295A5CCF76841Cd` |
| Cert tree `contracts/.env` | **Absent** |

**Confidence: HIGH** — direct local attestation + prior recon agreement (`SECURITY_GATE_RECONCILIATION.md` §I · prior probe).

### 1.2 Foundry keystore (MEDIUM confidence on existence; UNKNOWN address binding)

| Field | Value |
|---|---|
| Path | `/home/raghu/.foundry/keystores/arbicore-base-mainnet-deployer` |
| Mode | `0600` · size 436 · mtime `2026-09-07T07:43:07Z` |
| Format | Encrypted keystore JSON (`crypto.ciphertext` present) |
| Plaintext private-key field | **Absent** |
| `address` field in JSON | **Absent** (Foundry variant without address metadata) |

**UNKNOWN without password unlock (not authorised):** which address this keystore decrypts to (`0x3b37…`, `0x65af…`, `0x0a43…`, or other).

### 1.3 Documented address files (HIGH)

| Path | Address | Tracked |
|---|---|---|
| `arbicore-x-v2/contracts/.deployer_address.txt` | `0x65afB0a65Fd22F88022915F53eD48DA34fb02003` | **Yes** (git) |
| `arbicore-x-cert/contracts/.deployer_address.txt` | same | **Yes** |

### 1.4 Git / upload / other channels

| Check | Result | Confidence |
|---|---|---|
| `contracts/.env` gitignored | **Yes** (`.env` / `.env.*` in `contracts/.gitignore`) | HIGH |
| `contracts/.env` tracked / in index | **No** (v2 + cert) | HIGH |
| `git log -- contracts/.env` | **0** commits | HIGH |
| Pickaxe `DEPLOYER_PRIVATE_KEY` on `.env` path | **0** commits | HIGH |
| Repo-wide pickaxe `DEPLOYER_PRIVATE_KEY` | Hits in **docs/commits** (string mentions / runbooks) — **not** verified as key material | MEDIUM |
| Other env-like files with same `sha12` `7e792fd2e48f` | **Only** the primary v2 `contracts/.env` (58 env-like files scanned) | HIGH for scanned set |
| Docs/`DEPLOYER_PRIVATE_KEY=` mentions | **66** paths — classified as documentation/examples (no second real 64-hex assignment found in env-like scan) | MEDIUM |
| Uploaded to remote / CI secrets / chat | **UNKNOWN** — no evidence in this host audit; not disproven | UNKNOWN |
| Historical shell history / process argv exposure | **UNKNOWN** historically; this preflight used local derive (may have briefly appeared in process table) — treat as residual risk | LOW–MEDIUM |
| R4 quarantine / approved recovery | Not carriers of this deployer key (admin/JWT focus) | HIGH |

**Committed plaintext key:** **No evidence** in v2/cert git history for `contracts/.env`.  
**Exposed via other known channels:** **UNKNOWN** (backups off-host, operator laptops, chat, CI — not audited here).

### 1.5 Compromise posture

**Treat the plaintext material as compromised for containment purposes** despite zero balances:

- Plaintext on multi-user VPS disk since ≥ `2026-09-01`
- Readable by the file owner whenever the host is accessed
- Zero balance **does not** prove non-compromise (key could still sign if funded later, or may have been copied)

---

## 2. Address and dependency reconciliation

### 2.1 Three distinct addresses (MUST NOT collapse)

| Role | Address | Base ETH (live Alchemy RPC) | Notes |
|---|---|---:|---|
| **A — Plaintext `.env` key derived** | `0x3b37a5E124b177fEE30365deb295A5CCF76841Cd` | **0** | Key `sha12` `7e792fd2e48f` |
| **B — Documented `.deployer_address.txt`** | `0x65afB0a65Fd22F88022915F53eD48DA34fb02003` | **0** | Tracked in git; Sepolia broadcast `from` |
| **C — Live executor owner / vault signer** | `0x0a43F432681cA5eE053D53B79Ae1648FDAaBFa89` | **~0.006337** | On-chain `owner()` of receiver; S1-B vault address; mainnet broadcast `from` |
| FlashLoanReceiver | `0x0E3FDb0F0e615A517588Bd44ac6C78Bb7615927f` | **0** | `owner()` = **C** (eth_call this preflight) |

| Match test | Result |
|---|---|
| A == B (key vs address file) | **FAIL** |
| A == C (key vs live owner) | **FAIL** |
| B == C | **FAIL** |
| Keystore address field == A/B/C | **UNKNOWN** (no address metadata) |

### 2.2 Broadcast / script / workflow dependencies

| Asset | Dependency |
|---|---|
| `contracts/script/Deploy.s.sol` | Documents `DEPLOYER_PRIVATE_KEY` for **`forge --private-key` at broadcast**; script itself uses `vm.envAddress` for venues, not the key |
| Broadcast chain **8453** (Base mainnet) | `from` = **C** `0x0a43…` |
| Broadcast chain **84532** (Base Sepolia) | `from` = **B** `0x65af…` |
| GitHub workflows | **No** `DEPLOYER_PRIVATE_KEY` hits in `.github` (v2/cert) |
| Backend runtime | **Does not** consume deployer key |
| Active `forge`/`cast`/`anvil` processes | **None** observed |

### 2.3 Contract ownership / admin surface

| Contract / capability | Controlling address | Tied to plaintext A? |
|---|---|---|
| Base FlashLoanReceiver `owner` | **C** `0x0a43…` | **No** |
| Owner-gated rescue / admin on receiver | **C** | **No** |
| Vault-stored execution key (S1-B) | **C** (separate workstream) | **No** |
| Address **A** on-chain roles | **No hits** in contracts/docs scan for `3b37…` | Appears unused in-repo |
| Address **B** | Sepolia deploy `from` + tracked address file | Testnet deployer identity |

**Implication:** Removing plaintext key **A** from disk does **not** by itself change live mainnet ownership (**C**). On-chain ownership migration for **C** is a **separate** authorisation (wallet/vault), not required to contain key **A**.

---

## 3. Known vs unknown

| Known | Unknown |
|---|---|
| Plaintext key on disk at v2 `contracts/.env` | Whether keystore decrypts to A, B, C, or other |
| Derived address A; doc address B; owner C | Off-host copies / CI / chat exfiltration |
| A and B Base balances = 0; C funded ~0.006 ETH | Full nonce/history of A beyond balance=0 |
| Not in git blob history for `.env` | Whether B’s private key still exists anywhere |
| Backend/legacy containers do not load deployer key | Whether operators historically broadcast with A |
| Deploy scripts expect forge `--private-key` when used | Future need for a **new** mainnet deployer EOA |

---

## 4. Proposed containment and recovery (NOT EXECUTED)

### 4.1 Principles

1. **Separate local plaintext removal** from any **on-chain** ownership change or fund move.  
2. **No transaction** in R5-APPLY unless separately and explicitly authorised (not requested here).  
3. Zero balance on A/B ⇒ no funding recovery step for those EOAs in the minimum plan.  
4. Do **not** touch vault key **C** under R5 unless operator explicitly expands scope.

### 4.2 Minimum safe R5-APPLY plan (proposed)

| Step | Action | Backup / recovery | Rollback limit |
|---|---|---|---|
| R5-0 | Freeze recheck: digest/controls; key still only at attested path; sha12 still `7e792fd2e48f` | — | Abort if drift |
| R5-1 | Escrow attestation: record path/mode/mtime/sha12/derived address into `0700` backup dir (**no** key value in git-tracked evidence) | `/home/raghu/arbicore_backups/r5_deployer_<TS>/` | Metadata only |
| R5-2 | **Optional password verify** of Foundry keystore → print **address only** to evidence | Operator password | If wrong password, stop |
| R5-3 | Quarantine plaintext: `mv` `contracts/.env` → backup `0700` **or** rewrite file removing only `DEPLOYER_PRIVATE_KEY=` line while retaining RPC/API names as operator chooses | Keep quarantine ≥14 days before shred | Restore via `mv` before shred |
| R5-4 | Reconcile `.deployer_address.txt`: document that B ≠ A ≠ C; update file only with operator-chosen canonical label (likely **B** for Sepolia history or “deprecated”) — **no** silent overwrite to A | Commit of address file is public — address-only OK | Revert git |
| R5-5 | Verify: no `DEPLOYER_PRIVATE_KEY=` in v2/cert contracts trees; backend still without key; controls held | — | — |
| R5-6 | Destroy quarantine | Only after hold + separate destroy auth | Irreversible for that copy |

### 4.3 Explicitly out of minimum R5-APPLY

- Generate/deploy a **replacement** deployer key (unless operator expands auth)  
- Fund any address / transfer ETH from **C**  
- Change FlashLoanReceiver `owner` (immutable EOA model — may be impossible; anyway not for key A)  
- Rewrite git history  
- Delete Foundry keystore without proving address + operator confirmation  
- R6 Alchemy revoke · P2 deploy · strategy activation · Phase B legacy `docker rm`

### 4.4 Approvals required before apply

1. Explicit **R5-APPLY** text naming: quarantine/remove plaintext from `arbicore-x-v2/contracts/.env` only (or listed paths).  
2. Operator decision on keystore: verify-in-apply vs leave encrypted untouched.  
3. Operator decision on `.deployer_address.txt` text update (optional).  
4. Separate auth later for shred and for any on-chain/wallet work involving **C**.

---

## 5. Mutations that require separate R5-APPLY authorisation

Exact mutations **not** performed now:

1. Edit or delete `/home/raghu/projects/arbicore-x-v2/contracts/.env`  
2. Move/quarantine that file into backups  
3. Unlock/modify/delete `/home/raghu/.foundry/keystores/arbicore-base-mainnet-deployer`  
4. Change `.deployer_address.txt` contents  
5. Any `forge script --broadcast`, `cast send`, funding, or ownership tx  
6. Generate a new key / write a new `.env`  
7. `git filter-repo` / history rewrite  
8. Shred of any escrow  

---

## 6. Verification and rollback criteria (for future APPLY)

### 6.1 Verification (PASS)

| ID | Check |
|---|---|
| V1 | `DEPLOYER_PRIVATE_KEY` absent from v2/cert `contracts/.env*` (or file absent) |
| V2 | Backend ENV still has no deployer/private-key vars; digest `69fe2459…`; SHADOW; AUTOEXEC/RUNTIME false |
| V3 | R1 404 · R2 503 · six RPC SET · R4 quarantine intact · legacy exited |
| V4 | Escrow dir `0700` exists with attestation JSON (sha12 + derived address; **no** raw key in git tree) |
| V5 | Address inventory note committed/updated explaining A/B/C split |

### 6.2 Rollback

| Stage | Rollback |
|---|---|
| After quarantine `mv`, before shred | Restore `.env` from escrow via `mv` |
| After line-delete edit with escrow copy | Restore from escrow copy |
| After shred | **Cannot** restore that plaintext copy; rely on keystore (if it matches) or accept loss of A |
| On-chain | N/A for A (no txs authorised); C untouched |

---

## 7. Readiness gates

| Gate | Result |
|---|---|
| Exposure path identified without leaking key material | **PASS** |
| Address inventory reconciled (A/B/C mismatch documented) | **PASS** |
| Active runtime consumption ruled out | **PASS** |
| Controls / R4 / six-network preserved | **PASS** |
| Minimum apply plan + approvals listed | **PASS** |
| Blocking ambiguity requiring more research before *planning* | **None** for local plaintext containment |
| Keystore address binding | **UNKNOWN** — acceptable to proceed with apply that **does not delete keystore** until verified |

**Blocking for APPLY execution:** only missing **explicit R5-APPLY authorisation**.

---

## 8. Verdict

# READY FOR EXPLICIT R5-APPLY AUTHORISATION

Recommended default authorisation text:

> **R5-APPLY Phase 1 only:** quarantine (or redact) plaintext `DEPLOYER_PRIVATE_KEY` from `/home/raghu/projects/arbicore-x-v2/contracts/.env` into a `0700` escrow; verify absence + controls; do **not** shred; do **not** delete Foundry keystore; do **not** generate a replacement key; do **not** send transactions; do **not** modify vault/owner `0x0a43…`; leave R4 quarantine, six-network config, and P2 untouched.

Optional add-on (separate sentence): password-verify keystore address only.

**Stopped — no mutation performed. R5-APPLY not authorised by this preflight.**
