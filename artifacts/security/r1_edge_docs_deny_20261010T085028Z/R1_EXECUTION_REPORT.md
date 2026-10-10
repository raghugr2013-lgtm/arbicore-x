# R1 — Public documentation edge denial (execution report)

**Verdict: PASS**  
**Overall security gate / P2: still BLOCKED** (R2–R6 not started)  
**Report UTC:** `2026-10-10T08:56:11Z`  
**Artifact dir:** `artifacts/security/r1_edge_docs_deny_20261010T085028Z/`

Authority: R1-only authorisation (Caddy edge deny). No Mongo, credential, Alchemy, deployer, app, P2, or control-plane changes.

---

## Executive summary

Public `/docs`, `/redoc`, and `/openapi.json` now return **404** on:

- `https://144-91-78-175.sslip.io/…`
- `https://arbicorex.in/…` / `www` (same Caddyfile site block)
- `https://api.arbicorex.in/…` (**true FastAPI** Swagger/OpenAPI path)

`/api/` remains **200** on all three hosts. Backend image digest **unchanged**. S2-A primary fps still `ca6545ba`. SHADOW / AUTOEXEC=false / RUNTIME=false preserved. Legacy stopped. g5.79 untouched.

---

## Phase 1 — Pre-change

| Item | Result |
|---|---|
| Live config | `/opt/caddy/Caddyfile` bind-mounted RO into container `caddy` (`caddy:2-alpine`) |
| Compose | `/opt/caddy/docker-compose.yml` · project `caddy` · network `vqb-network` |
| Site identity | `144-91-78-175.sslip.io` → `/api/*` to `arbicore-x-backend` (= `arbicore-x-backend-new`); catch-all → frontend |
| Sibling ArbiCore sites in same file | `arbicorex.in` / `www`; `api.arbicorex.in` (catch-all → backend — **real FastAPI docs**) |
| Unrelated sites unchanged | `strategy.coinnike.com`, `foreman.coinnike.com` (no deny handlers added) |
| Baseline public probes | All listed docs URLs **200**; `/api/` **200** (`probes_before.json`) |
| Discovery note | On sslip.io / arbicorex.in, baseline `/docs` was **SPA HTML via frontend nginx**, not uvicorn. True FastAPI `/docs` + OpenAPI JSON were on **`api.arbicorex.in`** and localhost `:8001`. |
| Backup | `/opt/caddy/Caddyfile.pre-r1-docs-deny-20261010T085028Z` mode `0600` |
| Backup sha256 | `8a1cb3bdca34c181be558304c2c5c351ede4eb5ddf342b39731adc79aa965d47` |
| Pre-apply validate | `caddy validate` on proposed file → **Valid configuration** |

**Rollback command** (also in `rollback.sh`):

```bash
docker run --rm -v /opt/caddy:/opt/caddy:rw alpine:3.20 \
  sh -c 'cat /opt/caddy/Caddyfile.pre-r1-docs-deny-20261010T085028Z > /opt/caddy/Caddyfile'
cd /opt/caddy && docker compose up -d --force-recreate
```

(Use in-place `cat >` so the bind-mount inode stays stable; then recreate/reload caddy.)

---

## Phase 2 — Apply

| Step | Result |
|---|---|
| Minimal change | `handle /docs*`, `/redoc*`, `/openapi.json` → `respond "Not Found" 404` on the three ArbiCore site blocks; `api.arbicorex.in` wrapped so deny precedes reverse_proxy |
| First apply attempt | Host file replaced via `cp` → **new inode**; running container kept **old inode** (RO mount). Reload appeared to succeed but served pre-change config. |
| Correction | In-place write of proposed content; **`docker compose up -d --force-recreate`** for **caddy only** to remount. Backend **not** recreated. |
| Post-recreate validate | **Valid configuration**; host sha256 = container sha256 `125d2b721a545aaf3c2b852639ff1ff9bc2f4a79df167a087c244b2409f491ba` |

Redacted diff: `Caddyfile.diff` (deny handlers only; factory/foreman untouched).

---

## Phase 3 — Acceptance (`probes_after.json` @ `2026-10-10T08:55:47Z`)

| Check | Result |
|---|---|
| Public sslip.io `/docs`, `/docs/`, `/redoc`, `/openapi.json` | **404** |
| Public api.arbicorex.in same | **404** (FastAPI surface closed at edge) |
| Public arbicorex.in docs paths | **404** |
| `/api/` on all three hosts | **200** |
| Backend digest before/after | `sha256:69fe2459…e7315313` · **unchanged** |
| Image tag | `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` |
| Live dotenv Alchemy fps | primary `ca6545ba` only (fallbacks not in dotenv map; S2-A retain policy unchanged) |
| SHADOW | `ARBICORE_EXECUTION_MODE=SHADOW` |
| AUTOEXEC | `ARBICORE_AUTOEXEC_AUTOSTART=false` |
| RUNTIME | `ARBICORE_RUNTIME_AUTOSTART=false` |
| `sendRawTransaction` 30m | **0** |
| Legacy b7/h05/w1 | **Exited** |
| g5.79 | Up, untouched |

**Limitation (documented, not R1 FAIL):** `http://127.0.0.1:8001/docs` and `/openapi.json` still **200** (direct to backend). Edge deny does not cover localhost. App-level `docs_url=None` remains a later defense-in-depth item (would require image change — out of R1 scope).

---

## Scope confirmation

| Prohibited | Done? |
|---|---|
| Mongo / bootstrap / admin / JWT / Alchemy revoke / deployer | **No** |
| App source / image rebuild / digest change | **No** |
| P2 deploy | **No** |
| R2–R6 | **No** |
| Control flags / legacy start / g5.79 | **No** |

---

## GO / BLOCKED

| Gate | Decision |
|---|---|
| **R1 public docs edge deny** | **PASS / GO** |
| R2–R6 | **BLOCKED** (not authorised) |
| Overall security gate / P2 reconsider | **BLOCKED** |

Stopped for human review.
