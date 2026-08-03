# v2.0.3 → v2.0.4 — Deployment Engineering Fix

**Date:** 2026-08-02
**Scope:** deployment/release-engineering only. Zero application code change.
**Trigger:** VPS validation of v2.0.3 found `docker compose build` did not rebuild the backend image on the shared-infra profile.

## Root cause

Historical asymmetry between the two compose profiles:

| Profile | File | Backend `build:` section? | Behavior of `docker compose build` for backend |
|---|---|:-:|---|
| Greenfield (own Mongo) | `deployment/compose/docker-compose.yml` | ✅ present | Rebuilds backend from source |
| Shared infrastructure | `deployment/compose/docker-compose.shared.yml` | ❌ **missing** | **Reuses whatever `${BACKEND_IMAGE_TAG}` points at** — falls back to `arbicore-x-backend:1.0.2` default |

Frontend and Opportunity Center already had `build:` sections in the shared profile, so they rebuilt cleanly on the VPS. Backend did not.

The intent when `docker-compose.shared.yml` was authored was that shared-profile deployments would pull a pre-built backend image from a private registry (a common pattern for multi-tenant hosts). In practice, the operator is building on the same VPS as the deployment, so this asymmetry surfaced as a surprise.

## Fix (applied in v2.0.4)

1. **Add `build:` section to backend in `docker-compose.shared.yml`** — mirrors the frontend + opportunity-center pattern already in the same file. `docker compose build` now rebuilds all three application services identically across both profiles.
2. **Bump default image tags** in both compose files from `:1.0.2` to `:2.0.3` so a clean `docker compose up -d` after `docker compose build` picks up the v2.0.3 code and cannot collide with the stale `arbicore-x-backend:1.0.0` image sitting on the VPS from 2026-07-29.
3. **New Makefile targets** for per-service rebuilds:
   - `make build`          — build all three application services (unchanged)
   - `make build-backend`  — build only backend
   - `make build-frontend` — build only frontend
   - `make build-oc`       — build only opportunity_center

## Answers to the operator's three questions

**1. Is the backend intentionally expected to be built separately before deployment?**
No. The historical shared-profile compose omitted the `build:` block on the assumption of a registry pull, but the canonical intent is that `docker compose build` rebuilds every application service from source. The fix aligns backend with the frontend + opportunity-center behaviour already present in the same file.

**2. If yes, provide the canonical command…**
Not applicable — the fix in v2.0.4 removes the need. See question 3.

**3. If not, provide the canonical deployment fix so the backend is rebuilt from source during deployment.**
Applied in v2.0.4:
- `deployment/compose/docker-compose.shared.yml` — backend service now has `build: { context: ../.., dockerfile: deployment/docker/backend/Dockerfile, args: { GITSHA: ${GITSHA:-unknown} } }`
- Default image tags bumped `1.0.2 → 2.0.3` in both compose files
- `make build-backend` target added for explicit per-service rebuilds

## Canonical deployment command (post-fix)

From the operator's VPS, after checking out v2.0.4:

```bash
cd /opt/arbicore-x
# Optional: verify the fix is in place
grep -A3 "^  backend:" deployment/compose/docker-compose.shared.yml
#   backend:
#     build:
#       context: ../..
#       dockerfile: deployment/docker/backend/Dockerfile

# Rebuild all three application services from source
make build
#   builds arbicore-x-backend:2.0.3, arbicore-x-frontend:2.0.3, arbicore-x-opportunity-center:2.0.3

# Or rebuild backend only (fastest turnaround for a code-only change):
make build-backend

# Verify the new backend image contains v2.0.3
docker run --rm arbicore-x-backend:2.0.3 python -c "print(open('/app/VERSION').read().strip())"
#   2.0.3    ← must print 2.0.3, not 1.0.0 or 1.0.2

# Bring the stack up
docker compose -f deployment/compose/docker-compose.shared.yml up -d
```

## Verification checklist (operator, before cutover)

- [ ] `git describe --tags` → `v2.0.4`
- [ ] `grep "build:" deployment/compose/docker-compose.shared.yml` returns 3 matches (backend, frontend, opportunity_center)
- [ ] `grep "arbicore-x-backend" deployment/compose/docker-compose.shared.yml` shows default `:2.0.3`
- [ ] `make build-backend` completes without error
- [ ] `docker images | grep arbicore-x-backend` shows the new `:2.0.3` tag alongside any older tags
- [ ] `docker run --rm arbicore-x-backend:2.0.3 python -c "print(open('/app/VERSION').read().strip())"` prints exactly `2.0.3`
- [ ] `docker run --rm arbicore-x-backend:2.0.3 python -c "from arbicore.auth import authenticate; print('auth-module-present')"` prints `auth-module-present`
- [ ] `docker run --rm arbicore-x-backend:2.0.3 python -c "from arbicore.data.mid import MidWriter; print('mid-module-present')"` prints `mid-module-present`

If all boxes tick, the image is the certified v2.0.3 backend. Proceed with cutover.

## Backward compatibility

The stale `arbicore-x-backend:1.0.0` image on the VPS is **not deleted** by this fix — it remains on disk for rollback. If the v2.0.3 cutover has any issue, the operator can revert by pinning `BACKEND_IMAGE_TAG=arbicore-x-backend:1.0.0` in `.env.shared` and running `docker compose up -d`. This is the same rollback path documented in `docs/DEPLOYMENT_CHECKLIST_v2.0.3.md` §7.

## Regression

No application code changed. Backend regression untouched: **1469 pass, 76 skipped, 0 failed** — same as v2.0.3.
