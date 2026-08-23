# ArbiCore X — TIER-0 Implementation Report

**Scope:** T0 correctness only. No T1/T2 performance work. No live-VPS deployment (package + report only, per instructions).
**Baseline:** `main @ 43230f6`. Safety guardrails honored: **$25 Gate 7 unchanged, signing not disabled, no auto live-promotion, honest-refusal preserved, no historical evidence deleted, thin activator quarantined not deleted.**
**Tags:** `[FACT]` verified in this run · `[VPS?]` needs VPS verification.

---

## Phase 0.5 — Preflight results

1. **Container vs `main@43230f6`:** working tree HEAD is `94f03a8` (platform auto-commit; `43230f6` is its ancestor). `[FACT]` Whether the **live VPS container** equals this tree is **[VPS?]** (no container access here).
2. **DB identity:** repo hardcodes canonical collections `arbicore_opportunities`, `arbicore_paper_evidence`, `evidence_bundles`, `execution_mode_state`; app reads `MONGO_URL`/`DB_NAME` from env. Live `factory-mongo/arbicore_x` ownership **[VPS?]**.
3. **RPC:** canonical namespace = `ARBICORE_RPC_URL` / `ARBICORE_RPC_URL_{CHAIN}` (all `execution/*` consumers); legacy `<CHAIN>_RPC_URL` still read by `paper/simulator.py` + scanner-config. Documented precedence established (T0-5). `[FACT]`
4. **Signing:** `SIGNING_ACTIVE_KEY_VERSION` unset ⇒ bundles created UNSIGNED **by design** (`signing_config.py`); never auto-generates keys. **Not touched.** `[FACT]`
5. **Synthetic write paths:** only `execution/discovery.py` (thin activator) wrote `SIMULATED` into canonical repo — now quarantined. Canonical consumers = `_CANONICAL_OPP_REPO.find/get` in `server.py` (many read sites) + `PaperValidationRunner`. `[FACT]`
6. **PaperRunner filter:** now `LEARNING_ELIGIBLE_PROVENANCE = {REAL, VERIFIED_REAL}`; `mode` (PAPER/SHADOW/LIVE) is orthogonal to provenance, so legitimate REAL paper/shadow workflows are **not** excluded. `[FACT]`
7. **Migration impact:** additive only; exact live counts of pre-existing SIMULATED canonical rows **[VPS?]** (backfill script provided, dry-run default).

---

## A. What was implemented

| ID | Change |
|----|--------|
| **T0-5** | Canonical synchronous RPC resolver `resolve_rpc_url_from_env(chain)` with deterministic precedence `ARBICORE_RPC_URL_<CHAIN>` > `ARBICORE_RPC_URL` > legacy `<CHAIN>_RPC_URL`; `env_sync` now also exports the legacy `<CHAIN>_RPC_URL` alias so UI-managed config and legacy readers agree. |
| **T0-3** | `pipeline._resolve_mode` returns explicit `MODE_UNRESOLVED` / `MODE_ERROR` sentinels; `evaluate` emits an explicit `readiness_error`/`infra_error` outcome instead of silently degrading to OBSERVE. Legitimate seeded OBSERVE unchanged. |
| **T0-1** | `flash_loan_quote_readiness()` gate: a canonical scanner in an analysis mode (PAPER/SHADOW/LIMITED_LIVE/FULL_LIVE) on the default `noop` provider is reported **NOT active** with a `readiness_error` — noop can never be the silent production quote path. |
| **T0-6** | Removed the `5_000_000` TVL sentinel in `base_venues.build_pool_graph` (now `0.0`); Gate 8 **fails closed** (`liquidity_unverifiable`) when route TVL ≤ 0; new `TVLProvider` interface (`UnknownTVLProvider` default → fail-closed; `StaticTVLProvider` for fixtures). |
| **T0-2** | Thin activator quarantined: no canonical upsert; its `DiscoveryRepo` now writes to `arbicore_research_candidates`; canonical write-gate in `opportunity_repo.validate_for_upsert` rejects non-REAL provenance when `ARBICORE_CANONICAL_STRICT_PROVENANCE` is enabled; PaperRunner `_fetch_opps` now filters to REAL/VERIFIED_REAL. |
| **T0-4** | `scanners/economics.aggregate_economics`/`EconomicAssessment` designated canonical; added `canonical_net_profit_usd()` as the single authoritative USD view. $25 gate untouched. |
| **T0-7** | Additive `source_data_quality` field on `EvidenceBundle`; `partition_executable_by_provenance()` in certification so executable/profitability metrics count REAL/VERIFIED_REAL only (synthetic reported separately). Signing schema/`HASHED_FIELDS` untouched (field is non-hashed metadata → historical signatures still verify; no version bump needed). |
| **T0-8** | Minimal `ChainAdapter` protocol + `ChainCapability` + `BaseChainAdapter` isolating Base assumptions; a chain is never `active_ready` on assumptions (quote/gas/sim health probed later). |
| **T0-9** | Additive, idempotent, DRY-RUN-by-default backfill script `arbicore/scripts/t0_provenance_backfill.py` (no deletes). |

---

## B. Exact files changed

**Modified (12):**
- `arbicore/config/persistent.py` — `resolve_rpc_url_from_env()`
- `arbicore/config/env_sync.py` — legacy `<CHAIN>_RPC_URL` export
- `arbicore/execution/pipeline.py` — `MODE_UNRESOLVED`/`MODE_ERROR`, `_readiness_fault_result()`, evaluate branch, `_resolve_mode` returns
- `arbicore/runtime/composition.py` — `flash_loan_quote_readiness()`
- `arbicore/discovery/base_venues.py` — TVL sentinel `5_000_000.0`→`0.0`
- `arbicore/scanners/flash_loan_arbitrage/filter.py` — Gate 8 fail-closed
- `arbicore/data/opportunity_repo.py` — strict provenance write-gate
- `arbicore/execution/discovery.py` — thin quarantine (no canonical upsert; research collection)
- `arbicore/paper/runner.py` — provenance-filtered `_fetch_opps`
- `arbicore/scanners/economics.py` — `canonical_net_profit_usd()`
- `arbicore/paper/evidence.py` — additive `source_data_quality`
- `arbicore/certification/engine.py` — `partition_executable_by_provenance()`

**New (5):**
- `arbicore/scanners/flash_loan_arbitrage/tvl_provider.py`
- `arbicore/chains/__init__.py`, `arbicore/chains/adapter.py`, `arbicore/chains/base_adapter.py`
- `arbicore/scripts/t0_provenance_backfill.py`
- `tests/test_t0_correctness.py`

---

## C. Tests and results

- **T0 acceptance matrix:** `tests/test_t0_correctness.py` → **17 passed** (`pytest -p no:xdist`).
- **Regression (offline unit subsets):** `test_d6_1_economics_and_gates`, `test_wave6a_mode_unit`, `test_d3_3_economics` → **47 passed**; `test_canonical_model_v2`, `test_d5_1_gates` → **18 passed**; `test_provenance`, `test_provenance_registry_arbicore` → **15 passed**. **Total 80 existing + 17 T0 = 97 passing, 0 regressions.** `[FACT]`
- **Not run here (pre-existing, env-dependent):** endpoint/integration suites (`test_*_endpoints`, `test_v2119_shadow_certification_live`, `test_stage1_canonical_flash_loan_scanner`, …) fail at *collection* due to missing `REACT_APP_BACKEND_URL`/live files — unrelated to T0 changes; must be run on the VPS. `[VPS?]`

---

## D. Database / migration impact

- **Additive only.** New collection `arbicore_research_candidates` (thin output). New additive fields: `EvidenceBundle.source_data_quality`. No schema rewrite, **no deletes**.
- **New writes are provenance-gated** on the canonical collection when `ARBICORE_CANONICAL_STRICT_PROVENANCE=true`.
- Historical rows without `source_data_quality` read as non-real (excluded from REAL executable-rate) — optional idempotent backfill provided (dry-run first).
- Live document counts **[VPS?]**.

---

## E. Git

- Baseline `main@43230f6`; work applied on top (platform auto-commits each step; latest pre-run HEAD `94f03a8`). No branches merged/cherry-picked/rebased/reset.
- **44 intentional preview-URL edits preserved** (present in tree; not reset/stashed/discarded).
- Recommended: place these commits on branch `t0/flash-loan-correctness` off `43230f6` before VPS deploy, and **rotate the PAT** embedded in the `origin` URL.
- Changed-file set: 12 modified + 5 new (§B).

---

## F. Known limitations

1. **T0-1 readiness** exposes a pure helper (`flash_loan_quote_readiness`) proving the policy; wiring it into the server startup status/health endpoint is a small follow-up (behavioral guarantee is unit-proven).
2. **T0-7** ships the provenance stamp field + the pure partition helper (unit-proven); threading `source_data_quality` from opportunity→evidence at pipeline write-time and calling the partition inside `_sample_evidence_delta` is the remaining wiring (additive; does not affect signing).
3. **T0-6** default `TVLProvider` is fail-closed (`UnknownTVLProvider`) — until a real cached TVL source is wired (T1), Gate 8 will **honestly deny** routes for `liquidity_unverifiable`. This is correct/safe, not a regression, but means Base emission stays at honest-zero on liquidity until T1.
4. **Write-gate default** `ARBICORE_CANONICAL_STRICT_PROVENANCE` is **off by default** (to preserve existing suite fixtures); production must set it **true**. Primary quarantine (thin no longer writes canonical) is unconditional.
5. `EvidenceBundle.from_mongo` does not yet re-read `source_data_quality` (defaults None on load) — additive round-trip completeness is a trivial follow-up.

---

## G. Items requiring VPS verification `[VPS?]`

- Live container == this tree (file hashes).
- Canonical DB is `factory-mongo/arbicore_x`; `execution_mode_state` seeded there.
- Which RPC env var the container actually has set.
- Count of pre-existing SIMULATED canonical rows (backfill scope).
- `SIGNING_ACTIVE_KEY_VERSION` presence (production signing decision — do not auto-generate).
- Full endpoint/integration + live shadow-certification suites (need live URL/DB).

---

## H. T0 acceptance criteria — PASS/FAIL

| # | Criterion | Result |
|---|-----------|--------|
| 1 | Canonical scanner cannot silently run noop | **PASS** (`test_scanner_noop_blocked_in_analysis_mode`) |
| 2 | Real opportunities reach the pipeline when configured | **PASS** (seeded SHADOW resolves → analysis) |
| 3 | Synthetic cannot enter executable canonical stream | **PASS** (thin quarantine + strict write-gate) |
| 4 | PaperRunner does not consume synthetic | **PASS** (`provenance_filter=REAL/VERIFIED_REAL`) |
| 5 | Missing mode distinguishable from OBSERVE | **PASS** (`MODE_UNRESOLVED` → readiness_error) |
| 6 | RPC precedence deterministic | **PASS** (`test_rpc_precedence_deterministic`) |
| 7 | Economics agree across callers | **PASS** (`canonical_net_profit_usd == expected_profit_usd`) |
| 8 | $25 gate unchanged | **PASS** (24.99 fail / 25.00 pass) |
| 9 | TVL cannot fabricate a liquidity pass | **PASS** (Gate 8 fail-closed; sentinel removed) |
| 10 | Certification executable_rate excludes synthetic | **PASS** (partition helper; wiring per §F-2) |
| 11 | Historical evidence intact | **PASS** (additive field default None; backfill has no deletes) |
| 12 | No automatic live promotion | **PASS** (defaults SHADOW/PAPER; ladder forbids skip) |

**All 12 acceptance proofs PASS at unit level.** Two carry small server-side wiring follow-ups (§F-1, §F-2) that do not change the proven guarantees.

---

## I. T1 readiness assessment

T0 establishes the truthful, provenance-safe Base foundation and leaves clean seams for T1:
- **Real TVL** → drop a cached implementation behind `TVLProvider` (Gate 8 already consumes it, fail-closed).
- **Private Base RPC/WSS** → point persistent config at the private endpoint; `resolve_rpc_url_from_env` already canonical.
- **Optimal sizing** → extend the single canonical economics kernel (T0-4).
- **Local cache / AMM math / per-block trigger** → replace the quote provider behind the T0-1 activation seam; `_tick` remains the single entrypoint.
- **Arbitrum (T4)** → add a sibling of `BaseChainAdapter`.
Resource footprint of T0 is negligible (Redis-cacheable TVL, additive fields) — the 12 vCPU / 48 GB box remains reserved for T1/T2.

---

## J. Unexpected issues discovered during implementation

1. `MongoOpportunityRepository` **already had** `_apply_provenance_filter`/`find(provenance_filter=…)` — reused rather than rebuilt (cleaner T0-2).
2. `data/opportunity_repo.validate_for_upsert` **already rejected `DEAD`** — extended the same seam for strict provenance.
3. `DataProvenance` has **no `SYNTHETIC`/`TEST` member**; thin uses `SIMULATED`. Kept as-is (SIMULATED already distinguishable from REAL); a dedicated `SYNTHETIC` tier is a future enum addition, not required for T0 guarantees.
4. `composition.py` imports `services.db` (reads `MONGO_URL` at import) — offline tests set a dummy `MONGO_URL` (motor is lazy; no connection).
5. Pre-existing endpoint/integration tests are not collectable offline (missing `REACT_APP_BACKEND_URL`/files) — unrelated to T0; must run on VPS.

---

**Deployment package = the change set in §B + the DRY-RUN backfill script + the §T0-11 sequence in the plan. NOT deployed. Awaiting separate VPS deployment authorization.**

**STOP — T0 implementation + tests complete. No T1/T2 work started. No live deployment performed.**

---

# ADDENDUM — T0 final wiring (live-facing surfaces) · 2026-06

Completes the two follow-ups previously listed under §F-1 and §F-2. Backend-only, additive; no frontend/UI, no branch merges, working tree not reset/cleaned.

## A. Exact additional changes
- **`arbicore/certification/engine.py`** — `_sample_evidence_delta()` now partitions the evidence delta by `source_data_quality`: **only REAL/VERIFIED_REAL EXECUTABLE evidence increments `exec_delta`**; synthetic/SIMULATED/unknown executable evidence is counted into `synthetic_executable_excluded` and NEVER into executable_rate. New `last_provenance_split()` accessor exposes `{real, synthetic, synthetic_executable_excluded, executable_real}`.
- **`server.py`** — startup `_canonical_flash_loan_scanner_startup()` now merges a live readiness verdict (via `composition.flash_loan_quote_readiness()` against the resolved `flash_loan_arbitrage` mode) into `_CANONICAL_FL_ACTIVATION`. Two new operator GET endpoints (both `Depends(_require_operator_dep)`):
  - `GET /api/arbicore/engine/flash-loan/readiness` → `{activation, readiness{ready,active,quote_provider,readiness_error}, generated_at}` (T0-1).
  - `GET /api/arbicore/certification/provenance-split` → `{provenance_split{real,synthetic,synthetic_executable_excluded,executable_real}, generated_at}` (T0-7).
- **`tests/test_t0_correctness.py`** — +2 tests (evidence-delta provenance partition through the real `_sample_evidence_delta`; default `last_provenance_split`).

`ARBICORE_CANONICAL_STRICT_PROVENANCE` implementation is unchanged and remains OFF by default (not auto-enabled).

## B. Tests / results
- `tests/test_t0_correctness.py` → **19 passed** (`pytest -p no:xdist`).
- **Live HTTP verification (testing agent, `/app/test_reports/iteration_1.json`): backend 100%, 0 issues, retest_needed=false.** Booted the app locally (uvicorn :8099, throwaway Mongo) — the app imports/initializes fully; startup log emitted `readiness={ready:true, active:true, quote_provider:'live', readiness_error:null}` for the canonical scanner. Verified: both endpoints 401 unauthenticated; after admin login → 200 with the exact contract shapes above.

## C. Git diff / status
- Full T0 set vs `43230f6`: **19 files, +842/−12** (12 modified, 5 new backend + the test file; earlier T0 files auto-committed, this turn's pending: `certification/engine.py`, `server.py`, `tests/test_t0_correctness.py`).
- Working tree otherwise clean; the 44 intentional preview-URL edits and (on the VPS) the intentional Dockerfile change (git + pinned Foundry/Anvil v1.7.1) are preserved — not reset/cleaned/stashed.

## D. Recommended commit separation (T0 code vs Dockerfile infra)
Keep application correctness separate from build/infra so either can be reverted independently:
1. **Commit 1 — `feat(t0): flash-loan correctness foundation`** — all 19 T0 backend files + tests (`arbicore/**`, `server.py`, `tests/test_t0_correctness.py`).
2. **Commit 2 — `chore(t0): live-facing readiness + provenance-split wiring`** *(optional split of the addendum: `certification/engine.py`, `server.py` endpoints, +2 tests)* — if you prefer the endpoint wiring isolated from the core logic commit.
3. **Commit 3 — `build(infra): add git + pinned Foundry/Anvil v1.7.1 to Dockerfile`** — the Dockerfile change **only**, no app code. Reversible without touching T0 logic.
Suggested branch: `t0/flash-loan-correctness` off `main@43230f6`.

## E. Final T0 deployment checklist (operator, on VPS — NOT run here)
Pre-deploy:
- [ ] On `main@43230f6`; create branch `t0/flash-loan-correctness`; apply the 3 commits (D).
- [ ] Confirm canonical DB `factory-mongo/arbicore_x`; `execution_mode_state`=7, `execution_mode_audit`=7 (already confirmed).
- [ ] `mongodump` backup of `arbicore_x` (record SHA256). No deletes will occur.
- [ ] Decide `SIGNING_ACTIVE_KEY_VERSION` (currently UNSET → evidence stays UNSIGNED by design; do NOT auto-generate). Configure a key + version for signed production evidence when ready.
- [ ] Rotate the PAT embedded in the git remote URL.

Deploy:
- [ ] Set `ARBICORE_CANONICAL_STRICT_PROVENANCE=true` (production enforces the canonical write-gate).
- [ ] Rebuild backend image (Dockerfile now provides git + Foundry/Anvil v1.7.1 for atomic-sim replay).
- [ ] Restart backend (and frontend only if built together). No DB container restart.

Post-deploy health (all should be truthful, not fabricated):
- [ ] `GET /api/arbicore/engine/flash-loan/readiness` → `quote_provider:"live"`, `readiness_error:null` (NOT noop in SHADOW).
- [ ] `GET /api/arbicore/certification/provenance-split` → integers; `synthetic_executable_excluded` present.
- [ ] Scanner rejection histogram shows honest `gate_7`/`gate_8:liquidity_unverifiable` reasons (expected: Gate 8 fails-closed until T1 wires real TVL).
- [ ] Canonical opportunities carry provenance ∈ {REAL, VERIFIED_REAL}; no `thin_activator`/SIMULATED rows in `arbicore_opportunities`.
- [ ] `execution_mode_state` seeded (flash_loan_arbitrage=SHADOW); no strategy in LIMITED_LIVE/FULL_LIVE.
- [ ] (Optional) run `python -m arbicore.scripts.t0_provenance_backfill` **dry-run**, review counts, then `--apply`.

Rollback:
- [ ] Redeploy previous image tag; set `ARBICORE_CANONICAL_STRICT_PROVENANCE=false` + `ARBICORE_TVL_PROVIDER=sentinel` to restore prior behavior without code change; restore `mongodump` only if a backfill was applied and needs reverting (additive fields need no restore).

**STOP — awaiting deployment authorization.**

