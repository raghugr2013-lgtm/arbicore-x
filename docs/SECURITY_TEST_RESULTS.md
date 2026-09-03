# SECURITY TEST RESULTS — First-Admin Bootstrap (P0)

Environment: local backend `http://localhost:8001`, Mongo `arbicore_x`, real code
path (`routes/auth.py`, `services/auth.py`). Token used = provisioned
`ARBICORE_BOOTSTRAP_TOKEN` in `backend/.env`.

## Adversarial results (curl, reproduced live)

| # | Case | Expected | Actual | Pass |
|---|---|---|---|---|
| 1 | `POST /setup` **no token** | 403 | 403 | ✅ |
| 2 | `POST /setup` **wrong token** | 403 | 403 | ✅ |
| 3 | `POST /setup` **correct token** | 200 (admin created, cookies set) | 200 | ✅ |
| 4 | `POST /setup` **repeat w/ correct token** | 403 (locked) | 403 | ✅ |
| 5 | **12-way concurrent** authorized `POST /setup` (distinct usernames) | exactly 1 admin | 1× 200, 11× 403; users=1 | ✅ |
| 6 | `POST /login` correct | 200 + cookies | 200 | ✅ |
| 7 | `GET /me` with cookie | 200 | 200 | ✅ |
| 8 | `POST /login` wrong password | 401 | 401 | ✅ |
| 9 | `GET /me` without cookie | 401 | 401 | ✅ |

Pre-fix control: the same 10-way race produced **3 admins** (fail). Post-fix:
**1 admin** (pass) — atomicity proven by the unique-indexed sentinel lock.

## Fail-closed proof

- With `ARBICORE_BOOTSTRAP_TOKEN` **unset**, `_authorize_bootstrap` returns `503`
  ("bootstrap disabled") — the no-admin state never authorizes an anonymous visitor.
- `/api/auth/status` exposes only `bootstrap_requires_token: true` and
  `bootstrap_available: <bool>` — never the token value.

## Independent verification (testing agent, external ingress)

`tests/test_p0_bootstrap_external_ingress.py` — **15/15 pass** against the public
ingress URL. Confirmed: 12-way concurrent authorized setup → exactly 1 admin; token
via query-param or JSON body does NOT bypass (403); `GET /setup` → 405; header-case
variants still 403; **no cookies issued on any rejected `/setup`**; login/me/401 and
fail-closed safety posture all correct.

## Follow-up security fixes applied this pass

1. **Brute-force lockout was ineffective behind the k8s ingress** (keyed on the
   proxy pod IP, so counters fragmented across pods). FIXED:
   - `services/auth.py::client_ip()` resolves the real client from
     `X-Forwarded-For` (left-most hop) / `X-Real-IP`.
   - Login now maintains a **username-scoped** counter (`user:<name>`) in addition
     to `ip:<ip>:<name>`, so rotating source IPs cannot bypass the 5-attempt / 15-min
     lock. Verified through the ingress: 5 wrong → 6th (correct) → **429**; real
     client IP correctly recorded.
2. **Info disclosure** — `/api/auth/status` no longer returns `bootstrap_available`
   (only the non-sensitive `bootstrap_requires_token`).
3. **Cookie flags env-driven** — `set_auth_cookies`/`set_access_cookie` read
   `ARBICORE_COOKIE_SECURE` / `ARBICORE_COOKIE_SAMESITE` (default safe for the http
   preview; set `Secure` on direct-HTTPS prod). `/refresh` now reuses the shared
   helper (removed DRY drift).

