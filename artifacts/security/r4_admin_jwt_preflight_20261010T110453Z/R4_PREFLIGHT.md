# R4-PREFLIGHT — Admin/JWT secret remediation readiness

**Verdict: READY FOR EXPLICIT R4-APPLY AUTHORISATION**  
**Preflight UTC:** `2026-10-10T11:04:53Z`  
**Authorisation:** Read-only only · **R4-APPLY not executed**  
**Artifact dir:** `artifacts/security/r4_admin_jwt_preflight_20261010T110453Z/`

**Inputs:** R3 closeout + R4 proposal under `r3_closeout_r4_plan_20261010T105818Z/` · matrix · reconciliation blocker G  
**Probe:** [`r4_preflight_probe.json`](r4_preflight_probe.json) · [`r4_inventory_reconcile.json`](r4_inventory_reconcile.json)

**Preserved (verified this preflight):** R3 `arbicore_app` · digest `69fe2459…` · healthy · SHADOW · AUTOEXEC=false · RUNTIME=false · no BOOTSTRAP · no private-key ENV · R1 404 · R2 503 · g5.79/Foreman untouched · legacy **exited**

---

## 1. Inventory reconciliation

### 1.1 File copies

| Source | Count | Notes |
|---|---:|---|
| Prior closeout inventory | **17** | Under-counted approved recovery archives (0 backup hits in prior scan) |
| This preflight re-scan | **24** | Prior 17 retained · **+7** approved `/home/raghu/arbicore_backups/…` env copies |
| Removed since prior | **0** | — |

**Classification (current 24):**

| Class | Count | R4-APPLY treatment |
|---|---:|---|
| `live_dotenv` | 1 | **In scope** — rotate |
| `local_upgrade_backup_scrub_candidate` | 8 | Out of apply · Phase C / R4-SCRUB |
| `ephemeral_tmp_scrub_candidate` | 8 | Out of apply · Phase C / R4-SCRUB |
| `approved_recovery_archive` | 7 | **Retain** under DR policy · not deleted by R4-APPLY |

Paths by class: `r4_inventory_reconcile.json` → `by_class_paths`.

**Discrepancy:** Proposal text “17 file copies” matches prior incomplete scan (live + 8 local + 8 `/tmp`). Preflight corrects the inventory to **24** by including 7 approved recovery `.env` backups (R2/R3/S1-B/S2-A). No paths disappeared.

### 1.2 Stopped legacy container Env (4)

| Container | Status | Admin sha12 | JWT sha12 |
|---|---|---|---|
| `arbicore-x-backend-h05` | exited | `6780d7b21193` | `7013ef842946` |
| `arbicore-x-backend-w1` | exited | `6780d7b21193` | `7013ef842946` |
| `arbicore-x-b7-candidate` | exited | `6780d7b21193` | `7013ef842946` |
| `arbicore-x-backend` | exited | `6780d7b21193` | `7013ef842946` |

Matches prior set exactly. **Do not start.** Env scrub/`docker rm` only under separate auth.

### 1.3 Live secret attestation (sha12 only)

| Location | Admin sha12 | JWT sha12 |
|---|---|---|
| Container ENV | `6757aa3396d8` (len 36) | `066b178751e1` (len 64) |
| Live `.env` | same | same |

Username: `admin`. `ARBICORE_JWT_SECRET` alias: **absent** (canonical consumer is `JWT_SECRET`). `ARBICORE_ADMIN_PASSWORD` alias: **absent** (consumer accepts it as fallback; live uses `ARBICORE_ADMIN_PASS`).

Distinct generations across inventory: admin `{6757aa3396d8, 6780d7b21193}` · JWT `{066b178751e1, 7013ef842946}`.

---

## 2. Secret-consumer and session-validation map

### 2.1 Consumers

| Secret | Runtime consumer | Effect |
|---|---|---|
| `JWT_SECRET` | `services/auth.py` → `_secret()` → HS256 sign/verify for access + refresh JWTs | Missing → login cannot issue tokens (boot warns) |
| `ARBICORE_ADMIN_PASS` (or `ARBICORE_ADMIN_PASSWORD`) | `ensure_provisioned_users()` on boot only | **Insert-only** seed if `users` lacks username; **never** overwrites existing `password_hash` |
| `ARBICORE_ADMIN_USER` | Same provisioner (default `admin`) | Username for seed only |
| Mongo `users.password_hash` | `POST /api/auth/login` via `verify_password` | **Authoritative** for interactive login |
| Mongo `users.session_version` | Embedded in JWT as `sv`; checked in `get_user_by_payload` | Mismatch → `401 Session revoked` |

Boot hook: `server.py` calls `ensure_provisioned_users()` at startup.

### 2.2 Session lifecycle

```
login/setup → set_auth_cookies (access 30m + refresh 7d, httpOnly)
           → JWT payload {sub, sv, type, exp} signed with JWT_SECRET

request    → cookie access_token (or Bearer) → decode_token(JWT_SECRET)
           → load user by sub → require payload.sv == user.session_version

change-password (authed) → verify current → bcrypt new hash → session_version++
                         → re-issue cookies for THIS session; others die on sv

logout-all (authed) → session_version++ → clear cookies

JWT_SECRET rotate + recreate → all prior signatures invalid (immediate global logout)
```

Endpoints: `/api/auth/login`, `/me`, `/refresh`, `/logout`, `/logout-all`, `/change-password`, `/setup` (R2: 503 without bootstrap token).

### 2.3 Live Mongo admin doc (read-only)

| Field | Value |
|---|---|
| username / role | `admin` / `admin` |
| id | `eeeeb6d9-…` |
| `session_version` | **2** |
| `password_hash` | present · bcrypt `$2b$` prefix |
| updated_at | `2026-10-07T01:04:47Z` |

---

## 3. Ordered R4-APPLY proposal (not executed)

### 3.1 In scope vs out of scope

| In R4-APPLY | Out (separate auth) |
|---|---|
| Backup live `.env` | Delete/move local `.env.*` / `/tmp` copies (R4-SCRUB) |
| Generate + escrow new admin pass + JWT | Touch approved `arbicore_backups` recovery sets |
| Update live `.env` both secrets (0600) | Start/rm legacy containers |
| One backend recreate `--pull never` + S2-A override | R5/R6/P2/RPC/Mongo user/Factory/g5.79 |
| `change-password` (or equivalent) so Mongo hash matches new pass + `session_version` bump | Compose secrets-mount redesign (optional follow-on) |

### 3.2 Secure generation / delivery

1. `umask 077`; backup dir `/home/raghu/arbicore_backups/r4_admin_jwt_<TS>/` mode `700`.  
2. Copy live `.env` → `backend.env.pre-r4` (`0600`).  
3. Generate into `0600` files only (never host argv / never chat):  
   - JWT: `openssl rand -hex 32` (≥ 64 hex chars)  
   - Admin pass: `openssl rand -base64 24` (or stronger)  
4. Attest **sha12 + len only** in evidence.  
5. Write `.env` via script that does not print values; `chmod 600`.

### 3.3 Recommended apply order (single recreate)

1. **Pre-checks** — digest, R3 user, controls, login works with current password (record `session_version`).  
2. **Backup + generate** — §3.2.  
3. **Patch live `.env`** — set new `ARBICORE_ADMIN_PASS` + new `JWT_SECRET` only (no other keys).  
4. **Recreate** —  
   `docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml up -d --no-deps --force-recreate --pull never backend`  
   Expect: old cookies dead (JWT signature); login still accepts **old** password (hash unchanged); ENV admin pass is new (seed-only until users wiped).  
5. **Coordinate hash** — `POST /api/auth/login` with **old** password → `POST /api/auth/change-password` `{current_password: old, new_password: new}` → hash + `session_version` (++ from 2).  
6. **Verify** — §6 checklist.  
7. **Escrow** — retain new secrets `0600` in backup dir; do not shred until operator confirms.

**Why this order:** One recreate; avoids needing a live session across JWT cutover; matches insert-only provisioner behaviour.

### 3.4 Rollback

```bash
cp -a "$BK/backend.env.pre-r4" …/upgrade/backend/.env && chmod 600 …
# recreate backend (same compose flags, --pull never)
# If change-password already applied: either change-password new→old while on rolled-back JWT,
# or restore password_hash + session_version from pre-apply Mongo export (take users doc backup in apply).
```

**Mandatory add to apply:** before step 5, export redacted users doc metadata + allow hash restore via one-shot using known old password verify path — simplest rollback if step 5 done: login with new pass on restored ENV is wrong; prefer **users collection backup** (`mongodump --collection=users` authenticated as `arbicore_app` or root INITDB) into `$BK` during apply backup phase.

### 3.5 Impact / maintenance window

| Item | Expectation |
|---|---|
| API downtime | ~1–3 min recreate blip |
| Operator sessions | **All** invalidated at JWT recreate; must re-login |
| After change-password | Any session minted between recreate and password change (old-pass logins) revoked by `sv` bump except the change-password response cookies |
| End users | Single-admin system — operator reauth only |
| Additional approvals | **Explicit R4-APPLY** required; optional **R4-SCRUB** later for historical copies |

---

## 4. Verification checklist (future R4-APPLY)

| ID | Check | Pass |
|---|---|---|
| V1 | Digest still `69fe2459…` · healthy | |
| V2 | Live ENV + `.env` admin/JWT sha12 **≠** `6757aa3396d8` / `066b178751e1` | |
| V3 | Login **new** password → 200 · `/api/auth/me` 200 | |
| V4 | Login **old** password → 401 | |
| V5 | Pre-rotation cookie / refresh → 401 | |
| V6 | `session_version` > preflight baseline (**2**) | |
| V7 | R1 docs 404 · R2 setup 503 · `/api/` 200 | |
| V8 | SHADOW · AUTOEXEC=false · RUNTIME=false · no BOOTSTRAP | |
| V9 | Mongo user still `arbicore_app` · Factory/g5.79/Foreman unchanged | |
| V10 | No secrets in reports (sha12/len only) | |

Evidence dir for apply: `artifacts/security/r4_admin_jwt_apply_<TS>/`.

---

## 5. Readiness gates (this preflight)

| Gate | Result |
|---|---|
| Inventory reconciled (17→24 explained) | **PASS** |
| Consumers + session map documented | **PASS** |
| Live sha12 match proposal baselines | **PASS** |
| Admin Mongo doc + `session_version=2` + bcrypt hash | **PASS** |
| Compose + override + `.env` 0600 present | **PASS** |
| `change-password` / JWT code path confirmed | **PASS** |
| R3 + safety controls held | **PASS** |
| Historical cleanup separated | **PASS** (not in apply) |
| Secret generation / rotation | **Not done** (correct) |

**Blocking failures:** none.

---

## 6. Verdict

# READY FOR EXPLICIT R4-APPLY AUTHORISATION

R4-APPLY remains **unexecuted**. Historical scrub and legacy Env disposal require **separate** authorisation. Overall security gate / P2 stays **BLOCKED** until R4–R6 close.

**Stopped — awaiting R4-APPLY (or R4-SCRUB) authorisation.**
