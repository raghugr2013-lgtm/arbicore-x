# R4-APPLY — Admin/JWT secret rotation (execution report)

**Verdict: PASS**  
**Authorisation:** R4-APPLY only  
**Final evidence dir:** `artifacts/security/r4_admin_jwt_apply_20261010T110918Z/`  
**Backup/escrow:** `/home/raghu/arbicore_backups/r4_admin_jwt_20261010T110918Z/` (`0700`)  
**Overall security gate / P2:** **BLOCKED** (unchanged — R5/R6 open; historical scrub separate)

---

## Precondition gate (mandatory)

| Condition | Result |
|---|---|
| JWT rotate + recreate invalidates old cookies; fresh login still uses Mongo `password_hash` | **VERIFIED** (`services/auth.py`, `routes/auth.py`) |
| `ARBICORE_ADMIN_PASS` boot seed only; does not overwrite existing hash | **VERIFIED** (`ensure_provisioned_users` insert-only) + post-recreate hash sha12 unchanged |
| `POST /api/auth/change-password` updates intended admin `password_hash` | **VERIFIED** (by user `id`; hash sha12 changed; `session_version` 2→3) |
| Safe recovery path | **VERIFIED** — `rollback.sh` + `backend.env.pre-r4` + users dump/doc escrow |
| Live ENV password authenticates pre-apply | **VERIFIED** — login **200** · `/me` **200** |

See [`PRECONDITION_CHECK.md`](PRECONDITION_CHECK.md).

---

## Timeline (UTC)

| Time | Stage | Result |
|---|---|---|
| `11:12:15Z`–`11:12:16Z` | Pre-checks (digest, controls, login, baseline sha12) | **PASS** |
| `11:12:20Z` | Backup `.env` + users dump/doc + generate secrets | **PASS** |
| `11:12:20Z` | Patch live `.env` (`ARBICORE_ADMIN_PASS`, `JWT_SECRET` only) | **PASS** |
| `11:12:20Z`–`11:12:52Z` | Recreate backend `--pull never` + S2-A override | **PASS** · healthy · digest unchanged |
| `11:12:52Z`–`11:12:57Z` | Login old pass → `change-password` → login new pass | **PASS** |
| `11:12:59Z` | V1–V10 verification | **PASS** |

---

## Actions performed (exact scope)

1. Backed up live `…/upgrade/backend/.env` → `backend.env.pre-r4` (`0600`); recorded mode `0600`.  
2. Escrowed pre-r4 admin password + admin users doc; `mongodump` of `users` collection (`0600`).  
3. Generated replacement JWT (`openssl rand -hex 32`) and admin password (`openssl rand -base64 24`) into `0600` escrow files only (never printed / never host argv).  
4. Updated **only** `ARBICORE_ADMIN_PASS` and `JWT_SECRET` in the live `.env` (`0600`).  
5. Recreated **only** compose service `backend` → `arbicore-x-backend-new` with `--no-deps --force-recreate --pull never` and `/tmp/arbicore-s2a-rpc-redact-override.yml`.  
6. Authenticated with the **existing** (pre-r4) password; `POST /api/auth/change-password` to the replacement password.  
7. Verified V1–V10; wrote attestations (sha12/len only).

**Did not:** R4-SCRUB / delete historical copies; modify R3/Factory/Mongo roles/RPC/R5/R6/P2/strategy; start legacy containers; touch g5.79 or Foreman.

---

## Before / after (sha12 + len only)

| Item | Before | After |
|---|---|---|
| Backend digest | `sha256:69fe2459…e7315313` | **unchanged** |
| Health | healthy | **healthy** |
| `ARBICORE_ADMIN_PASS` | sha12 `6757aa3396d8` · len 36 | sha12 `112c88ac69e1` · len 32 |
| `JWT_SECRET` | sha12 `066b178751e1` · len 64 | sha12 `f98650d468b2` · len 64 |
| Mongo `password_hash` sha12 | `11f3311f9cb0` | `e8f87bd9285b` |
| `session_version` | **2** | **3** |
| Mongo app user | `arbicore_app` | **`arbicore_app`** |
| Execution controls | SHADOW · AUTOEXEC/RUNTIME false | **unchanged** |

Live `.env` and container ENV sha12s match after recreate.

---

## Verification (executed)

| ID | Check | Result |
|---|---|---|
| V1 | Digest `69fe2459…` · healthy | **PASS** |
| V2 | Live admin/JWT sha12 ≠ preflight baselines | **PASS** (`112c88ac69e1` / `f98650d468b2`) |
| V3 | Login new password → 200 · `/api/auth/me` 200 | **PASS** |
| V4 | Login old password → 401 | **PASS** |
| V5 | Pre-rotation cookie → `/me` 401 | **PASS** |
| V6 | `session_version` > 2 | **PASS** (**3**) |
| V7 | Public `/docs` 404 · setup 503 · `/api/` 200 | **PASS** |
| V8 | SHADOW · AUTOEXEC=false · RUNTIME=false · no BOOTSTRAP · no private-key ENV | **PASS** |
| V9 | Mongo user `arbicore_app` · legacy exited · g5.79/Foreman untouched | **PASS** |
| V10 | No secrets in evidence reports (leak scan empty) | **PASS** |

Evidence: [`post_apply_verification.json`](post_apply_verification.json) · [`auth_rotation_probe.json`](auth_rotation_probe.json)

Post-recreate (before change-password): Mongo hash sha12 **unchanged** — confirms seed-only provisioner behaviour ([`post_recreate_probe.json`](post_recreate_probe.json)).

---

## Backup / recovery

| Item | Path / mode |
|---|---|
| Pre-r4 `.env` | `…/r4_admin_jwt_20261010T110918Z/backend.env.pre-r4` · `0600` |
| Pre-r4 admin pass escrow | `…/admin.password.pre-r4` · `0600` |
| New admin/JWT escrow | `…/admin.password.new`, `…/jwt.secret.new` · `0600` |
| Users doc + mongodump | `…/users_admin_doc.pre-r4.json`, `…/mongodump_users/` · `0600` |
| Rollback helper | [`rollback.sh`](rollback.sh) |

**Rollback:** not required. If needed: restore `backend.env.pre-r4` + recreate; if password already changed, restore users hash/sv from escrow then login with pre-r4 password.

---

## Remaining historical copies (not scrubbed)

Preflight inventory **24** paths all still present (R4-SCRUB **not** authorised):

| Class | Count | Notes |
|---|---:|---|
| `live_dotenv` | 1 | Rotated (new sha12s) |
| `local_upgrade_backup_scrub_candidate` | 8 | Still hold prior generations |
| `ephemeral_tmp_scrub_candidate` | 8 | Still hold prior generations |
| `approved_recovery_archive` | 7 | Retained under DR policy |
| **New** R4 recovery set | +1 dir | This apply escrow (includes pre-r4 + new secrets) |

Stopped legacy containers (4) still **exited** with old Env — not started; Env scrub/`docker rm` requires separate auth.

Distinct prior generations remain on disk (`6757aa3396d8` / `6780d7b21193` admin; `066b178751e1` / `7013ef842946` JWT) in historical copies only.

---

## Deviations / rollback

- First orchestrator attempt failed at precheck `/me` (cookie session helper) **before any mutation**; baselines re-confirmed intact; helper fixed; apply re-run succeeded.  
- **Rollback:** not invoked.

---

## Limitations (do not clear overall gate)

- Historical plaintext copies + legacy container Env **not** scrubbed (needs **R4-SCRUB**).  
- R5 (deployer key) and R6 (Alchemy revoke) **not** addressed.  
- P2 / live execution / signing-broadcast enablement **still blocked**.

---

## Safety state (runtime)

- Execution mode: **SHADOW**  
- AUTOEXEC / RUNTIME autostart: **false**  
- Signing/broadcast: not enabled  
- Digest: **`69fe2459…`**  
- R1/R2/R3: held  

**Stopped after R4-APPLY report — awaiting review. No R4-SCRUB, R5, R6, or P2 activation.**
