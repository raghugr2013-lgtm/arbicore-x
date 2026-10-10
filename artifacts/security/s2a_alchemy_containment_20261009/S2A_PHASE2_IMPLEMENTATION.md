# S2-A Phase 2 — Log redaction implementation

**Status:** Implementation + validation **COMPLETE** · Production deploy **EXECUTED** (see `S2A_PHASE2_DEPLOYMENT.md`)  
**Verdict: DEPLOYED_VERIFIED** (deployment record supersedes prior READY gate)  
**Timestamp (UTC):** `2026-10-09T11:35:56Z` (impl) / deploy completed `2026-10-09T11:45:01Z`  

Alchemy **key rotation is NOT authorised** by this document — see separate §6 plan only.

---

## 1. Minimal patch

### Files (identical intent in cert + v2 trees)

| Path | Change |
|---|---|
| `app/backend/arbicore/log_redaction.py` | **Added** — F2-B-LITE module + small robustness: skip %-format template `msg` redaction when `args` present (avoids breaking `getMessage()`); still redacts URL args and fully-formed messages |
| `app/backend/server.py` | **Wired** `install_credential_url_log_redaction()` immediately after `logging.basicConfig` (before any request path) |
| `app/backend/tests/test_log_redaction_credential_urls.py` | **Added** — synthetic-credential regression tests |

**sha256:**

| File | sha256 |
|---|---|
| `log_redaction.py` | `5e28dfb54c73bf21a886344b6da4bcb55ceb442e28c08656d01255610ab513c6` |
| `test_log_redaction_credential_urls.py` | `2c6ca3d2134e5f4607556d1723e9242266e22ae2de9f574889ac41f3af54757b` |

### Diff summary (approved scope only)

`server.py` hunk (v2):

```diff
 logging.basicConfig(
     level=logging.INFO,
     format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
 )
+# httpx logs full request URLs at INFO; Alchemy (and similar) put API keys in
+# the path (/v2/<key>). Install a URL-aware filter so credentials never reach
+# log handlers. Does not alter RPC endpoints, keys, or request behavior.
+try:
+    from arbicore.log_redaction import install_credential_url_log_redaction
+    install_credential_url_log_redaction()
+except Exception:  # noqa: BLE001
+    pass
 logger = logging.getLogger(__name__)
```

No RPC routing, workers, retries, risk, vault, or trading-logic files touched.

### Installation point

Hybrid-E / current `server.py` configures logging once via `logging.basicConfig(INFO)`. Redaction installs **immediately after** that call so root + `httpx` / `httpcore` / `urllib3` / `aiohttp` / `web3` filters are active before uvicorn serves traffic. Covers httpx INFO lines, exception/retry messages that embed URLs in `msg` or `args`, and fallback diagnostics on those loggers.

---

## 2. Test results

```
tests/test_log_redaction_credential_urls.py  ........  8 passed
tests/test_quoter_eth_call_429_amplification.py (-k redact/secret/URL/log)  1 passed
```

Assertions use synthetic tokens only (`SYNTHETIC_ALCHEMY_KEY_DO_NOT_USE_…`). Tests fail if the full synthetic key **or** any 12+ character contiguous fragment appears in captured logs. Hostnames and `[REDACTED]` markers are preserved.

Evidence: `pytest_log_redaction.txt`.

---

## 3. Prepared image (built locally — **not** running in production)

| Field | Value |
|---|---|
| Tag | `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` |
| Image ID / manifest | `sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` |
| Base | `arbicore-x-backend:hybrid-e-rpc-9244ebd` @ `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| Build method | Thin Dockerfile `FROM` Hybrid-E + COPY `log_redaction.py` + patched `server.py` |
| Source HEAD (v2) | `5bd952568aeda55bc90702289a9bfbfa9d6ba82c` (**dirty** with S2-A patch; not a committed SHA of the patch itself) |
| Production container | **Unchanged** — still Hybrid-E `40b2116b…`, healthy, SHADOW |

Image smoke: module present; synthetic URL → `https://base-mainnet.g.alchemy.com/v2/[REDACTED]`.

---

## 4. Proposed deployment commands — **NOT EXECUTED**

Preserve: `SHADOW`, `AUTOEXEC=false`, `RUNTIME=false`, legacy stopped, no P2, no vault changes.

```bash
# --- PRECHECK (read-only) ---
docker inspect arbicore-x-backend-new --format 'Image={{.Image}} Health={{if .State.Health}}{{.State.Health.Status}}{{end}}'
docker exec arbicore-x-backend-new sh -c 'printf "%s %s %s\n" "$ARBICORE_EXECUTION_MODE" "$ARBICORE_AUTOEXEC_AUTOSTART" "$ARBICORE_RUNTIME_AUTOSTART"'
# expect: SHADOW false false
# expect Image=sha256:40b2116b…

# --- OPTIONAL: pin rollback tag (idempotent) ---
docker tag arbicore-x-backend:hybrid-e-rpc-9244ebd arbicore-x-backend:rollback-pre-s2a-redact

# --- WRITE override for redaction image (do not start yet) ---
# Copy current override and change only the backend image line:
#   image: arbicore-x-backend:s2a-rpc-redact-5bd952568aed
# Keep all SHADOW / AUTOEXEC / RUNTIME env from /tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml

COMPOSE_DIR=/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
# Example (operator prepares file, reviews, then):
# docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml \
#   up -d --no-deps --force-recreate backend

# --- POSTCHECK ---
# docker inspect arbicore-x-backend-new --format 'Image={{.Image}} Health={{if .State.Health}}{{.State.Health.Status}}{{end}}'
# expect Image=sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313
# docker logs --since 5m arbicore-x-backend-new 2>&1 | grep -c 'alchemy.com/v2/[^[]'   # expect 0 raw keys
# docker logs --since 5m arbicore-x-backend-new 2>&1 | grep -c 'alchemy.com/v2/\[REDACTED\]'  # expect >0 after traffic
```

### Digest-pinned rollback — **NOT EXECUTED**

```bash
COMPOSE_DIR=/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
# Restore Hybrid-E override (existing):
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml \
  up -d --no-deps --force-recreate backend

# Verify digest pin:
docker inspect arbicore-x-backend-new --format '{{.Image}}'
# MUST equal sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52
```

If tag `hybrid-e-rpc-9244ebd` were retagged, use digest reference in override:

```yaml
services:
  backend:
    image: arbicore-x-backend@sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52
```

---

## 5. Posture at end of implementation task

| Control | Value |
|---|---|
| Production image | Still `hybrid-e-rpc-9244ebd` / `40b2116b…` |
| Mode | SHADOW |
| AUTOEXEC / runtime | false / false |
| Legacy b7/h05/w1 | exited |
| P2 | not deployed |
| Vault | unchanged |
| Credentials | not rotated |

---

## 6. Separate Alchemy key-rotation plan (NOT AUTHORISED / NOT EXECUTED)

Execute only after redaction is **live** in production and a follow-on written approval.

### Replacement inventory (prepare before revoke)

| Current fp8 | Location | Replacement action |
|---|---|---|
| `24dab5d1` | Mongo `network` primary (all chains) — **actively logged** | Create new Alchemy key(s); update Mongo `rpc_urls` index 0 |
| `e315c86f`, `dc432a6b`, `6e67e161`, `cd505118`, `124bc59c` | Mongo fallbacks | Replace each or collapse list per operator policy |
| `5e5d5bb1` | ENV bootstrap / archive / per-chain ENV | Update `.env` after Mongo cutover |
| `ce00e63d`, `ff5eb596` | Legacy (stopped) historical | Revoke in Alchemy dashboard if still present |

### Procedure (high level)

1. In Alchemy UI: create labeled replacement keys; **never paste into chat/git**.  
2. Stage new URLs in a private operator note; validate format `https://<host>/v2/<newkey>`.  
3. Under change control: update Mongo `arbicore_config` `_id=network` `rpc_urls` then ENV bootstrap vars.  
4. Recreate backend-new on **redaction** image (already deployed).  
5. Confirm logs show only `/v2/[REDACTED]`; spot-check chain heads.  
6. Revoke old fps in Alchemy; confirm rejected auth without logging raw URLs.  
7. Keep historical Docker logs restricted (contain pre-redaction secrets); do not broadly publish.

**Stop / BLOCKED for rotation if:** no Alchemy UI access, cannot create replacements, or rollback would require re-enabling non-redacted image without accepting residual log risk.

---

## 7. Residual risk until deploy + rotate

- Production **still leaks** fp8 `24dab5d1` via httpx until recreate onto `s2a-rpc-redact-5bd952568aed`.  
- Even after redaction, keys remain in Mongo/ENV until rotated.  
- Pre-patch Docker json-file history retains raw URLs — restrict access; scrub only under separate approval.

---

## 8. Approvals still required

1. **Deploy** recreate `arbicore-x-backend-new` onto `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` (`sha256:69fe2459e0…`) with SHADOW flags unchanged.  
2. **Optional later:** Alchemy key rotation/revocation per §6.

---

## Verdict

**READY FOR DEPLOYMENT AUTHORISATION**

Patch is minimal, tested, imaged, and digest-pinned with a Hybrid-E rollback. Production was **not** modified. Key rotation remains a separate gated step.
