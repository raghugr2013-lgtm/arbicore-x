# ArbiCore X — PRD (Program Reference Document)

## Original problem statement (v2.9.1 maintenance)

Continue ArbiCore X — v2.9.1 Maintenance Release.

The previous workspace was interrupted mid-flight while preparing a
v2.9.1 maintenance release; it had identified three deployment blockers
but had not implemented them. Ship a clean v2.9.1 that:

1. Renames `app/backend/arbicore/providers/aux.py` (Windows reserves AUX;
   blocks git checkout on Windows dev machines).
2. Promotes `REACT_APP_BACKEND_URL` to REQUIRED in the .env contract so
   fresh Docker builds don't fail on the empty variable.
3. Removes runtime `pip install` from `arbictl` (Ubuntu 24 / PEP 668).
4. Verifies deployment end-to-end (compose, backend, frontend, OCE,
   arbictl, env loading, Windows clone, Ubuntu VPS).
5. No new features, scanners, providers, UI work, execution logic, APIs
   or behavioural changes.
6. Produces v2.9.1 bundle + SHASUMS + release notes; updated OPS_GUIDE
   and DEPLOYMENT_CHECKLIST; git tag v2.9.1; commit and tag pushed to
   the connected GitHub repository from the workspace.

## Architecture summary

FastAPI backend on :8001, CRA operator UI + Vite Opportunity Center
served by nginx-alpine, MongoDB persistence. Docker compose (greenfield
+ shared-infra profiles). `arbictl` = single-file Python CLI for
operations (deploy, preflight, dashboard, snapshot, evidence-pack,
validate-start, upgrade, rollback).

## User personas

- **VPS operator** — runs `scripts/install.sh` on a fresh Ubuntu 24 host
  and expects a clean bring-up without manual pip installs.
- **Windows developer** — clones the repo on Windows for local review;
  `AUX`-collision must not block checkout.
- **Ops on-call** — uses `arbictl` for deploy / rollback / snapshot on a
  running validation run.

## What's been implemented (v2.9.1 — 2026-08-04)

- ✅ Windows-safe module rename: `aux.py` → `aux_providers.py`.
- ✅ Single internal import updated in `providers/bootstrap.py`; no other
     references to the old name in code.
- ✅ `.env.example` promotes `REACT_APP_BACKEND_URL` to REQUIRED with a
     compile-time-baking explanation.
- ✅ `scripts/install.sh` pre-flight now gates on
     `REACT_APP_BACKEND_URL` (fails fast before Docker build).
- ✅ `ops/arbictl` (bash wrapper) rewritten: discovers a Python that has
     `httpx` (via `ARBICTL_PYTHON`, `ARBICTL_VENV`, `.venv/`, `venv/`,
     `/app/venv/`, `python3`). Never runs pip. Exits 3 with actionable
     four-path provisioning message when none available.
- ✅ `ops/arbictl.py` ImportError branch mirrors the wrapper guidance.
- ✅ `docs/OPERATIONS_GUIDE.md` — new "httpx runtime dependency" section.
- ✅ `docs/DEPLOYMENT_CHECKLIST.md` — rewritten for v2.9.1 (Windows
     clone note, PEP-668 step, REQUIRED env var, `arbictl deploy`).
- ✅ `docs/RELEASE_NOTES_v2.9.1.md`.
- ✅ Release artifacts in `releases/v2.9.1/`:
     `arbicore-x-v2.9.1.tar.gz`, `arbicore-x-v2.9.1.SHASUMS`,
     `arbicore-x-v2.9.1.MANIFEST.sha256`, `RELEASE_NOTES_v2.9.1.md`.
- ✅ Commit + annotated tag `v2.9.1` pushed to
     `raghugr2013-lgtm/arbicore-x` on GitHub main.

## Deployment gates verified

| Concern | State |
|---|---|
| Windows checkout (`aux.py` collision) | ✅ resolved |
| Windows-reserved filename scan | ✅ none remain |
| Docker frontend build (`REACT_APP_BACKEND_URL` empty) | ✅ hard-fails with actionable message at three layers (.env, install.sh, compose, Dockerfile) |
| `arbictl` on Ubuntu 24 (PEP 668) | ✅ no runtime pip; interpreter-discovery only |
| `arbictl` on legacy hosts (v2.9.0 compat) | ✅ `python3` remains last-resort candidate |
| YAML parse (3 compose files) | ✅ pass |
| Bash syntax (install / verify / upgrade / healthcheck) | ✅ pass |
| Python import of `aux_providers` + `bootstrap` | ✅ pass (rename accepted) |
| SHASUMS self-verify | ✅ pass |
| GitHub commit push | ✅ `9391f85` on main |
| GitHub tag push | ✅ `v2.9.1` |

## Prioritized backlog (out of scope for v2.9.1)

None — v2.9.1 is maintenance-only. Next milestone is the 7-day VPS
validation run against v2.9.1 to gate Stage 6 go/no-go.

## Non-goals for this release

- No new scanners, providers, UI work, execution logic, or APIs.
- No changes to safety defaults, MID schema, or evidence-writer.
- No refactors beyond the three deployment fixes.

---

## v2.10.0 — Phase 2: Canonical Runtime Activation (in-progress)

Goal: transition each user-facing surface from preview/hardcoded data
to the real canonical engines behind it. No UI or engine redesign. Each
slice is a surgical replacement.

### Slice 1 — Opportunity Pipeline (2026-08-05) — ✅ COMPLETE (GO)
Branch: `hotfix/canonical-slice-1` — commits `3d69bd2`, `a3e06a3`.

- ✅ Removed `_V2_OPPS` (8 hardcoded opps + `_hydrate_opps`) from `server.py`.
- ✅ Rewired GET `/opportunities`, `/opportunities/summary`,
     `/opportunities/{id}` to read exclusively from `_CANONICAL_OPP_REPO`.
     Empty DB → empty responses. Always `source: 'canonical'`.
- ✅ Rewired POST `/opportunities/{id}/approve` and `/reject` to canonical
     FSM (`mark_validated → mark_approved` / `mark_rejected`) + persist via
     `_CANONICAL_OPP_REPO.upsert`.
- ✅ Extended timeline to include `opportunity_journal` per-opp tap.
- ✅ Added `_journal_record_operator_event` bridge: seeds a `record_discovery`
     row when a canonically-seeded opp has no prior journal entry so every
     operator decision produces an audit-trail row.
- ✅ Normalized timeline event `kind` (raw, no `journal:` prefix).
- ✅ Approve/reject exceptions now logged instead of silently returning 404.
- ✅ Zero frontend, engine, or storage-schema changes.
- ✅ Testing verified: iter3 (26/27, 1 HIGH resolved) + iter4 (18/18 PASS).
- 📄 Deliverables: `docs/roadmap_v2.10/SLICE1_DELIVERABLES.md`.

Deployment impact: none (additive; empty DB safe; rollback trivial via
`git revert 3d69bd2 a3e06a3`).

### Slice 1.1 — Opportunity endpoints session auth gate (2026-08-05) — ✅ COMPLETE (GO)
Branch: `hotfix/canonical-slice-1.1` — commit `3b092ec`.

- ✅ Added `_require_operator_ctx()` helper delegating to unified
     `_resolve_current_user` (v2.9.3 cookie + bearer paths).
- ✅ Gated all 6 `/api/arbicore/opportunities*` endpoints (list, summary,
     detail, approve, reject, timeline). Anonymous → 401
     `{"detail":"not_authenticated"}`.
- ✅ Preserved 200 response shapes and query params. Frontend unchanged
     (already sends cookies via `withCredentials`).
- ✅ Testing verified: iter5 (55/55 PASS — 37 auth-matrix + 18 regression).
- 📄 Report: `test_reports/iteration_5.json`.

### Slice 2 — Canonical Discovery View (2026-08-05) — ✅ COMPLETE (GO)
Branch: `hotfix/canonical-slice-2` — commits `c1ca7d0`, `eb6c8a3`.
Merged to main as v2.10.1.

- ✅ Removed `_V2_DISCOVERY` (7 hardcoded narrative candidates) and
     `_hydrate_discovery` from `server.py`.
- ✅ Rewrote GET `/arbicore/discovery/candidates` to project the canonical
     opportunity population (`arbicore_opportunities`) into the existing
     UI contract via `_canonical_opp_to_discovery`. Filters
     status/kind/min_score/limit preserved. Empty DB → empty items.
- ✅ Rewrote POST `/arbicore/discovery/candidates/{id}/action` to route
     through the canonical FSM (`mark_validated / mark_approved /
     mark_rejected`), journals as `discovery_watch/promote/dismiss`.
     Illegal transitions return `{ok:false, error:<msg>}`.
- ✅ Replaced the hardcoded `{n_samples:214, ...}` calibration block with
     an honest one computed from live canonical rows (decile promotion
     rates; defaults to 0.0 when n<10).
- ✅ Session-cookie auth-gated (Slice 1.1 pattern).
- ✅ Testing verified: iter6 (33/34, 1 MEDIUM fixed) + iter7 (**79/79 PASS**
     — 42 Slice 2 + 37 Slice 1 regression).
- 📄 Deliverables: `docs/roadmap_v2.10/SLICE2_DELIVERABLES.md`,
     `docs/RELEASE_NOTES_v2.10.1.md`.

Status vocabulary map (canonical FSM → UI):
```
CANDIDATE  ↔ NEW
VALIDATED  ↔ WATCHING
APPROVED   ↔ PROMOTED
REJECTED   ↔ DISMISSED
```

Explicitly out of scope per user directive: narrative-intelligence engine,
external integrations (Twitter/CoinGecko/GitHub), new collections. Discovery
is the pre-approval view of the same funnel Slice 1 activated.

### Slice 2 — Canonical Discovery View (2026-08-05) — ✅ COMPLETE (v2.10.1)
Merged to main. See earlier entry above.

---

## v2.11 — Execution Ready (2026-08-05) — ✅ COMPLETE (FULL GO)

**Branch**: `hotfix/canonical-v2.11` (merged to main).
**Commits**: `57fb80f`, `17a41ec`, `133ffdb`.
**Test evidence**: `test_reports/iteration_8.json` — **145 / 145 PASS**.
**Deliverables**: `docs/roadmap_v2.10/V2.11_DELIVERABLES.md`, `docs/RELEASE_NOTES_v2.11.md`.

### Slice 3 — Market Intelligence canonical activation (P0)

- ✅ 6 intelligence endpoints (`recommendations`, `decisions`, `calibration`,
     `models`, `certification`, `entities`) rewired to canonical sources.
- ✅ Empty stores return empty responses; no fabricated fallbacks.
- ✅ Session-cookie auth-gated.

### Slice 4 — Execution Planning readiness (P0)

- ✅ 20 planner routes now session-cookie auth-gated (`/execution/*`).
- ✅ End-to-end pipeline verified (build → simulate → sign → calldata → broadcast(dry)).
- ✅ Bug fixes: swap-hop validation (no more 500 KeyError); orphan `except` removed.

### Phase C — Backend architectural cleanup (P0)

- ✅ Auth pattern consolidated: all 34 protected endpoints in `server.py`
     use `dependencies=[Depends(_require_operator_dep)]`.
- ✅ Manual `await _require_operator_ctx(...)` calls removed from 14
     Slice 1/1.1/2/3 handlers.
- ✅ Auth helpers moved to top-of-file for decorator import-time binding.

### Missing links before Limited Live (documented, deferred)

1. Calldata encoder for `aave_v3` / `uniswap_v3` flash heads (Wave 7C).
2. Executor smart-contract deployment on `base`.
3. 20-cycle shadow certification threshold (operational).
4. Adaptive-weight / calibration fitting scheduler.
5. Kill-switch operator UI wiring.

See `V2.11_DELIVERABLES.md` §8 for the full assessment.

### Slice 5 — Dashboard Canonicalization (2026-08-05) — ✅ COMPLETE (v2.11.5)
Commit `36bbe9d` on main.

- ✅ `GET /arbicore/dashboard/pulse` — opportunity_vitals from
     `_CANONICAL_OPP_REPO`, regime from `get_regime_snapshot_repo().latest()`
     (empty → UNKNOWN/0.0), route_learning from journal count. Auth-gated.
- ✅ `GET /arbicore/dashboard/deck` — fresh (created_at desc), pending
     (FSM=VALIDATED), requires_attention (CANDIDATE > 6h stale). Auth-gated.
- ✅ Removed all hardcoded arrays (`{total:14, CEX_ARBITRAGE:6,...}`,
     opp-001..opp-005, 'CALM · 0.82' regime).
- ✅ Testing: iter10 (161/161 PASS · 145 baseline + 16 Slice 5).

### Slice 6 — Portfolio Canonicalization (2026-08-06) — ✅ COMPLETE (v2.11.6)

- ✅ 8 portfolio endpoints canonicalized: `/positions`, `/balances`,
     `/transfers`, `/deployable`, `/treasury`, `/ledger`, `/exposure`,
     `/allocation`.
- ✅ Removed every hardcoded array (pos-01..pos-06 positions; binance/kucoin
     /okx balances; tr-014..tr-009 transfers; deployable per-venue rows;
     cold_wallet/hot_wallet vaults; led-035..led-042 ledger; BTC/ETH/USDT
     exposure rows; CEX_ARBITRAGE/DEX_ARBITRAGE allocation buckets).
- ✅ Every endpoint returns a graceful empty payload preserving the UI
     contract shape. Each carries a `TODO` naming the future canonical
     source (ExecutionPositionRepository / VenueBalanceService / TreasuryLedger
     / CapitalRouter / ExposureAnalyzer / AllocationPolicy) so later
     activation is a repo swap with no contract change.
- ✅ Session-cookie auth-gated via `dependencies=[Depends(_require_operator_dep)]`
     on every route. Anonymous → 401 `{"detail":"not_authenticated"}`.

### Slice 7 — Operations Canonicalization (2026-08-06) — ✅ COMPLETE (v2.11.6)

- ✅ 10 operations endpoints canonicalized:
     - `/scanners` + `/scanners/{family}/action` → canonical
       `ScannerConfigRepository` + `ScannerStateRepository` (6 real families:
       CEX/FUNDING/DEX/LAUNCH/CROSS_CHAIN/FLASH_LOAN_ARBITRAGE). Start/pause/
       stop persists via `ScannerStateRepository.set_enabled` and is
       round-trip verified through GET `/scanners`. SPATIAL_ARBITRAGE and
       STATISTICAL_ARBITRAGE removed (no canonical row exists for them).
     - `/venues` → `VenueCapabilityRepository.all_live()` (empty until a
       probe lands a row). `kind`/`role` default to `UNKNOWN`/`primary`
       with a TODO to extend the repo schema.
     - `/queues` → derived from `DiscoveryQueue.queue_status()` (single
       `discovery` queue today; TODO for full QueueTelemetryRepo).
     - `/cycles`, `/interlock`, `/interlock/action`, `/integrations`,
       `/alerts`, `/alerts/{id}/ack` → graceful empty/default shapes with
       TODOs pointing to CycleRepository / OperatorFlags / IntegrationHealthRepo
       / AlertRepository.
- ✅ Removed the module-level `_V2_SCANNERS` placeholder and every
     hardcoded cycles/venues/queues/alerts/integrations/interlock array.
- ✅ Session-cookie auth-gated on every route. Anonymous → 401.

### Regression evidence

- iter11: **221/221 PASS** (161 baseline preserved + 60 new Slice 6/7
  tests). `backend_issues.critical: []`, `backend_issues.minor: []`.
  Full GO. Zero regressions.

### Executor Package (v2.11.7) — 2026-08-06 — ✅ PHASE 1 COMPLETE (built + tested, NOT broadcast)

- ✅ Foundry project scaffolded at `/app/contracts/` per user layout:
     `contracts/{core,adapters,interfaces,libraries,tests}`, `script/`,
     `docs/`.
- ✅ Canonical `FlashLoanReceiver.sol` implements `execute(address[],
     uint256[],bytes)` (selector `0x64ba4bc1`) and `executeAave(address,
     uint256,bytes)` (selector `0x4343d8b2`) — both selectors match the
     Python encoders byte-for-byte (verified via `cast sig`).
- ✅ Providers wired: Balancer V2 Vault (0 bps) + Aave V3 Pool (5 bps).
     DEX = Uniswap V3 `SwapRouter02`. Owner-immutable, no upgrade path,
     re-entry gate + provider gate + caller check on every callback.
- ✅ 8 Foundry unit tests passing (`forge test` — mock-driven, no forked
     RPC required). Compiled artefact: runtime bytecode ~4988 bytes,
     `solc 0.8.24` + `via_ir` + 200 optimizer runs.
- ✅ Deployment scripts: `Deploy.s.sol` (one-command deploy, env-driven
     venue overrides), `Verify.s.sol` (post-deploy verify helper),
     `.env.example` (Base + Base Sepolia).
- ✅ Docs: `contracts/docs/DEPLOYMENT.md`,
     `contracts/docs/VERIFICATION.md`, evidence bundle under
     `contracts/docs/evidence/`.

### Executor Package (v2.11.7) — Phase 2 (Aave V3 encoders) — ✅ COMPLETE

- ✅ Three new Python encoders in `arbicore/execution/calldata.py`:
     - `encode_aave_v3_flash_loan_simple` — selector `0x42b0b77c`.
     - `encode_aave_v3_flash_loan` — selector `0xab9c4b5d`
       (multi-asset, direct-to-Pool).
     - `encode_executor_execute_aave` — selector `0x4343d8b2`
       (executor-relayed, LIMITED_LIVE Aave entry point).
- ✅ `encode_plan_head_call` now routes `flash_loan_provider="aave_v3"`
     through the executor-relayed encoder. Unknown providers still
     raise `NotImplementedError`.
- ✅ `broadcast.py:_REVERT_SELECTORS` extended with all 10 canonical
     `FlashLoanReceiver` error selectors + backward-compat legacy
     aliases.

### Paper Validation Framework (v2.11.8) — 2026-08-06 — ✅ COMPLETE (all 3 slices)

- ✅ **Slice A** — Canonical 8-outcome vocabulary
  (EXECUTABLE / REJECTED / UNPROFITABLE / LIQUIDITY_FAILURE /
  GAS_FAILURE / ROUTE_FAILURE / RISK_FAILURE / SIMULATION_FAILURE) +
  immutable `EvidenceBundle` (frozen dataclass) + validation_id
  linkage + per-stage `StageMetric` (started_at / ended_at /
  duration_ms / failure_reason) + insert-only Mongo repo
  (`arbicore_paper_evidence`) + terminal classification exactly once
  at pipeline completion.  iter13 — 100% GO.
- ✅ **Slice B** — Liquidity check stage (env-configurable safety
  ratio, permissive on missing annotation) + Simulation stage with
  `SimulationBackend` Protocol (Anvil / Tenderly / forge-fork can
  plug in without pipeline changes).  Two backends ship:
  `EthCallSimulator` (real RPC) + `HeuristicSimulator` (documented
  offline).  `SimulationRouter.from_env()` picks eth_call when
  `BASE_RPC_URL` is wired, heuristic otherwise.  Backend name
  recorded on every bundle.  iter14 — 100% GO.
- ✅ **Slice C** — `PaperValidationRunner` (idempotent, bounded,
  fail-open, gated behind `ARBICORE_PAPER_VALIDATION_ENABLED`).  Four
  new auth-gated endpoints under `/api/arbicore/validation/{report,
  evidence, evidence/{id}, metrics}`.  `/dashboard/pulse` now
  surfaces a `paper_validation` snapshot (total, executable_rate,
  runner_running, outcome_counts).  iter15 — 100% GO.

### Regression evidence (Paper Validation)

- iter13: 100% (Slice A + 275 iter12 baseline).
- iter14: 100% (Slice B).
- iter15: 100% (Slice C, all 4 new endpoints auth-gated + pulse hook).
- Zero critical / minor issues across all three iterations.
- 59 dedicated Slice-A/B/C unit tests + 8 iter15 live e2e tests +
  full Slice 1-7 + v2.11.7 regression, all green.

### Framework readiness

Full deliverables + sample EvidenceBundle + coverage report:
`/app/docs/PAPER_VALIDATION_v2.11.8_DELIVERABLES.md`.

**Ready for Shadow Certification design** — do NOT enable
`ARBICORE_PAPER_VALIDATION_ENABLED=true` in production until an
operator has explicitly reviewed a paper-validated evidence sample
and gated promotion criteria are agreed.

---

## Deployment architecture — FROZEN (2026-08-05)

### Regression evidence (Executor Package)

- iter12: **275/275 PASS** (221 iter11 baseline + 54 new encoder tests +
  24-check live API smoke). `backend_issues.critical: []`,
  `backend_issues.minor: []`. FULL GO for v2.11.7.
- Foundry: **8/8 PASS**.

### On-chain state

- **Base mainnet:** NOT DEPLOYED.
- **Base Sepolia:** NOT DEPLOYED.
- Definition of Done for Phase 1 = "buildable, testable, deployment-
  ready package" — MET. Broadcast is the next phase (Base Sepolia
  dry-run → Paper Validation → Shadow Certification → Base mainnet).

---

## Roadmap after v2.11.8

Backend canonicalization + Executor Package + Paper Validation
Framework are **complete**.  The platform pivots from *building* to
*proving*.

1. ✅ **Infrastructure Validation** — Mongo DNS, EvidenceBundle persistence,
   runner idempotency all green (2026-08-06, v2.11.9,
   `docs/INFRA_VALIDATION_v2.11.9.md`).
2. ✅ **Shadow Certification framework** — 20-cycle canonical validation
   gate with immutable `ShadowCertificationRun`, cycle-linked
   `EvidenceBundle.validation_id`, PASS/WARNING/FAIL/ABORTED status,
   operator + history endpoints, pulse hook (2026-08-06, v2.11.9,
   iter16 28/28 PASS).
3. **Shadow Certification live 20-cycle run** — operator triggers a
   real run against a warm scanner pool.  Gate to Base Sepolia
   promotion.
4. **Base Sepolia deploy** — first real on-chain broadcast, gated
   behind a Shadow Certification PASS.
5. **Limited Live** — real flash-loan opportunity execution, gated
   behind explicit operator approval.
6. **Base mainnet deploy** — final promotion, gated behind Limited
   Live green stripe.
7. **P3 · Docker networking discrepancy documentation** (deferred).

### v2.11.10 — Opportunity Decision Analytics (2026-08-06) — ✅ COMPLETE · Shadow Cert graded **PASS**

**Executable rate 54.00% on 20-cycle Shadow Certification** (up from 0.00% in v2.11.9). Three
canonical opportunity-engine defects surfaced by the analytics layer and fixed:

1. Pipeline mode lookup was case-sensitive — every opp hit the OBSERVE default
   short-circuit. Fix: `_resolve_mode()` tries raw / lower / upper.
2. Quote stage required `swap_hops[]` — venue-pair scanner emissions were
   blanket-rejected as `no_hops`. Fix: `_extract_quote()` synthesises a
   2-hop route from `(buy_venue, sell_venue, asset)` when hops absent.
3. Gas heuristic was on-chain-only (0.6% of capital) — CEX opps ate a $60
   gas charge against a $50 profit. Fix: venue-family-aware rates
   (CEX 0.20%, DEX/Flash 0.60%, cross-chain 1.00%) + enum stringification
   guard (`OpportunityType.CEX_ARBITRAGE` .value unwrap).

**Decision Analytics module (`arbicore/analytics/`) shipped**:

- Canonical rejection taxonomy: 12 categories + 2 meta (`EXECUTABLE`,
  `OBSERVE_ONLY`) + `OTHER` catch-all. Closed enum — a new failure
  category never lands silently.
- `DecisionRecord` — frozen projection of an EvidenceBundle carrying
  category, attributing stage, sub-code, stage failures, stage durations,
  e2e duration.
- `DecisionAnalyticsService` — 6 read-only aggregations
  (summary, rejection_breakdown, by_scanner, bottlenecks, trend, recent_decisions).
- 6 auth-gated endpoints under `/api/arbicore/analytics/decisions/*`.
- OpsCenter dashboard `section-decision-analytics`: 4 KPI tiles,
  rejection-reasons table, stage-bottlenecks table, per-scanner table.
- 12 pytest unit tests locking the taxonomy + service surface.

**PASS Shadow Certification run**:
- Run `shadowcert-7832a1b0-ee76-41ad-84ca-8af227b8fa38`
- 20/20 cycles, all PASS
- 50 opps processed, 27 EXECUTABLE (54%), 23 UNPROFITABLE
- worst stage p95: 2.3ms, 0 exceptions, infra_healthy=true
- Reports: `docs/DECISION_ANALYTICS_v2.11.10_REPORT.md` + `reports/shadow_cert_v2.11.10_PASS.json`

**Base Sepolia promotion now unblocked** per the canonical PASS gate.

### v2.11.9 — Shadow Certification (2026-08-06) — ✅ FRAMEWORK COMPLETE, LIVE RUN GRADED FAIL

**Live Shadow Certification results**: 2 full 20/20-cycle runs executed against
the live Wave1B scanner emission chain. Both terminated with status **FAIL**
(executable_rate=0.00%, 73 opps processed cumulatively, worst stage p95<0.01ms,
0 runner exceptions, infra_healthy=true across every cycle). **Base Sepolia
promotion is BLOCKED** — this is the correct outcome; the framework refused
to green-light on an environment where the trade logic finds nothing
economically executable. Full report: `docs/SHADOW_CERT_v2.11.9_LIVE_REPORT.md`.

Framework + wiring shipped this iteration:

- Infrastructure Validation gate passed clean: no DNS/refused/index-conflict,
  Paper Validation runner enabled and producing immutable
  EvidenceBundles in the `arbicore_paper_evidence` collection,
  `/dashboard/pulse.paper_validation` reporting live counts, journal
  integrity confirmed.
- New canonical module `arbicore/certification/`:
  * `thresholds.py` — 8 env-tunable canonical thresholds + closed
    `CycleStatus` / `CertificationStatus` vocabularies.
  * `models.py` — frozen `ShadowCertificationRun` +
    `ShadowCertificationCycle`; strict RUNNING → terminal transitions.
  * `repo.py` — Mongo-backed repository with fail-open reads and 3
    idempotent indexes (`uniq_run_id`, `status_recent`, `recent`).
  * `engine.py` — orchestrates one run at a time, computes per-cycle
    delta metrics (outcomes, executable rate, stage p95, infra
    health), grades each cycle, auto-finalises at `target_cycles`.
  * `runner.py` — background tick coroutine gated by
    `ARBICORE_SHADOW_CERT_ENABLED` env.
- 7 auth-gated endpoints under `/api/arbicore/certification/shadow/*`:
  `thresholds`, `current`, `start` (POST), `stop` (POST), `tick`
  (POST — operator-driven cycle), `runs`, `runs/{run_id}`.
- `/api/arbicore/dashboard/pulse.shadow_certification` block wired
  with `{active, run_id, status, cycles_completed, target_cycles,
  executable_rate}`.
- 11 pytest unit tests locking model immutability, threshold env
  overrides, engine grading precedence (infra > p95 > exec_rate),
  RUNNING/PASS/WARNING/FAIL/ABORTED transitions, repo insert-then-replace
  idempotency, and validation_id capture per cycle.
- iter16 live regression: **28/28 PASS** (17 live HTTP + 11 unit)
  including 401 auth-gating on all 7 endpoints, duplicate-start 409,
  auto-finalise summary shape, stop→ABORTED idempotency, ?status /
  ?limit filters, 404 on unknown run_id, Mongo persistence + indexes,
  Paper Validation regression clean.
- Environment additions: `ARBICORE_PAPER_VALIDATION_ENABLED=true`
  now default in `/app/backend/.env` for continuous cycles.
  `ARBICORE_SHADOW_CERT_ENABLED` / `ARBICORE_SHADOW_CERT_CYCLE_S` /
  `ARBICORE_SHADOW_CERT_AUTOSTART_RUN` / 8 threshold overrides
  documented in `arbicore/certification/thresholds.py` +
  `runner.py` module docstrings.
- **Live Shadow Certification wiring shipped (2026-08-06 v2.11.9)**:
  * Wave1B scanner autostart (`ARBICORE_RUNTIME_AUTOSTART=on`) — the
    six individual scanners (CEX / DEX / Flash Loan / Funding /
    Cross Chain / Launch) now instantiate and emit through
    `EmissionBus → arbicore_opportunities` at boot.
  * Idempotent `arbicore_collections.ensure_indexes` — fixes
    `IndexOptionsConflict` on second boot (mirrors the v2.11.8
    opportunity-repo hotfix).
  * `get_opportunity_repo()` composition fix — passes `services.db.db`
    to `MongoOpportunityRepository(db)` (v2.11.8 signature drift).
  * `PaperValidationRunner.reprocess_stale_after_s` — re-evaluates
    scanner emissions when their prior evidence is older than the env
    threshold, so deterministic route-hash IDs don't become permanent
    dedup skips.
  * `/api/arbicore/certification/shadow/readiness` — canonical pre-flight
    snapshot (scanners_running, canonical_opps, paper_runner state,
    issues[], is_live_ready).
  * `/certification/shadow/start` now HTTP 412 refuses if not live-ready
    unless body carries `infrastructure_only=true`.  Every run embeds
    the readiness snapshot + operator notes under
    `summary.start_markers`.
  * OpsCenter dashboard section `section-shadow-cert`: KPI, live
    progress bar, last-8-cycles table (status, processed, executable,
    validation_ids, stage p95, reason), history of 5 latest runs.
    Auto-polls every 6s.
- 15 additional pytests locked into
  `tests/test_v2119_shadow_cert_live.py` (74 total v2118/v2119 PASS).

VPS audit confirmed: **`factory-mongo` is the canonical ArbiCore production
database.** All four components (backend, frontend, Opportunity Center,
Strategy Factory) are healthy against it. Deployment profile of record is
`deployment/compose/docker-compose.shared.yml` with `.env.shared`.

**Do not** provision `arbicore-x-mongo` as the primary. **Do not** migrate
data. **Do not** disturb the existing Docker network attachments — they
are the reason connectivity works.

Full details: `docs/DEPLOYMENT_ARCHITECTURE_FROZEN.md`.

Roadmap ahead: ~~Slice 5 → 6 → 7~~ ✅ **all backend canonicalization complete
(v2.11.6, iter11 221/221)**. ~~Shadow Certification framework~~ ✅
**complete (v2.11.9, iter16 28/28)**. Focus shifts from *building* to
*proving* the platform:

1. Live Shadow Certification 20-cycle run against warm scanner pool.
2. Deploy executor smart contract on `base`.
3. Limited Live + real flash-loan opportunity discovery/execution.
4. Kill-switch operator UI wiring (P1).
5. Adaptive-weight / calibration fitting scheduler (P1).

### Deferred documentation task (P3)
- Docker networking discrepancy (backend on `arbicore-x-net`,
  `factory-mongo` on `vqb-network`) — purely documentation, do not
  investigate further per user directive.
- Wire `arbicore_opportunity_journal.validation_id` for the
  Paper-Validation runner path (currently null on runner-driven
  evaluations; not blocking Shadow Certification since the link key
  we use is `EvidenceBundle.validation_id`).

### Slice 4 — Execution Planning / Readiness (P2)
### Slice 5 — Dashboard Summary — replace hardcoded pulse/deck (P2)
### Slice 6 — Portfolio activation (P2)
### Slice 7 — Operations activation (P3)


---

## LIMITED_LIVE Flash Loan — Readiness Audit + Base Sepolia prep (2026-06)

**Directive:** shortest safe path to LIMITED_LIVE. No new unrelated
features. No private keys, no irreversible on-chain tx this session —
stop at the first operator gate.

**Deliverables produced:**
- `docs/LIMITED_LIVE_FLASH_LOAN_READINESS_AUDIT.md` (the audit).
- `docs/OPERATIONAL_VALIDATION_REPORT_BASE_SEPOLIA.md` (S1–S3 evidence).
- `contracts/docs/DEPLOY_RUNBOOK_BASE_SEPOLIA.md` (single-action deploy).

**Slices delivered:**
- **S1 — Workspace bring-up & config wiring.** Created `backend/.env`
  (`MONGO_URL`, `DB_NAME`, `ARBICORE_RPC_URL=https://sepolia.base.org`) +
  `frontend/.env`. Backend/frontend/Mongo RUNNING. Fixed genuine defect:
  `arbicore/execution/operator_wizard.py::_rpc_post` lacked a `User-Agent`,
  so the public Base RPC (Coinbase CDP) returned 403 to the readiness /
  executor-verify probes. Added browser-like UA. `rpc/check` → READY,
  chain_id 84532.
- **S2 — Executor package.** Foundry 1.7.1 installed; `forge build` OK
  (runtime 4987 bytes); `forge test` **8/8 PASS**. `contracts/script/Deploy.s.sol`
  rewritten chain-aware (auto Sepolia vs mainnet venues) with verified
  Base Sepolia addresses (Aave Pool `0x8bAB…aE27`, UniV3 `0x94cC…2bc4`);
  `contracts/.env.example` updated. Dry-run deploy simulated on Base
  Sepolia (no key). ABI exported to `contracts/artifacts/`.
- **S3 — E2E pipeline validation.** Autonomous AutoExecutor loop runs
  unattended, journals, halts before broadcast (SHADOW). Wizard reports
  wallet + executor as the only BLOCKED gates. 26/26 wizard+calldata tests
  green.

**Governance preserved:** `flash_loan_arbitrage = SHADOW`, kill switch
disengaged, no live trading, no broadcast.

**Remaining to first flash loan (ALL operator-gated):** fund deployer key
→ `forge script … --broadcast` (Base Sepolia) → set
`ARBICORE_EXECUTOR_ADDRESS_BASE` → register/fund burner + wrap key → flip
mode LIMITED_LIVE → confirm broadcast (Aave V3 head). Then promote the
same build to Base mainnet.

### Slice 4 — Operator Opportunity Probe (2026-06) — ✅ COMPLETE (testing_agent 7/7)

- New READ-ONLY endpoint `POST /api/arbicore/wizard/opportunity-probe`
  (integrates existing `QuoterRegistry`; no new engine). Live UniV3
  `eth_call` quotes across fee tiers 500/3000/10000. No broadcast/signing.
- Additive Base Sepolia UniV3 QuoterV2
  `0xC5290058841028F1614F3A6F0F5816cAd0df5E27` under chain `base-sepolia`
  in `arbicore/execution/quoter.py` — mainnet `base` unchanged.
- Verified: Base Sepolia HAS live WETH/USDC pools (0.01 WETH → ~2 USDC),
  visible cross-tier spread. Test: `tests/test_arbicore_opportunity_probe.py`.
- urllib-403 UA defect swept: only `operator_wizard._rpc_post` affected
  (fixed S1); all other execution RPC paths use httpx / urllib.parse only.

### STOP POINT — credential gate

Session halted (per directive) at the first operator gate. Remaining =
deploy executor (needs funded Base Sepolia deployer key) → set
`ARBICORE_EXECUTOR_ADDRESS_BASE` → burner wallet + first tiny flash loan
(Aave V3 head) → flip LIMITED_LIVE. No keys were requested/used; no
on-chain tx performed. Governance intact: flash_loan_arbitrage=SHADOW.



### Executor DEPLOYED to Base Sepolia (2026-06) — ✅ VERIFIED (testing_agent 6/6)

- **Executor:** `0x99c0b64e8F24fc1aADb07dAbA938d9f11dCD1052` (Base Sepolia, chain_id 84532).
- **Owner:** `0x65afB0a65Fd22F88022915F53eD48DA34fb02003` (throwaway testnet deployer; key in `contracts/.env`, gitignored).
- Deployed via `contracts/script/Deploy.s.sol` (chain-aware). On-chain venue triplet:
  balancerVault `0xBA12…F2C8`, uniRouter `0x94cC…2bc4`, aavePool `0x8bAB…aE27`.
- `ARBICORE_EXECUTOR_ADDRESS_BASE` wired into `backend/.env`.
- **Fixed genuine defect** in `operator_wizard.verify_executor`: it called
  non-existent `VAULT()`/`ROUTER()` getters and compared against MAINNET
  addresses → always BLOCKED. Now calls `balancerVault()/uniRouter()/aavePool()`
  and picks expected venue addresses by chain_id (adds `aave_pool_matches`).
- `/executor/verify` → **overall READY** (all 6 checks green). wizard/state:
  executor + executor_verify READY; only remaining blocker = **wallet**.
- Governance intact: flash_loan_arbitrage = SHADOW. No broadcast performed.

**STOP POINT:** halted after deploy + verify per operator directive. Next =
burner wallet + first tiny flash loan, pending explicit operator approval.
NOTE: executor `execute`/`executeAave` are **onlyOwner** → the broadcasting
burner wallet must be the executor owner (reuse `0x65afB0…02003`, or transfer
ownership to the chosen burner).

### Phase A — Technical Validation PASSED (2026-06) — ✅ first real flash loan

- **Reusable endpoint** `POST /api/arbicore/wizard/technical-validation`
  (`execute=false` dry sim via eth_call state-override; `execute=true`
  real broadcast) + `GET .../technical-validation/history`. Module:
  `arbicore/execution/technical_validation.py`. Records in Mongo
  `arbicore_technical_validations`. Verified by testing_agent (6/6).
- **First successful on-chain flash loan (Base Sepolia):** tx
  `0x7b61cdb6a5bcceb41875398a6b9ba512ff8cc2c15b823cbb9bca65d269185f20`,
  status 1, gas 310,530, block 45,170,478. Aave V3 borrow 0.00001 WETH →
  real Uniswap V3 WETH→USDC swap → repay + 5bps premium → no revert →
  ExecutionCompleted event. Engine TECHNICALLY READY.
- Governance intact: flash_loan_arbitrage=SHADOW (dedicated engineering
  signer `ARBICORE_VALIDATION_SIGNER_KEY`, independent of trading ladder).
- Findings: Balancer V2 Vault not deployed on Base Sepolia (Aave-only on
  testnet); executor rejects zero-hop flash (`EmptyHops()`=0x199bb70b) so
  validation includes one real swap; premium self-funded via ETH wrap.
- Reusable: rerun this exact proof after any contract/backend/chain change.


### Base Mainnet Promotion Plan / Production Runbook (2026-06) — 📄 DOC ONLY

- Created `docs/BASE_MAINNET_PROMOTION_PLAN.md` — the complete SHADOW→LIMITED_LIVE
  mainnet (chain 8453) runbook for the VPS (`git pull + docker compose`).
- Contents: Production Readiness Checklist (top) + 4 hard STOP gates
  (burner / deploy / arm / go-live), fresh dedicated mainnet burner via
  secret registry (scope=evm_sign, algo=eth_privkey — never plaintext .env),
  `forge script ... --rpc-url base` deploy, mainnet venue map, executor verify,
  prod .env (JWT_SECRET, CORS_ORIGINS, ARBICORE_RPC_URL dedicated+public
  fallback, chain=base), capital caps (placeholder per-trade + daily loss),
  kill-switch test, evidence check, go/no-go, monitoring, rollback.
- CORRECTED payloads vs old PHASE_B doc: mode transition uses `{"to_mode":...}`
  (NOT `mode`); scanner action is query param `?action=start`; secret scopes
  are cex_read/cex_trade/cex_withdraw/evm_sign/custom.
- NO mainnet action taken: no burner, no deploy, no key, no broadcast, no
  LIMITED_LIVE. SHADOW remains default until operator clears STOP-4.
- Defaults chosen: RPC dedicated+public fallback; capital placeholders;
  Basescan verify optional; engine auto-selects flash-loan head.

### Frontend vqb-network 502 — permanent fix (2026-06) — 🔧 NETWORKING/DOCS

- Root cause: peer Caddy proxy on `vqb-network` could not DNS-resolve
  `arbicore-x-frontend` (frontend was only on `arbicore-x-net`) → HTTP 502.
  Backend was already dual-homed (v2.11.9); frontend was not.
- Permanent fix in `deployment/compose/docker-compose.yml`: `frontend` AND
  `opportunity_center` now attach to BOTH `arbicore-x-net` + `vqb-network`
  (backend unchanged). No more manual `docker network connect` after
  `docker compose up`.
- `scripts/healthcheck.sh`: added greenfield Caddy-attachment guard — asserts
  backend/frontend/opportunity_center are on vqb-network when it exists.
- Docs: new `docs/HOTFIX_FRONTEND_VQB_NETWORK_ATTACH.md`; TROUBLESHOOTING §16;
  additive note in DEPLOYMENT_ARCHITECTURE_FROZEN.md (frozen rules unchanged).
- Scope: networking + docs only. No app code, business logic, or trading mode
  touched. Governance stays SHADOW. YAML + bash syntax validated.

### Shared-profile healthcheck fix (2026-06) — 🔧 SCRIPT/DOCS ONLY

- Bug: `scripts/healthcheck.sh` shared branch probed `127.0.0.1:8101/api/` and
  always returned 000 — the backend publishes NO host port (design: peer Caddy
  reaches it over vqb-network by container name; canonical shared compose maps
  only loopback 8101). Healthcheck bug, not a deploy defect.
- Fix (shared branch only): (1) authoritative in-container probe
  `docker exec arbicore-x-backend curl http://127.0.0.1:8001/api/`; (2) optional
  end-to-end probe via Caddy `https://$DOMAIN/api/` when DOMAIN set; (3) loopback
  host-port probe ONLY when a port is actually published (never false-fails).
- Did NOT expose a host port (would change architecture + need VPS change).
- Docs: `docs/HEALTHCHECK_SHARED_PROFILE.md` records the determination.
- Read-only probes; SHADOW governance untouched. bash -n + logic validated.
