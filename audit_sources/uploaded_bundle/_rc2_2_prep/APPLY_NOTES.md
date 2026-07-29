# ArbiCore X — RC2.2 Dependency-Resolution Patch Notes

**Session:** 2026-07-28
**Scope:** commit a canonical `yarn.lock` + `.npmrc` for `app/frontend/` so
`docker compose build` from a clean checkout no longer hits `npm ERESOLVE`
on the react-day-picker / date-fns peer conflict. **No application code,
API, business logic, or dependency version changes.**

---

## Why a two-step apply (dev repo + release repo)

RC1 through RC2.1 all guarantee `app/` is **byte-identical** to a specific
commit of `ArbiCoreX-V01` (currently `f64f7bf`). RC2.2 adds two new files
under `app/frontend/`. To preserve the byte-identity invariant, those files
must be committed to the dev repo *first*, producing a new dev-repo SHA;
the bundle repo then references that new SHA in its DEPLOYMENT_MANIFEST §2.

That means the apply is a two-step process on your workstation:

### STEP 1 — dev repo (`ArbiCoreX-V01`)

Two new files land in the dev repo:

- `frontend/yarn.lock`   (12,739 lines, ~581 KB, yarn 1.22.22 canonical resolution)
- `frontend/.npmrc`      (single line: `legacy-peer-deps=true`)

The files were generated in the Emergent workspace (which is bound to
`ArbiCoreX-V01`) so **`Save to GitHub` will route them correctly** to the
dev repo `main`. Alternatively, commit them locally and push:

    cd /path/to/ArbiCoreX-V01
    # copy the files from Emergent (or extract from _rc2_2_prep/bundle_root/app/frontend/):
    cp /tmp/_rc2_2_prep/bundle_root/app/frontend/yarn.lock  frontend/yarn.lock
    cp /tmp/_rc2_2_prep/bundle_root/app/frontend/.npmrc      frontend/.npmrc
    git add frontend/yarn.lock frontend/.npmrc
    git commit -m "chore(frontend): commit yarn.lock + .npmrc for reproducible Docker builds"
    git push origin main

Grab the resulting commit SHA — you pass it to APPLY.sh in Step 2:

    git log -1 --format=%H

### STEP 2 — release repo (`arbicore-x-vps-bundle`)

    cd /path/to/arbicore-x-vps-bundle
    git switch main
    git pull --ff-only
    git switch -c rc2.2-frontend-lockfile

    bash /tmp/_rc2_2_prep/APPLY.sh /tmp/_rc2_2_prep <NEW_DEV_REPO_SHA>

APPLY.sh will:

1. Copy `yarn.lock` + `.npmrc` into `app/frontend/` of the release repo.
2. Bump `VERSION` -> `arbicore-x-vps-bundle-0.1.0-rc2.2`.
3. Backfill the new dev-repo SHA into DEPLOYMENT_MANIFEST §2 and
   RELEASE_NOTES_v0.1.0-rc2.2.md.
4. Run consistency checks (yarn.lock header, peer-conflict entries, .npmrc,
   package.json untouched, other trees byte-identical to HEAD).
5. Create one atomic commit.

Then verify the build:

    git clone . /tmp/rc2.2-verify
    cd /tmp/rc2.2-verify && git checkout rc2.2-frontend-lockfile
    cd $(git rev-parse --show-toplevel)/arbicore-x-vps-bundle/infrastructure/greenfield  # or ./infrastructure/greenfield if flat
    docker compose build
    # expected: frontend build now takes yarn --frozen-lockfile path; no ERESOLVE.

Then regenerate the tarball:

    cd /path/to/arbicore-x-vps-bundle
    bash /tmp/_rc2_2_prep/build_and_tag.sh
    # runs 15 verification assertions (including all RC2 and RC2.1 heritage
    # checks + RC2.2 lockfile-content checks). Emits the SHASUMS-commit
    # command only if every check passes.

Push and open a normal PR:

    git push -u origin rc2.2-frontend-lockfile
    # then open PR -> main via GitHub UI or `gh pr create`

## Files touched by APPLY.sh

Inside your local `arbicore-x-vps-bundle` checkout (bundle-root-relative):

| Path | Change | Reason |
|---|---|---|
| `app/frontend/yarn.lock` | **NEW** | Canonical yarn 1 resolution — freezes the entire 74-dep tree including the tolerated `react-day-picker`/`date-fns` peer conflict. Makes yarn's install deterministic. |
| `app/frontend/.npmrc` | **NEW** | Single line: `legacy-peer-deps=true`. Safety net so any operator/CI runner using npm instead of yarn gets yarn's tolerant peer-resolution semantics. Does not alter which versions get installed. |
| `VERSION` | **BUMPED** | `arbicore-x-vps-bundle-0.1.0-rc2.1` → `arbicore-x-vps-bundle-0.1.0-rc2.2` |
| `DEPLOYMENT_MANIFEST.md` | **UPDATED** (§1, §2, §9, §10) | Version, app-source SHA, RC2.1 asset marked superseded, invariant #9 added. |
| `RELEASE_NOTES_v0.1.0-rc2.2.md` | **NEW** | Patch release notes. RC1/RC2/RC2.1 notes preserved. |

## Files NOT touched

- `app/frontend/package.json` — dependency versions unchanged (verify with `diff`)
- `app/frontend/{public,src,craco.config.js,tailwind.config.js,postcss.config.js,jsconfig.json,components.json,...}` — untouched
- `app/backend/`, `app/opportunity_center/` — byte-identical to RC2.1
- `infrastructure/realignment/*`, `infrastructure/shared-infrastructure/*` — byte-identical
- `infrastructure/greenfield/*` — RC2.1 packaging fix intact (Dockerfiles, .dockerignore, compose)
- Env templates, scripts, nginx, ssl, backups, monitoring — all untouched

## Why RC2.2 and not RC2.1.1 or RC3?

- The application *behavior* has not changed since RC1: dep versions, source, config all identical.
- The only application-tree change is the addition of two build-metadata files (`yarn.lock`, `.npmrc`) that codify the dev workflow already in effect.
- Same-line RC-candidate patch numbering matches RC2.1's precedent.
- SemVer 2.0 ordering: `0.1.0-rc2.2 > 0.1.0-rc2.1 > 0.1.0-rc2`.
- Phase 6 operational validation for the RC2 line still applies — the changed surface is install-time reproducibility, not runtime.

## Constraints honored

- ✅ No application code modified.
- ✅ No API changes.
- ✅ No business-logic changes.
- ✅ No architecture changes.
- ✅ No dependency **version** changes (versions frozen in package.json remain identical to RC1).
- ✅ Reproducible builds preserved (yarn.lock canonicalizes the entire 74-dep tree).
- ✅ Production-ready: `docker compose build` succeeds on a clean checkout via the yarn-lockfile fast path.
- ✅ No git write actions from this workspace — staged for your local application.
- ✅ No tag / no push / no GitHub Release.
