# ArbiCore X v2.0.0 — Canonical Consolidation Audit

**Date:** 2026-08-02
**Sources:**
- `arbicore-x` v1.0.2 (previous canonical, deployment-complete)
- `Arbicorex-ui-v2-slice-02` (active development, UI v2 + Wave 6 + Phase 7–10)

**Verdict:** ✅ Merged into a single canonical repository. **1442 tests pass, 76 skipped, 0 failures.**

---

## 1. Method

Each subsystem was audited independently. The stronger implementation was kept.
Where both trees held complementary work, they were merged with explicit tie-breakers:

| Tie-breaker rule | When applied |
|---|---|
| **Newest verified logic wins** | Any module actively tested in `Arbicorex-ui-v2-slice-02` |
| **Deployment-proven wins** | Any module in `arbicore-x` v1.0.2 that shipped to production |
| **Union, not replacement** | Where a subdirectory holds independent files in each tree |
| **Dormant, not deleted** | Modules that lost their consuming server routes are kept in-tree but not wired into `server.py` (per user directive 4b) |

---

## 2. Subsystem-by-subsystem decisions

### 2.1 Backend — `app/backend/server.py`
- **`arbicore-x` v1.0.2**: 243 lines, minimal shell, D-1…D-6 scanner families + Wave 1–5 routes registered
- **`Arbicorex-ui-v2-slice-02`**: 3645 lines, all Wave 6A–E + Phase 7–10 endpoints wired (flash-loan operator, journey, execution certification, calldata encoding, broadcast pipeline, revert decoder, etc.)
- **Decision:** ✅ Keep the ui-v2-slice server; it supersedes the v1.0.2 shell. The v1.0.2 route mounts remain reachable through the modules in `backend/routes/` (dormant — see §2.4).

### 2.2 Backend — `arbicore/data/`
- **v1.0.2**: 15 files including `_inmemory.py`, `discovery_source_metrics_repo.py`, `metrics_repo.py`, `outcome_repo.py`, `regime_snapshot_repo.py`, `scanner_config_repo.py`, `state_observer.py`, `venue_capability_repo.py`, `wallet_profile_repo.py`
- **ui-v2-slice**: 9 files including `journal.py` (Phase P0-A Opportunity Journal) and `scanner_config_defaults.py`
- **Decision:** ✅ Union. Every file from both trees present. Rich `__init__.py` (canonical re-exports) restored. **17 files.**

### 2.3 Backend — `arbicore/data/mongo/`
- **v1.0.2**: `arbicore_collections.py`, `metrics_repo_mongo.py`, `outcome_repo_mongo.py`, `regime_snapshot_repo_mongo.py`, `wallet_profile_repo_mongo.py`
- **ui-v2-slice**: `adaptive_weights_repo.py`, `calibration_models_repo.py`, `evidence_bundles_repo.py`
- **Decision:** ✅ Union. Both share `opportunity_repo_mongo.py` (ui-v2-slice version wins — has the CanonicalOpportunity FSM upgrades from Phase 8). **10 files.**

### 2.4 Backend — `arbicore/{intel, intelligence, routes, runtime, scanner, scanners, scripts, shadow}` + `emission_bus.py`
- **v1.0.2**: Present and active (wired into server.py of v1.0.2)
- **ui-v2-slice**: Absent (never imported)
- **Decision:** ✅ Preserve from v1.0.2 into the canonical tree; **DORMANT** — not imported by the merged `server.py`.
  - **Rationale (user directive 4b):** These modules ship in-tree so future controlled validation waves can activate them without a code-move. Tests that require them live under `tests/_pending_scanner_activation/`.

### 2.5 Backend — `arbicore/learning/`
- **v1.0.2**: 6 files (`base.py`, `calibration.py`, `outcomes.py`, `route_success.py`, `weights.py`, `concrete/` w/ 19 workers)
- **ui-v2-slice**: 5 files (`calibration.py`, `weights.py`, `ledger.py` — Phase P0-B Learning Ledger)
- **Decision:** ✅ Union. **8 files** at top; `concrete/` unioned to 19 workers including `adaptive_weights_worker`, `calibration_worker`, `evidence_signing_worker` (all active in merged server) plus dormant workers (regime_worker, evaluator_worker, sequence_miner, etc.).
- **Tie-break:** `calibration.py` and `weights.py` — ui-v2-slice versions win (they are tested by the Wave 3/4 tests that pass green).

### 2.6 Backend — `arbicore/{config, execution, evidence, secrets, notifications}`
- **v1.0.2**: Absent
- **ui-v2-slice**: Present — Wave 6A–E + Phase 7–10 exclusive work (execution pipeline, calldata encoder, broadcast gates, kill switch, live signer, wallet registry, capital policy, evidence signer, secret registry, telegram notifier)
- **Decision:** ✅ Adopt ui-v2-slice implementation as-is. This is the production execution surface.

### 2.7 Backend — `arbicore/models/`, `arbicore/config/`
- **v1.0.2** `models/`: `canonical.py`, `category_metadata.py`, `discovery.py`, `enums.py`
- **ui-v2-slice** `models/`: same 4 files, updated versions (Phase 8 FSM additions)
- **Decision:** ✅ Prefer ui-v2-slice versions (tested by ~502 tests in slice). Canonical shape identical, so no drift.

### 2.8 Backend — root files (`api.py`, `conftest.py`, `reset_admin.py`, `pytest.ini`, `requirements.txt`)
- **v1.0.2**: `api.py`, `conftest.py`, `reset_admin.py`, `requirements.txt` (120 lines)
- **ui-v2-slice**: `pytest.ini` (xdist config), `requirements.txt` (updated deps)
- **Decision:** ✅ Union.
  - `conftest.py`, `api.py`, `reset_admin.py` from v1.0.2 (deployment-proven)
  - `pytest.ini` from ui-v2-slice (production test config)
  - `requirements.txt` **merged** — 145 packages, ui-v2-slice versions win for shared deps

### 2.9 Backend — `connectors/`, `core/`, `engines/`, `routes/`, `services/`, `diagnostics/`
- **v1.0.2**: Present (13 exchange connectors, portal/vault/venues services, execution engines)
- **ui-v2-slice**: Absent
- **Decision:** ✅ Preserve from v1.0.2. **DORMANT** — not imported by merged `server.py` (per 4b). Modules become active as `backend/routes/*.py` routers are registered in future validation waves.

### 2.10 Backend — Tests
- **v1.0.2**: 117 test files (`test_arbicore_*`, `test_d1_*`…`test_d6_*`, `test_e1_*`…`test_e4_*`, `test_sprint*`, `test_wave*`)
- **ui-v2-slice**: 46 test files (`test_v2_slice*`, `test_v2_wave*`, `test_phase10_*`, `test_stage13_*`, `test_wave6*`, `test_dashboard`, `test_wallet_registry`, etc.)
- **Overlap:** ZERO filename collisions.
- **Decision:**
  - 46 ui-v2-slice tests → `tests/` (all pass, 599 assertions green)
  - 72 canonical tests (that pass green against the merged server) → `tests/`
  - 45 canonical tests (that require dormant modules to be wired) → `tests/_pending_scanner_activation/` with an activation README

**Final active regression: 118 test files, 1442 pass, 76 skipped, 0 fail.**

### 2.11 Frontend — `app/frontend/`
- **v1.0.2**: React 19 + CRACO + shadcn/ui, minimal `src/v2/` shell (SectionPlaceholder in 6/7 sections, only Home wired)
- **ui-v2-slice**: Full UI v2 — 12 pages (`FlashLoanOperatorPage`, `FlashLoanJourneyPage`, `ExecutorVerifyPage`, `LimitedLiveWizardPage`, `PostTradeDashboardPage`, `HomePage`, `OperationsPage`, `OpportunitiesPage`, `PortfolioPage`, `SettingsPage`, `DiscoveryPage`, `IntelligencePage`), full v2 primitives, tokens.css theme, Slices 0–5 wired
- **Decision:** ✅ ui-v2-slice frontend wins entirely — the canonical UI is v2. Legacy CRA pages retained (per user directive 3b: fallback behind feature flag).
- `package.json` merged — ui-v2-slice versions win for shared deps; canonical-only deps (`mermaid`, `react-markdown`, `remark-gfm`) preserved.

### 2.12 Frontend — Opportunity Center
- **v1.0.2**: Vite SPA present at `app/opportunity_center/`
- **ui-v2-slice**: Absent
- **Decision:** ✅ Preserve from v1.0.2 unchanged.

### 2.13 Deployment — `deployment/`
- **v1.0.2**: Complete deployment tree — 6-service greenfield compose, 3-service shared-infra compose, Dockerfiles per service, nginx reverse proxy (site.conf.template + snippets), Let's Encrypt SSL init + renewal, backups (mongodump + rclone), monitoring (healthcheck + uptime-probe + snapshot), SHA-locked 11-step upgrade toolkit, .dockerignores, requirements.prod.txt / requirements.dev.txt
- **ui-v2-slice**: Absent
- **Decision:** ✅ Preserve v1.0.2 deployment tree entirely as-is. Deployment topology is unchanged in v2.0.0 (the additive `arbicore/execution/*` runtime respects the same env/port surface).

### 2.14 Scripts — `scripts/`
- **v1.0.2**: `install.sh` (9-phase guarded installer), `upgrade.sh`, `healthcheck.sh`, `backup.sh`, `restore.sh`, `verify-deployment.sh` + `verify-browser.mjs` (Playwright)
- **ui-v2-slice**: Absent
- **Decision:** ✅ Preserve from v1.0.2. `env-check` target in Makefile now also validates the two new required env vars (`REACT_APP_BACKEND_URL`, `ARBICORE_EXECUTOR_ADDRESS_BASE` — the latter optional).

### 2.15 Docs — `docs/`
- **v1.0.2**: 16 files (`ARCHITECTURE`, `INSTALL`, `OPERATIONS`, `UPGRADE`, `ROLLBACK`, `BACKUP_RESTORE`, `SSL`, `SECURITY`, `TROUBLESHOOTING`, `SHARED_INFRASTRUCTURE`, `REPOSITORY_PHILOSOPHY`, `MIGRATION_SUMMARY`, `CANONICAL_CERTIFICATION`, `EXCLUSIONS`, `ROADMAP`, `README`) + `releases/`
- **ui-v2-slice**: 7 files (`FLASH_LOAN_OPERATOR_MANUAL`, `OPERATOR_EXPERIENCE_AUDIT_v1`, `OPERATOR_WALKTHROUGH_v1.0`, `PHASE10_10_IMPLEMENTATION_REPORT`, `PHASE10_10_1_IMPLEMENTATION_REPORT`, `PREFLIGHT_AUDIT_v1`, `OPERATOR_MANUAL_PREVIEW`) + `ui_v2/` (30 files: architecture audits, phase reports, wave-6 delivery, etc.)
- **Decision:** ✅ Union. Deployment/operations docs kept from v1.0.2. Operator + UI-v2 architecture docs merged in.
- New v2.0.0-specific doc: **this file** (`docs/V2_CONSOLIDATION_AUDIT.md`) + `docs/V2_MIGRATION_GUIDE.md` + `docs/CANONICAL_CERTIFICATION.md` (updated to v2.0.0)

### 2.16 Root — `README.md`, `VERSION`, `Makefile`, `LICENSE`, `CONTRIBUTING.md`, `.gitignore`, `.gitattributes`, `.dockerignore`, `.env.*.example`
- **Decision:** ✅ All preserved from v1.0.2. `VERSION` bumped `1.0.0 → 2.0.0`. `README.md` gets a v2.0.0 note referencing this audit.

---

## 3. What was NOT migrated (dropped intentionally)

| Item | Source | Reason |
|---|---|---|
| `/app/.emergent/`, `/app/.gitconfig`, `/app/test_reports/`, `/app/test_result.md` | Slice repo session artifacts | Not production content |
| `/app/audit/`, `/app/audit_sources/` | Prior consolidation session working dir | Superseded by this audit |
| `/app/arbicore-x-v1.0.1.bundle`, `/app/arbicore-x-v1.0.2.bundle`, `/app/arbicore-x-v1.0.2.sha256`, `/app/arbicore-x-v1.0.1.SHASUMS` | Previous canonical release artifacts | v2.0.0 supersedes; retained in git history of the two source repos |
| `/app/canonical_repo/` (the empty directory left by prior sessions) | Placeholder | Replaced by this build |
| `/app/design_guidelines.json` | Slice repo agent config | Not production |
| `__pycache__/` and `.pyc` files anywhere | Build artifacts | Regenerated on install |
| `node_modules/`, `build/`, `.env` (real) | Both trees | Environment/build outputs |

All exclusions are recorded in `docs/EXCLUSIONS.md` (v1.0.0 excludes + additions from this pass).

---

## 4. Provenance snapshot

- Canonical shell HEAD (before merge): `arbicore-x-v1.0.2.bundle` @ `0789e6a`
- Slice HEAD (before merge): `Arbicorex-ui-v2-slice-02` @ `2e26aab` (post Phase 10.10.6)
- Merge date: 2026-08-02
- Merge author: canonical-consolidation session
- Verification: `pytest tests/ -n 2 --dist loadscope` → **1442 passed, 76 skipped, 0 failed**

---

## 5. Post-consolidation invariants

Enforced by CI at every future PR (documented in `CONTRIBUTING.md`):

1. **No parallel architecture** — one server.py, one arbicore package, one frontend tree, one opportunity_center tree, one deployment tree.
2. **Dormant modules stay in-tree** — modules in `backend/{routes,services,connectors,core,engines,diagnostics}/` and `arbicore/{intel,intelligence,scanner,scanners,shadow,runtime}/` are not imported by `server.py`. Activation requires a validation wave + associated test move-back from `tests/_pending_scanner_activation/`.
3. **`docs/EXCLUSIONS.md` is the trash bag** — anything intentionally omitted is recorded there.
4. **Env surface is minimal** — bootstrap `.env` = `MONGO_URL`, `DB_NAME`, `VAULT_KEY`, `CORS_ORIGINS`. Everything else configured via UI (Phase 10.10 env-sync shim).

---

## 6. Next actions

1. Deploy this canonical repo on a fresh VPS using only runtime configuration (see `docs/V2_MIGRATION_GUIDE.md`)
2. Run Playwright browser suite against the deployed instance to certify UI v2 flows
3. Runtime certification recorded in `docs/CANONICAL_CERTIFICATION.md` §runtime
4. First scanner-tree activation wave: pick a single dormant module cluster, activate its routes in `server.py`, move its test file back to `tests/`, verify green, tag as `v2.1.0`

_End of audit._
