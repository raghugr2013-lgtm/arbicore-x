# Repository Philosophy

Why the canonical repository is designed the way it is, and the rules that will keep it clean over the long term.

---

## 1. What this repository *is*

**One repository. One source of truth. One clone. No dependencies on other repositories or historical release bundles.**

A new engineer who has never seen ArbiCore X should be able to:

1. `git clone` the canonical repo.
2. Read `README.md` and know what they have.
3. `make install` on a fresh Ubuntu VPS.
4. Have a running system.

If any of those steps requires consulting a legacy repo, a historical bundle, an out-of-band tarball, an external playbook, or tribal knowledge — the repository is broken.

## 2. What this repository is *not*

- Not an archive of the platform's history. Legacy commits and release notes live in the two archived repositories. This repository starts fresh at `v1.0.0`.
- Not a monorepo of every conceivable future service. It contains the current ArbiCore X application and its production deployment — nothing speculative.
- Not a documentation dumping ground. Every doc has a specific operational purpose. Everything that would have been "background reading" in a legacy setup is either folded into the current docs or referenced (not copied) from the legacy repos.

## 3. The two trees

The repository has exactly two content trees:

### `app/` — what the software *is*
All application source. Backend, frontend, opportunity_center, and their tests. Self-contained. **Never references anything outside `app/`.**

If the application needs a value that differs across deployments, the value comes from an env variable — no deployment-aware code, no deployment-aware paths. This is a hard rule.

### `deployment/` — how the software *runs in production*
All infrastructure: Dockerfiles, compose files, nginx, SSL, backups, monitoring, upgrade toolkit. **Consumes `app/`; never modifies it at build time.**

Deployment code may know about the application (which paths to COPY, which port to expose). Application code may not know about deployment. This asymmetry is deliberate: it makes the application portable and the deployment substitutable.

Everything else at the repo root is a *thin* wrapper or metadata: `scripts/` are entry points that delegate into `deployment/`; `docs/` is documentation; `.env.*.example`, `Makefile`, `README.md`, `LICENSE`, `CONTRIBUTING.md`, `VERSION` are the top-level surface.

## 4. Anti-fragmentation rules

The two legacy repositories fragmented over time. This one will not, if we follow these rules.

### 4.1 No parallel structures
There is exactly one Dockerfile per service, exactly one compose file per profile, exactly one env template per audience (canonical, prod, dev, shared). If a new arrangement is "needed," it must replace an existing one — not sit next to it.

### 4.2 No orphaned artefacts
Every file in the repository must trace to a purpose someone can articulate in one sentence. If a reviewer cannot state the purpose, the file is either documented in this session or removed.

### 4.3 No legacy revival without ADR
Anything the initial canonical baseline dropped (see [`EXCLUSIONS.md`](EXCLUSIONS.md)) cannot be reintroduced without an Architecture Decision Record in `docs/ARCHITECTURE.md` and approval by the repository owner. This includes: binary release bundles, secondary compose files at the repo root, submodules, embedded audit archives, historical release notes, and Emergent-session scratch directories.

### 4.4 Docs update in the same commit
Every non-trivial change touches the docs that describe it. Reviewers reject PRs where implementation and documentation drift within a single PR. See `CONTRIBUTING.md` §3.

### 4.5 Env template completeness
Every env variable the application or the deployment reads must appear in every relevant `.env.*.example`. This is enforced by convention and by `make env-check`.

### 4.6 Smallest correct change
Fixes fix one thing. Features add one thing. Refactors happen only when the current structure blocks a specific fix or feature. "While I'm in here" cleanups belong in a separate PR.

## 5. How future contributors should think

- **Application changes** → start in `app/`. Ask "would this work if I ran the app outside Docker?" — if not, the change probably belongs in `deployment/`.
- **Deployment changes** → start in `deployment/`. Ask "does the application need to know this changed?" — if yes, you are about to violate the app/deployment asymmetry; step back.
- **New operator command** → add to `Makefile` first, then implement in `scripts/` as a thin wrapper over `deployment/`.
- **New env variable** → add to `.env.example` first, then reference in whichever tree consumes it, then document in `docs/OPERATIONS.md` or the relevant profile guide.
- **New service** → requires ADR in `docs/ARCHITECTURE.md`, a Dockerfile in `deployment/docker/<service>/`, a compose entry in `deployment/compose/docker-compose.yml`, a healthcheck, resource limits, log caps, provenance labels, and docs updates. See `CONTRIBUTING.md` §5.
- **New deployment profile** → requires ADR, a new compose file in `deployment/compose/`, a new `.env.<profile>.example`, and a new `docs/<PROFILE>.md`. Never a new top-level directory. See [`SHARED_INFRASTRUCTURE.md`](SHARED_INFRASTRUCTURE.md) for the pattern.

## 6. Rules that prevent fragmentation

These are the specific things this repository will *never* have. Enforced by `CONTRIBUTING.md` §9:

- `release_bundle/` directory or any binary release artefact
- A second compose file at the repo root
- Committed `.env` (real, non-example)
- New top-level directory without an ADR
- Git submodules
- Restored historical `arbicore-x-vps-bundle/` nested layout
- `emergentintegrations`, `litellm`, or any dev tool in `requirements.prod.txt`
- Hard-coded domains / IPs / FQDNs
- Build steps that assume an external release bundle exists
- Revival of `/api/arbicore/release/*` as actual bundle-download endpoints

## 7. Success criterion

This repository succeeds if, in five years, a new operator can `git clone` it and deploy it without needing to speak to anyone who worked on it. Everything else is instrumentation.
