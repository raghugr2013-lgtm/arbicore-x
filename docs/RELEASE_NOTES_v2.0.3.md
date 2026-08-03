# ArbiCore X v2.0.3 — Release Notes

**Release date:** 2026-08-02
**Tag:** `v2.0.3`
**Status:** ✅ **READY FOR DEPLOYMENT**

## Summary

v2.0.3 closes the final production gaps identified before VPS deployment:

1. **Backend authentication** — real JWT-based `/api/auth/{login,logout,me}` with role support (admin / operator), Mongo-backed session revocation, and drop-in `AuthContext` for the frontend.
2. **Release readiness** — every critical production endpoint certified operational (17 endpoints across health, MID, opportunities, journal, execution, policy, certification, autonomous executor, discovery).
3. **OCE design** — a comprehensive design document for the future Operational Certification Engine (`docs/V2_OCE_DESIGN.md`). Not implemented; scheduled for a later release after MID accumulates production data.

## What's new since v2.0.2

### Backend authentication
- New module: `arbicore/auth/__init__.py`
- Endpoints:
  - `POST /api/auth/login` — accepts `{username, password}` or `{username, passphrase}` → issues JWT (HS256, 24h TTL) + records session in `auth_sessions`
  - `POST /api/auth/logout` — revokes JTI (session bearer)
  - `GET /api/auth/me` — validates bearer token, returns user + role
- Storage: `auth_users` (seeded on first boot), `auth_sessions` (JTI revocation with 7d TTL)
- Roles supported: `admin`, `operator` (extensible; not gated at endpoint level yet — endpoint-level RBAC is a future increment)
- Password hashing: bcrypt (10 rounds, industry standard)
- JWT secret: `ARBICORE_JWT_SECRET` env var (32+ chars required in production); dev fallback derives from `MONGO_URL` for local stability

### Frontend authentication
- `AuthContext.jsx` rewrites to use the real backend
  - `login()` posts credentials, stores JWT in localStorage
  - `logout()` calls backend + clears localStorage
  - Mount-time `validate()` calls `GET /api/auth/me` to detect revoked/expired sessions
  - The API shape (`{user, role, token, isAuthenticated, isInitialized, login, logout, markInitialized}`) is unchanged from v2.0.2 — no consumer changes required

### Operational Certification Engine (design only)
- New doc: `docs/V2_OCE_DESIGN.md` (~350 lines)
- 4-tier ladder: OBSERVE → PAPER → SHADOW → AUTONOMOUS
- Per-tier promotion criteria (evidence + KPIs + score threshold + policy compliance)
- Per-tier automatic demotion criteria
- Full audit-trail contract via existing evidence bundles + MID decisions
- Not implemented — scheduled for after MID accumulates ≥ 30 SHADOW-tier days

## Backend regression

**1469 tests pass, 76 skipped, 0 failed** (same as v2.0.2 — no test-suite regressions introduced by the auth wiring).

## Backend certification results

All 27 auth tests pass:
- Login (admin, operator, wrong password, unknown user, empty body)
- `/auth/me` (no header, valid, tampered)
- `/auth/logout` + subsequent `/auth/me` returns 401 (session revoked)
- Seed idempotency (user_id stable across logins)

All 17 production endpoints operational (200 OK):
- `/api/`, `/api/system/status`
- `/api/arbicore/opportunities/{summary,list}`
- `/api/arbicore/journal/{summary,recent}`
- `/api/arbicore/dashboard/pulse`
- `/api/arbicore/mid/{status,enums,query/gas}` — 11 domains available, invalid-domain returns 404
- `/api/arbicore/execution/{mode,capital-policy,kill-switch,certification/stages,discovery/status}`
- `/api/arbicore/auto-executor/status`

## Frontend integration

Previously verified in v2.0.2:
- `/` → `/login` for unauthenticated users
- Login validation (empty fields, short passphrase)
- Login → `/initialization` → 4 sequential steps → `/dashboard`
- Session persistence across reload
- `/v2` legacy redirect to `/dashboard`

v2.0.3 wires the login form to the real backend endpoint. Same UI. Same flow. Real credentials now required.

## Default credentials (dev / test)

See `/app/memory/test_credentials.md`:

| Username | Password | Role |
|---|---|---|
| `admin` | `admin-shadow-2026` | admin |
| `operator` | `operator-shadow-2026` | operator |

**⚠ These are dev fallbacks.** Every VPS deployment must override via `.env`:
```
ARBICORE_ADMIN_PASSWORD=<long random>
ARBICORE_OPERATOR_PASSWORD=<long random>
ARBICORE_JWT_SECRET=<32+ char random>
```

## Breaking changes

**None.** v2.0.3 is strictly additive over v2.0.2:
- No existing endpoints changed
- No existing collections modified
- No existing tests broken
- `AuthContext` API shape preserved (backend swap is invisible to consumers)

## Distribution artifacts

- `arbicore-x-v2.0.3.bundle` — git bundle, deploy with `git clone <bundle>`
- `arbicore-x-v2.0.3.tar.gz` — flat source
- `arbicore-x-v2.0.3.SHASUMS` — sha256

## Next steps

1. Follow `docs/DEPLOYMENT_CHECKLIST_v2.0.3.md` to deploy to VPS
2. Operate in SHADOW mode; let the MID accumulate for at least 30 days
3. Begin Sprint 1B (dormant intelligence activations) on the canonical repo
4. When ready, build the OCE per `docs/V2_OCE_DESIGN.md`
