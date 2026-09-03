# AUTHORIZATION ENDPOINT MATRIX

Classification of representative API surfaces. Auth model: canonical single-admin,
httpOnly access/refresh JWT cookies (`services/auth.py`), `Depends(require_auth)`
on privileged routers.

| Endpoint | Method | Class | Notes |
|---|---|---|---|
| `/api/auth/status` | GET | PUBLIC | Booleans only; no secrets. |
| `/api/auth/setup` | POST | **BOOTSTRAP-GATED** | Requires `X-Bootstrap-Token`; fail-closed; one-shot atomic lock. |
| `/api/auth/login` | POST | PUBLIC (rate-limited) | Brute-force lockout: 5 fails → 15 min (`login_attempts`). |
| `/api/auth/refresh` | POST | AUTHENTICATED (refresh cookie) | Rotates access token. |
| `/api/auth/me` | GET | AUTHENTICATED | 401 without valid access cookie/bearer. |
| `/api/auth/logout` | POST | AUTHENTICATED | Clears cookies. |
| `/api/auth/logout-all` | POST | AUTHENTICATED | Bumps `session_version` (revokes all). |
| `/api/auth/change-password` | POST | AUTHENTICATED | Verifies current pw; revokes other sessions. |
| `/api/arbicore/safety/status` | GET | ADMIN | Reports kill/mode/capital posture. |
| `/api/arbicore/safety/kill/engage` | POST | ADMIN | Cookie-auth (verified V15). |
| `/api/arbicore/safety/kill/disengage` | POST | ADMIN | Cookie-auth. |
| `/api/arbicore/scanners/*` | GET/POST | ADMIN | Router mounted with `Depends(require_auth)`; read/config only — never signs/broadcasts. |
| `/api/arbicore/execution/mode/*` | GET/POST | ADMIN/OPERATOR | Mode transitions logged (`execution_mode_audit`). Promotion to LIMITED_LIVE/FULL_LIVE gated by readiness. |
| `/api/auth/diagnostics` | GET | DISABLED | Legacy Tree-B; returns 404 (V10). |

## Adversarial verification (see SECURITY_TEST_RESULTS.md)

- Unauthenticated `/api/auth/me` → **401**. ✅
- `/api/auth/setup` without token → **403**. ✅
- `/api/auth/setup` wrong token → **403**, no admin created. ✅
- Repeat `/api/auth/setup` after success → **403** locked. ✅
- 12-way concurrent authorized setup → **exactly 1** admin. ✅
- 5× wrong login then correct → **429** lockout. ✅ (existing V9 regression)
