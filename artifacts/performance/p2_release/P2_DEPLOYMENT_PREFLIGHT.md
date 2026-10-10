# P2 Deployment Preflight

**Status:** Plan only — **no deploy executed**.  
**Date:** 2026-10-09  
**Final disposition:** **READY FOR EXPLICIT DEPLOYMENT AUTHORISATION**

Related package docs: `P2_FINAL_REVIEW.md`, `P2_RELEASE_MANIFEST.md`, `P2_DIFF_AUDIT.md`, `P2_TEST_RESULTS.md`, `P2_RELEASE_CHECKSUMS.txt`.

---

## 1. Target verification

### Canonical repository / branch / HEAD

| Item | Value |
|---|---|
| Repository | `/home/raghu/projects/arbicore-x-cert` |
| Branch | `cert/gate7-dynamic-profitability-20261007` |
| HEAD | `9244ebdee6a95188d925084e7e10d4a972cda7ad` |
| HEAD subject | `fix(quoter): host-scoped 429 cooldown with bounded retry and A→F failover` (2026-10-08) |
| Working tree | **Dirty** (P2 edits + unrelated `queue_status`/scanner/frontend/ledger/etc.) |

### Patch base alignment

| Check | Result |
|---|---|
| Intended patch base | `9244ebdee6a95188d925084e7e10d4a972cda7ad` |
| Repo HEAD equals base | **Yes** |
| Combined patch SHA-256 | `56739a3d65470f61abfe3becfdf5a929576c41ce4ddc0a8bdd80615395690669` |
| Matches `P2_RELEASE_CHECKSUMS.txt` | **Yes** (recomputed match) |

### Seven approved files (patch scope)

1. `app/backend/arbicore/data/discovery_queue.py` (P2 durable-`claimed_at` only)
2. `app/backend/arbicore/models/discovery.py`
3. `app/backend/arbicore/scanners/flash_loan_arbitrage/verifier.py`
4. `app/backend/arbicore/data/mongo/evidence_bundles_repo.py`
5. `app/backend/tests/test_flashloan_diagnostic_provenance.py`
6. `app/backend/tests/test_p2_flashloan_timing_instrumentation.py`
7. `app/backend/tests/test_p2_evidence_persisted_mongo.py`

**Confirmed absent from patch:** `fresh_eligible`, `per_chain_backlog`, `per_strategy_backlog`.

### Critical packaging rule

- **Do not** `git add` / commit / build from the dirty working-tree `discovery_queue.py`.
- Apply `artifacts/performance/p2_release/P2_ONLY_COMBINED.patch` to a **clean** tree at `9244ebde…`.
- Unrelated WT edits (including queue-status backlog reporting) remain in the dirty checkout and must stay untouched.

### Production vs repo divergence (resolved for planning)

| Signal | Value | Implication |
|---|---|---|
| Running image tag | `arbicore-x-backend:hybrid-e-rpc-9244ebd` | Aligns with base prefix `9244ebd` |
| Image ID | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` | Rollback target |
| Container env `ARBICORE_GIT_TAG` | `hybrid-e-rpc-9244ebd` | Consistent with image tag |
| Container env `ARBICORE_GIT_SHA` | `fff0d0eced5ce3783cff18fb976e55a2a6504504` | **Stale/mismatch vs HEAD** — do not treat as patch base; set correctly in the P2 override when deploying |
| Compose origin | Project `compose`, working dir `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose`, files `docker-compose.prod.yml` + `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` | Production recreate uses **v2 compose path**, not the dirty cert WT as build context |

**Conclusion:** Patch target base is repo HEAD `9244ebde…`. Running image tag matches that lineage. Deploy must use a clean apply of the P2 patch onto that base, then build/recreate via the established compose path — not the dirty cert tree.

---

## 2. Production preflight (read-only)

### Container / image / health

| Item | Value |
|---|---|
| Container | `arbicore-x-backend-new` |
| Status | `running` |
| Health | `healthy` (Docker healthcheck OK; recent log output `{"message":"Hello World"}`) |
| StartedAt | `2026-10-08T08:33:43.476717081Z` (~20h+ uptime at preflight) |
| RestartCount | `0` |
| Image | `arbicore-x-backend:hybrid-e-rpc-9244ebd` |
| Image digest/ID | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| Publish | `127.0.0.1:8001->8001/tcp` |

### Runtime safety posture (non-secret flags)

| Flag | Current value |
|---|---|
| `ARBICORE_ENV` / `ARBICORE_RUNTIME_ENV` | `production` |
| `ARBICORE_EXECUTION_MODE` | `SHADOW` |
| `ARBICORE_AUTOEXEC_AUTOSTART` | `false` |
| `ARBICORE_RUNTIME_AUTOSTART` | `false` |
| `ARBICORE_SCANNER_AUTOSTART` | `true` |
| `ARBICORE_SHADOW_CERT_ENABLED` | `true` |
| `ARBICORE_FLASH_LOAN_SHADOW_ROUTE` | `true` |
| `ARBICORE_PAPER_VALIDATION_ENABLED` | `true` |
| `ARBICORE_FLASH_LOAN_VERIFICATION_WORKERS` | `6` |
| Strategy scanner toggles (`DEX`/`CEX`/`FUNDING`/`LAUNCH`) | `false` |
| Signing / broadcasting | No evidence of live broadcast enablement in these flags; execution mode is **SHADOW**; AUTOEXEC autostart **false**. Do **not** change these during P2. |

Secrets present in container env were inspected only to locate flag names; **they are not reproduced here**.

### Rollback image / config recovery

| Rollback asset | Value |
|---|---|
| Primary rollback image | `arbicore-x-backend:hybrid-e-rpc-9244ebd` |
| Primary rollback image ID | `sha256:40b2116bc01ae999f8ed24cf8bb147533e2bb3c7275f488dccba2de2a3ed8d52` |
| Prior override file (current) | `/tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml` |
| Compose directory | `/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose` |
| Compose files | `docker-compose.prod.yml` + override |
| Recovery pattern | Recreate `backend` with previous override/image tag (`--no-deps --force-recreate --no-build`); do not edit Mongo Network Config for P2 |

Additional local tags exist (e.g. `b1-route-coverage-1b52d09`, `rpc-429-9244ebd`) but **authorised rollback for this change is the currently running hybrid-e image**, unless the human deployer explicitly selects another known-good.

### Downtime / migration assessment

| Question | Finding |
|---|---|
| Schema / Alembic migration required? | **No** — patch contains no migrations; Option D only stamps a field on **new** inserts |
| Index changes? | **No** — existing `ensure_indexes` unchanged by P2 |
| Historical backfill? | **No** — append-only; old rows may keep `evidence_persisted: null` |
| Downtime? | **Brief** — only during `backend` force-recreate (seconds to low minutes). Frontend/other containers should remain up if `--no-deps` is used |
| Data loss risk? | Low for Mongo volumes if compose volume mounts are preserved (same as prior backend-only recreates). Verify volume mounts in rendered compose before apply |

---

## 3. Exact deployment procedure (DO NOT EXECUTE until authorised)

### A. Build a clean P2 source tree

```bash
BASE=9244ebdee6a95188d925084e7e10d4a972cda7ad
PATCH=/home/raghu/projects/arbicore-x-cert/artifacts/performance/p2_release/P2_ONLY_COMBINED.patch
WORKDIR=$(mktemp -d /tmp/p2_deploy_src_XXXX)

git -C /home/raghu/projects/arbicore-x-cert archive "$BASE" | tar -x -C "$WORKDIR"
cd "$WORKDIR"
sha256sum "$PATCH"  # must equal 56739a3d65470f61abfe3becfdf5a929576c41ce4ddc0a8bdd80615395690669
git apply --check "$PATCH" && git apply "$PATCH"

# Sanity: durable claimed_at present; queue_status extras absent
grep -n 'Keep claimed_at durable' app/backend/arbicore/data/discovery_queue.py
! grep -n 'fresh_eligible\|per_chain_backlog\|per_strategy_backlog' app/backend/arbicore/data/discovery_queue.py
```

**Stop if:** checksum mismatch, apply conflict, or forbidden queue-status tokens appear.

### B. Focused tests (non-production Mongo)

```bash
cd "$WORKDIR/app/backend"
MONGO_URL=mongodb://172.26.0.2:27017 PYTHONPATH=. \
  /home/raghu/projects/arbicore-x-v2/.venv/bin/python -m pytest \
  tests/test_p2_evidence_persisted_mongo.py \
  tests/test_p2_flashloan_timing_instrumentation.py \
  tests/test_flashloan_diagnostic_provenance.py \
  tests/test_m2_3_evidence_bundle.py \
  -q --tb=line -o addopts=
```

**Expected:** `35 passed` (timing may vary; previously 3.68s–4.96s).

**Stop if:** any failure, or Mongo unavailable and required round-trip tests cannot run.

### C. Build image (commands only — not executed in preflight)

Follow established backend-only pattern (see `docs/certification/PHASE_0_RUNTIME_DEPLOYMENT_20261004.md`):

```bash
# Example — adjust Dockerfile path if the clean tree layout differs
P2_TAG=p2-instrumentation-9244ebd
BUILD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)

docker build --network=host \
  -f "$WORKDIR/deployment/upgrade/backend/Dockerfile" \
  --build-arg GITSHA=9244ebdee6a95188d925084e7e10d4a972cda7ad \
  --build-arg GITTAG="$P2_TAG" \
  --build-arg BUILD_TIME="$BUILD_TIME" \
  --build-arg APP_VERSION="$P2_TAG" \
  --build-arg ARBICORE_GIT_SHA=9244ebdee6a95188d925084e7e10d4a972cda7ad \
  --build-arg ARBICORE_GIT_TAG="$P2_TAG" \
  -t "arbicore-x-backend:$P2_TAG" \
  "$WORKDIR/app/backend"
```

**Note:** backend `.dockerignore` typically excludes `tests/`; runtime image needs the four runtime modules, not the new test files.

**Stop if:** build fails or image tag already points at unexpected content.

### D. Compose override + recreate (commands only — not executed)

Working directory (current production):

`/home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose`

Create a **new** override (do not edit production secrets/env files) that changes **only**:

- image → `arbicore-x-backend:$P2_TAG`
- `ARBICORE_GIT_SHA=9244ebdee6a95188d925084e7e10d4a972cda7ad`
- `ARBICORE_GIT_TAG=$P2_TAG`

and **preserves** current safety flags:

- `ARBICORE_EXECUTION_MODE=SHADOW`
- `ARBICORE_AUTOEXEC_AUTOSTART=false`
- `ARBICORE_RUNTIME_AUTOSTART=false`
- `ARBICORE_SCANNER_AUTOSTART=true` (unchanged — do not flip)
- `ARBICORE_SHADOW_CERT_ENABLED=true`
- `ARBICORE_FLASH_LOAN_SHADOW_ROUTE=true`
- worker count / RPC URLs / signing addresses unchanged

```bash
cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose

# Render/diff gate (recommended before recreate)
docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f /tmp/arbicore-${P2_TAG}-override.yml \
  config > /tmp/p2_compose_render.yml

# Recreate backend only
docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f /tmp/arbicore-${P2_TAG}-override.yml \
  up -d --no-deps --force-recreate --no-build backend
```

**Stop if:** rendered config changes RPC/AUTOEXEC/execution mode/worker counts unexpectedly, or more than `backend` would recreate.

### E. Post-deployment checks (after future authorisation)

1. Container healthy; image tag/digest is `$P2_TAG`.
2. `ARBICORE_GIT_SHA` / `ARBICORE_GIT_TAG` match intended values (fix stale `fff0d0ec` env).
3. Execution posture unchanged: `SHADOW`, AUTOEXEC autostart false.
4. **claimed_at:** after a candidate is processed, Mongo candidate doc retains `claimed_at`; `claimed_by`/`claimed_until` null.
5. **timing:** new evidence bundles include `diagnostics.timing.stage_ms` with null-vs-zero semantics.
6. **evidence_persisted:** successful inserts store `diagnostics.timing.evidence_persisted: true` in Mongo; failed inserts do not create a success row.
7. Spot-check recent outcomes: verdict/gate behaviour unchanged vs pre-deploy sample (no Gate-7 threshold drift).
8. No new signing/broadcast activity attributable to P2.

### F. Rollback (commands only)

```bash
cd /home/raghu/projects/arbicore-x-v2/deployment/upgrade/compose

docker compose --env-file .env \
  -f docker-compose.prod.yml \
  -f /tmp/arbicore-hybrid-e-rpc-9244ebd-override.yml \
  up -d --no-deps --force-recreate --no-build backend
```

**Rollback verification:**

- Image back to `arbicore-x-backend:hybrid-e-rpc-9244ebd` / `sha256:40b2116b…`
- Health `healthy`
- Safety flags restored/unchanged (`SHADOW`, AUTOEXEC false)
- P2 code paths absent from running container modules if inspected

Historical evidence rows written under P2 remain harmless audit data (no migration to undo).

### G. Stop conditions (abort / roll back)

Stop **before** recreate if:

- Patch checksum ≠ `56739a3d…`
- Patch apply fails or introduces queue-status extras
- Focused tests ≠ 35 passed
- Compose render alters trading/RPC/AUTOEXEC/worker settings

Stop **after** recreate / roll back if:

- Health not healthy within agreed window
- Execution mode ≠ SHADOW or AUTOEXEC becomes true
- Unexpected RPC/config drift
- Evidence/timing behaviour contradicts Rev 2 / Option D semantics

---

## 4. Unresolved risks

1. **Dirty working tree contamination** if someone builds from `/home/raghu/projects/arbicore-x-cert` instead of a clean patched archive.
2. **Compose path lives under `arbicore-x-v2`** — operators must use that compose directory and a dedicated override; wrong compose file could recreate unintended services.
3. **Stale `ARBICORE_GIT_SHA=fff0d0ec…` on current container** — identity drift; P2 deploy should set SHA/tag explicitly.
4. **Brief availability gap** during backend recreate while scanners/SHADOW routing restart with existing autostart flags.
5. **Validator Mongo `172.26.0.2` availability** for pre-deploy retest — if unreachable, do not silently skip Mongo round-trips.
6. **Newer local image tags exist** (`b1-route-coverage-…`) but are not the running baseline; do not accidentally roll forward/back to them without separate approval.

---

## 5. Preflight execution confirmation

| Action | Done in this preflight? |
|---|---|
| Apply patch to production checkout | **No** |
| Commit / push | **No** |
| Build / restart / deploy | **No** |
| Config / scanner / SHADOW / signing / broadcast changes | **No** |
| Unrelated WT edits modified | **No** |

**Production remains unchanged** (`arbicore-x-backend-new` still `hybrid-e-rpc-9244ebd`, healthy, started 2026-10-08T08:33:43Z).

---

## READY FOR EXPLICIT DEPLOYMENT AUTHORISATION
