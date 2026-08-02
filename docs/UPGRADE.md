# ArbiCore X — UPGRADE.md (Backend-only Realignment)

**Use this when:** an ArbiCore X VPS already runs a prior backend + Mongo, and you want to swap the backend image for a newer version **without touching Mongo, data, indexes, or scanner state**.

**Do NOT use this for:** fresh installs (use `docs/INSTALL.md` instead), destructive full restores (use `docs/BACKUP_RESTORE.md`), or the first-ever build of a VPS (use `docs/INSTALL.md`).

**Guaranteed properties (from the audited realignment toolkit, doc 15 sign-off):**

- MongoDB container + `arbicore-x-mongo-data` volume are **never** touched.
- OLD backend container is **stopped, never removed** — rollback = `docker start OLD`.
- Preserves running scanners (`cex_arb`, `funding_arb`) via env flags baked in step 00.
- Three-layer safety: cutover ERR trap + canary auto-rollback + operator manual rollback.

---

## 0. Prerequisites

- The VPS already runs an ArbiCore X backend + Mongo (`docker ps` shows both).
- Operator has Docker access on the VPS.
- The updated `app/backend/` source is present in the bundle (via `git pull` or fresh bundle drop).

## 1. Prepare

```bash
cd /opt/arbicore-x
# Ensure the bundle is up to date (app/backend now contains the target version):
git pull   # or scp the new bundle over the old one

# Stage the backend source into the realignment toolkit's build slot:
cp -a app/backend/. deployment/upgrade/backend/
```

`backend/README.md` inside the toolkit describes exactly what must be present. Step `01_preflight.sh` will hard-fail if `arbicore/intel/launch/labels.json` is missing.

## 2. Safe execution (recommended — stops before build)

```bash
./scripts/upgrade.sh safe
```

This runs, in order:

| Step | Script | What it does | Destructive? |
|---|---|---|---|
| 00 | `00_detect_env.sh` | Auto-detects OLD backend, Mongo, network, env from live containers | No |
| 01 | `01_preflight.sh` | Sanity gate: mongo up, source staged, no name collision | No |
| 02 | `02_backup.sh` | **Mandatory** mongodump --gzip + counts + OpenAPI snapshot; aborts on tiny archive | No |
| 03 | `03_index_audit.sh` | Read-only index conflict report | No |

Then STOPS and prints continuation instructions. Review each log:

- `deploy.env`, `compose/.env`, `backend/.env` — the auto-detected env
- `${LOG_DIR}/env_parity_*.txt` — verify all OLD application env vars carried over
- `${BACKUP_DIR}/preupgrade_*.archive.gz` — the rollback anchor (KEEP THIS OFF-HOST too)
- `${LOG_DIR}/index_audit_*.log` — flags any REVIEW-worthy indexes

## 3. Optional: expired discovery queue cleanup (OPT-IN)

Only if the `arbicore_discovery_candidates` collection has a large expired backlog and you want to trim it before cutover. Non-durable queue rows only.

```bash
cd deployment/upgrade
make cleanup   # requires --confirm on the underlying script
```

**Skip this step for a maximally conservative first realignment.**

## 4. Build (still zero downtime)

```bash
cd deployment/upgrade
make build
```

Builds `arbicore-x-backend:0.1.0-realign-<gitsha>`. The OLD backend keeps serving traffic.

## 5. Cutover (the only downtime — seconds)

```bash
make cutover
```

Sequence:

1. Snapshot OLD container inspect → `${LOG_DIR}/old_backend_state_*.json`
2. `docker stop OLD` (container preserved, not removed)
3. `docker compose up -d backend` (NEW attached to existing Mongo network)
4. Wait ≤ 60 s for `/api/` to return 200
5. Verify `/api/arbicore/*` is present in `openapi.json` (correct build check)

Auto-rollback if any step fails: `docker compose down` NEW, `docker start` OLD.

## 6. Canary (60 s read-only probe)

```bash
make canary
```

Threshold-driven abort:

- `CANARY_MAX_CONSEC_FAIL=3` (defaults) — 3 back-to-back failures triggers rollback
- `CANARY_MAX_FAIL_PCT=20` — > 20 % failure rate over the 60 s window triggers rollback
- Auto-rollback invokes `99_rollback.sh` unless `CANARY_AUTO_ROLLBACK=no`

## 7. Validate (acceptance)

```bash
make validate
```

Checks:

- `arbicore_scanner_config` = 6, `arbicore_scanner_state` = 6
- `cex_arb` + `funding_arb` `enabled:true`
- `arbicore_opportunities` count ≥ pre-upgrade (preserved)
- TTL indexes `ttl_30d`, `ttl_90d` present
- Pre vs post count delta report

## 8. Snapshot (observability)

```bash
make snapshot
```

Point-in-time collection counts + scanner state. Safe to run repeatedly post-upgrade.

## 9. If something's wrong

See `docs/ROLLBACK.md`. Short version:

```bash
cd /opt/arbicore-x/deployment/upgrade
make rollback
```

This runs `99_rollback.sh` — `docker compose down` (NEW), `docker start` (OLD). Mongo is never touched.

## 10. After a successful realignment

- The OLD backend container is **left stopped** on the VPS for ≥ 72 h. Do not `docker rm` it — it's your instant rollback anchor.
- The pre-cutover archive at `${BACKUP_DIR}/preupgrade_*.archive.gz` is the disaster-recovery anchor. Move it off-host (e.g. `rclone` in step 8b of `INSTALL.md`).
- Update `DEPLOYMENT_MANIFEST.md` with the new backend image tag + git SHA on the VPS.

---

## Reference documents (byte-verbatim from the audited toolkit)

- `deployment/upgrade/EXECUTION_ORDER.md` — the canonical execution order (this file paraphrases it).
