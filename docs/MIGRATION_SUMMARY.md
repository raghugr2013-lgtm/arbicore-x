# Migration Summary

One-time record of how the ArbiCore X canonical repository was constructed. This document exists for provenance and reviewability; it is not consulted during normal operations.

Once `v1.0.0` is tagged, this document freezes. Future changes go into `docs/ROADMAP.md` §9.

---

## 1. Sources

Three sources contributed evidence to the canonical baseline. Only two contributed *files*.

| Source | Role | Provided files? |
|---|---|:-:|
| `raghugr2013-lgtm/ArbiCoreX-V01` @ commit `f64f7bf` | Application source of truth | ✅ |
| `raghugr2013-lgtm/arbicore-x-vps-bundle` @ HEAD `90a296d` on `main` (VERSION `arbicore-x-vps-bundle-0.1.0-rc2.2`, tags `v0.1.0-rc1`, `v0.1.0-rc2`, `v0.1.0-rc2.2`) | Deployment source of truth | ✅ |
| `_rc2_2_prep.tar.gz` (RC2.2 overlay) | Supplemental evidence — the patch that added `yarn.lock` + `.npmrc` and moved VERSION/manifest to RC2.2. Already applied to the VPS bundle repo before this migration. | ❌ (retained as evidence only; contributed no additional files beyond what the VPS bundle already carried) |

Both legacy repositories are now archived and read-only. This canonical repository has no runtime dependency on either.

## 2. What was migrated

### 2.1 From `ArbiCoreX-V01`
| Legacy path | Canonical path | Disposition |
|---|---|---|
| `backend/**` | `app/backend/**` | **Copy** — byte-preserved application source |
| `frontend/**` (minus lockfiles) | `app/frontend/**` | **Copy** — byte-preserved application source |
| `opportunity_center/**` | `app/opportunity_center/**` | **Copy** — byte-preserved application source |
| `backend/arbicore/routes/opportunity_center.py` | `app/backend/arbicore/routes/opportunity_center.py` | **Merge** — surgical edit: the legacy `/api/arbicore/release/manifest` + `/api/arbicore/release/bundle` implementations were replaced with retirement stubs returning `{"status":"retired",…}`. See §5. |

### 2.2 From `arbicore-x-vps-bundle` (bundle-root only; repo-root leakage excluded — see §3)
| Legacy path (in `arbicore-x-vps-bundle/`) | Canonical path | Disposition |
|---|---|---|
| `app/frontend/yarn.lock` | `app/frontend/yarn.lock` | **Copy** — the RC2.2 reproducibility fix; missing from `ArbiCoreX-V01`, present here. |
| `app/frontend/.npmrc` | `app/frontend/.npmrc` | **Copy** — same. |
| `.env.example`, `.env.production.example`, `.env.development.example` | `.env.example`, `.env.production.example`, `.env.development.example` | **Copy** — byte-preserved templates. |
| `.dockerignore` | `.dockerignore` | **Regenerate** — rewritten for the flat repo layout. |
| `infrastructure/greenfield/docker-compose.yml` | `deployment/compose/docker-compose.yml` | **Merge** — path adjustments: `../../infrastructure/nginx` → `../../deployment/nginx`, image tags bumped to `1.0.0`, everything else preserved. |
| `infrastructure/greenfield/{backend,frontend,opportunity_center}/**` | `deployment/docker/{backend,frontend,opportunity_center}/**` | **Copy** with the `nginx-spa.conf` COPY-line path corrected in the frontend and opportunity_center Dockerfiles (was `infrastructure/greenfield/…`, now `deployment/docker/…`). |
| `infrastructure/nginx/**` | `deployment/nginx/**` | **Copy** — byte-preserved. |
| `infrastructure/ssl/**` | `deployment/ssl/**` | **Copy** — byte-preserved. |
| `infrastructure/backups/**` | `deployment/backups/**` | **Copy** — byte-preserved. |
| `infrastructure/monitoring/**` | `deployment/monitoring/**` | **Copy** — byte-preserved. |
| `infrastructure/realignment/arbicore-x-deploy/**` | `deployment/upgrade/**` | **Copy** with parent renamed + inner `arbicore-x-deploy/` flattened. Toolkit internals (`Makefile`, `steps/*.sh`, `lib/common.sh`) reference "realignment" only in comments, verified safe to flatten. |
| `infrastructure/shared-infrastructure/docker-compose.shared.yml` | `deployment/compose/docker-compose.shared.yml` | **Copy** — optional profile. |
| `infrastructure/shared-infrastructure/.env.shared.example` | `deployment/compose/.env.shared.example` | **Copy** — optional profile env template. |
| `scripts/install.sh`, `scripts/upgrade.sh`, `scripts/healthcheck.sh` | `scripts/install.sh`, `scripts/upgrade.sh`, `scripts/healthcheck.sh` | **Regenerate** — same logic, paths updated (`BUNDLE_ROOT` → `REPO_ROOT`; `infrastructure/*` → `deployment/*`; requirements.prod path adjusted). |
| `docs/INSTALL.md`, `docs/UPGRADE.md`, `docs/ROLLBACK.md`, `docs/BACKUP_RESTORE.md`, `docs/SSL.md`, `docs/SECURITY.md`, `docs/OPERATIONS.md`, `docs/TROUBLESHOOTING.md`, `docs/SHARED_INFRASTRUCTURE.md` | `docs/…` | **Copy** — byte-preserved. Any documented path that changed (rare) is corrected in a subsequent commit if runtime validation surfaces it. |

### 2.3 Newly authored
| Canonical path | Purpose |
|---|---|
| `README.md` | Top-level orientation |
| `LICENSE` | Proprietary — All Rights Reserved |
| `CONTRIBUTING.md` | Contribution standards |
| `VERSION` | `1.0.0` |
| `Makefile` | Operator convenience wrapper |
| `.gitignore` | Clean minimal ignore |
| `.gitattributes` | LF line-ending enforcement |
| `.dockerignore` | Regenerated for the flat layout |
| `app/README.md` | App-tree orientation |
| `deployment/README.md` | Deployment-tree orientation |
| `deployment/compose/README.md` | Profile selection guide |
| `docs/README.md` | Doc index |
| `docs/ARCHITECTURE.md` | Single canonical architecture doc — supersedes DEPLOYMENT_MANIFEST + PRE_DEPLOYMENT_VALIDATION_CHECKLIST + the 24 numbered app-repo docs |
| `docs/REPOSITORY_PHILOSOPHY.md` | Design principles + anti-fragmentation rules |
| `docs/ROADMAP.md` | Repository roadmap + versioning + branch strategy + governance |
| `docs/MIGRATION_SUMMARY.md` | This document |
| `docs/CANONICAL_CERTIFICATION.md` | Phase 4 certification output |
| `docs/EXCLUSIONS.md` | Intentionally-omitted assets record |
| `scripts/backup.sh`, `scripts/restore.sh` | Symmetric thin wrappers over `deployment/backups/` |

## 3. What was intentionally left out

Full list with justifications: [`EXCLUSIONS.md`](EXCLUSIONS.md).

Summary of the largest categories:

- **From `ArbiCoreX-V01`:** the entire `release_bundle/` tree (embedded 2-service shadow bundle + zip + screenshots + api_samples), the `memory/` directory (agent-session artifacts), `test_reports/`, `test_result.md`, `.emergent/`, `.gitconfig`, and the 24 numbered app-repo docs (superseded by the single `docs/ARCHITECTURE.md`).
- **From `arbicore-x-vps-bundle`:** all repo-root Emergent-session leakage (`audit_output/`, `audit_workspace/`, stub `backend/`, `frontend/`, `memory/`, `tests/`, `test_reports/`, `test_result.md`, `.emergent/`, `.gitconfig`, root `README.md` = "Here are your Instructions", root `.gitignore`); all four legacy release-notes files (`RELEASE_NOTES_v0.1.0.md`, `-rc2.md`, `-rc2.1.md`, `-rc2.2.md`); all three `arbicore-x-vps-bundle-0.1.0*.SHASUMS` files; `DEPRECATIONS.md`; `PRE_DEPLOYMENT_VALIDATION_CHECKLIST.md` (folded into `docs/OPERATIONS.md`); the entire `docs/audit/` legacy tree (18 files + patches subdir); `infrastructure/greenfield/startup.sh` (superseded by `scripts/install.sh`); the nested `arbicore-x-vps-bundle/` wrapper directory itself (flattened).
- **From the RC2.2 overlay:** everything. The overlay was a one-time patch whose payload had already been applied to the VPS bundle.

## 4. Verification anchors

For anyone auditing this migration:

| Claim | How to verify |
|---|---|
| `app/backend/` is byte-identical to `ArbiCoreX-V01@f64f7bf/backend/` (except the surgical opportunity_center.py edit) | `git clone https://github.com/raghugr2013-lgtm/ArbiCoreX-V01 && git -C ArbiCoreX-V01 checkout f64f7bf && diff -qr ArbiCoreX-V01/backend app/backend` — only `arbicore/routes/opportunity_center.py` should differ. |
| `app/opportunity_center/` is byte-identical to `ArbiCoreX-V01@f64f7bf/opportunity_center/` | `diff -qr ArbiCoreX-V01/opportunity_center app/opportunity_center` — no output. |
| `app/frontend/` matches `ArbiCoreX-V01@f64f7bf/frontend/` plus the RC2.2 additions | `diff -qr ArbiCoreX-V01/frontend app/frontend` — only `yarn.lock` and `.npmrc` present in canonical, absent from legacy. |
| `yarn.lock` matches the VPS bundle's `app/frontend/yarn.lock` | `cmp` — identical. |
| `deployment/upgrade/` internal tree is byte-preserved from `arbicore-x-vps-bundle/arbicore-x-vps-bundle/infrastructure/realignment/arbicore-x-deploy/` | `diff -qr arbicore-x-vps-bundle/arbicore-x-vps-bundle/infrastructure/realignment/arbicore-x-deploy deployment/upgrade` — no output. |
| `nginx/`, `ssl/`, `backups/`, `monitoring/` under `deployment/` are byte-preserved from the corresponding `infrastructure/` subtrees | Analogous `diff -qr`. |

## 5. Retired API endpoints — implementation note

The routes `/api/arbicore/release/manifest` and `/api/arbicore/release/bundle` on the backend are retained in the URL surface for backward compatibility but no longer serve their original purpose (streaming a legacy deployment ZIP). They now return:

```json
{
  "status": "retired",
  "message": "Release bundles are no longer distributed separately. Deploy directly from the canonical repository (https://github.com/raghugr2013-lgtm/arbicore-x).",
  "since_version": "1.0.0"
}
```

Rationale for keeping the routes rather than removing them: preserves URL compatibility during the transition without dragging the legacy dependency (the ZIP file) into the canonical repository. The routes may be removed entirely in `v2.0.0`. See `docs/ROADMAP.md` §2 retirement path.

## 6. Historical references

Users who need historical context for anything not carried forward may consult:

- `raghugr2013-lgtm/ArbiCoreX-V01` — application history through `f64f7bf`.
- `raghugr2013-lgtm/arbicore-x-vps-bundle` — deployment history through tags `v0.1.0-rc1`, `v0.1.0-rc2`, `v0.1.0-rc2.2` and HEAD `90a296d`.
- `docs/audit/` and `docs/audit/legacy/` inside the VPS bundle repo — 18 legacy audit documents.
- `memory/` inside the app repo — Emergent-session working memory, PRD, changelog, and various interim reports.

Neither legacy repository is required for any current operational task.
