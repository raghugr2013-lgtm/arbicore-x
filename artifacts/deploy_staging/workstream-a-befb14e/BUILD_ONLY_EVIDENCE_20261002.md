# Workstream A `befb14e` — BUILD ONLY Evidence (2026-10-02)

- **Status:** **IMAGE BUILT — NOT DEPLOYED**
- **Authorization:** BUILD-ONLY (no compose cutover)
- **Built (UTC):** ~`2026-10-02T14:52:33Z` (build-arg) / image Created `2026-10-02T16:58:29+02:00`
- **Gate9:** **UNTOUCHED**

---

## Source

| Field | Value |
|---|---|
| Bundle | `artifacts/workstream-a-quoter-429-befb14e-selfcontained.bundle` |
| Bundle SHA256 | `b7f3952e29a5664bb6c7a144e7a76c9df7ba207b3f2ee6a430bb84a3a4dff964` (**PASS**) |
| Throwaway tree | `/tmp/ws-a-befb14e-build-only-20261002/checkout` |
| `git rev-parse HEAD` | `befb14e6aa77515daa038e142ff978822a4fab91` |
| Tree | `fdd6f7996a4364885fca31d394eeae75d04b379a` |
| Cert workspace dirty files | **not** reset/cleaned |
| Production `/home/raghu/projects/arbicore-x-v2` source | **not** modified for this build |

## Build command

```bash
docker build \
  -t arbicore-x-backend:ws-a-befb14e-20261002 \
  -f deployment/upgrade/backend/Dockerfile \
  --build-arg GITSHA=befb14e6aa77515daa038e142ff978822a4fab91 \
  --build-arg GITTAG=ws-a-befb14e-20261002 \
  --build-arg BUILD_TIME=2026-10-02T14:52:33Z \
  --build-arg APP_VERSION=ws-a-befb14e \
  --build-arg ARBICORE_GIT_SHA=befb14e6aa77515daa038e142ff978822a4fab91 \
  --build-arg ARBICORE_GIT_TAG=ws-a-befb14e-20261002 \
  app/backend
```

- Context: tip `app/backend`
- Dockerfile: tip `deployment/upgrade/backend/Dockerfile` (same path as prod compose)
- Full log: `artifacts/deploy_staging/workstream-a-befb14e/build_ws-a-befb14e-20261002.log`
- Result: **SUCCESS** (`DOCKER_BUILD_EXIT=0`)

## New image (immutable)

| Field | Value |
|---|---|
| Tag | `arbicore-x-backend:ws-a-befb14e-20261002` |
| Image Id / digest | `sha256:12759b11a783619ad25746a030c5bbcc71b83ed64ff05b3316153d6402a594ae` |
| Distinct from g5.79 | **YES** |

## Gate9 / rollback image freeze (post-build)

| Field | Value |
|---|---|
| Tag | `arbicore-x-backend:g5.79-green-20260927` |
| Image Id | `sha256:aaadc3a9cc78d695a9e7e2d16681babc71c576033ad3764061a918946d8e993a` |
| Match prior freeze | **YES** (unchanged) |
| Retagged/overwritten | **NO** |
| Container | `arbicore-x-backend-new` |
| StartedAt | `2026-10-02T06:19:33.513948555Z` |
| RestartCount | `0` |
| Running image | `arbicore-x-backend:g5.79-green-20260927` → same Id as freeze |

## Explicitly NOT executed

- compose up/down
- container recreate/restart
- deploy of `ws-a-befb14e-20261002`
- env / SHADOW / Gate9 / AUTOEXEC / RUNTIME / signing / broadcast / live changes

## Next (DOCUMENT ONLY — requires separate GO)

Compose cutover is **not** authorized by this build. See operator cutover plan in the build report §H / `POST_8H_12H_SHADOW_VALIDATION_PACKAGE_20261002.md` §9.
