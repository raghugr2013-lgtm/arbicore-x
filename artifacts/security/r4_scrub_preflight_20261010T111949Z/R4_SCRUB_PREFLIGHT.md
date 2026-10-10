# R4-SCRUB PREFLIGHT — Historical admin/JWT copy cleanup readiness

**Verdict: READY FOR EXPLICIT R4-SCRUB AUTHORISATION**  
**Preflight UTC:** `2026-10-10T11:19:49Z`  
**Authorisation:** Read-only only · **R4-SCRUB not executed**  
**Artifact dir:** `artifacts/security/r4_scrub_preflight_20261010T111949Z/`

**Inputs:** R4-APPLY [`../r4_admin_jwt_apply_20261010T110918Z/R4_APPLY_EXECUTION_REPORT.md`](../r4_admin_jwt_apply_20261010T110918Z/R4_APPLY_EXECUTION_REPORT.md) · prior inventory [`../r4_admin_jwt_preflight_20261010T110453Z/`](../r4_admin_jwt_preflight_20261010T110453Z/)  
**Probe:** [`r4_scrub_preflight_probe.json`](r4_scrub_preflight_probe.json) · [`r4_scrub_inventory_reconcile.json`](r4_scrub_inventory_reconcile.json)

**R4 live rotation verdict (unchanged):** **PASS WITH LIMITATIONS**

**Preserved (verified this preflight):** digest `69fe2459…` · healthy · SHADOW · AUTOEXEC=false · RUNTIME=false · no BOOTSTRAP · no private-key ENV · Mongo `arbicore_app` · R1 public `/docs` **404** · R2 setup **503** · `/api/` **200** · Alchemy fps `ca6545ba` · legacy **exited** · g5.79/Foreman status-only (untouched)

---

## 1. Live active configuration (must not scrub)

| Location | Admin sha12 | JWT sha12 | Class |
|---|---|---|---|
| Live `.env` `…/upgrade/backend/.env` (`0600`) | `112c88ac69e1` | `f98650d468b2` | **active_live_dotenv** |
| Container `arbicore-x-backend-new` ENV | same | same | **active_runtime** |

| Check | Result |
|---|---|
| Live uses **new** credentials | **PASS** |
| Old admin/JWT sha12 in live `.env` or running ENV | **ABSENT** |
| `.env` ↔ container sha12 match | **PASS** |

No old secret remains in active runtime configuration.

---

## 2. Inventory reconciliation

### 2.1 Prior apply inventory (24 file paths)

| Metric | Value |
|---|---:|
| Prior paths still present | **24 / 24** |
| Prior paths removed | **0** |

### 2.2 Rescan expansion (this preflight)

| Class (scrub taxonomy) | Count | vs prior |
|---|---:|---|
| `active_live_dotenv` | 1 | same (rotated) |
| `redundant_local_upgrade_backup` | 8 | same 8 |
| `redundant_temporary` (admin/JWT carriers) | **9** | prior 8 + **+1** `/tmp/arbicore-production-env.backup` |
| `redundant_temporary` (no admin/JWT keys) | **9** | **new** discovery (RPC/cutover leftovers; out of core admin/JWT scrub) |
| `approved_recovery_archive` | **12** | prior 7 + R4 escrow (4) + S2-A replacements file (1, no admin/JWT) |
| Stopped legacy container Env | **4** | same set |

**Discrepancy vs apply report “24 + R4 dir”:** explained by broader `/tmp` + `arbicore_backups` rescan. No prior path disappeared. Core old-admin/JWT carriers for scrub = **17 files** (+ 4 legacy Env separately).

### 2.3 Secret generations still on host (sha12)

| Kind | sha12 set |
|---|---|
| Admin | `112c88ac69e1` (**live/new**), `6757aa3396d8` (**pre-R4** in recovery), `6780d7b21193` (**legacy/tmp/local**) |
| JWT | `f98650d468b2` (**live/new**), `066b178751e1` (**pre-R4** in recovery), `7013ef842946` (**legacy/tmp/local**) |

---

## 3. Classification

### 3.1 Active — retain / do not modify

- Live `.env` and running backend ENV (new sha12s only).

### 3.2 Approved recovery — **RETAIN** (not R4-SCRUB delete targets)

Parent `/home/raghu/arbicore_backups` mode `0775`; per-remediation dirs typically `0700`; secret files `0600`.

| Path | Admin | JWT | Retention |
|---|---|---|---|
| `…/r2_bootstrap_disable_…/backend.env.pre-disable` | `6757aa…` | `066b17…` | Retain — R2 DR |
| `…/r3_mongo_leastpriv_*/backend.env.pre-r3` (×3) | `6757aa…` | `066b17…` | Retain — R3 DR |
| `…/s1b_phase2_rotation_…/backend.env.pre-rotation` | `6757aa…` | `066b17…` | Retain — S1-B DR |
| `…/s1b_phase2_rotation_…/root.env.pre-rotation` | `6757aa…` | `066b17…` | Retain — S1-B DR |
| `…/s2a_alchemy_cutover_…/backend.env.pre-cutover` | `6757aa…` | `066b17…` | Retain — S2-A DR |
| `…/s2a_alchemy_cutover_…/s2a_alchemy_replacements.env.used` | — | — | Retain — S2-A (no admin/JWT) |
| `…/r4_admin_jwt_20261010T110918Z/backend.env.pre-r4` | `6757aa…` | `066b17…` | Retain — R4 rollback |
| `…/r4_admin_jwt_…/admin.password.pre-r4` | `6757aa…` | — | Retain — R4 rollback |
| `…/r4_admin_jwt_…/admin.password.new` | `112c88…` | — | Retain — current escrow |
| `…/r4_admin_jwt_…/jwt.secret.new` | — | `f98650…` | Retain — current escrow |

**Access / retention requirements:** dirs `0700`, files `0600`, owner operator only; retain until operator confirms R4 rollback window closed **and** a dated DR policy allows destroy of pre-rotation material (separate auth from Phase A file scrub). **Do not** delete R4 escrow while it is the sole offline copy of the **current** admin/JWT.

### 3.3 Redundant temporary — scrub candidates (old admin/JWT)

Nine `/tmp` files with admin `6780d7b21193` / JWT `7013ef842946` (list in inventory `scrub_candidates`).

Nine additional `/tmp/arbicore*.env*` with **no** admin/JWT keys — **optional adjacent** cleanup only (may hold other displaced material); not required to clear R4 admin/JWT residual.

### 3.4 Redundant local upgrade backups — scrub candidates

All eight `…/upgrade/backend/.env.*` backups: admin `6780d7b21193` / JWT `7013ef842946`.

### 3.5 Stopped-legacy configuration — separate category

| Container | Status | Admin sha12 | JWT sha12 |
|---|---|---|---|
| `arbicore-x-backend-h05` | exited | `6780d7b21193` | `7013ef842946` |
| `arbicore-x-backend-w1` | exited | `6780d7b21193` | `7013ef842946` |
| `arbicore-x-b7-candidate` | exited | `6780d7b21193` | `7013ef842946` |
| `arbicore-x-backend` | exited | `6780d7b21193` | `7013ef842946` |

**Do not start. Do not alter Config.** Disposal = `docker rm` (or equivalent) under explicit Phase B auth only.

---

## 4. Proposed R4-SCRUB plan (not executed)

### 4.1 In scope vs out of scope

| In R4-SCRUB (proposed) | Out |
|---|---|
| Quarantine then delete **17** old-admin/JWT file carriers (8 local + 9 `/tmp`) | Live `.env` / running ENV |
| Optional: 9 `/tmp` env files without admin/JWT | Approved recovery archives (12) |
| Phase B (separate confirm): `docker rm` 4 exited legacy backends | R5/R6/P2/RPC/Mongo/Factory/g5.79/Foreman |
| | Destroy R4/current secret escrow |

### 4.2 Minimal reversible procedure

1. **Freeze check** — re-attest live sha12s still `112c88ac69e1` / `f98650d468b2`; digest/controls held; legacy still exited.  
2. **Quarantine (reversible)** — `umask 077`; mkdir `/home/raghu/arbicore_backups/r4_scrub_quarantine_<TS>/` mode `0700`; `mv` (not copy) each of the 17 targets into class subdirs; record path map + sha12 attestations; **do not** print values.  
3. **Verify absence** — original 17 paths gone; live unchanged; no process restart required.  
4. **Hold** — quarantine retained ≥ **14 days** (or operator-set window) for undelete via `mv` back.  
5. **Destroy quarantine** — only after hold expiry + explicit confirm; `shred -u` or equivalent; then remove empty dir.  
6. **Phase B (optional, separate confirm)** — after quarantine holds the `6780d7…` / `7013ef…` generation: `docker rm` the four exited containers; verify `docker inspect` missing; **do not** start substitutes.

### 4.3 Exact Phase A targets (17)

**Local (8):**  
`.env.pre-m25-usd-numeraire-20260912T121226Z`, `.env.g5.27-backup-20260927-101642`, `.env.pre-paper-20260916T112833Z`, `.env.backup.20261002-081704`, `.env.g5.62-backup-20260927-105923`, `.env.bak-20260916-133913`, `.env.pre-executor-owner-refresh-20260912T100117Z`, `.env.pre-t2-wss-20260911T160217Z`  
under `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/`.

**Tmp (9):**  
`/tmp/arbicore_ctr_all.env`, `arbicore-runtime-cert-ad64a50.env`, `arbicore-x-backend.env`, `arbicore-runtime-cert.env`, `arbicore-x-candidate.env`, `arbicore-backend-p0-3.env`, `arbicore-backend.env`, `arbicore-x-runtime.env`, `arbicore-production-env.backup`.

### 4.4 Verification after scrub

| ID | Check |
|---|---|
| S1 | Live admin/JWT sha12 still new; digest/health/controls unchanged |
| S2 | All 17 original paths absent |
| S3 | Approved recovery paths still present + modes `0600`/`0700` |
| S4 | Legacy still exited (or removed if Phase B) — never running |
| S5 | R1 404 · R2 503 · `/api/` 200 |
| S6 | No secrets in scrub evidence (sha12 only) |

### 4.5 Rollback limitations

| Stage | Rollback |
|---|---|
| After quarantine `mv`, before destroy | **Fully reversible** — `mv` files back to original paths |
| After quarantine destroy | **Irreversible** for those file copies; `6780d7…`/`7013ef…` generation lost unless other copies remain |
| After Phase B `docker rm` | **Container Config.Env not restorable** from Docker; same generation only if quarantine/files still exist |
| Approved recovery retained | Restores **pre-R4** generation (`6757aa…`/`066b17…`) + R4 rollback kit — **not** a substitute for current live secrets (use `admin.password.new` / `jwt.secret.new`) |

---

## 5. Readiness gates

| Gate | Result |
|---|---|
| R4-APPLY live rotation still PASS; active uses new secrets | **PASS** |
| Inventory reconciled; no prior path missing | **PASS** |
| Scrub targets enumerated (17 + optional 9 + Phase B ×4) | **PASS** |
| Approved recovery classified + permissions documented | **PASS** |
| Legacy separated; not started | **PASS** |
| Controls / digest / R1–R3 held | **PASS** |
| Mutation / deletion | **Not done** (correct) |

**Blocking failures:** none.

---

## 6. Verdict

# READY FOR EXPLICIT R4-SCRUB AUTHORISATION

Recommended default authorisation text: **R4-SCRUB Phase A only** (quarantine→verify→hold the 17 old-admin/JWT file carriers). Phase B legacy `docker rm` and optional non-admin/JWT `/tmp` cleanup require explicit add-on language.

R4 live verdict remains **PASS WITH LIMITATIONS** until historical residual is scrubbed or risk-accepted. Overall security gate / P2 stays **BLOCKED**. R5, R6, and P2 are **not** authorised by this preflight.

**Stopped — awaiting R4-SCRUB authorisation. No mutation performed.**
