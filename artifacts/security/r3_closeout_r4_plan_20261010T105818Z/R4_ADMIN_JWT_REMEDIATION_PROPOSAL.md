# R4 proposal — Admin / JWT plaintext hygiene (PLAN ONLY)

**Status:** Proposal · **not authorised** · **no mutation**  
**UTC:** `2026-10-10T10:59:10Z`  
**Inventory:** [`r4_secret_location_inventory.json`](r4_secret_location_inventory.json)  
**Gate context:** Reconciliation blocker **G** (FAIL) · Matrix R4 **BLOCKED**  
**Depends on:** R3 closed (PASS WITH LIMITATIONS) · R1/R2 held · digest `69fe2459…` preserved

---

## 1. Problem statement

Live ArbiCore still stores **plaintext** `ARBICORE_ADMIN_PASS` and `JWT_SECRET` in:

1. Running container environment (`arbicore-x-backend-new`)  
2. Host file `…/deployment/upgrade/backend/.env` (mode `0600`)

Gate criterion “not long-lived plaintext admin/JWT in ENV/files” is unmet. Username remains `admin`.

**Live attestation (sha12 only):**

| Secret | len | sha12 |
|---|---:|---|
| `ARBICORE_ADMIN_PASS` | 36 | `6757aa3396d8` |
| `JWT_SECRET` | 64 | `066b178751e1` |

---

## 2. Read-only inventory (affected locations)

### 2.1 Live (in scope for R4-APPLY)

| Location | Notes |
|---|---|
| Container ENV on `arbicore-x-backend-new` | Source of runtime auth |
| `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env` | Compose env_file · `0600` · mtime after R3 |

### 2.2 Historical / residual copies (inventory only; scrub = separate auth)

Inventory found **17** readable `.env*` / backup files containing admin and/or JWT material under upgrade backend + `/home/raghu/arbicore_backups/*`, plus **4** stopped legacy containers with Config.Env copies.

**Distinct secret generations observed (sha12):**

| Kind | sha12 values |
|---|---|
| Admin pass | `6757aa3396d8` (live) · `6780d7b21193` (older historical / legacy) |
| JWT | `066b178751e1` (live) · `7013ef842946` (older historical / legacy) |

Many historical files also still contain retired `ARBICORE_BOOTSTRAP_TOKEN` sha12 `d5a682fbe887` (R2 residual; cleanup already proposed under R2 historical-copy plan — do **not** bundle unless R4 auth explicitly includes it).

**Stopped legacy containers (keep stopped):**  
`arbicore-x-backend-h05`, `arbicore-x-backend-w1`, `arbicore-x-b7-candidate`, `arbicore-x-backend` — older admin/JWT sha12s in inspect Env.

**Approved recovery archives:** R2/R3/S1-B/S2-A backups under `/home/raghu/arbicore_backups/` may retain pre-rotation secrets — **retain** under policy; not auto-deleted by R4.

**Out of R4 scope:** deployer key (R5), Alchemy revoke (R6), Factory secrets, g5.79, Foreman, Mongo passwords (R3 done).

Full path list: `r4_secret_location_inventory.json`.

---

## 3. Application behaviour (drives rotation design)

From `services/auth.py` / `routes/auth.py` (code review, not modified):

| Behaviour | Implication for R4 |
|---|---|
| JWT HS256 signed with `os.environ["JWT_SECRET"]` | Changing JWT invalidates **all** outstanding access/refresh cookies immediately |
| Tokens carry `sv` = Mongo `users.session_version` | Password change via API increments `session_version` and rejects old `sv` |
| `ensure_provisioned_users()` on boot | Seeds admin **only if user missing**; **does not** overwrite existing `password_hash` when ENV pass changes |
| Login verifies against Mongo `password_hash` | Rotating **only** `ARBICORE_ADMIN_PASS` in ENV **without** updating Mongo hash leaves login on old password; ENV becomes break-glass seed for empty-users wipe only |
| HttpOnly cookies `access_token` / `refresh_token` | Operators must re-login after JWT and/or `session_version` change |

Therefore R4 must treat **admin password** and **JWT secret** as two coordinated steps with explicit session invalidation.

---

## 4. Recommended remediation strategy (smallest safe)

### Phase A — Preflight (separate auth: R4-PREFLIGHT)

1. Freeze scope: live `.env` + backend recreate only; historical scrub optional Phase C.  
2. Confirm R3 still held (mongo user `arbicore_app`, digest, controls).  
3. Confirm admin login works; record current `session_version` (no secret print).  
4. Confirm compose recreate path (`docker-compose.prod.yml` + S2-A override `--pull never`).  
5. Produce exact command checklist + rollback; **stop**.

### Phase B — Apply (separate auth: R4-APPLY)

**B1 — Backup / escrow**

- Copy live `.env` → `/home/raghu/arbicore_backups/r4_admin_jwt_<TS>/backend.env.pre-r4` mode `0600`.  
- Generate new secrets offline into `0600` files (never echo / never argv):  
  - `JWT_SECRET` ≥ 64 random bytes (hex/base64)  
  - `ARBICORE_ADMIN_PASS` strong random (≥ 24 chars)  
- Escrow new secrets in same backup dir (`0600`); attest **sha12 only** in reports.

**B2 — Secret delivery (prefer file-backed; avoid improvising)**

Smallest options (pick one in preflight; do not invent a third mid-apply):

| Option | Method | Pros | Cons |
|---|---|---|---|
| **B2-a (recommended first cut)** | Write new values into live `.env` via script (no print); recreate backend so ENV refreshes | Matches current deploy pattern; same as R2/R3 | Still plaintext on disk (improved entropy / unknown-to-attackers copies); historical copies remain until Phase C |
| **B2-b (stronger)** | Docker Compose `secrets:` or bind-mount `0600` files; remove plaintext from `.env` if app supports file/env dual read | Better hygiene | May need image/compose change → **out of first R4** unless preflight proves zero code change |

**Default proposal for first R4-APPLY: B2-a** (rotate in place + recreate), with explicit residual that disk plaintext remains until secrets-mount follow-on.

**B3 — Admin password vs Mongo hash (mandatory coordination)**

Because boot provisioning does **not** update existing hashes, R4-APPLY must either:

1. **Preferred:** After ENV update + recreate, use **authenticated** `POST /api/auth/change-password` (or equivalent) with old password → new password (bumps `session_version`); **or**  
2. **Break-glass:** Operator updates Mongo `password_hash` via one-shot script using app DB user (bcrypt), then bump `session_version`, then recreate — higher risk; only if API path unavailable.

Do **not** rely on ENV-only admin pass change for login cutover.

**B4 — JWT rotation**

- Set new `JWT_SECRET` in `.env` before or with recreate.  
- Recreate backend once (`--no-deps --force-recreate --pull never backend`).  
- Expect all prior cookies invalid (signature fail) — operators re-login with **new** password.

**B5 — Preserve**

- Digest `69fe2459…` · SHADOW · AUTOEXEC/RUNTIME false · R1/R2 · R3 mongo user · RPC/Alchemy unchanged · Factory/g5.79/Foreman untouched · no P2 / signing / broadcast.

### Phase C — Historical scrub (separate auth: R4-SCRUB or extend R2 cleanup)

- Operator-reviewed delete/move of non-approved local `.env.*` copies and `/tmp` dumps matching old sha12s.  
- **Do not** scrub approved `arbicore_backups` recovery sets without DR policy sign-off.  
- Stopped legacy Config.Env: leave stopped; optional `docker rm` only under explicit auth (destroys inspect evidence).

---

## 5. Session invalidation / versioning

| Event | Effect |
|---|---|
| JWT_SECRET change + recreate | All JWTs unverifiable → immediate logout |
| Password change API / `session_version++` | Old tokens with prior `sv` rejected even if JWT secret unchanged |
| Recommended order | Backup → write new `.env` (both secrets) → recreate → change-password (if hash not already updated offline) → verify login new / reject old → attest sha12 |

Document expected operator impact: **all admin sessions end**; refresh cookies die; ~1–2 min API blip on recreate.

---

## 6. Backup and rollback

| Artifact | Requirement |
|---|---|
| Pre-R4 `.env` | `0600` under `/home/raghu/arbicore_backups/r4_admin_jwt_<TS>/` |
| New secret escrow | Same dir · `0600` · not logged |
| Rollback | Restore `backend.env.pre-r4` → recreate backend → confirm login with **old** password works · sha12 back to pre-R4 · digest unchanged |
| Mongo | If password_hash updated, rollback must restore prior hash **or** change-password back — record which path was used |
| R3 | Must remain `arbicore_app`; rollback script must not revert `MONGO_URL` user |

---

## 7. Verification (post R4-APPLY)

| Check | Expect |
|---|---|
| Digest | still `69fe2459…` |
| Health / `/api/` | healthy · 200 |
| Admin login **new** password | 200 · `/api/auth/me` 200 |
| Admin login **old** password | 401 |
| Cookie from pre-rotation session | 401 |
| Live ENV + `.env` sha12 | **changed** for JWT and admin pass |
| `session_version` | increased vs preflight baseline |
| R1 / R2 | 404 / 503 |
| Controls | SHADOW · AUTOEXEC/RUNTIME false · no BOOTSTRAP |
| R3 mongo user | still `arbicore_app` |
| Factory / g5.79 / Foreman | unchanged |
| Reports | sha12 + lens only — **no secret values** |

---

## 8. Explicit authorisation boundary

| Token | Allowed | Forbidden |
|---|---|---|
| **R4-PREFLIGHT** | Read-only inventory refresh, readiness verdict | Any secret write, recreate, scrub |
| **R4-APPLY** | Backup; rotate live admin pass + JWT in `.env`; one backend recreate; password-hash / session_version update as planned; verify | Historical scrub; R5/R6; P2; RPC; Mongo user changes; Factory; starting legacy |
| **R4-SCRUB** (optional later) | Delete/move listed non-approved copies | Touching approved recovery archives without DR auth |

**This document is not R4-APPLY authority.**

---

## 9. Acceptance / limitations after first R4-APPLY

**PASS WITH LIMITATIONS** expected if live sha12s rotated and login tests pass, while:

- Plaintext remains on disk in `.env` (unless B2-b authorised)  
- Historical copies still hold old sha12s until R4-SCRUB  
- Stopped legacy Env still holds old material  
- Boot-time ENV seed path still exists for empty-users disaster recovery  

Overall gate / P2 stays **BLOCKED** until R5/R6 (and policy residuals) close.
