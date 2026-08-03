# Repository Roadmap

Long-term direction and governance for the ArbiCore X canonical repository. This is **not** a development backlog — it describes *how* the repository will evolve, not *what* features to build.

For engineering standards, see [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
For the reasoning behind the repo's structure, see [`REPOSITORY_PHILOSOPHY.md`](REPOSITORY_PHILOSOPHY.md).

---

## 1. Repository philosophy (summary)

One repository. One source of truth. One clone. A new operator with only this repository must be able to build, deploy, operate, upgrade, back up, and restore ArbiCore X — without ever consulting a legacy repository or historical release bundle.

Everything in the repository fits into exactly one of four responsibility trees: `app/` (application), `deployment/` (infrastructure), `scripts/` (operator entrypoints), `docs/` (documentation). Root-level files are minimal: config, license, contributing guide, version, readme, makefile.

## 2. Versioning strategy

**SemVer 2.0.** `MAJOR.MINOR.PATCH` (e.g. `v1.0.0`, `v1.1.0`, `v1.1.1`).

| Bump | Trigger |
|---|---|
| **PATCH** (`v1.0.0` → `v1.0.1`) | Backward-compatible bug fixes only. No API, schema, env, or compose contract changes. |
| **MINOR** (`v1.0.0` → `v1.1.0`) | Backward-compatible additions: new env variables (with defaults), new API endpoints, additive Mongo schema (new collections / new optional fields), new operator scripts, new deployment profiles. |
| **MAJOR** (`v1.0.0` → `v2.0.0`) | Breaking API changes, breaking env changes (removals or semantics), breaking Mongo schema (removals or type changes), removal of a previously-retired compatibility shim, removal of a deployment profile. |

**Schema version** (`arbicore.schema=v1` label on backend image) tracks the Mongo schema and is independent of the SemVer of the repository. A MAJOR bump *may* also bump the schema. A MINOR bump *must not*.

**Retirement path** for legacy surfaces: retire in a MINOR release (stub returning `{"status":"retired",…}`), remove entirely in the next MAJOR release. `/api/arbicore/release/manifest` and `/api/arbicore/release/bundle` are the canonical example: retired in `v1.0.0`, eligible for removal in `v2.0.0`.

## 3. Release process

Every release originates from this repository. No external release bundles.

1. Merge everything intended for the release into `main`.
2. Bump `VERSION` (single-line file) in a dedicated commit.
3. Update `docs/ROADMAP.md` §9 "Recent releases" with a one-line summary + link to the tag.
4. Update `docs/OPERATIONS.md` if any operator-facing behavior changed.
5. Update `docs/ARCHITECTURE.md` §7 (retired surfaces) or §6 (invariants) if applicable.
6. Tag: `git tag -a vX.Y.Z -m "vX.Y.Z"` and push tag.
7. Create a GitHub Release from the tag with auto-generated release notes.
8. No side-loaded artifact. No SHASUMS file. Consumers deploy via `git clone --branch vX.Y.Z`.

**Release cadence:** as needed. There is no calendar-driven release train. Do not batch unrelated work into "release windows."

## 4. Branch strategy

Deliberately minimal.

| Branch | Purpose | Lifetime |
|---|---|---|
| `main` | Canonical trunk. Every tag originates here. Always deployable. | Permanent |
| `feat/<slug>` | Feature development | Merged and deleted |
| `fix/<slug>` | Bug fix | Merged and deleted |
| `docs/<slug>` | Docs-only change | Merged and deleted |
| `chore/<slug>` | Repo hygiene | Merged and deleted |
| `hotfix/<slug>` | Emergency fix to production | Merged and deleted |

**Rules:**

- No long-lived `develop`, `next`, `staging`, `release-*`, or `v1.x-maintenance` branches. If a MAJOR version demands ongoing maintenance of the previous MAJOR, cut a `maintenance/vN` branch *only when a specific patch requires it*.
- All work happens on topic branches → PR → squash-merge to `main`.
- Direct commits to `main` are limited to `VERSION` bumps and typo-only doc fixes.
- No force-push to `main`, ever.

## 5. Extension points — future evolution

The repository is deliberately conservative today. When new capabilities are needed, they fit these seams:

### 5.1 New services in the greenfield stack
Add a new service by:
1. Creating `deployment/docker/<service>/Dockerfile` (+ optional `nginx-spa.conf`, `.dockerignore`).
2. Adding a service entry to `deployment/compose/docker-compose.yml` with healthcheck, resource limits, log caps, and provenance labels.
3. If the service is user-facing, adding an nginx route in `deployment/nginx/conf.d/arbicore-x.conf.template`.
4. Updating `docs/ARCHITECTURE.md` §1 topology and §3 deployment.
5. Adding required env variables to every `.env.*.example`.

New services must justify their existence against the ArbiCore X mission — this is not a general-purpose services repo.

### 5.2 New deployment profiles
Add a new profile by:
1. Creating `deployment/compose/docker-compose.<profile>.yml`.
2. Creating `deployment/compose/.env.<profile>.example`.
3. Creating `docs/<PROFILE>.md` following the shape of `docs/SHARED_INFRASTRUCTURE.md`.
4. Adding a row to `deployment/compose/README.md`.
5. Updating `README.md` "Deployment profiles" section.
6. Recording an ADR in `docs/ARCHITECTURE.md`.

**Approved profiles today:** `greenfield` (default), `upgrade` (backend-only in-place upgrade), `shared-infrastructure` (optional multi-tenant peer).

### 5.3 New infrastructure concerns (new sibling under `deployment/`)
Introducing a new sibling directory under `deployment/` (e.g. `deployment/observability/`, `deployment/secrets/`, `deployment/network/`) is a bigger change than adding a service or profile. It requires:
1. ADR in `docs/ARCHITECTURE.md`.
2. A clear boundary against existing siblings: it must not overlap `docker/`, `compose/`, `nginx/`, `ssl/`, `backups/`, `monitoring/`, or `upgrade/`.
3. A dedicated `docs/<CONCERN>.md`.
4. Approval by the repository owner.

### 5.4 New operator scripts
Every new operator command:
1. Is a thin wrapper in `scripts/<name>.sh` that delegates into `deployment/`.
2. Adds a target in the root `Makefile`.
3. Adds a row in the `Makefile` `help` output.
4. Adds a row in `README.md` "Day-2 operations".
5. Documents its expected behavior in the matching `docs/*.md`.

Never build operational logic inside `scripts/` — logic lives under `deployment/`.

### 5.5 Application evolution
Application changes stay entirely inside `app/`. They may not require accompanying deployment changes; when they do (e.g., new dependency), the deployment change is a separate concern updated in the same PR.

## 6. Rules for adding new deployment profiles

A profile is an *alternative shape* of the deployment, not an alternative implementation. Rules:

- **A profile does not fork the application.** All profiles consume `app/` identically.
- **A profile does not fork the Dockerfiles.** All profiles consume `deployment/docker/` identically.
- **A profile is one compose file + one env template + one doc.** No sub-tree.
- **A profile is opt-in.** The default `make install` uses greenfield; other profiles require explicit invocation.
- **A profile is documented.** The `docs/<PROFILE>.md` explains when to use it and what invariants change.
- **A profile has an owner.** The person proposing a new profile takes responsibility for keeping it consistent with future changes to the default. If a proposed profile cannot be maintained alongside the default without proliferation of `if profile == ...` logic, it does not belong in this repository.

## 7. Rules for introducing new infrastructure

Any new infrastructure component (new sibling of `docker/`, `compose/`, `nginx/`, `ssl/`, `backups/`, `monitoring/`, `upgrade/`) must:

1. **Solve a problem the current infrastructure demonstrably cannot solve.** "Would be nicer" is not sufficient.
2. **Not overlap responsibilities with existing siblings.** If a proposed sibling could reasonably belong under an existing one, put it there instead.
3. **Come with the same production hygiene as the rest of `deployment/`:** documented, scripted where invoked, referenced by `docs/`, and tested on a disposable VPS.
4. **Pass the "clone-and-run" test.** After introducing it, a fresh clone still installs cleanly with `make install`.

Third-party managed services (e.g., a cloud metrics stack, a cloud secrets manager) are acceptable only if the greenfield install continues to work *without* them — they must be additive, never required by the default profile.

## 8. Future architectural direction (non-committing)

Areas the repository is *prepared* to evolve toward if operational experience demonstrates the need. Listed for governance clarity, not as commitments:

- **Observability profile.** A `deployment/monitoring/` extension (Prometheus + Grafana + Loki) as an optional profile, alongside current probe-based monitoring. Would require an ADR.
- **Secrets management.** A `deployment/secrets/` extension (env-file encryption, or integration with a secrets manager) if operator experience shows `.env` files becoming a burden.
- **Multi-region.** Currently single-VPS. Multi-region would probably live as a new profile rather than becoming default.
- **CI/CD.** A `.github/workflows/` addition running `make env-check`, static-analysis, and a docker-build dry-run on PRs. Would not change the deployment model.
- **Schema evolution beyond v1.** Any Mongo schema change beyond `v1` bumps the `arbicore.schema` label and requires migration steps in `deployment/upgrade/`. A migration file convention (`deployment/upgrade/migrations/vX_to_vY/`) would be introduced at that time.

None of the above is required for `v1.0.0`. All are eligible for consideration in later MINOR or MAJOR releases.

## 9. Recent releases

| Version | Date | Notes |
|---|---|---|
| `v2.0.0` | 2026-08-02 | **Major** — canonical consolidation. Merged `arbicore-x` v1.0.2 (deployment tree) with `Arbicorex-ui-v2-slice-02` (UI v2 + Wave 6 + Phase 7–10 execution). UI v2 primary, legacy CRA retained behind feature flag. Dormant modules preserved in-tree (activation deferred to per-cluster validation waves). 1442 tests passed, 76 skipped. See [`V2_CONSOLIDATION_AUDIT.md`](V2_CONSOLIDATION_AUDIT.md), [`V2_INTELLIGENCE_AUDIT.md`](V2_INTELLIGENCE_AUDIT.md), and [`V2_PLATFORM_ROADMAP.md`](V2_PLATFORM_ROADMAP.md) (product/feature roadmap toward the Autonomous Institutional Arbitrage Intelligence Platform vision). |
| `v1.0.1` | 2026-07-29 | Runtime-correctness patch. Backend build no longer depends on `install.sh` requirements swap (works uniformly for greenfield + shared profiles). Frontend + OC unprivileged-nginx made robust across `nginx:1.25-alpine` base variants. All healthchecks use `127.0.0.1` (alpine minimal `/etc/hosts` compatibility) and normalized on `/healthz`. `.env.shared.example` MongoDB auth guidance strengthened. See [`releases/v1.0.1.md`](releases/v1.0.1.md). |
| `v1.0.0` | 2026-01 | First canonical release. Full application absorption from `ArbiCoreX-V01`; deployment infrastructure absorbed from `arbicore-x-vps-bundle`; frontend reproducibility (`yarn.lock`, `.npmrc`) canonical from day one; legacy release-bundle download endpoints retired to structured stubs; nested bundle layout flattened; RC lineage retired. See [`MIGRATION_SUMMARY.md`](MIGRATION_SUMMARY.md). |

Future releases append here.

> **Product/feature roadmap:** see [`V2_PLATFORM_ROADMAP.md`](V2_PLATFORM_ROADMAP.md).
> This governance document (`ROADMAP.md`) covers *how* the repository evolves; the platform roadmap covers *what* is being built and in what order.

## 10. Governance

- **Owner:** `raghugr2013-lgtm`.
- **License:** Proprietary — All Rights Reserved. See [`../LICENSE`](../LICENSE).
- **Legacy repositories:** `raghugr2013-lgtm/ArbiCoreX-V01`, `raghugr2013-lgtm/arbicore-x-vps-bundle` — archived and read-only. Never a source of merges into this repository.
