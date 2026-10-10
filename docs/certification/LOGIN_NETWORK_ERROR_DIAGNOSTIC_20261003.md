# Login "Network Error" Diagnostic (READ-ONLY) — 2026-10-03

- Status: **READ-ONLY diagnosis** — no remediations executed, no restarts, no config/RPC changes
- Timestamp: 2026-10-03T04:26Z (approx)
- Secrets: **none printed** (passwords/keys/tokens redacted; Alchemy path segments → `/v2/<REDACTED>`)

---

## Verdict

**Root cause: frontend API origin mismatch + CORS deny + SameSite=Lax cookies.**

Operator opens UI at `https://arbicorex.in` (or `www`), but the baked SPA calls
`https://144-91-78-175.sslip.io/api/...` with credentialed axios. Backend
`CORS_ORIGINS` allows only the sslip origin, so browser preflight on
`OPTIONS /api/auth/login` returns **400 Disallowed CORS origin** → axios
surfaces **"Network Error"**.

Backend itself is healthy; admin login and Network settings work via API when
called same-origin / from host localhost.

**Classification:** CORS / frontend API URL mismatch (not backend-down, not Traefik, not auth-service crash). Reverse proxy (Caddy) is fine. `arbicore-x-nginx` unhealthy is **not on the live path**.

---

## 1. Login API endpoint (frontend)

| Item | Evidence |
|---|---|
| Auth client | `app/frontend/src/context/AuthContext.jsx` → `client.post("/auth/login", …)` with `baseURL: API_BASE`, `withCredentials: true` |
| API base helper | `computeApiBase(REACT_APP_BACKEND_URL)` → `{BACKEND}/api` |
| Baked build value | Live FE bundle `main.dc5f82a3.js` contains `computeApiBase("https://144-91-78-175.sslip.io")` |
| Browser login URL | **`POST https://144-91-78-175.sslip.io/api/auth/login`** |
| Status probe | `GET …/api/auth/status`, session `GET …/api/auth/me` |

"Network Error" string is axios `ERR_NETWORK` (XHR `onerror` / CORS/fetch failure), shown via `err.message` on LoginPage.

---

## 2. Endpoint reachability

| Target | Result |
|---|---|
| `http://127.0.0.1:8001/api/auth/status` (in-container) | **200** `setup_complete=true` |
| Caddy → `arbicore-x-backend:8001/api/auth/status` | **200** |
| `https://144-91-78-175.sslip.io/api/auth/status` | **200** |
| `https://arbicorex.in/api/auth/status` | **200** |
| `https://api.arbicorex.in/api/auth/status` | **200** |
| `https://arbicorex.in/login` / sslip `/login` | **200** HTML SPA |
| `https://arbicorex.coinnike.com/*` | **unreachable** (DNS → 2.59.170.20; not in live Caddyfile) |
| Dummy login POST sslip | **401** `Invalid username or password` (auth path alive) |
| Admin login POST sslip / localhost | **200** + cookies `access_token`,`refresh_token` |

---

## 3. Container health / names

| Container | Status | Role |
|---|---|---|
| `arbicore-x-backend-new` | Up ~13h **healthy** · image `arbicore-x-backend:ws-a-befb14e-20261002` · `127.0.0.1:8001` | Prod API (compose `deployment/upgrade/compose/docker-compose.prod.yml` + override) |
| `81bc9a41f21f_arbicore-x-frontend` | Up ~4w **healthy** · `arbicore-x-frontend:0.1.0` | SPA (Caddy upstream `arbicore-x-frontend:80`) |
| `caddy` | Up · publishes 80/443 | **Live reverse proxy** (not Traefik) |
| `arbicore-x-nginx` | Up **unhealthy** (healthcheck `GET /nginx-health` → 404; empty `arbicore-x.conf`) | **Not in Caddy path**; NetworkMode `arbicore-x-net` only |

Caddyfile hosts for ArbiCore: `144-91-78-175.sslip.io`, `arbicorex.in`/`www`, `api.arbicorex.in` → `arbicore-x-backend:8001` + FE.

---

## 4. Frontend → backend API base URL (configured)

**Baked:** `REACT_APP_BACKEND_URL=https://144-91-78-175.sslip.io`  
→ **`API_BASE=https://144-91-78-175.sslip.io/api`**

Runtime FE container env has no `REACT_APP_*` (CRA bake-at-build).  
Backend `CORS_ORIGINS` (len=30) = **only** `https://144-91-78-175.sslip.io`.

---

## 5. Failure class (with log evidence)

Browser on `arbicorex.in` / `www.arbicorex.in` loads `/login` (200), then calls sslip API:

From `arbicorex.access.log` (recent window):

- Browser `GET /api/auth/status` Origin=`https://arbicorex.in` → server 200 (JS cannot use response without ACAO)
- Browser `OPTIONS /api/auth/login` Origin=`https://www.arbicorex.in` → **400**
- Probe/confirm: Origin `https://arbicorex.in` OPTIONS → body **`Disallowed CORS origin`**
- Origin `https://144-91-78-175.sslip.io` OPTIONS → **200** + `Access-Control-Allow-Origin: https://144-91-78-175.sslip.io`

Auth cookies on successful login: `HttpOnly; Path=/; SameSite=lax` (**no Secure** in observed Set-Cookie).  
Even if CORS were widened, **SameSite=Lax blocks cross-site credentialed XHR** from `arbicorex.in` → `sslip.io`. Durable fix requires **same-site** API (rebuild FE to `arbicorex.in` or `/api`, or use sslip UI).

**Not:** backend unavailable, Traefik, auth service down, Alchemy/RPC, nginx edge.

---

## 6. Settings → Network via API (UI login failing)

Using host/container env admin creds (**values not printed**):

| Call | Result |
|---|---|
| `POST /api/auth/login` (sslip + localhost) | **200** (cookies set) |
| `GET /api/arbicore/settings/network` | **200** |

Masked network config (excerpt):

- `revision_id`: `rev-615fa528802d4bd8ab7074b03bfdf373`
- `rpc_urls.base`: `["https://mainnet.base.org", "https://base-mainnet.g.alchemy.com/v2/<REDACTED>"]`
- `updated_at`: `2026-09-27T09:31:23Z` · `updated_by`: `admin`
- Matches prior PAYG discovery (public Base primary; stale Alchemy fallback)

**Conclusion:** Network settings are reachable via authenticated API today; UI gate is the broken browser login path from `arbicorex.in`.

---

## 7. Smallest safe remediation (DESCRIBE ONLY — not executed)

**Immediate (zero infra change):** open  
`https://144-91-78-175.sslip.io/login`  
Same origin as baked API + allowed CORS + Lax cookies → login should work; then Settings → Network → VALIDATE → APPLY.

**Durable (preferred for `arbicorex.in`):** rebuild/redeploy frontend with  
`REACT_APP_BACKEND_URL=https://arbicorex.in` **or** same-origin `/api`, so browser calls `https://arbicorex.in/api/...` (Caddy already proxies). Optionally align `CORS_ORIGINS` for apex+www if any absolute cross-subdomain remains. Mirror env for next recreate.

**Insufficient alone:** only adding `arbicorex.in` to `CORS_ORIGINS` while FE still posts to sslip — blocked by **SameSite=Lax**.

Do **not** change Alchemy/RPC to “fix login”; unrelated.

---

## 8. Is a restart required?

| Action | Restart needed? |
|---|---|
| Use sslip.io UI now | **No** |
| CORS_ORIGINS-only tweak | Backend recreate/restart to pick env — **still insufficient** alone |
| FE rebuild for `arbicorex.in` / `/api` | Frontend image rebuild + container recreate; **backend restart not required** for login restore |
| PAYG Network APPLY after login | Hot-load via apply/env_sync — **no restart** (per PAYG discovery) |

---

## Exact next command/action (operator — not run here)

```bash
# Fastest restore of admin UI (no restart):
# Open in browser:
#   https://144-91-78-175.sslip.io/login
# Then: Settings → Network → VALIDATE → APPLY (Alchemy PAYG)

# Optional API confirm (credentials from env; do not echo password):
# docker exec arbicore-x-backend-new python3 -c '
# import os,json,urllib.request,http.cookiejar,ssl
# ... login with ARBICORE_ADMIN_USER/PASS then GET /api/arbicore/settings/network ...'
```

---

## STOP

Diagnosis complete. No remediation executed.
