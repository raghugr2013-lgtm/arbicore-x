# Network Settings — "Validation error" Diagnostic (READ-ONLY) — 2026-10-03

- **Status:** **READ-ONLY diagnosis complete** — no APPLY, no Mongo Network Config mutation, no production RPC/env changes, no risk-setting changes, no product-code changes, validation rules untouched
- **Operator failure window (UTC):** 2026-10-03T10:01:18Z – 10:03:34Z
- **Reproduction window (UTC):** 2026-10-03T10:10Z / reconfirm 2026-10-03T10:25Z
- **Container:** `arbicore-x-backend-new` · image `arbicore-x-backend:ws-a-befb14e-20261002`
- **UI host (operator):** `https://144-91-78-175.sslip.io` (same-origin)
- **Secrets:** Alchemy keys shown only as `/v2/<REDACTED:fp=sha256(key)[:8]>`. Passwords/cookies never printed.

**Related:** `LOGIN_NETWORK_ERROR_DIAGNOSTIC_20261003.md`, `ALCHEMY_PAYG_POST_APPLY_VERIFICATION_20261003.md`.

---

## Evidence trace (1–10) — BEFORE any fix

### 1. Frontend validation request

| Field | Evidence |
|---|---|
| UI action | Settings → Network → **VALIDATE** (`data-testid=v2-settings-network-validate`) |
| Source | Live FE bundle `main.dc5f82a3.js` contains strings `network/validate`, `Validation error`, `Validation failed` |
| Repo (matches live toast) | `app/frontend/src/v2/pages/SettingsPage.jsx` → `Network.validate()` |
| Client | `app/frontend/src/v2/lib/api.js` → `networkValidate(form)` |
| Method / content-type | `POST` · `application/json` |
| Body | Full Network Settings **form** (React state clone of `config`) |
| Toast that operator saw | `catch { toast.error("Validation error"); }` — thrown HTTP/axios path only |
| Soft-fail toast (not observed) | `toast.error(\`Validation failed — ${r.errors.length} error(s)\`)` when HTTP 200 and `r.ok === false` |

Caddy proves the browser request:

- Host: `144-91-78-175.sslip.io`
- Origin: `https://144-91-78-175.sslip.io`
- Referer: `https://144-91-78-175.sslip.io/dashboard/settings/network`
- Cookie header: **present**
- Payload sizes: **1834 / 1708 / 1712** bytes

---

### 2. Exact API endpoint

```
POST /api/arbicore/settings/network/validate
```

Full browser URL: `https://144-91-78-175.sslip.io/api/arbicore/settings/network/validate`

Mounted via FastAPI `api_router` under `/api` prefix.

---

### 3. HTTP status

| Attempt (UTC) | Status |
|---|---:|
| 2026-10-03T10:01:18.163Z | **401** |
| 2026-10-03T10:02:53.225Z | **401** |
| 2026-10-03T10:03:34.037Z | **401** |

Source: Caddy `arbicorex.access.log` + backend uvicorn access log (`401 Unauthorized` ×3).

---

### 4. Response body

Operator responses: Caddy `size=30` on each 401.

Exact body (reproduced unauthenticated against live container; same 30-byte payload):

```json
{"detail":"not_authenticated"}
```

Reconfirmed 2026-10-03T10:25Z: `UNAUTH_BODY 401 {"detail":"not_authenticated"}`.

This is **not** a schema validation payload (`ok`/`errors`/`warnings`). Auth dependency rejects before `NetworkConfigRepo.validate()` runs.

---

### 5. Backend validation handler (function / file)

**Route (deployed `/app/server.py`):**

```
5966:@api_router.post("/arbicore/settings/network/validate",
                   dependencies=[Depends(_require_operator_dep)])
5967:async def v2_settings_network_validate(patch: Dict[str, Any]) -> Dict[str, Any]:
5968:    return {**_NETWORK_CONFIG.validate(patch or {}),
             "generated_at": _iso_now()}
```

**Auth gate (must pass first):** `_require_operator_dep` → `_require_operator_ctx` → `_resolve_current_user`  
On failure: `HTTPException(401, detail="not_authenticated")` (`server.py` ~624–637).

**Schema validator (never reached on operator 401s):**  
`NetworkConfigRepo.validate()` · `/app/arbicore/config/persistent.py:293`  
Schema-only (URL prefix, chain allowlist, executor/gas types). **Does not** call RPC JSON-RPC methods.

---

### 6. Backend logs

Uvicorn (`arbicore-x-backend-new`):

```
POST /api/arbicore/settings/network/validate HTTP/1.1" 401 Unauthorized   # ×3 (operator, via Caddy 172.18.0.8)
```

Earlier same day (PAYG window, authenticated):

```
POST /api/arbicore/settings/network/validate HTTP/1.1" 200 OK   # 2026-10-03T04:53:21Z
```

No validate-handler exception stack for the 401s — rejection is the auth dependency.

**Session timeline (same client IP `152.57.78.112`):**

| UTC | Event |
|---|---|
| 09:13:15Z | `POST /api/auth/login` **200** |
| 09:13:35Z | `GET /api/arbicore/settings/network` **200** |
| ~09:43Z | Access JWT TTL expires (`ACCESS_TTL_MIN=30` in `/app/services/auth.py`) |
| 10:01–10:03Z | VALIDATE ×3 → **401** |

`_resolve_current_user` swallows canonical `HTTPException` (e.g. expired token) and returns `None`, so the surface detail is always `not_authenticated`.

---

### 7. Affected network

| Field | Value |
|---|---|
| Chain intended by UI / config | **base** (`chains_enabled.base=true`; others false) |
| Validate path effect | **None** — auth failed; no chain-specific schema/RPC evaluation |
| Soft “affected network” for toast | **N/A (auth)** |

Live Mongo Network Config revision at diagnosis: `rev-7c93bb93e65b4f5a9b7340bf513437c0` (updated 2026-10-03T04:57:17Z by `admin`).

---

### 8. Actual RPC endpoint (redacted)

From live `GET /api/arbicore/settings/network` → `config.rpc_urls.base`:

| Index | Role | Redacted URL |
|---:|---|---|
| 0 | PRIMARY | `https://base-mainnet.g.alchemy.com/v2/<REDACTED:fp=cd505118>` |
| 1 | FALLBACK | `https://mainnet.base.org` |

Other five chains: no Mongo RPCs / disabled. Fingerprint `cd505118` matches PAYG post-APPLY verification.

---

### 9. Direct RPC probe (same methods ArbiCore uses elsewhere)

**Note:** Network Settings `validate` itself does **not** probe RPCs. Probes use the same JSON-RPC methods ArbiCore uses for RPC readiness / wizard health (`eth_chainId`, `eth_blockNumber` — see `operator_wizard.py`, `technical_validation.py`, `GET /arbicore/rpc/check`).

Reconfirm from VPS (2026-10-03T10:25Z):

| Endpoint | Method | HTTP | Result |
|---|---|---:|---|
| Alchemy Base `…/v2/<REDACTED:fp=cd505118>` | `eth_chainId` | **200** | `0x2105` (8453) |
| Alchemy Base same | `eth_blockNumber` | **200** | `0x31b3da7` |
| `https://mainnet.base.org` | `eth_chainId` | **403** | `error code: 1010` |
| `https://mainnet.base.org` | `eth_blockNumber` | **403** | `error code: 1010` |

Primary healthy. Fallback 403 is a **separate** failover concern and **did not** produce the VALIDATE toast (auth never passed).

**Authenticated schema validate of live config (control):** HTTP **200**  
`{"ok":true,"errors":[],"warnings":["no executor address configured for chain 'base' — LIMITED_LIVE flow will BLOCK"],…}`

---

### 10. Exact root cause

**Root cause:** Operator session **access JWT expired** (30-minute TTL) after login at 09:13Z. VALIDATE requests at 10:01–10:03Z carried cookies that no longer authenticated → `_require_operator_dep` returned **401** `{"detail":"not_authenticated"}` → FE `catch` toasted **`"Validation error"`**.

**Supporting facts:**

1. Toast string is exclusively the axios exception path, not soft `{ok:false}`.
2. Response body is auth detail, not validation `errors[]`.
3. Login→VALIDATE gap (~48 min) exceeds `ACCESS_TTL_MIN=30`.
4. `GET /api/arbicore/settings/network` is unauthenticated on live image, so the Network page still loads with a dead session.
5. Fresh admin login + same live config → VALIDATE **200 / ok:true**.

**Classification:** auth-provider / session expiry + FE error-label masking.  
**Not:** invalid RPC URL, RPC HTTP error on validate path, chain ID mismatch, unsupported method, timeout, Base fallback 403 as toast cause, six-network env_sync mismatch, schema validation rule failure.

---

## Summary table

| # | Item | Evidence result |
|---:|---|---|
| 1 | FE request | Browser POST from sslip Settings Network; toast = catch `"Validation error"` |
| 2 | Endpoint | `POST /api/arbicore/settings/network/validate` |
| 3 | HTTP status | **401** (×3) |
| 4 | Response body | `{"detail":"not_authenticated"}` |
| 5 | Handler | `v2_settings_network_validate` (`server.py:5966`) → gated by `_require_operator_dep`; schema via `NetworkConfigRepo.validate` (`persistent.py:293`) |
| 6 | Backend logs | `401 Unauthorized` ×3; prior PAYG validate `200` |
| 7 | Network | **base** (intended); validate logic not reached |
| 8 | RPC (redacted) | Primary `base-mainnet.g.alchemy.com/v2/<REDACTED:fp=cd505118>`; fallback `mainnet.base.org` |
| 9 | RPC probes | Primary OK (8453); fallback 403/1010 (unrelated to toast) |
| 10 | Root cause | Expired access session → 401 → FE mislabeled as Validation error |

---

## Remediation recommendation — **NOT EXECUTED**

**Immediate (ops):** Re-login at `https://144-91-78-175.sslip.io/login`, then Settings → Network → VALIDATE within 30 minutes. Expect HTTP 200 / `ok:true` (executor warning only unless filled).

**Durable (product, later):** On VALIDATE 401, call `POST /api/auth/refresh` once or toast “Session expired — please log in”; do not label auth failures as “Validation error”. Optional: auth-gate GET network. Do **not** weaken validation, bypass auth, or APPLY config to clear this toast.

**Separate (not this toast):** Investigate `mainnet.base.org` 403/1010 for failover health — probe/policy only; no APPLY here.

---

## STOP

Diagnosis complete. Evidence above precedes any fix. No APPLY. No configuration or product-code changes. No validation-rule changes.
