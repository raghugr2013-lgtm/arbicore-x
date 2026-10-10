# R2-DISABLE — Bootstrap token removal (execution report)

**Verdict: PASS**  
**Overall security gate / P2: still BLOCKED** (R3–R6 not started)  
**Report UTC:** `2026-10-10T09:12:40Z` (final verify)  
**Artifact dir:** `artifacts/security/r2_bootstrap_disable_20261010T090646Z/`  
**Preflight:** `artifacts/security/r2_bootstrap_preflight/R2_BOOTSTRAP_PREFLIGHT.md`

Authority: explicit **R2-DISABLE** authorisation (token removal only).

---

## What changed

| Step | Result |
|---|---|
| Backup | `/home/raghu/arbicore_backups/r2_bootstrap_disable_20261010T090646Z/backend.env.pre-disable` mode **0600** · sha256 `725041f2…d63f` |
| Edit | Removed sole `ARBICORE_BOOTSTRAP_TOKEN=` line from live `…/upgrade/backend/.env` (mode **0600** retained) |
| Recreate | `docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml up -d --no-deps --force-recreate --pull never backend` |
| Image | **Unchanged** `arbicore-x-backend:s2a-rpc-redact-5bd952568aed` · digest `sha256:69fe2459e0021bbd3a90b7e4cda617cbeb45a8b41861f9ed0f6b8df8e7315313` |
| Healthy | `running healthy` ~18s after start |

No Mongo, Caddy, Alchemy, admin/JWT, deployer, source, or P2 changes. Historical `/tmp` and backup copies **not** scrubbed (out of scope).

---

## Acceptance (`verify.json`)

| Check | Result |
|---|---|
| Digest unchanged | **PASS** |
| Bootstrap absent from container ENV | **PASS** |
| Bootstrap absent from live `.env` | **PASS** |
| `POST /api/auth/setup` (valid body) local + public | **503** fail-closed |
| `GET /api/` | **200** |
| Admin login local + `api.arbicorex.in` | **200** |
| `GET /api/auth/me` (session) | **200** |
| R1 `/docs` `/openapi.json` on three hosts | **404** |
| R1 `/api/` | **200** |
| SHADOW / AUTOEXEC=false / RUNTIME=false | **PASS** |
| Alchemy primary fps (Mongo + dotenv) | **`ca6545ba`** all six chains |
| Mongo fallbacks `[1..5]` | **`e315c86f`…`124bc59c` unchanged** |
| Legacy b7/h05/w1 | **Exited** |
| g5.79 | Up, untouched |
| `sendRawTransaction` 15m | **0** |

---

## Rollback (if needed)

```bash
BACKUP=/home/raghu/arbicore_backups/r2_bootstrap_disable_20261010T090646Z/backend.env.pre-disable
ENVF=/home/raghu/projects/arbicore-x-v2/deployment/upgrade/backend/.env
cp -a "$BACKUP" "$ENVF"
chmod 600 "$ENVF"
cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose
docker compose -f docker-compose.prod.yml -f /tmp/arbicore-s2a-rpc-redact-override.yml \
  up -d --no-deps --force-recreate --pull never backend
```

Do **not** pull/rebuild; confirm digest `69fe2459…` after rollback.

---

## Residual: historical token copies (not scrubbed)

Preflight inventory still applies. Live path is clean; copies remain at (non-exhaustive):

- Local `.env.*` backups under `arbicore-x-v2/deployment/upgrade/backend/`
- Approved archives under `/home/raghu/arbicore_backups/s1b_*` and `s2a_alchemy_cutover_*`
- Many `/tmp/arbicore-*.env` and worktree memory backups
- Stopped legacy container Config.Env (same sha12 historically)

**Proposed separate cleanup plan (not authorised here):** see `HISTORICAL_COPY_CLEANUP_PROPOSAL.md` in this directory.

---

## GO / BLOCKED

| Gate | Decision |
|---|---|
| **R2-DISABLE** | **PASS / GO** |
| R3–R6 | **BLOCKED** (not authorised) |
| Overall security gate / P2 | **BLOCKED** |

Stopped for human review.
