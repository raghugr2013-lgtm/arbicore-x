# ArbiCore X — Security Remediation Matrix (durable)

**Overall security gate / P2: BLOCKED**  
**Updated UTC:** `2026-10-10T13:05:00Z`  
**Sources:** [`SECURITY_GATE_RECONCILIATION.md`](SECURITY_GATE_RECONCILIATION.md); R1 [`r1_edge_docs_deny_20261010T085028Z/`](r1_edge_docs_deny_20261010T085028Z/); R2 [`r2_bootstrap_disable_20261010T090646Z/`](r2_bootstrap_disable_20261010T090646Z/); R3 apply [`r3_mongo_leastpriv_apply_20261010T105128Z/`](r3_mongo_leastpriv_apply_20261010T105128Z/); R3 closeout + R4 plan [`r3_closeout_r4_plan_20261010T105818Z/`](r3_closeout_r4_plan_20261010T105818Z/); R4 preflight [`r4_admin_jwt_preflight_20261010T110453Z/`](r4_admin_jwt_preflight_20261010T110453Z/); R4 apply [`r4_admin_jwt_apply_20261010T110918Z/`](r4_admin_jwt_apply_20261010T110918Z/); R4-SCRUB preflight [`r4_scrub_preflight_20261010T111949Z/`](r4_scrub_preflight_20261010T111949Z/); R4-SCRUB Phase A [`r4_scrub_phase_a_20261010T122730Z/`](r4_scrub_phase_a_20261010T122730Z/); R5 preflight [`r5_preflight_base_audit_20261010T125526Z/`](r5_preflight_base_audit_20261010T125526Z/); R5 apply [`r5_deployer_containment_apply_20261010T130403Z/`](r5_deployer_containment_apply_20261010T130403Z/); coordinator board [`../CRITICAL_PATH_BOARD_BASE_FULL_LIVE_20261010.md`](../CRITICAL_PATH_BOARD_BASE_FULL_LIVE_20261010.md)

**Preserved:** S2-A **PASS WITH LIMITATIONS** · 429 **ACCEPTABLE WITH EXPLANATION** · RPC fallbacks unchanged · SHADOW · AUTOEXEC/RUNTIME false · signing/broadcast off · legacy stopped · g5.79 out of scope · MEV replay separate · six-network RPC env still SET (live recheck)

---

## Status board

| ID | Item | Live verdict | Evidence |
|---|---|---|---|
| R1 | Public `/docs` `/redoc` `/openapi.json` edge deny | **PASS** | `r1_edge_docs_deny_20261010T085028Z/` · public probes 404 · `/api/` 200 |
| R2 | Bootstrap token disable (unset → 503) | **PASS** | `r2_bootstrap_disable_20261010T090646Z/` · token absent · setup **503** · digest unchanged |
| R3 | MongoDB least privilege (non-root) | **PASS WITH LIMITATIONS** (closed) | Apply [`r3_mongo_leastpriv_apply_20261010T105128Z/`](r3_mongo_leastpriv_apply_20261010T105128Z/) · closeout [`r3_closeout_r4_plan_20261010T105818Z/R3_CLOSEOUT_AUDIT.md`](r3_closeout_r4_plan_20261010T105818Z/R3_CLOSEOUT_AUDIT.md) · Factory still root · note/log-gap residual |
| R4 | Admin/JWT plaintext hygiene | **PASS WITH LIMITATIONS** | Apply + Phase A quarantine [`r4_scrub_phase_a_20261010T122730Z/R4_SCRUB_PHASE_A_EXECUTION_REPORT.md`](r4_scrub_phase_a_20261010T122730Z/R4_SCRUB_PHASE_A_EXECUTION_REPORT.md) · live `112c88ac69e1` / `f98650d468b2` · 17 carriers quarantined (hold → `2026-10-24T12:29:00Z`) · destroy + Phase B legacy Env **pending** |
| R5 | Deployer private key on-disk containment | **PASS WITH LIMITATIONS** | Apply [`r5_deployer_containment_apply_20261010T130403Z/R5_APPLY_EXECUTION_REPORT.md`](r5_deployer_containment_apply_20261010T130403Z/R5_APPLY_EXECUTION_REPORT.md) · plaintext removed from live `.env` · escrow retained · address inventory mismatch **open** · no on-chain |
| R6 | Alchemy displaced-key provider revoke | **BLOCKED** | Not started · displaced fps `24dab5d1` / `5e5d5bb1` · provider revoke **UNKNOWN** · needs separate revoke auth · do not revoke fallbacks/g5.79 |
| S2-A | Alchemy redaction + primary cutover | **PASS WITH LIMITATIONS** | `s2a_alchemy_containment_20261009/` |
| S1-B | Vault rotation | **PASS WITH LIMITATIONS** | `s1b_vault_rotation_preflight_20261009/` |

---

## R1 — evidence and closure

| Field | Content |
|---|---|
| **Verdict** | **PASS** |
| **Fix** | Caddy deny `/docs*`, `/redoc*`, `/openapi.json` on sslip.io, arbicorex.in, api.arbicorex.in |
| **Limitation** | Localhost `:8001/docs` still open |

---

## R2 — evidence and closure

| Field | Content |
|---|---|
| **Verdict** | **PASS** |
| **Fix** | Removed `ARBICORE_BOOTSTRAP_TOKEN` from live `.env`; recreated backend on digest `69fe2459…` |
| **Backup** | `/home/raghu/arbicore_backups/r2_bootstrap_disable_20261010T090646Z/backend.env.pre-disable` (0600) |
| **Acceptance** | Setup **503**; admin login **200**; R1 held; S2-A primary `ca6545ba`; controls preserved |
| **Limitation** | Historical `/tmp` and backup copies of old token **not** scrubbed — see `HISTORICAL_COPY_CLEANUP_PROPOSAL.md` |

---

## R3 — evidence and closure

| Field | Content |
|---|---|
| **Verdict** | **PASS WITH LIMITATIONS** |
| **Fix** | Created `arbicore_app` with `readWrite` on `arbicore_x` only; switched ArbiCore `MONGO_URL`; recreated `arbicore-x-backend-new` on digest `69fe2459…` |
| **Backup** | Validation + apply dumps under `/home/raghu/arbicore_backups/r3_*`; `.env` pre-r3 escrow `0600` |
| **Acceptance** | Health **healthy**; API **200**; login + `/api/auth/me` **200**; CRUD/index ops OK; Factory DB denied; R1/R2 held; controls preserved; discovery 3.9M persisted |
| **Limitations** | Factory still root (out of scope); BASE public RPC pre-existing; ransom-note / pre-2026-09-07 log gap residual; empty `r3_apply_probe` collection may remain |
| **Report** | [`r3_mongo_leastpriv_apply_20261010T105128Z/R3_APPLY_EXECUTION_REPORT.md`](r3_mongo_leastpriv_apply_20261010T105128Z/R3_APPLY_EXECUTION_REPORT.md) |
| **Closeout** | [`r3_closeout_r4_plan_20261010T105818Z/R3_CLOSEOUT_AUDIT.md`](r3_closeout_r4_plan_20261010T105818Z/R3_CLOSEOUT_AUDIT.md) — live re-check confirms cutover; **closed** PASS WITH LIMITATIONS |

---

## R4 — evidence and closure

| Field | Content |
|---|---|
| **Verdict** | **PASS WITH LIMITATIONS** |
| **Fix** | Rotated live `JWT_SECRET` + `ARBICORE_ADMIN_PASS`; recreated backend on digest `69fe2459…`; coordinated Mongo hash via `POST /api/auth/change-password` |
| **Backup** | `/home/raghu/arbicore_backups/r4_admin_jwt_20261010T110918Z/` (`0700`) · `.env` / passwords / users dump escrow `0600` |
| **Acceptance** | V1–V10 **PASS** · new login + `/me` **200** · old password **401** · pre-cookie **401** · `session_version` 2→3 · R1/R2 held · controls preserved |
| **Limitation** | Phase A quarantine **done** (17 files · no shred). Residual: quarantine destroy after hold; **4** stopped legacy Env (Phase B); **12** approved recovery **retained** (incl. pre-R4 plaintext under DR) |
| **Report** | Apply [`r4_admin_jwt_apply_20261010T110918Z/R4_APPLY_EXECUTION_REPORT.md`](r4_admin_jwt_apply_20261010T110918Z/R4_APPLY_EXECUTION_REPORT.md) · Phase A [`r4_scrub_phase_a_20261010T122730Z/R4_SCRUB_PHASE_A_EXECUTION_REPORT.md`](r4_scrub_phase_a_20261010T122730Z/R4_SCRUB_PHASE_A_EXECUTION_REPORT.md) |
| **Apply preflight** | [`r4_admin_jwt_preflight_20261010T110453Z/R4_PREFLIGHT.md`](r4_admin_jwt_preflight_20261010T110453Z/R4_PREFLIGHT.md) |
| **Scrub preflight** | [`r4_scrub_preflight_20261010T111949Z/R4_SCRUB_PREFLIGHT.md`](r4_scrub_preflight_20261010T111949Z/R4_SCRUB_PREFLIGHT.md) |
| **Quarantine** | `/home/raghu/arbicore_backups/r4_scrub_quarantine_20261010T122730Z/` (`0700`) · hold until `2026-10-24T12:29:00Z` · restore: [`restore_from_quarantine.sh`](r4_scrub_phase_a_20261010T122730Z/restore_from_quarantine.sh) |

---

## R5 — evidence and closure

| Field | Content |
|---|---|
| **Verdict** | **PASS WITH LIMITATIONS** |
| **Fix** | Removed plaintext `DEPLOYER_PRIVATE_KEY` from live `arbicore-x-v2/contracts/.env`; retained `BASE_RPC_URL` / `BASESCAN_API_KEY`; Foundry keystore untouched |
| **Backup** | `/home/raghu/arbicore_backups/r5_deployer_containment_20261010T130403Z/contracts.env.pre-r5` (`0600`) · dir `0700` |
| **Acceptance** | Live key **absent** · `.env` `0600` · escrow integrity match · digest/controls/R1/R2 held · address file unchanged · no on-chain |
| **Limitations** | Address inventory mismatch open (`0x65af…` file ≠ `0x3b37…` former key ≠ `0x0a43…` owner); escrow still holds plaintext; keystore↔address binding unverified |
| **Report** | [`r5_deployer_containment_apply_20261010T130403Z/R5_APPLY_EXECUTION_REPORT.md`](r5_deployer_containment_apply_20261010T130403Z/R5_APPLY_EXECUTION_REPORT.md) |
| **Preflight** | [`r5_preflight_base_audit_20261010T125526Z/R5_PREFLIGHT_AND_BASE_CRITICAL_PATH_AUDIT.md`](r5_preflight_base_audit_20261010T125526Z/R5_PREFLIGHT_AND_BASE_CRITICAL_PATH_AUDIT.md) |

## R6 — status (reconcile only; not executed)

| Field | Content |
|---|---|
| **Verdict** | **BLOCKED** · provider revoke **UNKNOWN** |
| **App displacement** | PASS WITH LIMITATIONS — live primary fp **`ca6545ba`** (S2-A) |
| **Revoke candidates** | Old primary `24dab5d1` · ENV `5e5d5bb1` only (`S2A_ALCHEMY_ROTATION_EXECUTION_REPORT.md`) |
| **Do not revoke** | Fallbacks `[1..5]` · g5.79 `a7961b2b` without explicit scope |
| **Action** | Separate explicit revoke authorisation required; no dashboard proof of revoke in evidence tree |

---

## Remaining blockers

R6 revoke (or dated risk acceptance) still required for overall gate. R5 residual: address-inventory correction (separate auth after identity decision); escrow retention. R4 residual: quarantine **destroy** after `2026-10-24T12:29:00Z` and/or **Phase B**. Overall gate / P2 stays **BLOCKED**.

**Single safest next action:** explicit **R6** Alchemy displaced-key revoke auth — **or** dated risk acceptance — **not** P2. Address-file correction only after verified intended deploy identity.

---

## Independent gate acceptance (before P2 may be reconsidered)

Still requires R6 revoke **or** dated risk acceptance, plus disposition of R5 address-inventory residual / escrow policy, plus preserved S2-A/controls — per reconciliation acceptance criteria. R1–R5 (file containment) alone are **necessary but not sufficient**.
