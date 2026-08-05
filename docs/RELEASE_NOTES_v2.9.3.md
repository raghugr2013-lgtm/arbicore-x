# v2.9.3 — Authentication routing hotfix (release candidate)

**Release type:**  Maintenance hotfix — surgical
**Branch:**        `hotfix/auth-routing`
**Baseline:**      v2.9.2 (`293a2c4`)
**Scope:**         Restore the canonical `/api/auth/*` surface end-to-end.
                   No changes to trading, scanning, validation, execution,
                   MID, calibration, deployment infrastructure, or any
                   business route.

---

## 1. Which authentication implementation is canonical

**Canonical (as of v2.9.3):** the `routes/auth.py` + `services/auth.py` +
`services/db.py` tree, using Mongo collection **`users`**.

Endpoints under `/api/auth`:
`status`, `setup`, `login`, `logout`, `logout-all`, `me`, `refresh`,
`change-password`.

Contract:
- Single-admin system.  First-run flow: `GET /api/auth/status` reports
  `setup_complete=false` while `users` is empty; `POST /api/auth/setup`
  creates the sole admin and locks registration permanently.
- Session transport: **httpOnly** `access_token` + `refresh_token` cookies
  signed with HS256 via `JWT_SECRET`.  Also accepts `Authorization: Bearer`
  header (for CLI clients).
- Session revocation via server-side `session_version` counter on the user
  document; `POST /api/auth/logout-all` and `POST /api/auth/change-password`
  bump it so every other client is force-signed-out.
- Brute-force protection via `login_attempts` collection: 5 failures per
  `ip:username` → 15-minute lockout.

## 2. Why duplicate authentication implementations existed

| Commit    | Release                        | Auth artefact introduced |
| :-------- | :----------------------------- | :----------------------- |
| `23cbfe8` | v1.0.0 initial canonical       | `routes/auth.py`, `services/auth.py`, `api.py`, `reset_admin.py` — canonical single-admin cookie auth. |
| `6327c07` | v2.0.0 canonical consolidation | Merged in the 5052-line `server.py` monolith from `Arbicorex-ui-v2-slice-02`. Merge commit **explicitly preserved the canonical `routes/`, `services/`, `api.py` "in-tree" as dormant modules for later reactivation.** |
| `bfe5df9` | v2.0.3                         | Under VPS-deployment pressure, added a *second* auth module (`arbicore/auth/__init__.py`, bearer-JWT, auto-seeded `admin`/`operator`, collection `auth_users`) and stitched four endpoints directly into `server.py`. Faster than completing the canonical activation. The frontend `AuthContext.jsx` was rewired to consume this second module; the rest of the frontend (`Login.jsx`, `SecuritySection.jsx`, `Telegram/VaultSection.jsx`, `opportunity_center`) was still on the canonical contract but never reconciled. |
| `ec1a740`, `2e3704b`, … v2.9.2 | v2.1.x → v2.9.2 | Iterated on the Tree-B quick-wire (env-var name, self-heal, deployment profile). Nobody circled back to complete the canonical activation. |

Symptomatic outcome by Aug 2026: `/api/auth/status` and `/api/auth/setup`
were 404, `reset_admin.py` was clearing the wrong collection, and the
`arbicore-x-opportunity-center` micro-frontend had been silently unable to
log in against the running backend since v2.0.3.

## 3. Which legacy authentication code remains and why

Per the "surgical maintenance" scope, we do **not** delete Tree-B code in
this hotfix. Retained and gated:

| File / block | State after v2.9.3 | Reason retained |
| :----------- | :----------------- | :-------------- |
| `app/backend/arbicore/auth/__init__.py`                        | On-disk, no longer wired to any HTTP endpoint.                                                        | Deleting an entire module is out-of-scope refactoring; may still be imported by ops scripts. |
| `server.py` lines 3577–3592 (`arbicore.auth` import, try/except) | Kept.                                                                                                 | Removing shifts all downstream line numbers.  The import is already defensive.                |
| `server.py` `_auth_seed_startup` hook                          | **Gated OFF** by default. Runs only when env var `ARBICORE_LEGACY_AUTH_SEED=1`.                       | Prevents `auth_users` from being silently re-seeded on every boot, which would mask reset flows. Escape hatch preserved for operators running the old image in isolation. |
| `server.py` `_resolve_current_user`                            | Rewritten to **prefer** canonical cookie/bearer via `services.auth`, with legacy bearer as fallback.  | Preserves backward compatibility for any pre-v2.9.3 bearer tokens still in circulation (read-only — no new bearer tokens are issued after this hotfix).                        |
| `server.py` inline `/api/auth/{login,logout,me,diagnostics}`   | **Removed.**                                                                                          | Exact duplicates that would collide with the canonical router. `/api/auth/diagnostics` was Tree-B-only and is retired (see §7).                                                |
| `app/frontend/src/pages/Login.jsx`                             | On-disk, orphaned (`App.js` does not route to it).                                                    | Deleting orphaned frontend code is out-of-scope.                                              |
| `app/backend/api.py`, `app/backend/routes/{alerts,execution,observation,portal,portfolio,vault,venues}.py` | On-disk, not mounted. | Not required by the hotfix.                                                                   |

## 4. Files changed (5 files, +204 / −162 lines)

### Backend (2 files)

**`app/backend/server.py`** — 3 surgical edits, no other lines modified.

1. **Line 1** — added `Request` to the `fastapi` import so canonical resolver
   can read cookies.
2. **~line 3517** (after `app.include_router(api_router)`, immediately after
   logger configuration) — new block that imports `routes.auth.router` and
   calls `app.include_router(...)`, wrapped in `try/except` so a missing
   module can never crash boot. This is the primary fix: it mounts
   `/api/auth/{status,setup,login,logout,logout-all,me,refresh,change-password}`.
3. **~line 3595** (`_auth_seed_startup`) — added early-return when env var
   `ARBICORE_LEGACY_AUTH_SEED != "1"`. Logs the skip decision.
4. **~lines 3655–3760** — removed the four Tree-B inline endpoints
   (`auth_login`, `auth_logout`, `auth_me`, `auth_diagnostics`) and their
   ~90-line bodies. Replaced by an inline comment block explaining what was
   removed and why.
5. **`_resolve_current_user` (~line 3668)** — rewritten to accept an optional
   `Request` argument and to try canonical cookie/bearer auth via
   `services.auth.get_current_user` first, falling back to the legacy bearer
   path only if that fails. Return dict shape preserved (`user_id`,
   `username`, `role`, `jti`) so all 9 downstream call sites keep working.
6. **9 admin-only endpoint signatures** updated to accept `request: Request`
   and pass it into `_resolve_current_user(request, authorization)`:
   `scanner_start`, `scanner_stop`, `live_start`, `live_stop`, `flj_run`,
   `validation_daily_run_now`, `kill_engage`, `kill_disengage`,
   `paper_analyse`. No logic changes to any of these — just the extra
   parameter and the extra argument at the call site.

**`app/backend/reset_admin.py`** — full rewrite, still ~180 lines. Adds
`argparse`, `--dry-run`, `--legacy`, `--skip-canonical`. Prints an inventory
of both stores before touching anything. Refuses (exit code 3) if `users`
is empty but `auth_users` is populated, unless `--legacy` is passed. Only
resets the canonical store by default.

### Frontend (2 files)

**`app/frontend/src/context/AuthContext.jsx`** — replaced. New shape:
```js
{ user, role, isAuthenticated, isValidating, isInitialized,
  setupComplete, login, setup, logout, logoutAll, markInitialized }
```
plus a named export `formatApiErrorDetail(detail)` used by SecuritySection /
TelegramSection / VaultSection. Wire-up:
- Uses `axios` with `withCredentials: true`. Also sets
  `axios.defaults.withCredentials = true` at module load so business API
  calls elsewhere (Settings ➜ Change Password, Vault, Telegram) send the
  session cookie without touching each component.
- On mount: `GET /api/auth/status` → sets `setupComplete`; `GET /api/auth/me`
  → sets `user` if a cookie session already exists.
- `login({ username, passphrase })` maps `passphrase → password` for the
  canonical body shape.  `setup(username, password)` calls `/api/auth/setup`.
  `logoutAll()` calls `/api/auth/logout-all` (used by SecuritySection's
  "revoke all other sessions" button).

**`app/frontend/src/v2/pages/LoginPage.jsx`** — replaced. Same v2 dark card;
adds a conditional branch that renders as **CREATE ADMINISTRATOR** with a
"Confirm passphrase" field when `setupComplete === false`, and as the usual
sign-in form otherwise.  Route unchanged (`/login`).  Also adds a
`data-testid` set (`login-page`, `login-username-input`,
`login-passphrase-input`, `login-confirm-input`, `login-submit-button`,
`login-error`) for automated QA.

### Docs

- `docs/RELEASE_NOTES_v2.9.3.md`     (this file)
- `docs/verification_v2.9.3/`         (curl transcript + 5 screenshots)

## 5. Verification results

All 23 verification steps pass. Full transcript at
`docs/verification_v2.9.3/backend_curl_transcript.txt` and screenshots at
`docs/verification_v2.9.3/frontend_0{1..5}_*.jpeg`.

| # | Test | Expected | Observed |
| :- | :---- | :------- | :------- |
| 1  | `GET /api/auth/status` (users empty)                       | `{setup_complete:false, auth_required:true}` HTTP 200                       | ✅ |
| 2  | `POST /api/auth/setup {admin, testtest123}`                | 200 · returns user · sets access_token + refresh_token cookies              | ✅ |
| 3  | `POST /api/auth/setup` again                               | 403 "Setup already completed — registration is locked (single-admin system)"| ✅ |
| 4  | `GET /api/auth/status` after setup                         | `{setup_complete:true, auth_required:true}`                                 | ✅ |
| 5  | `GET /api/auth/me` (with cookie)                           | 200 · returns user                                                          | ✅ |
| 6  | `POST /api/auth/logout` (Set-Cookie clears)                | HTTP 200 · `access_token=""; Max-Age=0; Path=/` sent                        | ✅ |
| 7  | `GET /api/auth/me` (no cookie)                             | 401 "Not authenticated"                                                     | ✅ |
| 8  | `POST /api/auth/login {new password}` after change-password | 200 · sets new cookies                                                     | ✅ |
| 8n | `POST /api/auth/login {old password}` after change-password | 401 "Invalid username or password"                                         | ✅ |
| 9  | `POST /api/auth/refresh` (with refresh cookie)             | 200 · new access_token cookie                                               | ✅ |
| 10 | `GET /api/auth/me` after refresh                           | 200                                                                         | ✅ |
| 11 | `POST /api/auth/change-password`                           | 200 · session_version bumped                                                | ✅ |
| 12 | Old cookie after `/logout-all`                             | 401 "Session revoked"                                                       | ✅ |
| 13 | 6× wrong password → lockout                                | Attempt 5 → HTTP 429 "Too many failed attempts — locked until …"            | ✅ |
| 14 | Regression: `/api/`, `/api/status`, `/api/arbicore/dashboard/pulse` | HTTP 200 each                                                       | ✅ |
| 15 | `/api/auth/diagnostics` (Tree-B endpoint) now removed      | 404                                                                         | ✅ |
| 16 | `reset_admin.py --dry-run`                                 | Reports inventory + "would delete" lines; no writes                         | ✅ |
| 17 | `reset_admin.py`                                           | Deletes only canonical `users` + `login_attempts`; leaves `auth_users`      | ✅ |
| 18 | `GET /api/auth/status` after reset                         | `{setup_complete:false}` — setup reopens                                    | ✅ |
| 19 | `reset_admin.py` w/ empty `users` & populated `auth_users` | Refuses (exit 3); prints warning; no writes                                 | ✅ |
| 20 | `reset_admin.py --legacy`                                  | Clears legacy stores; exit 0                                                | ✅ |
| 21 | Full re-setup end-to-end                                   | status→setup→status all consistent                                          | ✅ |
| 22 | Boot without `ARBICORE_LEGACY_AUTH_SEED` env var           | Log: "legacy auth seed skipped (ARBICORE_LEGACY_AUTH_SEED != '1')" · auth_users unchanged | ✅ |
| 23 | Boot with `ARBICORE_LEGACY_AUTH_SEED=1`                    | Legacy seed runs; `auth_users` has 2 documents                              | ✅ |
| FE-1 | LoginPage renders CREATE ADMINISTRATOR when users empty  | Heading "Create administrator", CONFIRM PASSPHRASE input present, footer "FIRST-RUN SETUP" | ✅ |
| FE-2 | Submit setup form → redirected to `/initialization`      | URL becomes `/initialization`, cookies present, `/api/auth/me` returns admin | ✅ |
| FE-3 | Logout via `/api/auth/logout` → LoginPage renders sign-in variant | Heading "ArbiCore X", no confirm input, footer "SHADOW mode"          | ✅ |
| FE-4 | Sign in with same credentials → `/initialization`        | URL becomes `/initialization`                                              | ✅ |

## 6. Breaking changes

- **`GET /api/auth/diagnostics`** (Tree-B only) is removed. No known
  frontend consumers. Replacement: `GET /api/auth/me` +
  `python reset_admin.py --dry-run`.
- **`POST /api/auth/login`** request body: canonical accepts
  `{username, password}` only (Tree-B also accepted `passphrase`). The
  frontend already sends `password`; the alias is retired.
- **Session transport** changes from bearer-token JWT (localStorage) to
  httpOnly cookies. External clients holding bearer tokens issued before
  v2.9.3 will continue to work against `_resolve_current_user`-gated
  endpoints until those tokens expire, but cannot re-obtain new bearer
  tokens after this release. Recommended migration for CLI clients:
  `POST /api/auth/login` then reuse the `Set-Cookie` header, or send the
  access_token value as `Authorization: Bearer <token>` (canonical
  endpoints accept both).
- **Default admin/operator seed** in `auth_users` is disabled unless
  `ARBICORE_LEGACY_AUTH_SEED=1`. Operators who relied on the seeded
  `admin`/`operator` accounts must either set the env var or migrate
  to the canonical single-admin store via `POST /api/auth/setup`.

## 7. Deployment instructions

**Required env vars** (already present on the VPS; verify):

```
JWT_SECRET=<a strong 32+ byte secret; canonical services/auth.py reads this>
MONGO_URL=<pointer to factory-mongo>
DB_NAME=arbicore_x
CORS_ORIGINS=https://arbicorex.coinnike.com
# ARBICORE_LEGACY_AUTH_SEED is INTENTIONALLY unset (default off)
```

**Steps** (run on the VPS as the ops user):

```bash
# 1. Bring the hotfix into the deployment tree
cd /opt/arbicorex          # or wherever the compose file lives
git fetch origin
git checkout hotfix/auth-routing
git pull --ff-only

# 2. Rebuild the two container images that changed
COMPOSE_FILE=deployment/compose/prod.shared-mongo.yml
docker compose -f $COMPOSE_FILE build --pull arbicore-x-backend arbicore-x-frontend

# 3. Reset the auth store on the running database (single-admin flow)
docker compose -f $COMPOSE_FILE exec arbicore-x-backend \
    python reset_admin.py --dry-run          # inspect
docker compose -f $COMPOSE_FILE exec arbicore-x-backend \
    python reset_admin.py                     # apply

# 4. Roll out
docker compose -f $COMPOSE_FILE up -d arbicore-x-backend arbicore-x-frontend

# 5. Smoke test
curl -sSf https://arbicorex.coinnike.com/api/auth/status
# expect: {"setup_complete":false,"auth_required":true}

# 6. Complete first-run setup via the browser at
#    https://arbicorex.coinnike.com/login
```

## 8. Rollback instructions

Two independent rollback paths depending on how far you got:

**A. Roll back the images only (fast, no data loss)**

```bash
cd /opt/arbicorex
git checkout main           # v2.9.2 (293a2c4)
docker compose -f $COMPOSE_FILE build --pull arbicore-x-backend arbicore-x-frontend
docker compose -f $COMPOSE_FILE up -d arbicore-x-backend arbicore-x-frontend
# Optional: to re-enable the legacy seed so admin/operator return automatically:
#   set ARBICORE_LEGACY_AUTH_SEED=1 in the backend service env and restart.
```

If you had already completed setup on v2.9.3, the canonical `users`
collection remains populated but is not read by v2.9.2. The v2.9.2 backend
will fall back to `auth_users`; if that collection is empty (S-ON left it
empty), enable the legacy seed as above and it will be re-seeded on boot.

**B. Full re-verification after rollback**

```bash
# 1. Wait for backend to become healthy
sleep 8
# 2. Old /api/auth/login (Tree-B) should return 200 for seeded creds
curl -sSf -X POST https://arbicorex.coinnike.com/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"<your admin pw>"}'
# 3. /api/auth/status should return 404 (Tree-A router no longer mounted)
```

There is no schema migration to reverse. The two collections
(`users`, `auth_users`) coexist and neither is destructive to the other.

## 9. Merge plan

- This is a release candidate; **do not merge into `main` yet**.
- Suggested review path:
  1. Reviewer runs the 4-step verification (steps 1, 2, 6, 15 above)
     against a staging deployment of `hotfix/auth-routing`.
  2. If green, tag `v2.9.3-rc.1` on the branch.
  3. After 24h burn-in on staging with no auth-related issue, fast-forward
     merge into `main`, tag `v2.9.3`, and roll out to production.
