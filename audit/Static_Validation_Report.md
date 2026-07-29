# Phase 4 — Static Validation Report

**Repository:** `/app/canonical_repo/` (unpublished local canonical repo)
**HEAD:** `23cbfe8` on `main`, tag `v1.0.0`
**Executed:** Phase 4 validation suite, two remediation cycles applied
**Outcome:** ✅ CERTIFIED (see `docs/CANONICAL_CERTIFICATION.md` in the repo)

## Executive summary

| Metric | Result |
|---|---|
| Static validation checks | 16 |
| Findings — Critical | 0 |
| Findings — Major | 1 (fixed in Cycle 1) |
| Findings — Minor | 1 (fixed in Cycle 2) |
| Findings — Informational (retained) | 1 |
| Files edited during remediation | 16 |
| Lines added / removed | +85 / -100 |
| Repo history | Single clean commit; `v1.0.0` tag advanced to include fixes |

## Checks executed

1. Shell script syntax (`bash -n`) — 27/27 pass
2. Python AST parse — 377/377 pass
3. Compose YAML parse (greenfield) — pass, 6 services with full hardening
4. Compose YAML parse (shared) — pass, 3 services
5. `.env` template completeness (greenfield ↔ `.env.example`) — 0 missing
5. `.env` template completeness (greenfield ↔ `.env.production.example`) — 0 missing
5. `.env` template completeness (shared ↔ `.env.shared.example`) — 0 missing
6. Forbidden dependencies in `requirements.prod.txt` — 0
7. Hardcoded secrets in Dockerfiles — 0
8. Hardcoded public FQDNs in `deployment/` — 0 (excluding allow-listed `example.com`)
8. Hardcoded public IPs in `deployment/` — 2 (OCSP DNS resolvers `1.1.1.1` / `8.8.8.8`; retained per Informational note)
9. Path-reference sanity — 45/45 critical paths present
9. Legacy path patterns eliminated — clean
10. Application-tree isolation (no runtime code refs deployment/) — clean
11. Docs ↔ implementation path consistency — clean
12. install.sh required vars ↔ `.env.production.example` — 100% coverage
13. No real `.env` tracked in git
14. `.gitignore` + `.gitattributes` present and coherent
15. Line-ending enforcement — LF for all shell/py/yml/md/conf files
16. Executable bits on shell scripts — 27/27 marked `100755` in git index

## Remediation cycles

**Cycle 1 (MAJOR):** three deployment scripts had broken path resolution after the flat-layout rename (`infrastructure/greenfield/…` no longer exists). Fixed:
- `deployment/ssl/init-letsencrypt.sh` — `BUNDLE_ROOT` → `REPO_ROOT`, `cd` target corrected
- `deployment/ssl/renew.sh` — same
- `deployment/backups/backup-cron.sh` — same, plus `BACKUP_DIR` default aligned with the repo-root `backups/` directory
- `deployment/ssl/cronjob.example` — cron path updated
- `deployment/docker/frontend/Dockerfile` + `.../opportunity_center/Dockerfile` — header comments updated

**Cycle 2 (MINOR):** 9 operational docs referenced pre-flatten paths (`infrastructure/*`) and 10 lines pointed at dead audit-doc paths (`docs/audit/legacy/*.md`, `app/release_bundle/…`, `VPS_DEPLOYMENT_AND_SHADOW_RUNBOOK`). Fixed via systematic Python replacement pass — 69 path replacements + 10 dead-line removals + 2 targeted narrative fixes.

## Retained Informational note

`deployment/nginx/snippets/ssl.conf:12` hard-codes `1.1.1.1` and `8.8.8.8` as DNS resolvers for OCSP stapling. This is nginx's canonical default pattern; alternative (reading `/etc/resolv.conf`) is more fragile in containers. **No action recommended.**

## Certification linkage

Full certification detail — verdict, evidence per criterion, deferred runtime checks, ongoing governance — is written into the repository itself at `docs/CANONICAL_CERTIFICATION.md`. That file is the canonical certification record; this document is the Phase 4 audit trail.
