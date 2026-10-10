# S2-A Phase 2 — Production deployment (EXECUTED)

**Verdict: DEPLOYED_VERIFIED**  
**Completed (UTC):** `2026-10-09T11:45:01Z`  
**Authority:** explicit S2-A production-deployment-only authorisation (no key rotation).

Machine record: `S2A_PHASE2_DEPLOYMENT.json`

---

## 1. Preflight (passed)

| Check | Result |
|---|---|
| Approved image present | `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` = `sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` |
| Pre-deploy prod digest | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` (Hybrid-E) |
| Rollback pin | Tag `arbicore-x-backend:rollback-pre-s2a-redact` → same Hybrid-E digest |
| Controls pre-deploy | `SHADOW` / `AUTOEXEC=false` / `RUNTIME=false` |
| Legacy b7/h05/w1 | exited |
| Override delta | image + `ARBICORE_GIT_SHA` / `ARBICORE_GIT_TAG` only; all safety flags unchanged |

---

## 2. Deployment (backend-only recreate)

| Field | Value |
|---|---|
| Started (UTC) | `2026-10-09T11:42:04Z` |
| Finished (UTC) | `2026-10-09T11:42:32Z` |
| Compose | `docker-compose.prod.yml` + `/tmp/arbicore-s2a-rpc-redact-override.yml` |
| Command | `docker compose … up -d --no-deps --force-recreate backend` |
| Deployed digest | `sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` (**match**) |
| Health | `healthy` |
| API | `GET http://127.0.0.1:8001/api/` → `200` |
| Runtime identity | `ARBICORE_GIT_TAG=s2a-rpc-redact-5bd952568aed` / `ARBICORE_GIT_SHA=5bd952568aeda55bc90702289a9bfbfa9d6ba82c` |
| Controls post-deploy | `SHADOW` / `AUTOEXEC=false` / `RUNTIME=false` |
| Legacy | still exited |
| Rollback executed | **No** (not required) |

---

## 3. Redaction verification

### Synthetic (in running container)

`post_deploy_synthetic_regression.txt` — **PASS** (`synthetic_regression_ok`).  
Asserts full synthetic key and 12+ character fragments absent from redacted URL and captured httpx/httpcore log output; host + `[REDACTED]` preserved.

### Fresh production logs

| Field | Value |
|---|---|
| Observation window | `docker logs --since 5m` after recreate; scan end `2026-10-09T11:45:00Z` |
| httpx lines observed | 1183 |
| `/v2/[REDACTED]` markers | 1148 |
| Unredacted `alchemy.com/v2/<token>` hits | **0** |
| Raw token fp8s | none |
| Known live primary fp8 `24dab5d1` in fresh logs | **false** |

Sample (safe):

```
httpx - INFO - HTTP Request: POST https://base-mainnet.g.alchemy.com/v2/[REDACTED] "HTTP/1.1 200 OK"
```

Evidence: `post_deploy_log_scan.json`

---

## 4. Digest-pinned rollback (available, not used)

```bash
COMPOSE_DIR=/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml \
  up -d --no-deps --force-recreate backend
docker inspect arbicore-x-backend-new --format '{{.Image}}'
# MUST equal sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52
```

Alias: `arbicore-x-backend:rollback-pre-s2a-redact` (same digest).

---

## 5. Explicit exclusions (confirmed)

| Item | Status |
|---|---|
| Alchemy key rotation / revoke | **NOT EXECUTED** |
| P2 instrumentation | **NOT DEPLOYED** |
| Live trading / signing / broadcast / AUTOEXEC | unchanged disabled / SHADOW |
| Vault key / ciphertext | unchanged |
| RPC routing / retries / workers / risk / trading logic | unchanged (image is Hybrid-E + redaction only) |

---

## 6. Residual risk (post-deploy, pre-rotation)

- Keys remain in Mongo `network.rpc_urls` and ENV until a **separate** rotation authorisation.
- Pre-recreate Docker json-file history still contains raw URLs — keep access restricted; scrub only under separate approval.
- Exception objects that embed raw URLs in their own message text (not log `msg`/`args`) are outside the filter’s rewrite surface; dominant httpx INFO leak path is closed.

---

## Verdict

**DEPLOYED_VERIFIED**

Production backend-new is on the approved redaction digest, healthy, SHADOW controls preserved, synthetic regression passed, and fresh logs show Alchemy path credentials redacted with **zero** residual raw `/v2/<key>` hits in the observation window.

**Alchemy key rotation still requires separate explicit authorisation.**
