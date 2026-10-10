# ArbiCore X — Emergent Handoff Manifest (`arbicore-canonical-1`)

**Role:** Verifiable Git + evidence handoff only.  
**Not authorised:** production deploy · credential rotation · RPC changes · on-chain actions · strategy activation · live execution · quarantine destroy · Phase B · P2 deploy.

**Manifest UTC:** `2026-10-10` (local publish session)  
**Target Emergent project:** `arbicore-canonical-1`

---

## 1. Canonical repository identity

| Field | Value |
|---|---|
| **Canonical local path** | `/home/raghu/projects/arbicore-x-cert` (linked worktree of `/home/raghu/projects/arbicore-x-v2`) |
| **Canonical remote** | `git@github.com:raghugr2013-lgtm/arbicore-x.git` (`origin`) |
| **Handoff branch** | `handoff/emergent-arbicore-canonical-1-20261010` |
| **Verified base before handoff commit** | `9244ebdee6a95188d925084e7e10d4a972cda7ad` (`cert/gate7-dynamic-profitability-20261007` tip; quoter 429 cooldown) |
| **Local HEAD (branch tip)** | `a002cd141ad557d6fb68c0c712565dd43bf2b155` |
| **Verified remote SHA** | `a002cd141ad557d6fb68c0c712565dd43bf2b155` (`origin/handoff/emergent-arbicore-canonical-1-20261010`) |
| **Content package commit** | `f1e9b3f3307f3b839a95067f21157040e70b5037` |
| **Upstream before publish** | none on prior `cert/gate7-dynamic-profitability-20261007`; handoff branch tracks `origin/handoff/emergent-arbicore-canonical-1-20261010` |

**Authority note:** Sibling trees (`arbicore-x-v2` main worktree on `emergent/arbitrage-engineering-handoff-20260930`, older `arbicore-x`, validation clones) were inspected and **not** treated as the publish source. This cert worktree holds the Oct 2026 security/cert/strategy artifact set and uncommitted product deltas reviewed for this handoff.

---

## 2. Live runtime posture (do not change)

| Control | Required state |
|---|---|
| Backend digest | `69fe2459…` (`sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` · image `arbicore-x-backend:s2a-rpc-redact-5bd952568aed`) |
| Execution | `SHADOW` |
| `AUTOEXEC` | `false` |
| `RUNTIME` | `false` |
| Signing / broadcast | **disabled** (no deployer key in backend ENV; no `sendRawTransaction` authorisation) |
| Overall security gate / P2 | **BLOCKED** |

---

## 3. Security gate board (current)

| Gate | Verdict | Evidence (in-repo, safe) |
|---|---|---|
| **R1** | **PASS** | `artifacts/security/r1_edge_docs_deny_20261010T085028Z/` |
| **R2** | **PASS** | `artifacts/security/r2_bootstrap_disable_20261010T090646Z/` |
| **R3** | **PASS WITH LIMITATIONS** | `artifacts/security/r3_mongo_leastpriv_apply_20261010T105128Z/` · closeout `r3_closeout_r4_plan_20261010T105818Z/` |
| **R4 live + Phase A** | **PASS** (rotation) / Phase A quarantine **PASS** with hold | Apply `r4_admin_jwt_apply_20261010T110918Z/` · Phase A `r4_scrub_phase_a_20261010T122730Z/` |
| **R4 quarantine hold** | **ACTIVE** until `2026-10-24T12:29:00Z` | No shredding · **no Phase B** · restore script path only (see below) |
| **R5** | **PASS WITH LIMITATIONS** (local containment) | `artifacts/security/r5_deployer_containment_apply_20261010T130403Z/` · preflight `r5_preflight_base_audit_20261010T125526Z/` |
| **R6** | **UNRESOLVED / BLOCKED** (provider revoke UNKNOWN) | S2-A reports under `artifacts/security/s2a_alchemy_containment_20261009/` |
| **Overall / P2** | **BLOCKED** | `artifacts/security/SECURITY_REMEDIATION_MATRIX.md` |

**Durable matrix / reconciliation**

- `artifacts/security/SECURITY_REMEDIATION_MATRIX.md`
- `artifacts/security/SECURITY_GATE_RECONCILIATION.md`
- Root snapshot (earlier Oct 9): `SECURITY_REMEDIATION_STATUS.md` (superseded on R-gates by the matrix)

**Critical-path board**

- `artifacts/CRITICAL_PATH_BOARD_BASE_FULL_LIVE_20261010.md`  
  Note: board §6 still lists R5-APPLY as the next task; **R5-APPLY later completed** — trust the matrix + R5 apply report for R5 status.

### Restricted evidence (paths only — do **not** push / do **not** restore into git)

| Material | Host path (outside git) | Policy |
|---|---|---|
| R4 Phase A quarantine (17 carriers) | `/home/raghu/arbicore_backups/r4_scrub_quarantine_20261010T122730Z/` (`0700`) | Hold until `2026-10-24T12:29:00Z` · no shred · no Phase B |
| R5 deployer escrow (plaintext `.env` copy) | `/home/raghu/arbicore_backups/r5_deployer_containment_20261010T130403Z/` (`0700`) | Do **not** push · do **not** restore plaintext key to live without explicit auth |
| Foundry keystore | `~/.foundry/keystores/arbicore-base-mainnet-deployer` | Untouched · not in repo |
| Other DR / rotation escrows | `/home/raghu/arbicore_backups/r2_*`, `r3_*`, `r4_admin_jwt_*`, vault escrow dirs | Reference by path only |

In-repo restore/rollback scripts reference those host paths and must not be executed in this handoff:

- `artifacts/security/r4_scrub_phase_a_20261010T122730Z/restore_from_quarantine.sh`
- `artifacts/security/r5_deployer_containment_apply_20261010T130403Z/rollback.sh`

### R5 residuals (open)

- **Address-binding uncertainty:** inventory file `0x65af…` ≠ former key-derived `0x3b37…` ≠ on-chain owner/broadcast `0x0a43…`.
- **Off-host exposure uncertainty:** prior plaintext exposure not undone; escrow retains material; keystore↔owner binding unverified on-chain.

---

## 4. Strategy / research board

| Item | Status | Safe path |
|---|---|---|
| Family plan | **DEX-to-DEX first** · **triangular second** · **Morpho offline-replay-only** | Board + Phase 0.5 docs below |
| DEX↔DEX 266-candidate main sample | **MISSING** from inspected tree — **do not invent** | — |
| DEX↔DEX 15-tx hold-out + criteria | **MISSING** — **do not invent** | — |
| Queue wait / latency | p50 discovery→claim **~375 s**; active verify ~1.6 s | `artifacts/performance/p1_readonly_baseline/` |
| P2 latency package | Proposed (durable `claimed_at` + stage timing) · **not deployed** | `artifacts/performance/p2_release/` |
| G1.5 / MEV scout research | Reports + manifests in-repo; large raw jsonl/csv retained on host only | See §4.1 |
| G1.5 offline coverage audit | Present | `artifacts/g15/audit_offline_base_replay_20261009/` |
| G1.6 false-arb guard | Present | `artifacts/g15/g16_false_arbitrage_guard_20261009/` |
| UniV4 inventory | **DO NOT IMPLEMENT** | `artifacts/g15/audit_offline_base_replay_20261009/univ4_inventory/UNIV4_BASE_INVENTORY.md` |
| Phase 0.5 / SHADOW economics | Present | `docs/certification/PHASE_0_5_*`, `REAL_SHADOW_288_*`, `SHADOW_30MIN_*`, `STRATEGIC_ALPHA_AUDIT_BEFORE_LIVE1_20261005.md`, `FIRST_LIVE_PATH_DECISION_MEMO_20261005.md` |

### 4.1 MEV / “Grok MEV” paths

No file titled exactly “Grok MEV report” was found under the inspected tree. Closest safe/in-repo MEV research pointers:

- `artifacts/g15/core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z/REPORT.md`
- `artifacts/g15/core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z/MANIFEST.md`
- Host-only large exports (not committed; reference only):  
  - `/home/raghu/projects/arbicore-x-cert/artifacts/g15/core-20261008T2216Z/G1_5_EXPORT_20261008T2216Z/MEV_SCOUT_BASE_BSC_WINNERS_G1_5.jsonl`  
  - `…/BASE_SEARCHER_CONTRACT_LEDGER_G1_5.jsonl`  
  - `…/out/population_all.csv.gz`

---

## 5. Product deltas included in this handoff commit

Uncommitted work reviewed on base `9244ebd` and staged for this branch (non-exhaustive themes):

- Discovery queue / flash-loan scanner+verifier instrumentation and Hybrid-E backlog drain tests
- Log redaction helper + credential-URL tests
- Opportunity ledger + Ledger Explorer API/UI
- Strategy-intelligence / economics observability (`arbicore/observability/`)
- P2 timing/evidence persistence tests (package under `artifacts/performance/p2_release/` — **not** deployed)
- Certification docs under `docs/certification/` (Oct 2–8 package)
- Security artifact tree under `artifacts/security/` (R1–R5 + S1-B + S2-A evidence, fingerprint/sha12 only)
- Critical-path board + performance baselines

---

## 6. Explicit exclusions from Git publish

| Excluded | Reason |
|---|---|
| Any `.env` / live secrets | gitignored · never staged |
| R4 quarantine file contents | Outside tree under `/home/raghu/arbicore_backups/…` |
| R5 escrow plaintext | Outside tree · must not be restored into repo |
| Foundry keystores / private keys | Outside tree |
| `phase-*.bundle`, `artifacts/workstream-a-*.bundle` | Git bundle archives (not required for Emergent take-over; avoid history noise) |
| G1.5 raw mega-exports (jsonl/csv.gz above) | Host-only size/local evidence; reports/manifests committed |
| `__pycache__` / `.pytest_cache` / `*.log` | Ignored / noise |

---

## 7. Exact next steps and approval boundaries

**Emergent / next operator may (read-only / docs / offline research):**

1. Pull `handoff/emergent-arbicore-canonical-1-20261010` and reconcile this manifest to the matrix + board.
2. Locate or obtain the **established** DEX 266 + 15 hold-out package **without inventing criteria**; run offline when available.
3. Prepare triangular offline replay criteria as the **second** family (independent GO/INVESTIGATE/REJECT).
4. Morpho: offline E1/E2 disposition only; no liquidator build.
5. Review P2 package offline; **do not deploy** while security gate is BLOCKED.

**Requires separate explicit authorisation (do not do in this handoff):**

| Action | Boundary |
|---|---|
| R6 Alchemy displaced-key revoke (or dated risk acceptance) | Separate revoke auth · do not revoke fallbacks/g5.79 without scope |
| R5 address-inventory correction / keystore identity reconcile | After operator chooses authoritative deploy identity |
| R5 escrow destroy | Risk acceptance · not before operator decision |
| R4 quarantine shred | Only after `2026-10-24T12:29:00Z` + destroy auth |
| R4 Phase B (`docker rm` legacy ×4) | Separate auth |
| P2 deploy | After security gate clears (or dated exception) **and** deploy auth |
| Limited Live / Full Live / signing / broadcast / AUTOEXEC / RUNTIME | Frozen until evidence chain green + operator approval |
| Restore R4 quarantine or R5 escrow into live paths | Last-resort auth only (re-exposes secrets) |

**Single safest security next action (unchanged):** explicit **R6** revoke auth **or** dated risk acceptance — **not** P2.

---

## 8. Publish verification (filled at push)

| Field | Value |
|---|---|
| Handoff content commit SHA | `f1e9b3f3307f3b839a95067f21157040e70b5037` |
| Publish-verification commit SHA | `a002cd141ad557d6fb68c0c712565dd43bf2b155` |
| Remote ref | `origin/handoff/emergent-arbicore-canonical-1-20261010` |
| Remote tip SHA (verified equal to local tip) | `a002cd141ad557d6fb68c0c712565dd43bf2b155` |
| Push result | **success** — new branch created; force **not** used; `main` untouched |
| Branch URL | https://github.com/raghugr2013-lgtm/arbicore-x/tree/handoff/emergent-arbicore-canonical-1-20261010 |

---

## 9. Hard freezes for Emergent `arbicore-canonical-1`

- Do **not** enable LIMITED_LIVE / FULL_LIVE / AUTOEXEC / RUNTIME.
- Do **not** provision signing keys into the backend or broadcast.
- Do **not** promote/replace the production image away from digest `69fe2459…` without separate deploy auth.
- Do **not** invent the missing 266/15 Base DEX replay package.
- Do **not** shred R4 quarantine before hold expiry + auth; do **not** run Phase B without auth.
- Do **not** push or re-materialise R5 escrow plaintext into git or into `contracts/.env` without explicit auth.
