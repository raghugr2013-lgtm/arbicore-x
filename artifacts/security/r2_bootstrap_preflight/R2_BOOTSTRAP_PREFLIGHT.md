# R2 — Bootstrap exposure preflight (read-only)

**Phase:** 1 preflight only — **no mutation**  
**Captured UTC:** `2026-10-10T09:01:29Z` – `2026-10-10T09:02:44Z`  
**Baseline:** R1 **PASS** · overall security gate / P2 **BLOCKED**  
**Artifacts:** this dir · `preflight_probe.json` · `token_location_inventory.json` · `token_location_summary.json`

---

## Executive recommendation

**Prefer: DISABLE setup by removing `ARBICORE_BOOTSTRAP_TOKEN` from the live runtime environment** (empty/unset → app returns **503** on `POST /api/auth/setup`), then recreate the backend on the **same** S2-A image so the live ENV no longer carries sha12 `d5a682fbe887`.

| Why disable (not rotate) | Evidence |
|---|---|
| Initial setup is already complete | `/api/auth/status` → `setup_complete: true` (local + public) |
| Valid administrator exists | Mongo `users` count **1** · username `admin` · role `admin` · `session_version` **2** |
| App supports safe disable without rebuild | [`routes/auth.py`](../../../app/backend/routes/auth.py) `_authorize_bootstrap`: no token → **503** fail-closed |
| Design runbook agrees | [`docs/BOOTSTRAP_SECURITY_DESIGN.md`](../../../docs/BOOTSTRAP_SECURITY_DESIGN.md): after success, “Rotate/**remove** the token… if desired” |
| Gate criterion | Reconciliation requires old sha12 **absent from live ENV** and bootstrap path **closed or disabled** |

**Do not execute** until explicit R2 apply authorisation. Backend recreate is **required** for ENV drop and is **not** authorised in this phase.

**Rotate-only** is the fallback if the operator must retain an HTTP wipe-recovery path without relying on boot-time `ARBICORE_ADMIN_PASS` provisioning. That is weaker for R2 because a live token remains attack-useful after a users wipe.

---

## 1. Setup / admin status (verified)

| Check | Result |
|---|---|
| `GET /api/auth/status` (127.0.0.1:8001) | `setup_complete: true` |
| Same via sslip.io + api.arbicorex.in | `setup_complete: true` |
| Mongo `users` count | **1** |
| Admin doc (redacted) | `username=admin`, `role=admin`, `session_version=2` |
| `POST /api/auth/setup` no header | **403** “Invalid or missing…” (token **is** provisioned) |
| `POST /api/auth/setup` wrong header | **403** |
| Code lock when users exist | After authn, `count_documents > 0` → **403** “Setup already completed” |

**Residual risk while token remains in ENV:** if `users` is emptied and an attacker still knows sha12 `d5a682fbe887` material, `/setup` can create a new admin. Presence of the token is therefore still a gate FAIL even though day-to-day setup is locked.

**Secondary path (out of R2 scope, relevant to disable safety):** `ensure_provisioned_users()` can insert-only seed `admin` from `ARBICORE_ADMIN_PASS*` on boot if no user exists. Disabling the bootstrap **token** closes the HTTP setup path; it does not remove ENV admin-password recovery (that is R4).

---

## 2. Bootstrap flow (code)

| Item | Detail |
|---|---|
| Endpoint | `POST /api/auth/setup` |
| Header | `X-Bootstrap-Token` |
| Env | `ARBICORE_BOOTSTRAP_TOKEN` |
| No token | **503** — bootstrap disabled |
| Bad/missing header | **403** |
| Users already present | **403** locked |
| Status endpoint | Does **not** disclose whether a token is provisioned |

There is **no** separate feature flag to disable the route without ENV change or code/image change. Smallest safe disable = **unset token** (no rebuild).

---

## 3. Active configuration locations (redacted)

### Live production path

| Location | Present | len | sha12 | Notes |
|---|---|---:|---|---|
| Container `arbicore-x-backend-new` ENV | yes | 64 | `d5a682fbe887` | Image `s2a-rpc-redact-5bd952568aed` · digest `69fe2459…` |
| `…/arbicore-x-v2/deployment/upgrade/backend/.env` | yes | 64 | `d5a682fbe887` | mode `0600` · compose `env_file: ../backend/.env` |
| Compose project | — | — | — | working_dir `…/upgrade/compose` · `docker-compose.prod.yml` + `/tmp/arbicore-s2a-rpc-redact-override.yml` |

### Stopped legacy (must stay stopped)

| Container | Status | Bootstrap sha12 |
|---|---|---|
| b7 / h05 / w1 | exited | `d5a682fbe887` (same as live) |

### Copies inventory (assignment lines; values not printed)

| Class | Count (approx) | sha12 |
|---|---:|---|
| Live `.env` | 1 | `d5a682fbe887` |
| Historical/backups under upgrade + `arbicore_backups` | ~13 | mostly `d5a682fbe887` |
| `/tmp` env dumps / worktrees | ~71 | mix `d5a682fbe887` + older `f5748db3f254` (len 43) |
| Unique sha12s seen | 2 | `d5a682fbe887`, `f5748db3f254` |

Full path list: `token_location_inventory.json`. Summary: `token_location_summary.json`.

---

## 4. Proposed minimal change (for later authorisation)

### Recommended: R2-DISABLE

1. Backup live `backend/.env` to a **0600** timestamped file under an approved backup dir (not `/tmp`).  
2. **Remove** the `ARBICORE_BOOTSTRAP_TOKEN=…` assignment from live `.env` (or leave key unset — do not leave a placeholder secret).  
3. Recreate **only** `arbicore-x-backend-new` from existing compose + S2-A override so ENV drops the token; **same image digest**.  
4. Preserve SHADOW / AUTOEXEC=false / RUNTIME=false / R1 Caddy denies / S2-A RPC primary+fallbacks.  
5. Optionally scrub **non-essential** `/tmp` copies and local `.env.*` backups under change control; **retain** approved recovery archives restricted (S1-B / S2-A) but treat them as containing the old token.  
6. Do **not** start legacy containers.

| | |
|---|---|
| **Downtime** | Backend recreate ~1–2 minutes |
| **Image rebuild** | **Not required** |
| **Rollback** | Restore `.env` line from 0600 backup; recreate backend; confirm sha12 restored; `/setup` without token returns 403 again |

### Alternative: R2-ROTATE (only if wipe-recovery HTTP path must stay)

1. Generate new high-entropy token offline; escrow 0600.  
2. Replace live `.env` value; recreate backend.  
3. Accept that `/setup` remains usable after a users wipe with the **new** token.  
4. Still scrub `/tmp` and discourage reuse of sha12 `d5a682fbe887` copies.

---

## 5. Acceptance tests (post-apply)

| # | Test | Expected |
|---|---|---|
| A | `GET /api/auth/status` | `setup_complete: true` |
| B | `POST /api/auth/setup` without header (local + public api host) | **503** if disabled / **403** if rotated-but-wrong |
| C | Live container ENV | `ARBICORE_BOOTSTRAP_TOKEN` **absent** (disable) **or** sha12 ≠ `d5a682fbe887` (rotate) |
| D | Live `.env` | same as C |
| E | `POST /api/auth/login` with known admin | still works (no admin/JWT change in R2) |
| F | R1 public `/docs` | still **404**; `/api/` **200** |
| G | Backend digest | unchanged `69fe2459…` |
| H | Controls | SHADOW; AUTOEXEC/RUNTIME false; legacy exited; g5.79 untouched; S2-A fps primary `ca6545ba` |

Mark R2 **PASS** only if A–H hold on fresh evidence.

---

## 6. Unknowns and dependencies

| Item | Status |
|---|---|
| Whether `admin_singleton` sentinel exists on the live admin doc | **Unknown/absent in projection** — lock still enforced by `count > 0` |
| Full off-host / git-history / operator laptop copies of the token | **Unknown** |
| Exact recreate command operator will use (compose file + override) | **Dependency** — must preserve S2-A override and controls |
| Policy for scrubbing `/tmp` and local `.env.*` backups | **Needs human decision** |
| Whether operator wants HTTP wipe-recovery retained | **Decision** — drives DISABLE vs ROTATE |
| Boot-time admin seed via `ARBICORE_ADMIN_PASS` after users wipe | **Out of R2** (R4); not closed by token disable |
| Edge deny of `POST /api/auth/setup` without ENV change | Possible supplement; **does not** clear “absent from live ENV” gate alone |

---

## 7. Safety confirmation (this phase)

- No ENV edits, recreates, rotations, revokes, Caddy changes, Mongo changes, or P2 work.  
- R1 still held (public docs **404**, `/api/` **200**).  
- Secrets referenced only as presence / length / sha12.  

**Stop for human authorisation before any R2 apply.**
