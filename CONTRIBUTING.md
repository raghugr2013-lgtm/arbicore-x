# Contributing to ArbiCore X

This document defines the engineering standards that keep the canonical repository clean, self-contained, and reproducible over the long term. These are not stylistic preferences — they are architectural invariants. Any change that violates them will be reverted regardless of its runtime correctness.

Before contributing, read [`docs/REPOSITORY_PHILOSOPHY.md`](docs/REPOSITORY_PHILOSOPHY.md) and [`docs/ROADMAP.md`](docs/ROADMAP.md).

---

## 1. Folder organization

The repository has four top-level responsibility trees; nothing else exists at the root as content:

| Tree | Owns |
|---|---|
| `app/` | Application source only. Contains `backend/`, `frontend/`, `opportunity_center/`. |
| `deployment/` | Infrastructure only. Contains `docker/`, `compose/`, `nginx/`, `ssl/`, `backups/`, `monitoring/`, `upgrade/`. |
| `scripts/` | Operator entrypoints only. Each script is a thin wrapper that delegates into `deployment/`. |
| `docs/` | Documentation only. |

**Absolute rules:**

- Application code MUST NEVER reference paths under `deployment/`, `scripts/`, or `docs/`.
- Deployment code MAY reference paths under `app/` (it consumes the application) but NEVER modifies application source at build time.
- Scripts MUST delegate to `deployment/`; they do not implement business logic.
- Documentation MUST NOT be executable.

Any new top-level directory requires an ADR (Architecture Decision Record) added to `docs/ARCHITECTURE.md` and approval by the repository owner.

---

## 2. Naming conventions

- **Directories:** lowercase, hyphen-separated. Example: `deployment/upgrade/`, not `deployment/Upgrade/` or `deployment/upgrade_toolkit/`.
- **Shell scripts:** lowercase, hyphen-separated, `.sh` extension, always executable. Example: `init-letsencrypt.sh`.
- **Python modules:** lowercase, underscore-separated, `.py` extension. Follows PEP-8.
- **Docker images (built locally):** `arbicore-x-<role>:<version>`. Example: `arbicore-x-backend:1.0.0`.
- **Docker containers:** `arbicore-x-<role>`. Example: `arbicore-x-mongo`.
- **Named volumes:** `arbicore-x-<purpose>`. Example: `arbicore-x-mongo-data`.
- **Environment variables:** `SCREAMING_SNAKE_CASE`, prefixed by domain when appropriate (`ARBICORE_SCANNER_*`, `LETSENCRYPT_*`, `MONGO_*`).
- **Config templates:** `.env.example`, `.env.production.example`, `.env.development.example`, `.env.shared.example`. Do not create additional templates without ADR.
- **Docker labels:** `arbicore.role=<role>`, `arbicore.schema=v1`, `arbicore.gitsha=<sha>`. Consistent across every image.

---

## 3. Documentation expectations

Every non-trivial change updates docs *in the same commit*, not in a follow-up.

**When you must update docs:**

| Change | Docs to update |
|---|---|
| New env variable | `.env.example`, `.env.production.example`, `.env.development.example` (as appropriate); `docs/OPERATIONS.md` if operational |
| New deployment profile | `deployment/compose/README.md`, `docs/SHARED_INFRASTRUCTURE.md`-style profile guide, `README.md` "Deployment profiles" section |
| New service in the compose | `docs/ARCHITECTURE.md` service table, `docs/OPERATIONS.md`, `docs/TROUBLESHOOTING.md` |
| New operator script | `Makefile` `help` target, `README.md` "Day-2 operations" table, matching `docs/*.md` |
| Change to install flow | `docs/INSTALL.md` |
| Change to upgrade flow | `docs/UPGRADE.md`, `docs/ROLLBACK.md` |
| Change to backup/restore | `docs/BACKUP_RESTORE.md` |
| Change to SSL flow | `docs/SSL.md` |
| Anything security-relevant | `docs/SECURITY.md` |
| Break in observed behavior | `docs/TROUBLESHOOTING.md` |

Docs must reflect the current implementation. Docs that describe historical behavior belong in `docs/MIGRATION_SUMMARY.md`, not in the operational docs.

---

## 4. Deployment changes

Deployment changes are higher-risk than application changes. They require:

1. **A justification tied to one of these categories:**
   - correctness (something is broken)
   - reproducibility (a build/deploy is not deterministic)
   - security (a hardening gap)
   - operability (an operator pain point with a specific reproduction)
   - a new profile explicitly approved by the repository owner

   Aesthetic, "modernization", or "cleanup" motives are not sufficient on their own. See [`docs/REPOSITORY_PHILOSOPHY.md`](docs/REPOSITORY_PHILOSOPHY.md).

2. **The smallest possible change.** No incidental refactors bundled with a fix.

3. **Testing on a disposable Ubuntu VPS:** `make install` succeeds from a clean checkout on a fresh VPS. Runtime healthchecks pass. Backup + restore round-trip works. The upgrade path from the previous tagged release succeeds.

4. **Version bump appropriate to the change** (see §6).

---

## 5. Docker updates

Constraints on Dockerfile and compose changes:

- **Pinned base images.** No `latest` tags on any language runtime, database, or nginx.
- **Non-root runtime.** Every service runs as a non-root user. `USER 1001` for backend, `USER 101` for nginx-alpine variants, uid 999 for mongo.
- **Multi-stage builds** for anything with a build step (frontend, opportunity_center). Runtime image contains only artifacts, not toolchains.
- **No secrets in images.** Ever. `.env` is mounted at runtime; images are secret-free.
- **Provenance labels.** Every built image sets `arbicore.role`, `arbicore.schema`, and `arbicore.gitsha`.
- **Healthchecks.** Every service in the compose has a `HEALTHCHECK` in its Dockerfile *and* a `healthcheck:` block in compose.
- **Resource limits.** Every service in the compose has `deploy.resources.limits` and `reservations`.
- **Log caps.** Every service uses the shared `x-log-defaults` anchor (100 MB × 5 files).
- **No new build-time dependency without justification.** `requirements.prod.txt` must remain grep-clean of `emergentintegrations`, `litellm`, and dev tools (`black`, `flake8`, `isort`, `mypy`, `pytest`, `ruff`, `bandit`, `ipython`).

---

## 6. Configuration management

- **Every configuration value comes from an env variable.** No hard-coded paths, no hard-coded domains, no hard-coded credentials.
- **Every env variable is documented in `.env.example`.** If a new key is introduced without a template entry, the change fails review.
- **Env templates are versioned artifacts.** Do not edit them casually.
- **Real `.env` files are never committed.** Enforced by `.gitignore`. Verify with `git check-ignore .env`.
- **Secrets never appear in logs, images, or docs.** Rotate immediately if suspected exposed.

---

## 7. Review requirements

Every non-trivial change requires:

1. A pull request against `main` from a topic branch (`feat/…`, `fix/…`, `docs/…`, `chore/…`).
2. A description that explicitly answers:
   - *What* changed
   - *Why* (mapped to one of the justification categories in §4 for deployment changes)
   - *How to test* (specific commands and expected output)
3. Docs updated in the same PR (§3).
4. Passing runtime tests on a disposable VPS for any deployment change (§4).
5. Approval from the repository owner.
6. Squash-merge with a single, well-formed commit message referencing the PR number.

**Direct commits to `main` are limited to:** typo fixes in docs, and version-bump commits authored by the release process.

---

## 8. Versioning and releases

- **SemVer 2.0.** `MAJOR.MINOR.PATCH`.
- **Tag format:** `vMAJOR.MINOR.PATCH` (e.g., `v1.0.0`, `v1.1.0`, `v1.1.1`).
- **PATCH:** backward-compatible bug fixes with no schema or API changes.
- **MINOR:** backward-compatible feature additions, new env vars with defaults, additive schema changes.
- **MAJOR:** breaking API changes, breaking env changes, breaking schema changes, or removal of retired-in-earlier-version compatibility shims.
- **Release process:** merge to `main` → update `VERSION` → update `docs/ROADMAP.md` "Recent releases" → tag → GitHub release with generated release notes. No side-loaded release bundles.

---

## 9. What NOT to do

The following are automatic no-review-required rejects because they reintroduce fragmentation:

- ❌ Re-adding a `release_bundle/` directory or any binary release artefact
- ❌ Creating a second compose file at the repo root
- ❌ Committing `.env` (real, non-example)
- ❌ Adding a new top-level directory without an ADR
- ❌ Introducing a submodule
- ❌ Restoring the historical `arbicore-x-vps-bundle/` nested layout
- ❌ Adding `emergentintegrations`, `litellm`, or any dev tool to `requirements.prod.txt`
- ❌ Reintroducing hard-coded domains, IPs, or FQDNs
- ❌ Adding a build step that assumes an external release bundle exists
- ❌ Reviving the retired `/api/arbicore/release/manifest` and `/api/arbicore/release/bundle` endpoints as actual bundle-download endpoints

---

## 10. Questions

If a proposed change does not fit cleanly into the categories above, open a discussion issue *before* writing code. The repository's long-term cleanliness is worth the friction.
