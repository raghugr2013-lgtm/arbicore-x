# Exclusions

Assets from the legacy repositories that were intentionally NOT migrated to the canonical repository, with justification for each.

An asset appears here only if it was considered and rejected. Assets nobody considered are neither present nor recorded here.

---

## 1. From `ArbiCoreX-V01`

| Excluded asset | Reason |
|---|---|
| `release_bundle/arbicore-x/` (entire embedded 2-service shadow bundle, dated 2026-02-23) | **Superseded.** The 6-service greenfield stack in `deployment/` covers everything this old bundle did and more (nginx TLS, SSL, backups, monitoring, upgrade lifecycle, non-root images). Also violated `.gitignore` intent (folder was ignored yet tracked). |
| `release_bundle/arbicore-x-deployment-bundle.zip` | **Discontinued distribution model.** Canonical distribution is `git clone`, not authenticated API download. Endpoints that served it have been retired to structured stubs (see `MIGRATION_SUMMARY.md` §5). |
| `release_bundle/screenshots/` | Evidence captures, not runtime assets. |
| `release_bundle/api_samples/*.json` | Evidence captures, not runtime assets. |
| `memory/` (12 files: CHANGELOG.md, PRD.md, various `*_REPORT.md`, IMPORT_LOG.md, KEY_CONFIG_AUDIT.md, `.gitkeep`, etc.) | **Agent-session artifacts**, not production documentation. Historical CHANGELOG lineage referenced from `MIGRATION_SUMMARY.md` §6 for anyone needing it. |
| `test_reports/` | Session artifacts. |
| `test_result.md` | Session artifact. |
| `.emergent/` | Session config. |
| `.gitconfig` | Session leakage. |
| `docs/00-executive-summary.md` through `docs/24-production-workflow-blueprint.md` (24 numbered analysis docs) + `docs/audit/*` (14 sub-docs) + `docs/manifest.json` | **Historical design analyses.** Current-state summary distilled into a single `docs/ARCHITECTURE.md`. Full historical docs remain accessible in the legacy repo for anyone needing them (referenced in `MIGRATION_SUMMARY.md` §6). |
| `README.md` = `# Here are your Instructions` | Emergent template placeholder — never customized. Replaced by a real README. |
| Root `.gitignore` (legacy) | Simultaneously tracked and ignored `release_bundle/` — hygiene bug. Rewritten from scratch. |
| Root `tests/` directory (empty `__init__.py` only) | Placeholder for a directory with no content. Real tests already live at `app/backend/tests/`. |

## 2. From `arbicore-x-vps-bundle` — repo-root Emergent-session leakage

These sat at the root of the VPS bundle repository *outside* the actual `arbicore-x-vps-bundle/` bundle-root subdirectory. They were never part of any released deployment bundle.

| Excluded asset | Reason |
|---|---|
| `audit_output/` (contains `00_AUDIT_REPORT.md` 28 KB + `01_REPO_AUDIT_REPORT.md` 40 KB) | Prior audit-session scratch output. |
| `audit_workspace/app_bundle/`, `deploy_bundle/`, `frontend_bundle/`, `github/` | Prior audit-session scratch trees. |
| Stub `backend/` (only `server.py`, `pytest.ini`, `requirements.txt`) | Session-init stub. Real backend lives in `app/backend/`. |
| Stub `frontend/` (near-empty CRA scaffold) | Session-init stub. Real frontend lives in `app/frontend/`. |
| Empty `memory/`, `tests/`, `test_reports/`, `test_result.md` | Session artifacts. |
| `.emergent/`, `.gitconfig` | Session config. |
| Root `README.md` = `# Here are your Instructions` | Emergent template placeholder. |
| Root `.gitignore` | Redundant with the bundle-root `.gitignore`. Rewritten. |

## 3. From `arbicore-x-vps-bundle/` bundle root — historical release artefacts

| Excluded asset | Reason |
|---|---|
| `arbicore-x-vps-bundle-0.1.0.SHASUMS`, `arbicore-x-vps-bundle-0.1.0-rc2.SHASUMS`, `arbicore-x-vps-bundle-0.1.0-rc2.2.SHASUMS` | Integrity of retired RC-line tarballs. Canonical repo generates its own release integrity via `git tag`. |
| `RELEASE_NOTES_v0.1.0.md`, `RELEASE_NOTES_v0.1.0-rc2.md`, `RELEASE_NOTES_v0.1.0-rc2.1.md`, `RELEASE_NOTES_v0.1.0-rc2.2.md` | Historical RC-lineage. Canonical starts at `v1.0.0`. Provenance recorded in `MIGRATION_SUMMARY.md`. |
| `DEPRECATIONS.md` | RC-lineage bookkeeping — the items it deprecated are already gone in `v1.0.0`. |
| `PRE_DEPLOYMENT_VALIDATION_CHECKLIST.md` (19 KB) | Content folded into `docs/INSTALL.md` and `docs/OPERATIONS.md`. |
| `DEPLOYMENT_MANIFEST.md` (14.5 KB) | Content extracted into `docs/ARCHITECTURE.md` (single canonical source). |
| `docs/audit/16_vps_bundle_technical_review.md` + `docs/audit/legacy/` (18 files + `patches/` subdir) | Historical audit trail. Reference via `MIGRATION_SUMMARY.md` §6. |
| `app/docs/`, `app/memory/` (duplicated app-side docs inside the VPS bundle) | Deduplicated. Single source of truth is `docs/` at repo root. |
| `infrastructure/greenfield/startup.sh` | Superseded by `scripts/install.sh` (does its job and more, with guards). |
| Nested `arbicore-x-vps-bundle/` wrapper directory | Historical build-time layout. Canonical repo is flat. See design decision D-1 in `docs/MIGRATION_SUMMARY.md`. |

## 4. From `_rc2_2_prep.tar.gz` (RC2.2 overlay)

| Excluded asset | Reason |
|---|---|
| Everything | The overlay is a one-time patch. Its payload (`yarn.lock`, `.npmrc`, updated `VERSION`, updated `DEPLOYMENT_MANIFEST.md`, RC2.2 release notes) had already been applied to the VPS bundle repo (visible at HEAD commits `1f85b7d fix(deps,rc2.2)…` and `d72ae57 prep(rc2.2): SHASUMS…`). Retained only as historical evidence outside the canonical repo. |

---

## Rules for adding to this list

An asset gets added to this document only if it existed in a legacy source and someone might reasonably expect to find it in the canonical repository. If someone asks "where did *X* go?" and *X* is in a legacy repo but not here, this document should contain the answer.

If you are proposing to *reintroduce* something from this list, that requires an ADR in `docs/ARCHITECTURE.md` and repository-owner approval. See `CONTRIBUTING.md` §9.
